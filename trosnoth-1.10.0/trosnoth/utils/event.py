import functools
import inspect
import logging
import types
import weakref

from twisted.internet import defer

log = logging.getLogger(__name__)


class Event(object):
    '''
    If provided, signature is a sequence of strings indicating the names of
    arguments to the event calls.
    '''

    def __init__(self, signature=None, listener=None):
        self.listeners = {}
        if listener is not None:
            self.addListener(listener)
        self.signature = signature

    def addListener(self, obj, weak=True):
        assert callable(obj)
        if weak and isinstance(obj, types.MethodType):
            if getattr(obj.im_self, obj.im_func.__name__, None) == obj:
                if obj.im_self.__module__ != 'twisted.internet.defer':
                    obj = WeakMethod(self, obj)
            else:
                log.warning(
                    'Cannot create weak reference for %s.%s()',
                    obj.im_self, obj.im_func.__name__)
        self.listeners[obj] = obj

    def removeListener(self, obj):
        try:
            value = self.listeners.pop(obj)
        except KeyError:
            return
        if WeakMethod is None:
            # Final garbage collection during process termination
            return
        if isinstance(value, WeakMethod):
            value.done()

    def clear(self):
        self.listeners.clear()

    def execute(self, *args, **kwargs):
        for call in list(self.listeners):
            try:
                call(*args, **kwargs)
            except Exception:
                caller = inspect.currentframe().f_back
                log.exception(
                    'Error in event callback (from %s:%s)',
                    caller.f_code.co_filename, caller.f_lineno)

    __call__ = execute

    @defer.inlineCallbacks
    def wait(self):
        '''
        Returns a Deferred that waits for the given event to fire,
        and returns a dict of the parameters received by the call. This
        requires that the event was initialised with a signature.
        '''
        event, result = yield waitForEvents([self])
        defer.returnValue(result)


class WeakMethod(object):
    def __init__(self, event, method):
        self.event = event
        self.obj = weakref.ref(method.im_self, self.collect)
        self.attr = method.im_func.__name__
        self._hash = hash(method)

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        if other is self:
            return True
        if not isinstance(other, (types.MethodType, WeakMethod)):
            return False
        return other == self.get_method()

    def get_method(self):
        if self.obj is None:
            return None
        obj = self.obj()
        if obj is None:
            return None
        return getattr(obj, self.attr)

    def __call__(self, *args, **kwargs):
        method = self.get_method()
        if method:
            method(*args, **kwargs)

    def collect(self, r):
        if self.obj is None:
            # This is possible if garbage collection has been delayed
            return
        self.event.removeListener(self)

    def done(self):
        # Lose the reference to the weak reference so that it can be garbage
        # collected and so that it doesn't keep a circular reference to
        # self.collect.
        self.obj = None


def waitForEvents(events):
    '''
    Utility function that waits for the first of a number of given events to
    trigger. Returns (event, args), indicating which event fired, and the
    arguments that it fired with.
    '''
    d = defer.Deferred()

    listeners = {}

    def trigger(_event, *args, **kwargs):
        event = _event  # We do not want to collide with a keyword arg
        for k, v in listeners.items():
            k.removeListener(v)

        if event.signature is None:
            raise TypeError('to use wait(), event must have a signature')

        args = list(args)
        result = kwargs
        for i, argName in enumerate(event.signature):
            if args:
                if argName in result:
                    raise TypeError(
                        'event got multiple values for keyword argument '
                        '{!r}'.format(argName))
                result[argName] = args.pop(0)
            elif argName not in result:
                raise TypeError('event expected argument {!r}'.format(
                    argName))
        if args:
            raise TypeError('extra arguments provided to event')

        d.callback((event, result))

    for event in events:
        listeners[event] = functools.partial(trigger, event)
        event.addListener(listeners[event])

    return d
