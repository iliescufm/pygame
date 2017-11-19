# Trosnoth (UberTweak Platform Game)
# Copyright (C) 2006-2012 Joshua D Bartlett
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# version 2 as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.

import logging

from twisted.internet import reactor
from twisted.internet.error import CannotListenError

from trosnoth.model.agenthub import LocalHub
from trosnoth.network.base import MsgServer
from trosnoth.network.networkDefines import serverVersion

from trosnoth.messages import (
    ChatMsg, InitClientMsg,
    ResyncAcknowledgedMsg, BuyUpgradeMsg, ShootMsg,
    RespawnRequestMsg, JoinRequestMsg, UpdatePlayerStateMsg, AimPlayerAtMsg,
    PlayerIsReadyMsg, SetPreferredDurationMsg, SetPreferredTeamMsg,
    SetPreferredSizeMsg, RemovePlayerMsg, ChangeNicknameMsg, CheckSyncMsg,
    ThrowTrosballMsg, PlayerHasUpgradeMsg,
)
from trosnoth.utils import netmsg
from trosnoth.utils.message import UnhandledMessage
from trosnoth.utils.event import Event

log = logging.getLogger('server')

# The set of messages that the server expects to receive.
serverMsgs = netmsg.MessageCollection(
    ShootMsg,
    UpdatePlayerStateMsg,
    AimPlayerAtMsg,
    BuyUpgradeMsg,
    ThrowTrosballMsg,
    RespawnRequestMsg,
    JoinRequestMsg,
    ChatMsg,
    PlayerIsReadyMsg,
    SetPreferredDurationMsg,
    SetPreferredTeamMsg,
    SetPreferredSizeMsg,
    RemovePlayerMsg,
    ChangeNicknameMsg,
    PlayerHasUpgradeMsg,
    CheckSyncMsg,
    ResyncAcknowledgedMsg,
)


class TrosnothServerFactory(MsgServer):
    messages = serverMsgs

    def __init__(self, game, authTagManager=None, *args, **kwargs):
        self.game = game
        self.authTagManager = authTagManager

        self.connectedClients = set()

        self.onShutdown = Event()       # ()

        self.running = True
        self._alreadyShutdown = False

    def checkGreeting(self, greeting):
        return (greeting == 'Trosnoth18')

    def startListening(self, port=6789, interface=''):
        try:
            self.port = reactor.listenTCP(port, self, interface=interface)
        except CannotListenError:
            log.warning('WARNING: Could not listen on port %s', port)
            self.port = reactor.listenTCP(0, self, interface=interface)

    def getTCPPort(self):
        return self.port.getHost().port

    def stopListening(self):
        self.port.stopListening()

    def gotBadString(self, protocol, data):
        log.warning('Server: Unrecognised network data: %r' % (data,))
        log.warning('      : Did you invent a new network message and forget')
        log.warning('      : to add it to trosnoth.network.server.serverMsgs?')

    def connectionEstablished(self, protocol):
        '''
        Called by the network manager when a new incoming connection is
        completed.
        '''
        # Remember that this connection's ready for transmission.
        self.connectedClients.add(protocol)
        hub = LocalHub(self.game)
        hub.connectNode(protocol)

        # Send the setting information.
        protocol.gotServerCommand(InitClientMsg(self._getClientSettings()))

    def _getClientSettings(self):
        '''Returns a string representing the settings which must be sent to
        clients that connect to this server.'''

        result = self.game.world.dumpEverything()
        result['serverVersion'] = serverVersion

        return repr(result)

    def connectionLost(self, protocol, reason):
        if protocol in self.connectedClients:
            protocol.hub.disconnectNode()

        self.connectedClients.remove(protocol)

        # Check for game over and no connections left.
        if (len(self.connectedClients) == 0 and
                self.game.world.uiOptions.showReadyStates):
            # Don't shut down if local player is connected.
            for p in self.game.world.players:
                if not p.bot:
                    break
            else:
                # Shut down the server.
                self.shutdown()

    def shutdown(self):
        if self._alreadyShutdown:
            return
        self._alreadyShutdown = True

        # Kill server
        self.running = False
        self.game.stop()
        self.onShutdown.execute()
