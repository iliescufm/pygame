
class Trigger(object):
    '''
    Base class for defining standard triggers that multiple different levels
    might want to use.
    '''

    def __init__(self, level):
        assert level and level.world
        self.level = level
        self.world = level.world
        self.active = False

    def activate(self):
        if self.active:
            return
        self.active = True
        self.level.activeTriggers.add(self)
        self.doActivate()
        return self

    def deactivate(self):
        if not self.active:
            return
        self.active = False
        self.level.activeTriggers.discard(self)
        self.doDeactivate()

    def doActivate(self):
        '''
        Subclasses should override this to perform activation logic.
        '''
        raise NotImplementedError(
            '{}.doActivate'.format(self.__class__.__name__))

    def doDeactivate(self):
        '''
        Subclasses should override this to perform deactivation logic.
        '''
        raise NotImplementedError(
            '{}.doDeactivate'.format(self.__class__.__name__))
