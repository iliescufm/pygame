import logging

from twisted.internet import defer

from trosnoth.const import (
    BOT_GOAL_CAPTURE_MAP, ACHIEVEMENT_AFTER_GAME, ACHIEVEMENT_TERRITORY,
    ACHIEVEMENT_TACTICAL, BONUS_COINS_FOR_RABBIT_SURVIVAL,
)
from trosnoth.levels.base import Level, RandomLayoutHelper, playLevel
from trosnoth.messages import AwardPlayerCoinMsg
from trosnoth.triggers.coins import (
    SlowlyIncrementLivePlayerCoinsTrigger, AwardStartingCoinsTrigger,
)
from trosnoth.triggers.rabbits import RabbitHuntTrigger
from trosnoth.triggers.zonecaps import (
    StandardZoneCaptureTrigger, StandardGameVictoryTrigger,
    PlayerZoneScoreTrigger,
)
from trosnoth.utils.event import waitForEvents

log = logging.getLogger(__name__)


class StandardLevel(Level):
    '''
    The base class used for levels with standard joining rules and win
    conditions.
    '''
    keepPlayerScores = True

    def setupMap(self):
        pass

    def getDuration(self):
        return None

    @defer.inlineCallbacks
    def start(self):
        try:
            SlowlyIncrementLivePlayerCoinsTrigger(self).activate()
            startingCoinsTrigger = AwardStartingCoinsTrigger(self).activate()
            winTrigger = StandardGameVictoryTrigger(self).activate()
            if self.keepPlayerScores:
                PlayerZoneScoreTrigger(self).activate()

            onClockZero = self.world.clock.onZero

            self.initPregameCountdown()
            yield onClockZero.wait()
            startingCoinsTrigger.deactivate()

            zoneCapTrigger = StandardZoneCaptureTrigger(self).activate()
            self.initMainPhase()
            event, args = yield waitForEvents([onClockZero, winTrigger.onVictory])
            self.gameOver()

            winTrigger.deactivate()
            zoneCapTrigger.deactivate()
            rabbitHuntTrigger = RabbitHuntTrigger(self).activate()
            result = yield rabbitHuntTrigger.onComplete.wait()
            for player in result['liveRabbits']:
                self.world.sendServerCommand(
                    AwardPlayerCoinMsg(player.id, BONUS_COINS_FOR_RABBIT_SURVIVAL))
                self.world.game.achievementManager.triggerAchievement(
                    player, 'rabbitSurvival')
            yield self.world.sleep(3)

        finally:
            self.endLevel()

    def initPregameCountdown(self, delay=10):
        self.setUserInfo('Get Ready...', (
            '* Game will begin soon',
            '* Capture or neutralise all enemy zones',
            '* To capture a zone, touch the orb',
            "* If a team's territory is split, the smaller section "
                'is neutralised',
        ), BOT_GOAL_CAPTURE_MAP)
        self.world.clock.startCountDown(delay, flashBelow=0)
        self.world.clock.propagateToClients()

        self.world.abilities.set(respawn=False, leaveFriendlyZones=False)
        self.world.onChangeVoiceChatRooms(self.world.teams, self.world.players)

    def initMainPhase(self):
        self.world.setActiveAchievementCategories({
            ACHIEVEMENT_TERRITORY, ACHIEVEMENT_TACTICAL})
        self.setUserInfo('Trosnoth Match', (
            '* Capture or neutralise all enemy zones',
            '* To capture a zone, touch the orb',
            "* If a team's territory is split, the smaller section "
            'is neutralised',
        ), BOT_GOAL_CAPTURE_MAP)
        self.notifyAll('The game is now on!!')
        self.playSound('startGame.ogg')
        self.world.activateStats()
        self.world.abilities.set(respawn=True, leaveFriendlyZones=True)

        duration = self.getDuration()
        if duration is not None:
            self.world.clock.startCountDown(duration)
        else:
            self.world.clock.stop()
        self.world.clock.propagateToClients()

    def gameOver(self):
        self.world.setActiveAchievementCategories({ACHIEVEMENT_AFTER_GAME})
        self.world.abilities.set(zoneCaps=False)

        maxZones = max(t.numZonesOwned for t in self.world.teams)
        winners = [t for t in self.world.teams if t.numZonesOwned == maxZones]
        winner = winners[0] if len(winners) == 1 else None

        self.setWinner(winner)
        self.world.onStandardGameFinished(winner)


class StandardRandomLevel(StandardLevel):
    '''
    A standard Trosnoth level with no special events or triggers, played on
    a randomised map.
    '''

    def __init__(
            self, halfMapWidth=None, mapHeight=None, blockRatio=None,
            duration=None):
        super(StandardRandomLevel, self).__init__()

        self.halfMapWidth = halfMapWidth
        self.mapHeight = mapHeight
        self.blockRatio = blockRatio
        self.duration = None

    def setupMap(self):
        super(StandardRandomLevel, self).setupMap()
        layoutHelper = RandomLayoutHelper(
            self.world, self.halfMapWidth, self.mapHeight,
            self.blockRatio, self.duration)
        layoutHelper.apply()
        self.duration = layoutHelper.duration

    def getDuration(self):
        return self.duration


class StandardLoadedLevel(StandardLevel):
    def __init__(self, mapLayout):
        super(StandardLoadedLevel, self).__init__()

        self.mapLayout = mapLayout

    def setupMap(self):
        super(StandardLoadedLevel, self).setupMap()
        self.world.setLayout(self.mapLayout)


if __name__ == '__main__':
    playLevel(StandardRandomLevel(), aiCount=1)
