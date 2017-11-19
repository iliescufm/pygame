import logging
import struct

from twisted.internet import reactor

from trosnoth.const import TICK_PERIOD
from trosnoth.messages import TickMsg
from trosnoth.model.hub import Hub
from trosnoth.network.networkDefines import serverVersion
from trosnoth.network.client import clientMsgs
from trosnoth.utils.netmsg import MessageTypeError
from trosnoth.utils.twist import WeakLoopingCall
from trosnoth.utils.unrepr import unrepr

log = logging.getLogger(__name__)


class ReplayRecorder(object):
    def __init__(self, world, filename):
        self.filename = filename
        self.world = world
        self.file = open(self.filename, 'wb')
        self.stopped = False

        initialData = self.world.dumpEverything()
        initialData['serverVersion'] = serverVersion
        data = repr(initialData)
        self.file.write(struct.pack('!I', len(data)))
        self.file.write(data)

    def consumeMsg(self, msg):
        if self.stopped:
            return
        msgData = msg.pack()
        self.file.write(struct.pack('!I', len(msgData)))
        self.file.write(msgData)

    def stop(self):
        if not self.stopped:
            self.file.close()
            self.stopped = True


class ReplayFileError(Exception):
    '''
    There is a problem with the replay file format.
    '''


class ReplayPlayer(Hub):
    '''
    Emulates a normal server by outputting the same messages that a server once
    did.
    '''

    def __init__(self, filename, *args, **kwargs):
        super(ReplayPlayer, self).__init__(*args, **kwargs)
        self.tickPeriod = TICK_PERIOD
        self.file = open(filename, 'rb')
        self.finished = False
        self.loop = WeakLoopingCall(self, 'tick')
        self.agentIds = []
        self.nextAgentId = 0

        try:
            length = struct.unpack('!I', self.file.read(4))[0]
        except struct.error:
            raise ReplayFileError('invalid replay format')
        data = self.file.read(length)
        self.settings = unrepr(data)

    def popSettings(self):
        result, self.settings = self.settings, None
        return result

    def start(self):
        self.loop.start(self.tickPeriod)

    def stop(self):
        if self.loop.running:
            self.loop.stop()

    def tick(self):
        while True:
            data = self.file.read(4)
            if not data:
                self.finished = True
                if self.node:
                    while self.agentIds:
                        agentId = self.agentIds.pop(0)
                        # Give 2 seconds before ending the replay
                        reactor.callLater(
                            2, self.node.agentDisconnected, agentId)
                self.loop.stop()
                break
            length = struct.unpack('!I', data)[0]

            data = self.file.read(length)
            try:
                msg = clientMsgs.buildMessage(data)
            except MessageTypeError:
                log.warning('WARNING: UNKNOWN MESSAGE: %r' % (data,))
                continue

            self.node.gotServerCommand(msg)
            if isinstance(msg, TickMsg):
                break

    def connectNewAgent(self):
        agentId = self.nextAgentId
        self.nextAgentId += 1
        self.agentIds.append(agentId)
        return agentId

    def disconnectAgent(self, agentId):
        self.agentIds.remove(agentId)

    def sendRequestToGame(self, agentId, msg):
        pass
