import logging

from trosnoth.levels.base import playLevel
from trosnoth.levels.standard import StandardRandomLevel
from trosnoth.triggers.coins import AwardStartingCoinsTrigger

log = logging.getLogger(__name__)


class TestingLevel(StandardRandomLevel):

    def initPregameCountdown(self, delay=10):
        AwardStartingCoinsTrigger(self, coins=10000).activate()
        self.world.clock.startCountDown(0.1, flashBelow=0)
        self.world.clock.propagateToClients()


if __name__ == '__main__':
    playLevel(TestingLevel(halfMapWidth=5, mapHeight=4), aiCount=0)