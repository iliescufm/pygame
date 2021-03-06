import json
import logging

from trosnoth.messages.base import AgentRequest, ServerCommand

log = logging.getLogger()


class PlayerHasElephantMsg(ServerCommand):
    idString = 'jken'
    fields = 'playerId'
    packspec = 'c'


class PlayerHasTrosballMsg(ServerCommand):
    idString = 'ball'
    fields = 'playerId'
    packspec = 'c'

    def applyOrderToWorld(self, world):
        player = world.getPlayer(self.playerId)
        world.trosballManager.gotPlayerHasTrosballMsg(player)


class TrosballPositionMsg(ServerCommand):
    idString = 'bing'
    fields = 'xpos', 'ypos', 'xvel', 'yvel', 'inNet'
    packspec = 'ffff?'
    inNet = False

    def applyOrderToWorld(self, world):
        world.trosballManager.gotTrosballPositionMsg(
            (self.xpos, self.ypos), (self.xvel, self.yvel), self.inNet)


class ThrowTrosballMsg(AgentRequest):
    idString = 'pass'
    fields = 'tickId'
    packspec = 'H'

    def clientValidate(self, localState, world, sendResponse):
        if not localState.player:
            return False
        return localState.player.hasTrosball()

    def serverApply(self, game, agent):
        if agent.player and agent.player.hasTrosball():
            game.world.trosballManager.throwTrosball()


class AchievementUnlockedMsg(ServerCommand):
    idString = 'Achm'
    fields = 'playerId', 'achievementId'
    packspec = 'c*'


class UpdateClockStateMsg(ServerCommand):
    idString = 'clok'
    fields = 'showing', 'counting', 'upwards', 'value', 'flashBelow'
    packspec = 'bbbff'

    def applyOrderToWorld(self, world):
        if world.isServer:
            # These messages are generated by World.clock.propagateToClients,
            # based off the existing state of the clock, so we don't need to
            #  set it again on the server.
            return
        world.clock.value = self.value
        world.clock.flashBelow = self.flashBelow
        world.clock.setMode(
            showing=self.showing,
            counting=self.counting,
            upwards=self.upwards,
        )


class PlaySoundMsg(ServerCommand):
    idString = 'noyz'
    fields = 'filename'
    packspec = '*'


class UpdateGameInfoMsg(ServerCommand):
    idString = 'info'
    fields = 'info'
    packspec = '*'

    @classmethod
    def build(cls, title, info, botGoal):
        return cls(json.dumps([title, info, botGoal]))

    def applyOrderToLocalState(self, localState, world):
        (
            localState.userTitle,
            localState.userInfo,
            localState.botGoal,
        ) = json.loads(self.info)
        localState.onGameInfoChanged()


class UpdateScoreBoardModeMsg(ServerCommand):
    idString = 'xorz'
    fields = 'teamScoresEnabled', 'playerScoresEnabled'
    packspec = 'bb'

    def applyOrderToWorld(self, world):
        world.scoreboard.gotUpdateScoreBoardModeMsg(
            self.teamScoresEnabled,
            self.playerScoresEnabled,
        )


class SetTeamScoreMsg(ServerCommand):
    idString = 'tXor'
    fields = 'teamId', 'score'
    packspec = 'cl'

    def applyOrderToWorld(self, world):
        team = world.getTeam(self.teamId)
        if team:
            world.scoreboard.gotTeamScoreMsg(team, self.score)


class SetPlayerScoreMsg(ServerCommand):
    idString = 'pXor'
    fields = 'playerId', 'score'
    packspec = 'cl'

    def applyOrderToWorld(self, world):
        player = world.getPlayer(self.playerId)
        if player:
            world.scoreboard.gotPlayerScoreMsg(player, self.score)



class SetUIOptionsMsg(ServerCommand):
    idString = 'uiOp'
    fields = 'data'
    packspec = '*'

    def applyOrderToWorld(self, world):
        world.uiOptions.gotSetUIOptionsMsg(json.loads(self.data))


class SetWorldAbilitiesMsg(ServerCommand):
    idString = 'able'
    fields = 'data'
    packspec = '*'

    def applyOrderToWorld(self, world):
        world.abilities.gotSetWorldAbilitiesMsg(json.loads(self.data))
