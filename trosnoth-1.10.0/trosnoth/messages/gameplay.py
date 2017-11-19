import logging

from trosnoth.const import (
    PRIVATE_CHAT, TEAM_CHAT, OPEN_CHAT, RESYNC_IN_PROGRESS_REASON,
    GAME_NOT_STARTED_REASON, ALREADY_ALIVE_REASON, BE_PATIENT_REASON,
    ENEMY_ZONE_REASON, FROZEN_ZONE_REASON, DEFAULT_RESYNC_MESSAGE,
    DEFAULT_COIN_VALUE,
)
from trosnoth.messages.base import (
    AgentRequest, ServerCommand, ServerResponse, ClientCommand,
)
from trosnoth.model.universe_base import NO_PLAYER
from trosnoth.utils import globaldebug

log = logging.getLogger(__name__)


class TickMsg(ServerCommand):
    idString = 'tick'
    fields = ('tickId',)
    packspec = 'H'


class TaggingZoneMsg(ServerCommand):
    idString = 'Tag!'
    fields = 'zoneId', 'playerId', 'teamId'
    packspec = 'Icc'


class CreateCollectableCoinMsg(ServerCommand):
    idString = 'StCr'
    fields = 'coinId', 'xPos', 'yPos', 'xVel', 'yVel', 'value'
    packspec = 'cffffI'
    value = DEFAULT_COIN_VALUE


class RemoveCollectableCoinMsg(ServerCommand):
    idString = 'StCo'
    fields = 'coinId'
    packspec = 'c'


class BasePlayerUpdate(ServerCommand):
    '''
    attached may be:
        'f' - falling
        'g' - on ground
        'l' - on wall to left of player
        'r' - on wall to right of player
    '''
    fields = (
        'playerId', 'xPos', 'yPos', 'xVel', 'yVel', 'angle', 'ghostThrust',
        'jumpTime', 'gunReload', 'respawn', 'attached', 'coins', 'health',
        'resync', 'leftKey', 'rightKey', 'jumpKey', 'downKey')
    packspec = 'cfffffffffcIB?????'


class PlayerUpdateMsg(BasePlayerUpdate):
    idString = 'PlUp'

    def applyOrderToWorld(self, world):
        player = world.getPlayer(self.playerId)
        player.applyPlayerUpdate(self)


class ResyncPlayerMsg(BasePlayerUpdate):
    '''
    Carries the same information as PlayerUpdateMsg, but is sent only to the
    player in question to tell them to reposition their player and acknowledge
    the resync.
    '''
    idString = 'Sync'
    isControl = True


class DelayUpdatedMsg(ServerResponse):
    idString = 'Dlay'
    fields = 'delay'
    packspec = 'f'

    def applyOrderToLocalState(self, localState, world):
        localState.serverDelay = self.delay


class CheckSyncMsg(AgentRequest):
    '''
    Sent periodically by the client to confirm that it's idea of where its
    player is matches the server's idea.
    '''
    idString = 'syn?'
    fields = 'tickId', 'xPos', 'yPos', 'yVel'
    packspec = 'Hfff'
    timestampedPlayerRequest = True

    def serverApply(self, game, agent):
        if agent.player is None or agent.player.resyncing:
            return

        x, y = agent.player.pos
        if (
                abs(x - self.xPos) >= 1
                or abs(y - self.yPos) >= 1
                or abs(agent.player.yVel - self.yVel) >= 1):
            log.info('Player out of sync: %s', agent.player)
            agent.player.sendResync()


class ResyncAcknowledgedMsg(ClientCommand):
    idString = 'Synd'
    fields = (
        'tickId', 'xPos', 'yPos', 'yVel', 'angle', 'ghostThrust',
        'health', 'playerId',
    )
    packspec = 'HfffffBc'
    timestampedPlayerRequest = True
    playerId = NO_PLAYER

    def serverApply(self, game, agent):
        if agent.player is None:
            return
        if not agent.player.resyncing:
            log.warning(
                'Received unexpected resync acknowledgement from %s',
                agent.player)
            # If we get a resync acknowledgement when we're not resyncing
            # something is up and we need to resync again.
            agent.player.sendResync()
            return

        if not agent.player.checkResyncAcknowledgement(self):
            # If the values the client is acknowledging don't match up to where
            # we think the client is at, it's probably because another resync /
            # a game reset has happened, so we need to wait for the second
            # acknowledgement.
            return

        self.playerId = agent.player.id
        game.sendServerCommand(self)

    def applyRequestToLocalState(self, localState):
        localState.player.resyncing = False

    def applyOrderToWorld(self, world):
        player = world.getPlayer(self.playerId)
        player.resyncing = False


class RespawnMsg(ServerCommand):
    idString = 'Resp'
    fields = 'playerId', 'zoneId'
    packspec = 'cI'


class RespawnRequestMsg(AgentRequest):
    idString = 'Resp'
    fields = 'tickId'
    packspec = 'H'
    timestampedPlayerRequest = True

    def clientValidate(self, localState, world, sendResponse):
        if localState.player is None:
            return False
        code = self.getInvalidCode(localState.player, world)
        if code is None:
            return True

        sendResponse(CannotRespawnMsg(code))
        return False

    def applyRequestToLocalState(self, localState):
        localState.player.respawn()

    def serverApply(self, game, agent):
        # Since the client has already applied the respawn before the message
        # gets to the server, any invalid respawn necessitates a resync.
        if not agent.player or agent.player.resyncing:
            return
        code = self.getInvalidCode(agent.player, game.world)
        if code is None:
            game.sendServerCommand(
                RespawnMsg(agent.player.id, agent.player.getZone().id))
        else:
            if code == ENEMY_ZONE_REASON:
                reason = 'You no longer own the zone.'
                error = True
            else:
                reason = DEFAULT_RESYNC_MESSAGE
                error = False
            agent.player.sendResync(reason=reason, error=error)

    def getInvalidCode(self, player, world):
        '''
        Returns None if this respawn request seems valid, a reason code
        otherwise.
        '''
        if player.resyncing:
            return RESYNC_IN_PROGRESS_REASON
        if not world.abilities.respawn:
            return GAME_NOT_STARTED_REASON
        if not player.dead:
            return ALREADY_ALIVE_REASON
        if player.respawnGauge > 0:
            return BE_PATIENT_REASON
        if not player.inRespawnableZone():
            return ENEMY_ZONE_REASON
        if player.getZone().frozen:
            return FROZEN_ZONE_REASON
        return None


class CannotRespawnMsg(ServerResponse):
    '''
    reasonId may be:
        P: game hasn't started
        A: Already Alive
        T: Can't respawn yet
        E: In enemy zone
        F: Frozen Zone

    Note that this message actually always originates on the client rather than
    the server, so it never needs to travel on the network.
    '''
    idString = 'NoRs'
    fields = 'reasonId'
    packspec = 'c'


class UpdatePlayerStateMsg(ClientCommand):
    idString = 'Pres'
    fields = 'value', 'tickId', 'playerId', 'stateKey'
    packspec = 'bHc*'
    timestampedPlayerRequest = True
    playerId = NO_PLAYER

    def clientValidate(self, localState, world, sendResponse):
        if not localState.player:
            return False
        return True

    def applyRequestToLocalState(self, localState):
        localState.player.updateState(self.stateKey, self.value)

    def serverApply(self, game, agent):
        if not agent.player or agent.player.resyncing:
            return
        self.playerId = agent.player.id
        game.sendServerCommand(self)

    def applyOrderToWorld(self, world):
        player = world.getPlayer(self.playerId)
        if player:
            player.updateState(self.stateKey, self.value)


class AimPlayerAtMsg(ClientCommand):
    idString = 'Aim@'
    fields = 'angle', 'thrust', 'tickId', 'playerId'
    packspec = 'ffHc'
    timestampedPlayerRequest = True
    playerId = NO_PLAYER

    def applyRequestToLocalState(self, localState):
        localState.player.lookAt(self.angle, self.thrust)

    def serverApply(self, game, agent):
        if agent.player is None or agent.player.resyncing:
            return
        self.playerId = agent.player.id
        game.sendServerCommand(self)

    def applyOrderToWorld(self, world):
        player = world.getPlayer(self.playerId)
        if player:
            player.lookAt(self.angle, self.thrust)


class ShootMsg(AgentRequest):
    idString = 'shot'
    fields = 'tickId', 'localId'
    packspec = 'HH'
    localId = 0
    timestampedPlayerRequest = True

    def clientValidate(self, localState, world, sendResponse):
        if not world.canShoot():
            return False
        if not localState.player.canShoot():
            return False
        return True

    def applyRequestToLocalState(self, localState):
        self.localId = localState.shotFired()

    def serverApply(self, game, agent):
        if not game.world.canShoot():
            return
        if agent.player is None or agent.player.resyncing:
            return
        if not agent.player.canShoot():
            return
        if __debug__ and globaldebug.enabled:
            if (
                    globaldebug.shotLimit and
                    len(game.world.shotWithId) >= globaldebug.shotLimit):
                # When debugging shot physics, limit number of shots
                return

        xpos, ypos = agent.player.pos
        if agent.player.shoxwave:
            game.sendServerCommand(
                FireShoxwaveMsg(agent.player.id, xpos, ypos))
        else:
            shotId = game.idManager.newShotId()
            if shotId is not None:
                game.sendServerCommand(
                    ShotFiredMsg(agent.player.id, shotId, self.localId))


class ShotFiredMsg(ServerCommand):
    '''
    id manager -> agents
    '''
    idString = 'SHOT'
    fields = 'playerId', 'shotId', 'localId'
    packspec = 'cIH'

    def applyOrderToLocalState(self, localState, world):
        if localState.player and self.playerId == localState.player.id:
            localState.matchShot(self.localId, self.shotId)


class FireShoxwaveMsg(ServerCommand):
    '''
    id manager -> agents
    '''
    idString = 'Shox'
    fields = 'playerId', 'xpos', 'ypos'
    packspec = 'cff'


class ShotHitPlayerMsg(ServerCommand):
    '''
    The only reason shot collision is calculated server-side is that there are
    some times when a single shot may hit multiple players in the one tick. In
    that case, in order for the selection of killed player to be consistent,
    the server decides and broadcasts the result.
    '''
    idString = 'HitP'
    fields = 'playerId', 'shotId'
    packspec = 'cI'

    def applyOrderToWorld(self, world):
        shot = world.getShot(self.shotId)
        player = world.getPlayer(self.playerId)
        shot.collidedWithPlayer(player)


class PlayerNoticedZombieHitMsg(ServerCommand):
    '''
    Sent from the server at the point in time when a given player noticed that
    it had been hit.

    Valid values for deathType are defined in trosnoth.const.
    '''
    idString = 'Ouch'
    fields = 'playerId', 'killerId', 'deathType'
    packspec = 'ccc'

    def serverApply(self, game, agent):
        # In order for this message to enter the system at the correct time, it
        # acts as though it comes from the agent, even though it's really
        # generated by the AgentInfo object. This is why we need to implement
        # serverApply().
        game.sendServerCommand(self)

    def applyOrderToWorld(self, world):
        player = world.getPlayer(self.playerId)
        killer = world.getPlayer(self.killerId)
        player.noticeZombieHit(killer, self.deathType)


####################
# Communication
####################

class ChatFromServerMsg(ServerCommand):
    idString = 'ahoy'
    fields = 'error', 'text'
    packspec = '?*'


class ChatMsg(ClientCommand):
    '''
    Valid values for kind are defined in trosnoth.const.
    '''
    idString = 'chat'
    fields = 'kind', 'targetId', 'playerId', 'text'
    packspec = 'ccc*'
    playerId = NO_PLAYER
    targetId = NO_PLAYER

    def serverApply(self, game, agent):
        if agent.player is None:
            return

        if self.kind == TEAM_CHAT:
            if not agent.player.isFriendsWithTeam(
                    game.world.getTeam(self.targetId)):
                # Cannot send to opposing team.
                return
        elif self.kind == PRIVATE_CHAT:
            if game.world.getPlayer(self.targetId) is None:
                return
        elif self.kind != OPEN_CHAT:
            log.warning('unknown chat kind: %r', self.kind)
            return

        self.playerId = agent.player.id
        game.sendServerCommand(self)

    def applyOrderToWorld(self, world):
        sender = world.getPlayer(self.playerId)
        text = self.text.decode()
        if self.kind == OPEN_CHAT:
            world.onOpenChatReceived(text, sender)
        elif self.kind == PRIVATE_CHAT:
            target = world.getPlayer(self.targetId)
            target.onPrivateChatReceived(text, sender)
        elif self.kind == TEAM_CHAT:
            team = world.getTeam(self.targetId)
            world.onTeamChatReceived(team, text, sender)

    def applyOrderToLocalState(self, localState, world):
        if self.kind == PRIVATE_CHAT:
            player = localState.player
            if player and player.id == self.targetId:
                sender = world.getPlayer(self.playerId)
                text = self.text.decode()
                player.onPrivateChatReceived(text, sender)
