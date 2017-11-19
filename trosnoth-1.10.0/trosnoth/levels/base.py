import logging
import random

from twisted.internet import defer

from trosnoth.const import (
    GAME_FULL_REASON, PRIVATE_CHAT, BOT_GOAL_NONE,
)
from trosnoth.messages import (
    ChatMsg, PlaySoundMsg, UpdateGameInfoMsg, ChatFromServerMsg,
    SetPlayerTeamMsg,
)
from trosnoth.model.map import ZoneLayout
from trosnoth.model.universe_base import NEUTRAL_TEAM_ID
from trosnoth.triggers.lobby import (
    AddBotsForLobbyTrigger, MakeNewPlayersNeutralTrigger,
    StartGameWhenReadyTrigger,
)

log = logging.getLogger(__name__)


def preferredTeamOtherwiseSmallest(preferredTeam, universe):
    if preferredTeam is not None:
        return preferredTeam
    else:
        playerCounts = universe.getTeamPlayerCounts()

        minCount = len(universe.players) + 1
        minTeams = []
        for team in universe.teams:
            count = playerCounts.get(team.id, 0)
            if count < minCount:
                minCount = count
                minTeams = [team]
            elif count == minCount:
                minTeams.append(team)
        return random.choice(minTeams)


class Level(object):
    '''
    Base class for all standard and custom levels. A level provides
    server-only instructions about how a particular game is set up and
    operates.

    NOTE that clients know nothing about what level is being used, so any
    events that affect world state need to be carried out through the
    message-passing API in order that clients stay in sync with the server.
    '''

    recordReplay = True
    resetPlayerCoins = True

    def __init__(self, *args, **kwargs):
        super(Level, self).__init__(*args, **kwargs)
        self.world = None
        self._winner = None
        self.activeTriggers = set()

    def setupMap(self):
        '''
        Called before the game starts, to set up the map. Must be overridden.
        '''
        raise NotImplementedError('{}.setupMap'.format(
            self.__class__.__name__))

    def tearDownLevel(self):
        '''
        Called when a new level is selected, or the server terminates. This
        could be used to tear down event handlers which have been set up.
        '''
        while self.activeTriggers:
            trigger = self.activeTriggers.pop()
            try:
                trigger.deactivate()
            except Exception:
                log.exception('Error tearing down %s', trigger)

    def start(self):
        '''
        Called when the game has just started. By this point the Game and
        World have been completely initialised. May be used to set up event
        handlers and bots.
        '''
        pass

    def findReasonPlayerCannotJoin(self, game, teamId, user, bot):
        '''
        Checks whether or not another player with the given details can join
        the game. By default, this will respect game.maxTotalPlayers, and
        game.maxPerTeam.

        @param game: the LocalGame object of the current game
        @param teamId: the id of the team that the player will join if
            permitted (calculated from call to getIdOfTeamToJoin().
        @param user: the authentication server user object if this game is
            being run on an authentication server, or None otherwise.
        @param bot: whether or not the requested join is from a bot.

        @return: None if the player can join the game, or a reason constant
            otherwise (e.g. GAME_FULL_REASON, or UNAUTHORISED_REASON).
        '''
        if len(game.world.players) >= game.maxTotalPlayers:
            return GAME_FULL_REASON

        teamPlayerCounts = game.world.getTeamPlayerCounts()
        if (teamId != NEUTRAL_TEAM_ID and
                teamPlayerCounts.get(teamId, 0) >= game.maxPerTeam):
            return GAME_FULL_REASON

        return None

    def getTeamToJoin(self, preferredTeam, user, bot):
        '''
        When a player asks to join a game, this method is called to decide
        which team to put them on, assuming that they are allowed to join.

        @param preferredTeam: the team that the player would like to join if
            possible, or None if the player does not care
        @param user: the authentication server user object if this game is
            being run on an authentication server, or None otherwise.
        @param bot: whether or not the requested join is from a bot.

        @return: a team
        '''

        # Default team selection defers to bot manager
        if self.world.botManager:
            return self.world.botManager.getTeamToJoin(preferredTeam, bot)
        return preferredTeamOtherwiseSmallest(preferredTeam, self.world)

    def getWinner(self):
        '''
        Called when the server is saving the stats record for this game.
        Should return the team that has won, or None if the game has drawn.
        If the game is still in progress the Level may return None, or may
        return who is currently in the lead: this will only ever be used if
        the stats are saved half-way through the game and not saved at the
        end (e.g. server crashed).
        '''
        return self._winner

    def endLevel(self):
        '''
        Function for a level to call, to notify the server that the current
        level is complete.
        '''
        self.world.stopCurrentLevel()

    @defer.inlineCallbacks
    def addBot(self, game, team, nick, botName='puppet'):
        '''
        Utility function that adds a bot to the game, but bypasses the call
        to findReasonPlayerCannotJoin(), because it is this level that has
        requested the join. By default, creates a PuppetBot which does
        nothing until told.
        '''
        bot = yield game.addBot(botName, team=team, fromLevel=True, nick=nick)
        if bot.player is None:
            yield bot.onPlayerSet.wait()

        defer.returnValue(bot.ai)

    @defer.inlineCallbacks
    def waitForHumans(self, number):
        '''
        Utility function that waits until at least number human players have
        joined the game, then returns a collection of the human players in
        the game.
        '''
        while True:
            humans = [p for p in self.world.players if not p.bot]
            if len(humans) >= number:
                defer.returnValue(humans)

            yield self.world.onPlayerAdded.wait()

    def sendPrivateChat(self, fromPlayer, toPlayer, text):
        fromPlayer.agent.sendRequest(
            ChatMsg(PRIVATE_CHAT, toPlayer.id, text=text.encode()))

    def playSound(self, filename):
        '''
        Utility function to play a sound on all clients. The sound file must
        exist on the client system.
        '''
        self.world.sendServerCommand(PlaySoundMsg(filename.encode('utf-8')))

    def setUserInfo(self, userTitle, userInfo, botGoal):
        '''
        Utility function to set the tip that all players get to tell them
        their current objectives. Note that this function sets this tip
        globally for all players.
        '''
        self.world.uiOptions.setDefaultUserInfo(userTitle, userInfo, botGoal)
        self.world.sendServerCommand(
            UpdateGameInfoMsg.build(userTitle, userInfo, botGoal))

    def notifyAll(self, message, error=False):
        '''
        Sends a notification message to all players and observers.
        '''
        self.world.sendServerCommand(
            ChatFromServerMsg(text=message.encode('utf-8'), error=error))

    def setWinner(self, winner):
        '''
        Utility function that shows the game over banner, blows a whistle, and
        modifies what getWinner() will return.
        '''
        self.playSound('game-over-whistle.ogg')
        self._winner = winner
        self.world.uiOptions.set(showGameOver=True, winningTeam=winner)


class LobbyLevel(Level):
    recordReplay = False
    resetPlayerCoins = False

    def setupMap(self):
        # Just keep the existing map
        pass

    def start(self):
        for player in self.world.players:
            if player.team is not None:
                self.world.sendServerCommand(
                    SetPlayerTeamMsg(player.id, NEUTRAL_TEAM_ID))
        MakeNewPlayersNeutralTrigger(self).activate()
        if not self.world.isOnceOnly():
            self.world.uiOptions.set(showReadyStates=True)
            AddBotsForLobbyTrigger(self).activate()
            StartGameWhenReadyTrigger(self).activate()

            title = 'Lobby'
            userInfo = (
                '* Free for all',
                '* Select preferred options from top menu',
                '* A match will start when enough players select "ready"',
            )
        else:
            title = 'Game Over'
            userInfo = (
                'Use the menu in the bottom left to leave game',
            )
        self.setUserInfo(title, userInfo, BOT_GOAL_NONE)

        self.world.abilities.set(zoneCaps=False, renaming=True)
        self.world.onChangeVoiceChatRooms([], [])


class RandomLayoutHelper(object):
    '''
    Provides helper functions for generating a random map layout.
    '''

    def __init__(
            self, world, halfMapWidth=None, mapHeight=None, blockRatio=None,
            duration=None):
        self.world = world
        self.halfMapWidth = halfMapWidth
        self.mapHeight = mapHeight
        self.blockRatio = blockRatio
        self.duration = None

        self.ensureMapSizeIsNotNone()
        self.ensureBlockRatioIsNotNone()
        self.ensureDurationIsNotNone()

    def apply(self):
        zones = ZoneLayout.generate(
            self.halfMapWidth, self.mapHeight, self.blockRatio)
        layout = zones.createMapLayout(self.world.layoutDatabase)
        self.world.setLayout(layout)

    def ensureMapSizeIsNotNone(self):
        if self.halfMapWidth is not None and self.mapHeight is not None:
            return

        # Calculates a new map size based on what players vote for, with the
        # defaults (if most people select Auto) being determined by the size of
        # the teams.
        sizeCount = {}
        for player in self.world.players:
            if player.bot:
                continue
            size = player.preferredSize
            sizeCount[size] = sizeCount.get(size, 0) + 1

        if sizeCount:
            bestSize = max(sizeCount, key=sizeCount.get)
            if sizeCount.get((0, 0), 0) != sizeCount[bestSize]:
                self.halfMapWidth, self.mapHeight = bestSize
                return

        # Decide size based on player count.
        teamSize = sum(1 for p in self.world.players if not p.bot)

        if teamSize <= 3:
            self.halfMapWidth, self.mapHeight = (1, 1)
        elif teamSize <= 4:
            self.halfMapWidth, self.mapHeight = (5, 1)
        else:
            self.halfMapWidth, self.mapHeight = (3, 2)

        assert self.halfMapWidth is not None
        assert self.mapHeight is not None

    def ensureBlockRatioIsNotNone(self):
        '''
        By default, assume that larger maps want higher block ratios because a
        map that's too big with no obstacles results in chaos.
        '''
        if self.blockRatio is not None:
            return
        roughArea = (2 * self.halfMapWidth + 1) * (self.mapHeight + 0.5)
        self.blockRatio = max(0.3, 1 - 5. / roughArea)

        assert self.blockRatio is not None

    def ensureDurationIsNotNone(self):
        if self.duration is not None:
            return

        durationCount = {}
        for player in self.world.players:
            if player.bot:
                continue
            duration = player.preferredDuration
            durationCount[duration] = durationCount.get(duration, 0) + 1

        if durationCount:
            bestDuration = max(durationCount, key=durationCount.get)
            if durationCount.get(0, 0) != durationCount[bestDuration]:
                self.duration = bestDuration
                return

        # Decide default based on map size.
        if (self.halfMapWidth, self.mapHeight) == (3, 2):
            self.duration = 45 * 60
        elif (self.halfMapWidth, self.mapHeight) == (1, 1):
            self.duration = 10 * 60
        elif (self.halfMapWidth, self.mapHeight) == (5, 1):
            self.duration = 20 * 60
        else:
            self.duration = min(
                7200,
                2 * 60 * (self.halfMapWidth * 2 + 1) * (self.mapHeight * 1.5))

        assert self.duration is not None


def playLevel(level, withLogging=True, **kwargs):
    '''
    For testing new Levels - launches Trosnoth in single player mode with
    the given level.
    '''
    from trosnoth.run.solotest import Main

    if withLogging:
        from trosnoth.utils.utils import initLogging
        initLogging()

    Main(level=level, **kwargs).run_twisted()
