if __name__ == '__main__':
    import os, sys
    sys.path.insert(
        0, os.path.join(
            os.path.abspath(os.path.dirname(__file__)),
            '..', '..'))

import logging

from twisted.internet import defer

from trosnoth.const import GAME_FULL_REASON, UNAUTHORISED_REASON
from trosnoth.levels.base import Level, playLevel
from trosnoth.model.map import ZoneLayout, ZoneStep
from trosnoth.model.universe import PlayerProximityRegion, ZoneRegion
from trosnoth.utils.event import waitForEvents

log = logging.getLogger(__name__)


class TriggerDemoLevel(Level):
    '''
    Example of how to write a custom level that does not use the default
    triggers, but sets up its own.
    '''

    def __init__(self):
        super(TriggerDemoLevel, self).__init__()
        self.world = None
        self.blueTeam = None
        self.helperBot = None

    def setupMap(self):
        zones = ZoneLayout()
        zones.connectZone(zones.firstLocation, ZoneStep.NORTHWEST)
        zones.connectZone(zones.firstLocation, ZoneStep.SOUTHEAST)

        layout = zones.createMapLayout(self.world.layoutDatabase)
        tetris = self.world.layoutDatabase.getLayoutByFilename(
            'bckOpenTetris.block', reversed=True)
        tetris.applyTo(layout.blocks[0][2])
        self.world.setLayout(layout)

    @defer.inlineCallbacks
    def start(self):
        self.blueTeam = self.world.teams[0]

        humans = yield self.waitForHumans(1)
        human = humans[0]
        self.world.magicallyMovePlayer(
            human, self.world.getZone(0).defn.pos, alive=True)

        agent = yield self.addBot(
            self.world.game, team=self.blueTeam, nick='HelperGuy')
        self.helperBot = yield agent.getBot()
        self.world.magicallyMovePlayer(
            self.helperBot.player, self.world.getZone(1).defn.pos, alive=True)

        helperRegion = PlayerProximityRegion(
            self.world, self.helperBot.player, 100)
        zoneTwoRegion = ZoneRegion(self.world.getZone(2))
        self.world.addRegion(helperRegion)
        self.world.addRegion(zoneTwoRegion)

        while True:
            event, details = yield waitForEvents([
                helperRegion.onEnter, zoneTwoRegion.onEnter])
            if details['player'] != human:
                continue
            if event == zoneTwoRegion.onEnter:
                self.playSound('custom-not-there.ogg')
                self.sendPrivateChat(
                    self.helperBot.player, human, 'No, not over there')
                continue
            break

        self.playSound('custom-follow-me.ogg')
        self.sendPrivateChat(
            self.helperBot.player, human, 'Hello there, follow me!')
        yield self.world.sleep(2)
        self.helperBot.moveToZone(self.world.getZone(2))

        yield self.helperBot.onOrderFinished.wait()
        yield self.world.sleep(2)

        if not helperRegion.check(human):
            self.playSound('custom-come-on.ogg')
            self.sendPrivateChat(self.helperBot.player, human, 'Come on!!')
            while True:
                details = yield helperRegion.onEnter.wait()
                if details['player'] == human:
                    break

        self.playSound('custom-capture-orb.ogg')
        self.sendPrivateChat(
            self.helperBot.player, human, 'Now capture that orb!')
        yield self.world.sleep(2)
        self.helperBot.moveToOrb(self.world.getZone(2))
        yield self.helperBot.onOrderFinished.wait()

        self.playSound('custom-i-win.ogg')
        self.sendPrivateChat(self.helperBot.player, human, 'Game over. I win.')

        yield self.world.sleep(2)

        self.playSound('game-over-whistle.ogg')
        self.world.abilities.set(zoneCaps=False)
        self.world.uiOptions.set(showGameOver=True, winningTeam=self.blueTeam)

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
    playLevel(TriggerDemoLevel())
