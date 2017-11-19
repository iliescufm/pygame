import logging

from twisted.internet import defer

from trosnoth.const import (
    FRONT_LINE_TROSBALL, BOT_GOAL_SCORE_TROSBALL_POINT,
    ACHIEVEMENT_AFTER_GAME, ACHIEVEMENT_TACTICAL,
    BONUS_COINS_FOR_TROSBALL_SCORE,
)
from trosnoth.levels.base import Level, RandomLayoutHelper, playLevel
from trosnoth.messages import AwardPlayerCoinMsg
from trosnoth.triggers.coins import (
    SlowlyIncrementLivePlayerCoinsTrigger, AwardStartingCoinsTrigger,
)
from trosnoth.triggers.rabbits import RabbitHuntTrigger
from trosnoth.triggers.trosball import StandardTrosballScoreTrigger
from trosnoth.utils.event import waitForEvents

log = logging.getLogger(__name__)


class TrosballMatchBase(Level):
    def __init__(self, duration=None, *args, **kwargs):
        super(TrosballMatchBase, self).__init__(*args, **kwargs)

        self.totalDuration = duration
        self.roundDuration = duration
        self.scoreTrigger = None

    def setupMap(self):
        self.scoreTrigger = StandardTrosballScoreTrigger(self)

        self.makeNewMap(first=True)

    @defer.inlineCallbacks
    def start(self):
        assert self.world
        SlowlyIncrementLivePlayerCoinsTrigger(self).activate()
        startingCoinsTrigger = AwardStartingCoinsTrigger(self).activate()
        self.scoreTrigger.activate()
        self.world.scoreboard.setMode(teams=True)

        self.setGameOptions()

        onBuzzer = self.world.clock.onZero
        onScore = self.scoreTrigger.onTrosballScore
        while True:
            self.initCountdown()
            yield onBuzzer.wait()
            if startingCoinsTrigger:
                startingCoinsTrigger.deactivate()
                startingCoinsTrigger = None

            self.initRound()
            event, args = yield waitForEvents([onBuzzer, onScore])
            if event == onBuzzer:
                break
            self.handleScore(**args)

            yield self.world.sleep(3)
            self.resetMap()

        self.doGameOver()

        self.scoreTrigger.deactivate()

        rabbitHuntTrigger = RabbitHuntTrigger(self).activate()
        yield rabbitHuntTrigger.onComplete.wait()

        self.endLevel()

    def setGameOptions(self):
        self.world.setActiveAchievementCategories({ACHIEVEMENT_TACTICAL})
        self.world.uiOptions.set(
            showNets=True,
            frontLine=FRONT_LINE_TROSBALL,
        )
        self.world.abilities.set(zoneCaps=False)

        self.world.trosballManager.enable()

        self.setUserInfo('Trosball', (
            '* Score points by getting the trosball through the net',
            '* To throw the trosball, press the "use upgrade" key',
            '* The trosball explodes if held for too long',
        ), BOT_GOAL_SCORE_TROSBALL_POINT)

    def handleScore(self, team, player):
        self.playSound('short-whistle.ogg')
        self.world.trosballManager.placeInNet(team)
        self.world.scoreboard.teamScored(team)

        if self.totalDuration is not None:
            self.world.clock.pause()
            self.world.clock.propagateToClients()
            self.roundDuration = self.world.clock.value

        if player is not None:
            if player.team == team:
                message = '%s scored for %s!' % (player.nick, team.teamName)
            else:
                message = '%s scores an own goal!' % (player.nick,)
            self.world.sendServerCommand(AwardPlayerCoinMsg(
                player.id, count=BONUS_COINS_FOR_TROSBALL_SCORE))
        else:
            message = 'Score for %s!' % (team.teamName,)
        self.notifyAll(message)

        teams = list(self.world.teams)
        message = '%s: %d - %s: %d' % (
            teams[0].teamName,
            self.world.scoreboard.teamScores[teams[0]],
            teams[1].teamName,
            self.world.scoreboard.teamScores[teams[1]],
        )
        self.notifyAll(message)

    def resetMap(self):
        self.world.deactivateStats()
        self.makeNewMap(first=False)
        for player in self.world.players:
            zone = self.world.selectZoneForTeam(player.teamId)
            player.teleportToZoneCentre(zone)
            player.health = 0
            player.zombieHits = 0
            player.items.clear()
            player.respawnGauge = 0.0
            player.resyncBegun()

        self.world.trosballManager.resetToCentreOfMap()
        self.world.syncEverything()
        self.world.loadPathFindingData()

    def initCountdown(self, delay=6):
        self.world.clock.startCountDown(delay, flashBelow=0)
        self.world.clock.propagateToClients()

        self.world.abilities.set(
            upgrades=False, respawn=False, leaveFriendlyZones=False)

    def initRound(self):
        self.playSound('startGame.ogg')
        self.world.activateStats()
        self.world.abilities.set(
            upgrades=True, respawn=True, leaveFriendlyZones=True)

        if self.roundDuration is not None:
            self.world.clock.startCountDown(self.roundDuration)
        else:
            self.world.clock.stop()
        self.world.clock.propagateToClients()

    def doGameOver(self):
        self.world.setActiveAchievementCategories({ACHIEVEMENT_AFTER_GAME})

        maxScore = max(self.world.scoreboard.teamScores.values())
        winningTeams = [
            t for t, score in self.world.scoreboard.teamScores.items()
            if score == maxScore
        ]
        winner = winningTeams[0] if len(winningTeams) == 1 else None

        self.setWinner(winner)

    def makeNewMap(self, first):
        raise NotImplementedError('{}.makeNewMap'.format(
            self.__class__.__name__))


class RandomTrosballLevel(TrosballMatchBase):
    '''
    A standard Trosnoth level with no special events or triggers, played on
    a randomised map.
    '''

    def __init__(
            self, halfMapWidth=None, mapHeight=None, blockRatio=None,
            duration=None):
        super(RandomTrosballLevel, self).__init__(duration)

        self.halfMapWidth = halfMapWidth
        self.mapHeight = mapHeight
        self.blockRatio = blockRatio

    def makeNewMap(self, first):
        RandomLayoutHelper(
            self.world, self.halfMapWidth, self.mapHeight,
            self.blockRatio).apply()

    def start(self):
        return super(RandomTrosballLevel, self).start()


class LoadedTrosballLevel(TrosballMatchBase):
    def __init__(self, mapLayout, duration=None):
        super(LoadedTrosballLevel, self).__init__(duration)

        self.mapLayout = mapLayout

    def makeNewMap(self, first):
        if first:
            self.world.setLayout(self.mapLayout)


if __name__ == '__main__':
    playLevel(RandomTrosballLevel(duration=150), aiCount=7)
