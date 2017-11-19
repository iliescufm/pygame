if __name__ == '__main__':
    import os, sys
    sys.path.insert(
        0, os.path.join(
            os.path.abspath(os.path.dirname(__file__)),
            '..', '..'))

import logging
import random

from twisted.internet import defer, reactor

import pygame

from trosnoth.const import GAME_FULL_REASON, UNAUTHORISED_REASON
from trosnoth.levels.base import Level, playLevel
from trosnoth.model.map import ZoneLayout, ZoneStep
from trosnoth.model.universe import ZoneRegion, RectRegion
from trosnoth.utils.event import waitForEvents

log = logging.getLogger(__name__)


class TutorialLevel(Level):
    '''
    Example of how to write a custom level that does not use the default
    triggers, but sets up its own.
    '''

    def __init__(self):
        super(TutorialLevel, self).__init__()
        self.world = None
        self.blueTeam = None
        self.helperBot = None

    def setupMap(self):
        self.blueTeam = self.world.teams[0]
        self.redTeam = self.world.teams[1]

        zones = ZoneLayout()
        zone = zones.firstLocation
        zone = zones.connectZone(zone, ZoneStep.NORTHEAST)
        zone = zones.connectZone(zone, ZoneStep.SOUTHEAST)
        zone = zones.connectZone(zone, ZoneStep.SOUTHEAST)
        zone = zones.connectZone(zone, ZoneStep.NORTHEAST)

        layout = zones.createMapLayout(self.world.layoutDatabase)

        self.applyBlock(layout, 'tutorialblockA', 2, 1)
        self.applyBlock(layout, 'tutorialblockB', 2, 2)
        self.applyBlock(layout, 'bckOpenEmpty', 1, 2)
        self.applyBlock(layout, 'tutorialblockC', 1, 3)
        self.applyBlock(layout, 'tutorialblockD', 0, 3)
        # self.applyBlock(layout, 'tutorialblockE', 0, 4)
        self.applyBlock(layout, 'tutorialblockF', 1, 4)
        self.applyBlock(layout, 'tutorialblockG', 2, 4)
        self.applyBlock(layout, 'tutorialblockroom1', 2, 5)
        self.applyBlock(layout, 'bckOpenEmpty', 2, 6, reversed=True)
        self.applyBlock(layout, 'btmBlockedBasic', 3, 7)
        self.applyBlock(layout, 'bckOpenEmpty', 2, 8)

        self.world.setLayout(layout)
        for zone in self.world.zones:
            zone.owner = self.blueTeam
            zone.dark = False

    def applyBlock(self, layout, blockName, y, x, reversed=False):
        blockLayout = self.world.layoutDatabase.getLayoutByFilename(
            blockName + '.block', reversed=reversed)
        blockLayout.applyTo(layout.blocks[y][x])

    @defer.inlineCallbacks
    def start(self):
        humans = yield self.waitForHumans(1)
        human = self.human = humans[0]
        x, y = self.world.getZone(0).defn.pos
        self.world.magicallyMovePlayer(
            human, (x - 150, y + 20), alive=True)

        targetBot1 = yield self.addBot(
            self.world.game, team=self.redTeam, nick='Target1')
        targetBot1.setAggression(False)
        self.world.magicallyMovePlayer(
            targetBot1.player, (4096, 950), alive=True)
        targetBot2 = yield self.addBot(
            self.world.game, team=self.redTeam, nick='Target2')
        targetBot2.setAggression(False)
        self.world.magicallyMovePlayer(
            targetBot2.player, (4096, 1050), alive=True)


        lemmingBot1 = yield self.addBot(
            self.world.game, team=self.redTeam, nick='Lemming1')
        lemmingBot1.setAggression(False)
        start1 = (5410, 1233)
        end1 = (5860, 1233)
        self.world.magicallyMovePlayer(
            lemmingBot1.player, start1, alive=True)
        reactor.callLater(0, self.startMarching, lemmingBot1, start1, end1)

        lemmingBot2 = yield self.addBot(
            self.world.game, team=self.redTeam, nick='Lemming2')
        lemmingBot2.setAggression(False)
        start2 = (5410, 1379)
        end2 = (5860, 1379)
        self.world.magicallyMovePlayer(
            lemmingBot2.player, end2, alive=True)
        self.startMarching(lemmingBot2, end2, start2)

        nastyBot1 = yield self.addBot(
            self.world.game, team=self.redTeam,
            nick='Nasty1', botName='onezone',
        )
        self.world.magicallyMovePlayer(
            nastyBot1.player, (7168, 768), alive=True)

        nastyBot2 = yield self.addBot(
            self.world.game, team=self.redTeam,
            nick='Nasty2', botName='onezone',
        )
        self.world.magicallyMovePlayer(
            nastyBot2.player, (7168, 768), alive=True)

        yield self.world.sleep(0.5)
        # self.sendPrivateChat(human, human, 'Sound 1')
        self.playSound('tutorial1.ogg')

        yield self.regionWait(
            RectRegion(self.world, pygame.Rect(1080, 974, 200, 200)))

        # self.sendPrivateChat(human, human, 'Sound 2')
        self.playSound('tutorial2.ogg')

        yield self.regionWait(
            RectRegion(self.world, pygame.Rect(1178, 900, 200, 92)))

        # self.sendPrivateChat(human, human, 'Sound 3')
        self.playSound('tutorial3.ogg')

        yield self.regionWait(
            RectRegion(self.world, pygame.Rect(2000, 500, 300, 200)))

        # self.sendPrivateChat(human, human, 'Sound 4')
        self.playSound('tutorial4.ogg')

        yield self.regionWait(
            RectRegion(self.world, pygame.Rect(3350, 350, 100, 100))
        )

        # self.sendPrivateChat(human, human, 'Sound 6')
        self.playSound('tutorial6.ogg')

        yield self.regionWait(
            RectRegion(self.world, pygame.Rect(3090, 730, 450, 100))
        )

        # self.sendPrivateChat(human, human, 'Sound5')
        self.playSound('tutorial5.ogg')

        yield self.regionWait(
            RectRegion(self.world, pygame.Rect(3135, 789, 400, 100))
        )

        # self.sendPrivateChat(human, human, 'Sound7')
        self.playSound('tutorial7.ogg')

        yield self.regionWait(
            RectRegion(self.world, pygame.Rect(3552, 743, 100, 400))
        )

        # self.sendPrivateChat(human, human, 'Sound8')
        self.playSound('tutorial8.ogg')

        while pygame.mixer.Channel(0).get_busy():
            yield self.world.sleep(0.1)

        # self.sendPrivateChat(human, human, 'Sound9')
        self.playSound('tutorial9.ogg')

        zone3 = ZoneRegion(self.world.getZone(3))
        self.world.addRegion(zone3)
        while not (targetBot1.player.dead
                and targetBot2.player.dead or zone3.check(human)):
            event, details = yield waitForEvents([
                zone3.onEnter, targetBot1.player.onDied,
                targetBot2.player.onDied])
        self.world.removeRegion(zone3)

        # self.sendPrivateChat(human, human, 'Sound10')
        self.playSound('tutorial10.ogg')

        zone4 = ZoneRegion(self.world.getZone(4))
        self.world.addRegion(zone4)
        while not (lemmingBot1.player.dead
                and lemmingBot2.player.dead or zone4.check(human)):
            event, details = yield waitForEvents([
                zone4.onEnter, lemmingBot1.player.onDied,
                lemmingBot2.player.onDied])
        self.world.removeRegion(zone4)

        # self.sendPrivateChat(human, human, 'Sound11')
        self.playSound('tutorial11.ogg')

        playedSound12 = False
        while True:
            # TODO: check if they respawn in the new area and break loop
            if (nastyBot1.player.dead and nastyBot2.player.dead):
                self.world.magicallyMovePlayer(
                    human, human.pos, alive=False)

            if not playedSound12 and human.dead:
                playedSound12 = True
                # self.sendPrivateChat(human, human, 'Sound12')
                self.playSound('tutorial12.ogg')

            yield waitForEvents([
                human.onRespawned,
                human.onDied,
                nastyBot1.player.onDied,
                nastyBot2.player.onDied,
            ])


                # helperRegion
        #  = PlayerProximityRegion(
        #     self.world, self.helperBot.player, 100)
        # zoneTwoRegion = ZoneRegion(self.world.getZone(2))
        # self.world.addRegion(helperRegion)
        # self.world.addRegion(zoneTwoRegion)
        #
        # while True:
        #     event, details = yield waitForEvents([
        #         helperRegion.onEnter, zoneTwoRegion.onEnter])
        #     if details['player'] != human:
        #         continue
        #     if event == zoneTwoRegion.onEnter:
        #         self.playSound('custom-not-there.ogg')
        #         self.sendPrivateChat(
        #             self.helperBot.player, human, 'No, not over there')
        #         continue
        #     break
        #
        # self.playSound('custom-follow-me.ogg')
        # self.sendPrivateChat(
        #     self.helperBot.player, human, 'Hello there, follow me!')
        # yield self.world.sleep(2)
        # self.helperBot.moveToZone(self.world.getZone(2))
        #
        # yield self.helperBot.onOrderFinished.wait()
        # yield self.world.sleep(2)
        #
        # if not helperRegion.check(human):
        #     self.playSound('custom-come-on.ogg')
        #     self.sendPrivateChat(self.helperBot.player, human, 'Come on!!')
        #     while True:
        #         details = yield helperRegion.onEnter.wait()
        #         if details['player'] == human:
        #             break
        #
        # self.playSound('custom-capture-orb.ogg')
        # self.sendPrivateChat(
        #     self.helperBot.player, human, 'Now capture that orb!')
        # yield self.world.sleep(2)
        # self.helperBot.moveToOrb(self.world.getZone(2))
        # yield self.helperBot.onOrderFinished.wait()
        #
        # self.playSound('custom-i-win.ogg')
        # self.sendPrivateChat(self.helperBot.player, human, 'Game over. I win.')
        #
        # yield self.world.sleep(2)
        # Do game over

    @defer.inlineCallbacks
    def regionWait(self, region):
        self.world.addRegion(region)
        while not region.check(self.human):
            details = yield region.onEnter.wait()
        self.world.removeRegion(region)

    @defer.inlineCallbacks
    def startMarching(self, bot, start, end):
        while not bot.player.dead:
            bot.moveToPoint(end)
            yield bot.onOrderFinished.wait()
            yield self.world.sleep(random.random())
            if bot.player.dead:
                break
            bot.moveToPoint(start)
            yield bot.onOrderFinished.wait()
            yield self.world.sleep(random.random())

    def findReasonPlayerCannotJoin(self, game, teamId, user, bot):
        # Only allow one human player to join
        if any(not p.bot for p in self.world.players):
            return GAME_FULL_REASON
        if bot:
            return UNAUTHORISED_REASON
        return None

    def getTeamToJoin(self, preferredTeam, user, bot):
        return self.blueTeam


if __name__ == '__main__':
    playLevel(TutorialLevel())
