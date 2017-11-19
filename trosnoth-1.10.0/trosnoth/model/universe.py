'''universe.py - defines anything that has to do with the running of the
universe. This includes players, shots, zones, and the level itself.'''

from __future__ import division

from collections import defaultdict
import heapq
import json
import logging
from math import sin, cos
import random

import pygame
from twisted.internet import defer, reactor

from trosnoth.const import (
    TURRET_DEATH, TROSBALL_DEATH, SHOXWAVE_DEATH,
    COLLECTABLE_COIN_LIFETIME, TICK_PERIOD,
    MAX_PLAYER_NAME_LENGTH,BOMBER_DEATH, CUSTOM_DEATH, COINS_PER_KILL,
    FRONT_LINE_NORMAL, FRONT_LINE_TROSBALL, BOT_GOAL_NONE,
)
from trosnoth.levels.base import LobbyLevel
from trosnoth.levels.standard import StandardLoadedLevel, StandardRandomLevel
from trosnoth.utils import globaldebug
from trosnoth.model.idmanager import IdManager
from trosnoth.model.upgrades import upgradeOfType, allUpgrades
from trosnoth.model.physics import WorldPhysics

from trosnoth.model.map import MapLayout, MapState
from trosnoth.model.player import Player
from trosnoth.model.coin import CollectableCoin
from trosnoth.model.shot import Shot, GrenadeShot
from trosnoth.model.team import Team
from trosnoth.model.trosball import Trosball
from trosnoth.model.universe_base import NEUTRAL_TEAM_ID, NO_PLAYER
from trosnoth.model.voteArbiter import VoteArbiter

from trosnoth.utils.event import Event
from trosnoth.utils.math import distance
from trosnoth.utils.message import MessageConsumer
from trosnoth.utils.twist import WeakCallLater
from trosnoth.utils.unrepr import unrepr
from trosnoth.messages import (
    TaggingZoneMsg, ShotFiredMsg, RespawnMsg, ChatFromServerMsg,
    RemovePlayerMsg, ShotHitPlayerMsg, PlayerIsReadyMsg,
    AddPlayerMsg, PlayerCoinsSpentMsg, ZoneStateMsg,
    WorldResetMsg, UpdateClockStateMsg, SetPlayerCoinsMsg, WorldLoadingMsg,
    CreateCollectableCoinMsg, RemoveCollectableCoinMsg, PlayerHasElephantMsg,
    FireShoxwaveMsg, UpgradeChangedMsg, SetTeamScoreMsg, SetPlayerScoreMsg,
    PlayerHasTrosballMsg, TrosballPositionMsg, AwardPlayerCoinMsg,
    TickMsg, SetUIOptionsMsg,
    TICK_LIMIT, UpdateScoreBoardModeMsg,
    SetWorldAbilitiesMsg,
)

log = logging.getLogger('universe')

DEFAULT_GAME_COUNTDOWN = 10


class DelayedCall(object):
    def __init__(self, fn, args, kwargs):
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.cancelled = False

    def cancel(self):
        self.cancelled = True



class UnknownMapLayouts(Exception):
    def __init__(self, *args, **kwargs):
        super(UnknownMapLayouts, self).__init__(*args, **kwargs)
        self.keys = self.message


class ScoreBoard(object):
    '''
    Synchronises scores for teams and for individual players, if scores make
    sense for the current level.
    '''

    def __init__(self, world):
        self.world = world
        self.teamScoresEnabled = False
        self.playerScoresEnabled = False
        self.teamScores = {t: 0 for t in world.teams}
        self.playerScores = {p: 0 for p in world.players}
        world.onPlayerAdded.addListener(self._playerWasAdded)
        world.onPlayerRemoved.addListener(self._playerWasRemoved)

    def stop(self):
        self.world.onPlayerAdded.removeListener(self._playerWasAdded)
        self.world.onPlayerRemoved.removeListener(self._playerWasRemoved)

    def dumpState(self):
        return {
            'teamScoresEnabled': self.teamScoresEnabled,
            'playerScoresEnabled': self.playerScoresEnabled,
            'teamScores': {t.id: s for t, s in self.teamScores.items()},
            'playerScores': {p.id: s for p, s in self.playerScores.items()},
        }

    def restoreState(self, data):
        self.teamScoresEnabled = data['teamScoresEnabled']
        self.playerScoresEnabled = data['playerScoresEnabled']
        for team in self.teamScores:
            if team.id in data['teamScores']:
                self.teamScores[team] = data['teamScores'][team.id]
        for player in self.playerScores:
            if player.id in data['playerScores']:
                self.playerScores[player] = data['playerScores'][player.id]

    def _playerWasAdded(self, player, *args, **kwargs):
        self.playerScores[player] = 0

    def _playerWasRemoved(self, player, *args, **kwargs):
        del self.playerScores[player]

    def teamScored(self, team, amount=1):
        assert self.world.isServer
        self.world.sendServerCommand(
            SetTeamScoreMsg(team.id, self.teamScores[team] + amount))

    def gotTeamScoreMsg(self, team, score):
        self.teamScores[team] = score

    def playerScored(self, player, amount=1):
        assert self.world.isServer
        self.world.sendServerCommand(
            SetPlayerScoreMsg(player.id, self.playerScores[player] + amount))

    def gotPlayerScoreMsg(self, player, score):
        self.playerScores[player] = score

    def setMode(self, teams=None, players=None):
        assert self.world.isServer
        if teams is not None:
            self.teamScoresEnabled = teams
        if players is not None:
            self.playerScoresEnabled = players

        self.world.sendServerCommand(UpdateScoreBoardModeMsg(
            self.teamScoresEnabled, self.playerScoresEnabled))

    def gotUpdateScoreBoardModeMsg(self, teams, players):
        self.teamScoresEnabled = teams
        self.playerScoresEnabled = players


class Clock(object):
    '''
    Keeps track of what should be displayed on the in-game clock. This may
    mean different things for different levels or game states, and may be
    used in UI displays, or by the level or game state, but outside things
    should not rely on it for calculating remaining game time etc.
    '''

    def __init__(self, world):
        self.onZero = Event([])

        self.world = world
        self.value = 0.0
        self.flashBelow = 0
        self.counting = False
        self.showing = False
        self.upwards = False

    def dumpState(self):
        return {
            'value': self.value,
            'flashBelow': self.flashBelow,
            'counting': self.counting,
            'showing': self.showing,
            'upwards': self.upwards,
        }

    def restoreState(self, data):
        self.value = data['value']
        self.flashBelow = data['flashBelow']
        self.setMode(
            showing=data['showing'],
            counting=data['counting'],
            upwards=data['upwards'],
        )

    def getTimeString(self):
        if not self.showing:
            return '--:--'

        if self.upwards:
            seconds = self.value
        else:
            # We add 0.999 so that the timer is rounding up the seconds
            # rather than rounding them down. This is so that the instant it
            # hits zero, the game starts.
            seconds = self.value + 0.999
        minutes, seconds = divmod(int(seconds), 60)
        return '%02d:%02d' % (minutes, seconds)

    def shouldFlash(self):
        if not self.showing:
            return False
        if self.flashBelow == 0 or not self.showing:
            return False
        return self.value <= self.flashBelow

    def setMode(self, counting=None, showing=None, upwards=None):
        if counting is not None:
            self.counting = counting
        if showing is not None:
            self.showing = showing
        if upwards is not None:
            self.upwards = upwards

    def startCountDown(self, seconds, flashBelow=10):
        self.value = seconds
        self.flashBelow = flashBelow
        self.setMode(counting=True, showing=True, upwards=False)

    def startCountUp(self, seconds=0):
        self.value = seconds
        self.flashBelow = 0
        self.setMode(counting=True, showing=True, upwards=True)

    def pause(self):
        self.setMode(counting=False)

    def resume(self):
        self.setMode(counting=True)

    def stop(self):
        self.setMode(showing=False, counting=False)

    def tick(self):
        if not self.counting:
            return

        if self.upwards:
            self.value += TICK_PERIOD
        else:
            oldValue = self.value
            self.value -= TICK_PERIOD
            self.value = max(0, self.value)
            if self.value == 0 and oldValue > 0:
                self.onZero()

    def propagateToClients(self):
        '''
        Should be called on the server immediately after any direct clock
        state changed. Only works on the server.
        '''
        self.world.sendServerCommand(UpdateClockStateMsg(
            showing=self.showing, counting=self.counting,
            upwards=self.upwards, value=self.value,
            flashBelow=self.flashBelow))


class Abilities(object):
    RESERVED_ATTRIBUTES = ('world',)

    def __init__(self, world):
        self.world = world

        self.upgrades = True
        self.respawn = True
        self.leaveFriendlyZones = True
        self.zoneCaps = True
        self.renaming = False

    def dumpState(self):
        return {
            'upgrades': self.upgrades,
            'respawn': self.respawn,
            'leaveFriendlyZones': self.leaveFriendlyZones,
            'zoneCaps': self.zoneCaps,
            'renaming': self.renaming,
        }

    def restoreState(self, data):
        self.upgrades = data['upgrades']
        self.respawn = data['respawn']
        self.leaveFriendlyZones = data['leaveFriendlyZones']
        self.zoneCaps = data['zoneCaps']
        self.renaming = data['renaming']

    def set(self, **kwargs):
        assert self.world.isServer
        for key in kwargs:
            if not self._isKeyValid(key):
                raise KeyError('{!r} is not a valid UI option', key)
        self.world.sendServerCommand(SetWorldAbilitiesMsg(json.dumps(kwargs)))

    def reset(self):
        self.set(
            upgrades=True, respawn=True, leaveFriendlyZones=True,
            zoneCaps=True, renaming=False)

    def _isKeyValid(self, key):
        if not hasattr(self, key):
            return False
        if key in self.RESERVED_ATTRIBUTES:
            return False
        if key.startswith('_'):
            return False
        return True

    def gotSetWorldAbilitiesMsg(self, settings):
        for key, value in settings.items():
            if self._isKeyValid(key):
                setattr(self, key, value)


class UIOptions(object):
    '''
    Represents options related to how this kind of match should be displayed to
    the user.
    '''
    RESERVED_ATTRIBUTES = (
        'world', 'defaultUserTitle', 'defaultUserInfo', 'defaultBotGoal',
    )

    def __init__(self, world):
        self.world = world

        self.onChange = Event([])

        self.defaultUserTitle = ''      # Server only
        self.defaultUserInfo = ()       # Server only
        self.defaultBotGoal = BOT_GOAL_NONE     # Server only

        self.showNets = False
        self.frontLine = FRONT_LINE_NORMAL
        self.showReadyStates = False
        self.showGameOver = False
        self.winningTeamId = NEUTRAL_TEAM_ID

    @property
    def winningTeam(self):
        return self.world.getTeam(self.winningTeamId)

    def dumpState(self):
        return {
            'showNets': self.showNets,
            'frontLine': self.frontLine,
            'showReadyStates': self.showReadyStates,
        }

    def restoreState(self, data):
        self.showNets = data['showNets']
        self.frontLine = data['frontLine']
        self.showReadyStates = data['showReadyStates']

    def setDefaultUserInfo(self, userTitle, userInfo, botGoal):
        assert self.world.isServer
        self.defaultUserTitle = userTitle
        self.defaultUserInfo = userInfo
        self.defaultBotGoal = botGoal

    def getFrontLine(self):
        if self.frontLine == FRONT_LINE_TROSBALL:
            trosballPos = self.world.trosballManager.getPosition()
            if trosballPos is None:
                return None
            return trosballPos[0]
        return None

    def set(self, **kwargs):
        assert self.world.isServer

        # Special case for winningTeam=team so it can be sent over wire
        if 'winningTeam' in kwargs:
            winningTeam = kwargs.pop('winningTeam')
            if winningTeam is None:
                kwargs['winningTeamId'] = NEUTRAL_TEAM_ID
            else:
                kwargs['winningTeamId'] = winningTeam.id

        for key in kwargs:
            if not self._isKeyValid(key):
                raise KeyError('{!r} is not a valid UI option', key)
        self.world.sendServerCommand(SetUIOptionsMsg(json.dumps(kwargs)))

    def reset(self):
        self.set(
            showNets=False, frontLine=FRONT_LINE_NORMAL,
            showReadyStates=False,
            showGameOver=False, winningTeam=None,
        )

    def _isKeyValid(self, key):
        if not hasattr(self, key):
            return False
        if key in self.RESERVED_ATTRIBUTES:
            return False
        if key.startswith('_'):
            return False
        return True

    def gotSetUIOptionsMsg(self, settings):
        for key, value in settings.items():
            if self._isKeyValid(key):
                setattr(self, key, value)
        self.onChange()


class TrosballManager(object):
    def __init__(self, world):
        self.world = world
        self.enabled = False
        self.trosballUnit = None
        self.trosballPlayer = None
        self.lastTrosballPlayer = None
        self.trosballCooldownPlayer = None
        self.playerGotTrosballTick = None

    def dumpState(self):
        if not self.enabled:
            return None

        if self.trosballUnit:
            return {
                'pos': self.trosballUnit.pos,
                'vel': [self.trosballUnit.xVel, self.trosballUnit.yVel],
                'playerId': None,
                'catchTicksAgo': None,
            }

        return {
            'pos': None,
            'vel': None,
            'playerId': self.trosballPlayer.id,
            'catchTicksAgo': (
                self.playerGotTrosballTick - self.world.getMonotonicTick()),
        }

    def restoreState(self, data):
        self.trosballCooldownPlayer = None

        if data is None:
            self.enabled = False
            self.trosballPlayer = None
            self.trosballCooldownPlayer = None
            self.trosballUnit = None
            self.playerGotTrosballTick = None
            return

        self.enabled = True
        if data['pos'] is not None:
            self.trosballPlayer = None
            self.trosballCooldownPlayer = None
            self.playerGotTrosballTick = None

            self.trosballUnit = Trosball(self.world)
            self.trosballUnit.teleport(data['pos'], data['vel'])
            return

        self.trosballUnit = None
        self.trosballPlayer = self.world.getPlayer(data['playerId'])
        self.lastTrosballPlayer = self.trosballPlayer
        self.playerGotTrosballTick = self.world.getMonotonicTick() + (
            data['catchTicksAgo'])

    #### Server / client routines

    def getPosition(self):
        if not self.enabled:
            return None

        if self.trosballUnit:
            return self.trosballUnit.pos
        return self.trosballPlayer.pos

    def getCooldownPlayer(self):
        if not self.enabled:
            return None
        return self.trosballCooldownPlayer

    def getAdvancables(self):
        if not self.enabled:
            return []
        if self.trosballUnit:
            return [self.trosballUnit]
        return []

    def getTargetZoneDefn(self, team):
        return self.world.layout.getTrosballTargetZoneDefn(team)

    def afterAdvance(self):
        '''
        Called once per tick on both client and server, to advance Trosball
        position etc. Most be deterministic or client and server could get
        out of sync.
        '''
        if not self.enabled:
            return

        self._updateZoneOwnership()
        self._maybeExplode()

    def playerDroppedTrosball(self):
        '''
        Called on both client and server if the player carrying the Trosball
        died or left the game.
        '''
        assert self.trosballPlayer is not None
        self.trosballUnit = Trosball(self.world)
        self.trosballUnit.teleport(
            self.trosballPlayer.pos,
            self.trosballPlayer.getCurrentVelocity())
        self.trosballPlayer = None

    def _updateZoneOwnership(self):
        trosballPosition = self.getPosition()
        targetZones = {
            self.getTargetZoneDefn(team)
            for team in self.world.teams}

        for zone in self.world.zones:
            if zone.defn not in targetZones:
                zone.updateByTrosballPosition(trosballPosition)

    def _maybeExplode(self):
        if self.trosballPlayer is None:
            return
        explodeTick = (
            self.playerGotTrosballTick
            + self.world.physics.trosballExplodeTime // TICK_PERIOD)
        if self.world.getMonotonicTick() < explodeTick:
            return

        player = self.trosballPlayer
        player.killOutright(deathType=TROSBALL_DEATH)
        self.world.onTrosballExplosion(player)

    def getKickoffLocation(self):
        layout = self.world.map.layout
        return (layout.centreX, layout.centreY - 50)

    #### Server-side only

    def enable(self, pos=None, vel=None, inNet=False):
        assert self.world.isServer
        if self.enabled:
            return
        if pos is None:
            pos = self.getKickoffLocation()
        if vel is None:
            vel = (0, 0)
        self.world.sendServerCommand(
            TrosballPositionMsg(pos[0], pos[1], vel[0], vel[1], inNet))

    def disable(self):
        assert self.world.isServer
        if not self.enabled:
            return
        self.world.sendServerCommand(PlayerHasTrosballMsg(NO_PLAYER))

    def retransmit(self):
        if self.enabled:
            if self.trosballPlayer:
                self.giveToPlayer(self.trosballPlayer)
            else:
                vel = (self.trosballUnit.xVel, self.trosballUnit.yVel)
                self.teleport(self.trosballUnit.pos, vel)
        else:
            self.world.sendServerCommand(PlayerHasTrosballMsg(NO_PLAYER))

    def giveToPlayer(self, player):
        assert self.world.isServer
        if not self.enabled:
            raise RuntimeError('trosball mode not enabled')
        self.world.sendServerCommand(PlayerHasTrosballMsg(player.id))

    def teleport(self, pos, vel, inNet=False):
        assert self.world.isServer
        if not self.enabled:
            raise RuntimeError('trosball mode not enabled')
        self.world.sendServerCommand(
            TrosballPositionMsg(pos[0], pos[1], vel[0], vel[1], inNet))

    def placeInNet(self, team):
        assert self.world.isServer
        netPos = self.getTargetZoneDefn(team).pos
        self.teleport(netPos, (0, 0), True)

    def resetToCentreOfMap(self):
        pos = self.getKickoffLocation()
        self.lastTrosballPlayer = None
        self.teleport(pos, (0, 0))

    def throwTrosball(self):
        assert self.world.isServer
        player = self.trosballPlayer
        xVel, yVel = player.getCurrentVelocity()
        angle = player.angleFacing
        xVel += self.world.physics.trosballThrowVel * sin(angle)
        yVel += -self.world.physics.trosballThrowVel * cos(angle)
        self.trosballCooldownPlayer = player

        self.world.callLater(0.5, self._clearTrosballCooldown, player)
        self.teleport(player.pos, (xVel, yVel))

    def _clearTrosballCooldown(self, player):
        if self.trosballCooldownPlayer == player:
            self.trosballCooldownPlayer = None

    #### Message handling

    def gotTrosballPositionMsg(self, pos, vel, inNet):
        self.enabled = True
        self.trosballPlayer = None
        if self.trosballUnit is None:
            self.trosballUnit = Trosball(self.world)

        if inNet:
            self.trosballUnit.setIsInNet(pos)
        else:
            self.trosballUnit.teleport(pos, vel)

    def gotPlayerHasTrosballMsg(self, player):
        if player is None:
            self.enabled = False
            self.trosballPlayer = None
            self.trosballCooldownPlayer = None
            self.trosballUnit = None
        else:
            self.enabled = True
            self.trosballUnit = None
            self.trosballPlayer = player
            self.lastTrosballPlayer = player
            self.trosballPlayer.items.clear()
            self.playerGotTrosballTick = self.world.getMonotonicTick()
            self.trosballPlayer.onGotTrosball()


class Universe(MessageConsumer):
    '''
    Keeps track of where everything is in the level, including the locations
    and states of every alien, the terrain positions, and who owns the
    various territories and orbs.'''

    isServer = False

    def __init__(
            self, layoutDatabase,
            authTagManager=None, onceOnly=False):
        super(Universe, self).__init__()

        self.onPlayerAdded = Event(['player'])
        self.onPlayerRemoved = Event(['player', 'oldId'])
        self.onTeamScoreChanged = Event()
        self.onShotRemoved = Event()        # (shotId)
        self.onCollectableCoinSpawned = Event(['coin'])
        self.onCollectableCoinRemoved = Event()
        self.onStandardGameFinished = Event(['winner'])
        self.onZoneTagged = Event()         # (zone, player, previousOwner)
        self.onZoneStateChanged = Event()   # (zone)
        self.onOpenChatReceived = Event()   # (text, sender)
        self.onTeamChatReceived = Event()   # (team, text, sender)
        self.onPlayerKill = Event()         # (killer, target, deathType)
        self.onPlayerRespawn = Event()      # (player)
        self.onGrenadeExplosion = Event()   # (pos, radius)
        self.onTrosballExplosion = Event()  # (player)
        self.onBomberExplosion = Event()    # (player)
        self.onReset = Event()
        self.onServerTickComplete = Event()
        self.onChangeVoiceChatRooms = Event()   # (teams, players)

        self.delayedCalls = []

        self.isIncomplete = False
        self.playerWithElephant = None
        self.physics = WorldPhysics(self)
        if authTagManager is None:
            self.authManager = None
        else:
            self.authManager = authTagManager.authManager

        self.playerWithId = {}
        self.shotWithId = {}
        self.teamWithId = {NEUTRAL_TEAM_ID: None}

        # Create Teams:
        self.teams = (
            Team(self, 'A'),
            Team(self, 'B'),
        )
        Team.setOpposition(self.teams[0], self.teams[1])

        for t in self.teams:
            self.teamWithId[t.id] = t

        # Set up zones
        self.zoneWithDef = {}
        self.layout = None
        self.map = None
        self.zoneWithId = {}
        self.zones = set()
        self.zoneBlocks = []

        self.players = set()
        self.grenades = set()
        self.collectableCoins = {}      # coinId -> CollectableCoin
        self.deadCoins = set()
        self.gameMode = 'Normal'
        self.rogueTeamName = 'Rogue'
        self.tickPeriod = TICK_PERIOD
        self._gameSpeed = 1.0
        self.lastTickId = 0
        self.monotonicTicks = 0
        self.loading = False

        self.layoutDatabase = layoutDatabase
        self._onceOnly = onceOnly
        self.clock = Clock(self)
        self.scoreboard = ScoreBoard(self)
        self.trosballManager = TrosballManager(self)
        self.abilities = Abilities(self)
        self.uiOptions = UIOptions(self)

        self.loadedMap = None

    def getMonotonicTick(self):
        '''
        Returns an integer representing the number of ticks seen since some
        arbitrary point in the past. Unlike world.lastTickId, this is
        guaranteed to be monotonic, but may not be the same between server
        and clients.
        '''
        return self.monotonicTicks

    def getMonotonicTime(self):
        return self.monotonicTicks * TICK_PERIOD

    def isValidNick(self, nick):
        if len(nick) < 2 or len(nick) > MAX_PLAYER_NAME_LENGTH:
            return False
        return True

    @property
    def shots(self):
        '''
        Used by UI to iterate through shots.
        '''
        return self.shotWithId.values()

    def defaultHandler(self, msg):
        msg.applyOrderToWorld(self)

    def selectZoneForTeam(self, teamId):
        '''
        Randomly selects a zone, giving preference to:
            1. Zones owned by the given team that are adjacent to an enemy zone
            2. Zones owned by the given team that are adjacent to a zone not
                owned by the team.
            3. Other zones owned by the given team.
            4. Other zones.
        '''
        team = self.getTeam(teamId)
        allTeamZones = [
            z for z in self.map.zones
            if z.owner is not None and z.owner.id == teamId]
        nextToEnemy = []
        nextToNeutral = []
        for zone in list(allTeamZones):
            enemy = neutral = False
            for adj in zone.getAdjacentZones():
                if adj.owner is None:
                    neutral = True
                elif adj.isEnemyTeam(team):
                    enemy = True
            if enemy:
                nextToEnemy.append(zone)
            elif neutral:
                nextToNeutral.append(zone)

        return random.choice(
            nextToEnemy
            or nextToNeutral
            or allTeamZones
            or list(self.map.zones))

    @WorldResetMsg.handler
    def gotWorldReset(self, msg):
        if not self.isServer:
            data = unrepr(msg.settings)
            self.restoreEverything(data)

    def getTeam(self, teamId):
        if teamId == NEUTRAL_TEAM_ID:
            return None
        return self.teamWithId[teamId]

    def getPlayer(self, playerId, default=None):
        return self.playerWithId.get(playerId, default)

    def getUpgradeType(self, upgradeTypeId):
        return upgradeOfType[upgradeTypeId]

    def getZone(self, zoneId, default=None):
        return self.map.zoneWithId.get(zoneId, default)

    def getShot(self, sId):
        return self.shotWithId[sId]

    def setGameMode(self, mode):
        if self.physics.setMode(mode):
            self.gameMode = mode
            log.debug('Client: GameMode is set to ' + mode)

    def setGameSpeed(self, speed):
        '''Sets the speed of the game to a proportion of normal speed.
        That is, speed=2.0 is twice as fast a game as normal
        '''
        self._gameSpeed = speed
        self.tickPeriod = TICK_PERIOD * speed

    @AddPlayerMsg.handler
    def handle_AddPlayerMsg(self, msg):
        team = self.teamWithId[msg.teamId]
        zone = self.zoneWithId[msg.zoneId]

        # Create the player.
        nick = msg.nick.decode()
        player = Player(self, nick, team, msg.playerId, msg.dead, msg.bot)
        player.teleportToZoneCentre(zone)
        player.resyncBegun()

        self.addPlayer(player)

    def addPlayer(self, player):
        # Add this player to this universe.
        self.players.add(player)
        self.playerWithId[player.id] = player
        self.onPlayerAdded(player)

    @PlayerHasElephantMsg.handler
    def gotElephantMsg(self, msg):
        player = self.getPlayer(msg.playerId)
        self.playerWithElephant = player

    def delPlayer(self, player):
        playerId = player.id
        player.removeFromGame()
        self.players.remove(player)
        del self.playerWithId[player.id]
        if player == self.playerWithElephant:
            self.returnElephantToOwner()

        # In case anyone else keeps a reference to it
        player.id = -1
        player.onRemovedFromGame(playerId)
        self.onPlayerRemoved(player, playerId)

    def advanceEverything(self):
        '''Advance the state of the game by deltaT seconds'''

        for shot in list(self.shots):
            if shot.expired:
                del self.shotWithId[shot.id]
                self.onShotRemoved(shot.id)

        # Update the player and shot positions.
        advancables = (
            self.shotWithId.values() + list(self.players) + list(self.grenades)
            + self.collectableCoins.values())
        advancables.extend(self.trosballManager.getAdvancables())
        for unit in advancables:
            unit.reset()
            unit.advance()

        self.updateZoneInhabitants(advancables)
        self.trosballManager.afterAdvance()

    def getCollectableUnits(self):
        for coin in self.collectableCoins.values():
            yield coin
        if self.trosballManager.enabled and self.trosballManager.trosballUnit:
            yield self.trosballManager.trosballUnit
        for unit in list(self.deadCoins):
            yield unit

    def updateZoneInhabitants(self, advancables):
        for zone in self.map.zones:
            zone.clearPlayers()
        for unit in advancables:
            if isinstance(unit, Player):
                zone = unit.getZone()
                if zone:
                    zone.addPlayer(unit)

    def bomberExploded(self, player):
        player.killOutright(deathType=BOMBER_DEATH)
        self.onBomberExplosion(player)

    def canShoot(self):
        return self.physics.shooting

    def canRename(self):
        return self.abilities.renaming

    @CreateCollectableCoinMsg.handler
    def createCollectableCoin(self, msg):
        self.addCollectableCoin(CollectableCoin(
            self, msg.coinId,
            (msg.xPos, msg.yPos), msg.xVel, msg.yVel,
            msg.value,
        ))

    @RemoveCollectableCoinMsg.handler
    def gotRemoveCollectableCoinMsg(self, msg):
        # On the server, the coin must be remembered in case a player is about
        # to collect it but we don't know yet.
        if not self.isServer:
            coin = self.collectableCoins[msg.coinId]
            if not coin.vanished:
                coin.onVanish(coin)

            del self.collectableCoins[msg.coinId]
            self.onCollectableCoinRemoved(msg.coinId)

    def teamWithAllZones(self):
        # Now check for an all zones win.
        team2Wins = self.teams[0].isLoser()
        team1Wins = self.teams[1].isLoser()
        if team1Wins and team2Wins:
            # The extraordinarily unlikely situation that all
            # zones have been neutralised in the same tick
            return 'Draw'
        elif team1Wins:
            return self.teams[0]
        elif team2Wins:
            return self.teams[1]
        else:
            return None

    def teamWithMoreZones(self):
        if self.teams[0].numZonesOwned > self.teams[1].numZonesOwned:
            return self.teams[0]
        elif self.teams[1].numZonesOwned > self.teams[0].numZonesOwned:
            return self.teams[1]
        else:
            return None

    def getTeamPlayerCounts(self):
        '''
        Returns a mapping from team id to number of players currently on that
        team.
        '''
        playerCounts = {}
        for player in self.players:
            playerCounts[player.teamId] = playerCounts.get(
                player.teamId, 0) + 1
        return playerCounts

    def getTeamName(self, id):
        if id == NEUTRAL_TEAM_ID:
            return self.rogueTeamName
        return self.getTeam(id).teamName

    @FireShoxwaveMsg.handler
    def shoxwaveExplosion(self, msg):
        radius = 128
        # Get the player who fired this shoxwave
        shoxPlayer = self.getPlayer(msg.playerId)
        if not shoxPlayer:
            return
        shoxPlayer.weaponDischarged()

        # Loop through all the players in the game
        for player in self.players:
            if not (player.isFriendsWith(shoxPlayer) or distance(player.pos,
                    shoxPlayer.pos) > radius or player.dead or
                    player.isInvulnerable() or
                    player.phaseshift or player.turret):
                player.zombieHit(shoxPlayer, None, SHOXWAVE_DEATH)

        for shot in self.shotWithId.values():
            if (not shot.originatingPlayer.isFriendsWith(shoxPlayer) and
                    distance(shot.pos, shoxPlayer.pos) <= radius):
                shot.expired = True

    @ShotFiredMsg.handler
    def shotFired(self, msg):
        '''A player has fired a shot.'''
        try:
            player = self.playerWithId[msg.playerId]
        except KeyError:
            return

        shot = player.createShot(msg.shotId)
        self.shotWithId[msg.shotId] = shot
        player.weaponDischarged()
        player.onShotFired(shot)

    def _killTurret(self, tagger, zone):
        if zone.turretedPlayer is not None:
            zone.turretedPlayer.killOutright(
                deathType=TURRET_DEATH, killer=tagger)

    @TaggingZoneMsg.handler
    def zoneTagged(self, msg):
        if msg.playerId == NO_PLAYER:
            player = None
        else:
            player = self.playerWithId[msg.playerId]
        zone = self.map.zoneWithId[msg.zoneId]
        previousOwner = zone.owner
        zone.tag(player)
        self._killTurret(player, zone)
        self.onZoneTagged(zone, player, previousOwner)
        if player:
            player.onTaggedZone(zone, previousOwner)

    @ZoneStateMsg.handler
    def zoneOwned(self, msg):
        zone = self.map.zoneWithId[msg.zoneId]
        team = self.teamWithId[msg.teamId]
        zone.setOwnership(team, msg.dark)

    @RespawnMsg.handler
    def respawn(self, msg):
        player = self.getPlayer(msg.playerId)
        zone = self.getZone(msg.zoneId)
        if player and zone:
            player.respawn(zone)

    @PlayerCoinsSpentMsg.handler
    def coinsSpent(self, msg):
        player = self.getPlayer(msg.playerId)
        if player:
            oldCoins = player.coins
            player.coins -= msg.count
            player.onCoinsChanged(oldCoins)

    @UpgradeChangedMsg.handler
    def changeUpgrade(self, msg):
        for upgradeClass in allUpgrades:
            if upgradeClass.upgradeType == msg.upgradeType:
                if msg.statType == 'S':
                    upgradeClass.requiredCoins = msg.newValue
                elif msg.statType == 'T':
                    upgradeClass.totalTimeLimit = msg.newValue
                elif msg.statType == 'E':
                    upgradeClass.enabled = bool(msg.newValue)

    def addGrenade(self, grenade):
        self.grenades.add(grenade)

    def removeGrenade(self, grenade):
        self.grenades.remove(grenade)

    def addCollectableCoin(self, coin):
        self.collectableCoins[coin.id] = coin
        self.onCollectableCoinSpawned(coin)

    def setLayout(self, layout):
        self.zoneWithDef = {}
        for team in self.teams:
            team.numZonesOwned = 0
        self.layout = layout
        self.map = MapState(self, self.layout)
        self.zoneWithId = self.map.zoneWithId
        self.zones = self.map.zones
        self.zoneBlocks = self.map.zoneBlocks

        # Layout has changed, so move units to sensible places
        self.resetUnits()

    def resetUnits(self):
        for player in self.players:
            zone = self.selectZoneForTeam(player.teamId)
            player.teleportToZoneCentre(zone)
            player.health = 0
            player.zombieHits = 0
            player.items.clear()
            player.respawnGauge = 0.0

        self.deadCoins = set()
        self.collectableCoins = {}
        self.shotWithId = {}
        self.grenades = set()

    def setTestMode(self):
        for upgradetype in allUpgrades:
            upgradetype.requiredCoins = 1

    @TickMsg.handler
    def tickReceived(self, msg):
        self.monotonicTicks += 1
        self.clock.tick()
        self.advanceEverything()
        self.lastTickId = msg.tickId

        self.processDelayedCalls()

    def processDelayedCalls(self):
        now = self.getMonotonicTime()
        while self.delayedCalls:
            if self.delayedCalls[0][0] > now:
                break
            when, call = heapq.heappop(self.delayedCalls)
            if call.cancelled:
                continue
            try:
                call.fn(*call.args, **call.kwargs)
            except Exception:
                log.exception('Error in delayed call')

    def dumpEverything(self):
        '''Returns a dict representing the settings which must be sent to
        clients that connect to this server.'''

        result = {
            'loading': self.loading,
            'teams': [
                {
                    'id': team.id,
                    'name': team.teamName,
                } for team in self.teams
            ],
            'worldMap': self.map.layout.dumpState(),
            'mode': self.gameMode,
            'speed': self._gameSpeed,
            'zones': [
                {
                    'id': zone.id,
                    'teamId': zone.owner.id if zone.owner else NEUTRAL_TEAM_ID,
                    'dark': zone.dark,
                } for zone in self.zones
            ],
            'players': [player.dump() for player in self.players],
            'trosball': self.trosballManager.dumpState(),
            'upgrades': [
                {
                    'type': upgrade.upgradeType,
                    'cost': upgrade.requiredCoins,
                    'time': upgrade.totalTimeLimit,
                    'enabled': upgrade.enabled,
                } for upgrade in allUpgrades
            ],
            'elephant': self.playerWithElephant.id
                if self.playerWithElephant else None,
            'shots': [
                {
                    'id': shot.id,
                    'team': shot.team.id if shot.team else NEUTRAL_TEAM_ID,
                    'pos': shot.pos,
                    'vel': shot.vel,
                    'shooter': shot.originatingPlayer.id,
                    'time': shot.timeLeft,
                    'kind': shot.kind,
                } for shot in self.shotWithId.values() if not shot.expired
            ],
            'coins': [
                {
                    'id': coin.id,
                    'createdAgo': self.getMonotonicTick() - coin.creationTick,
                    'pos': coin.pos,
                    'xVel': coin.xVel,
                    'yVel': coin.yVel,
                } for coin in self.collectableCoins.values()
            ],
            'grenades': [
                {
                    'player': (
                        grenade.player.id if grenade.player else NO_PLAYER),
                    'pos': grenade.pos,
                    'xVel': grenade.xVel,
                    'yVel': grenade.yVel,
                    'timeLeft': grenade.timeLeft,
                } for grenade in self.grenades
            ],
            'physics': self.physics.dumpState(),
            'clock': self.clock.dumpState(),
            'scoreboard': self.scoreboard.dumpState(),
            'uiOptions': self.uiOptions.dumpState(),
            'abilities': self.abilities.dumpState(),
            'lastTickId': self.lastTickId,
        }

        return result

    def restoreEverything(self, data):
        self.loading = data['loading']
        if 'lastTickId' in data:
            self.lastTickId = data['lastTickId']

        for teamData in data['teams']:
            teamId = teamData['id']
            self.teamWithId[teamId].teamName = teamData['name']

        self.physics.restoreState(data['physics'])
        self.clock.restoreState(data['clock'])
        self.scoreboard.restoreState(data['scoreboard'])
        self.uiOptions.restoreState(data['uiOptions'])
        self.abilities.restoreState(data['abilities'])

        mapSpec = data['worldMap']
        keys = MapLayout.unknownBlockKeys(self.layoutDatabase, mapSpec)
        if keys:
            # We don't know all of the map blocks, so there is no point
            # proceeding.
            self.isIncomplete = True
            self.onReset()
            raise UnknownMapLayouts(keys)

        layout = MapLayout.fromDumpedState(self.layoutDatabase, mapSpec)
        self.setLayout(layout)

        self.setGameMode(data['mode'])
        self.setGameSpeed(data['speed'])

        for zoneData in data['zones']:
            self.getZone(zoneData['id']).setOwnership(
                self.teamWithId[zoneData['teamId']], zoneData['dark'])

        for playerData in data['players']:
            playerId = playerData['id']
            team = self.teamWithId[playerData['teamId']]
            nick = playerData['nick']

            if playerId in self.playerWithId:
                player = self.playerWithId[playerId]
            else:
                player = Player(self, nick, team, playerId)
                self.addPlayer(player)

            player.restore(playerData)

        self.trosballManager.restoreState(data['trosball'])

        for upgradeData in data['upgrades']:
            for upgradeClass in allUpgrades:
                if upgradeClass.upgradeType == upgradeData['type']:
                    upgradeClass.requiredCoins = upgradeData['cost']
                    upgradeClass.totalTimeLimit = upgradeData['time']
                    upgradeClass.enabled = upgradeData['enabled']

        self.playerWithElephant = self.getPlayer(data['elephant'])

        self.shotWithId = {}
        for shotData in data['shots']:
            shot = Shot(
                self, shotData['id'], self.getTeam(shotData['team']),
                self.getPlayer(shotData['shooter']), tuple(shotData['pos']),
                tuple(shotData['vel']), shotData['kind'], shotData['time'])
            self.shotWithId[shot.id] = shot

        self.deadCoins = set()
        self.collectableCoins = {}
        for coinData in data['coins']:
            coin = CollectableCoin(
                self, coinData['id'], tuple(coinData['pos']),
                coinData['xVel'], coinData['yVel'],
            )
            coin.creationTick = self.getMonotonicTick() - coinData[
                'createdAgo']
            self.collectableCoins[coin.id] = coin

        self.grenades = set()
        for grenadeData in data['grenades']:
            grenade = GrenadeShot(
                self, self.getPlayer(grenadeData['player']),
                grenadeData['timeLeft'])
            grenade.pos = grenadeData['pos']
            grenade.xVel = grenadeData['xVel']
            grenade.yVel = grenadeData['yVel']
            self.addGrenade(grenade)

        self.isIncomplete = False
        self.onReset()

    def isOnceOnly(self):
        return self._onceOnly

    def elephantKill(self, killer):
        pass

    def playerHasNoticedDeath(self, player, killer):
        pass

    def playerHasDied(self, player, killer, deathType):
        pass

    def stop(self):
        self.scoreboard.stop()
        self.scoreboard = None

    def callLater(self, _delay, _fn, *args, **kwargs):
        '''
        Schedules the given function to be called at the given game time.
        '''
        now = self.getMonotonicTime()
        result = DelayedCall(_fn, args, kwargs)
        heapq.heappush(self.delayedCalls, (now + _delay, result))
        return result

    def sleep(self, delay):
        '''
        Returns a Deferred that fires after the given number of game seconds.
        '''
        d = defer.Deferred()
        self.callLater(delay, d.callback, None)
        return d


class ServerUniverse(Universe):
    '''
    A universe that contains a few extra functions that are only needed
    server-side.
    '''

    isServer = True

    def __init__(self, game, *args, **kwargs):
        self.onUnitsAllAdvanced = Event([])
        self.onSwitchStats = Event(['enabled'])
        self.onStartMatch = Event([])
        self.onEndMatch = Event([])
        self.onActiveAchievementCategoriesChanged = Event([])
        self.onZoneCaptureFinalised = Event(['captureInfo'])

        level = kwargs.pop('level', None)
        gameType = kwargs.pop('gameType', None) or 'normal'
        super(ServerUniverse, self).__init__(*args, **kwargs)

        self.botManager = None
        self.voteArbiter = VoteArbiter(self)
        self.game = game
        self.idManager = IdManager(self)
        self._lastTickId = 0
        self.nextGameType = gameType
        self.paused = False
        self.level = None
        self._nextTick = None
        self._expectedTickTime = None
        self.stillLoadingCentralPathFinding = False
        self.regions = []
        self.activeAchievementCategories = set()

        if __debug__ and globaldebug.enabled:
            globaldebug.serverUniverse = self

        if level is None:
            level = LobbyLevel()
        self._startClock()
        self.startLevel(level)      # inlineCallbacks

    def activateStats(self):
        self.onSwitchStats(enabled=True)

    def deactivateStats(self):
        self.onSwitchStats(enabled=False)

    def setActiveAchievementCategories(self, categories):
        self.activeAchievementCategories = categories
        self.onActiveAchievementCategoriesChanged()

    @defer.inlineCallbacks
    def startLevel(self, level):
        self.onEndMatch()
        self.deactivateStats()

        self.regions = []
        if self.level is not None:
            oldLevel = self.level
            self.level.tearDownLevel()
            self.level = None

        self.scoreboard.stop()
        self.scoreboard = ScoreBoard(self)
        self.abilities.reset()
        self.uiOptions.reset()
        self.trosballManager.disable()
        self.clock = Clock(self)
        self.activeAchievementCategories = set()
        for team in self.teams:
            team.resetScore()

        # Remove any bots still in the game
        for agent in list(self.game.agents):
            if agent.player and agent.player.bot:
                log.warning('%s did not remove bot %s', oldLevel, agent)
                agent.stop()
                self.game.detachAgent(agent)

        self.level = level
        self.level.world = self
        if level.resetPlayerCoins:
            for p in self.players:
                p.coins = 0
        self.level.setupMap()


        # startLevel() is called from __init__, which is called during the
        # __init__ of a LocalGame object, so self.game is not fully
        # initialised yet. This is ok for setupMap(), but level.start()
        # needs to be able to access the game.
        reactor.callLater(0, self.level.start)

        yield self.syncEverything()

        # By not yielding, we start the loading process and it continues on
        # its own
        self.loadPathFindingData()

        self.onStartMatch()

    def stopCurrentLevel(self):
        '''
        Stops all triggers of the current level and returns to the lobby,
        or lobby equivalent (single player games do not have a lobby).
        '''
        if self.botManager is not None:
            self.botManager.stop()
            self.botManager = None
        self.onEndMatch()

        for player in self.players:
            if not player.bot:
                self.sendServerCommand(PlayerIsReadyMsg(player.id, False))
        return self.startLevel(LobbyLevel())    # inlineCallbacks

    def addRegion(self, region):
        self.regions.append(region)

    def removeRegion(self, region):
        self.regions.remove(region)

    def pauseOrResumeGame(self):
        self.paused = not self.paused

    def magicallyMovePlayer(self, player, pos, alive=None):
        '''
        Moves the given player to the given position. If alive is given,
        it should be a boolean indicating whether the player should become
        alive, or dead.
        '''
        if alive:
            if player.dead:
                player.returnToLife()
        elif alive is not None:
            if not player.dead:
                player.killOutright(CUSTOM_DEATH, resync=False)
        player.setPos(pos, 'f')
        player.sendResync(reason='')

    @defer.inlineCallbacks
    def loadPathFindingData(self):
        from trosnoth.bots.pathfinding import RunTimePathFinder

        if self.map.layout.pathFinder:
            # Map has not changed since last load of data
            return

        self.stillLoadingCentralPathFinding = True
        pf = self.map.layout.pathFinder = RunTimePathFinder(self.map.layout)
        try:
            yield self.map.layout.pathFinder.waitForCentralData()
        except:
            log.exception('Error loading pathfinding data')

        # Guard against two quick world resets
        if pf is self.map.layout.pathFinder:
            self.stillLoadingCentralPathFinding = False

    def sendServerCommand(self, msg):
        if not hasattr(self.game, 'world'):
            # This only happens in very initial game/world construction,
            # before any agents have had the chance to connect
            return

        self.game.sendServerCommand(msg)

    def advanceEverything(self):
        super(ServerUniverse, self).advanceEverything()

        self.checkShotCollisions()
        self.updateCollectableCoins()
        self.onUnitsAllAdvanced()
        self.bootTardyPlayers()

    def bootTardyPlayers(self):
        for player in list(self.players):
            if (
                    player.resyncing and
                    self.getMonotonicTick() > player.resyncExpiry):
                log.warning('%s took too long to resync', player)
                if player.agent:
                    player.agent.messageToAgent(ChatFromServerMsg(
                        error=True, text='You have been removed from the game '
                        'because your connection is too slow!'))
                self.sendServerCommand(RemovePlayerMsg(player.id))

    def checkShotCollisions(self, resolution=200):
        '''
        Performs collision checks of all shots with all nearby players.
        '''
        buckets = defaultdict(list)
        for player in self.players:
            if player.dead:
                continue
            x, y = player.pos
            xBucket, yBucket = x // resolution, y // resolution
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    buckets[xBucket + dx, yBucket + dy].append(player)

        for shot in list(self.shots):
            x, y = shot.pos
            xBucket, yBucket = x // resolution, y // resolution
            hitPlayers = [
                p for p in buckets[xBucket, yBucket]
                if shot.checkCollision(p)]
            if hitPlayers:
                # If multiple players are hit in the same tick, the server
                # randomly selects one to die.
                self.sendServerCommand(
                    ShotHitPlayerMsg(random.choice(hitPlayers).id, shot.id))

    def updateCollectableCoins(self):
        try:
            for coin in self.collectableCoins.values():
                endTick = coin.creationTick + (
                        COLLECTABLE_COIN_LIFETIME // TICK_PERIOD)
                if self.getMonotonicTick() >= endTick:
                    coin.removeDueToTime()

            for unit in list(self.deadCoins):
                unit.beat()
                if not unit.history:
                    self.deadCoins.remove(unit)
                    self.onCollectableCoinRemoved(unit.id)
        except:
            log.error('Error updating collectable coins', exc_info=True)

    def returnElephantToOwner(self):
        for p in self.players:
            if p.isElephantOwner():
                self.sendServerCommand(PlayerHasElephantMsg(p.id))
                return
        self.sendServerCommand(PlayerHasElephantMsg(NO_PLAYER))

    def elephantKill(self, killer):
        if not killer.dead:
            self.sendServerCommand(PlayerHasElephantMsg(killer.id))
        else:
            self.returnElephantToOwner()

    def playerHasNoticedDeath(self, player, killer):
        if killer:
            self.sendServerCommand(
                AwardPlayerCoinMsg(killer.id, COINS_PER_KILL))

    def playerHasDied(self, player, killer, deathType):
        if deathType != BOMBER_DEATH:
            self.dropPlayerCoinsDueToDeath(player)

    def dropPlayerCoinsDueToDeath(self, player):
        x, y = player.pos
        oldVel = player.getCurrentVelocity()
        coinsToKeep = player.coins
        for coinValue in player.getCoinsToDropOnDeath():
            coinsToKeep -= coinValue

            coinId = self.idManager.newCoinId()
            if coinId is None:
                continue

            xVel = 0.7 * oldVel[0] + random.random() * 200 - 100
            yVel = 0.7 * oldVel[1] + random.random() * 200 - 100
            self.sendServerCommand(CreateCollectableCoinMsg(
                coinId, x, y, xVel, yVel, coinValue))

        self.sendServerCommand(SetPlayerCoinsMsg(player.id, coinsToKeep))

    @defer.inlineCallbacks
    def _startGame(
            self, duration=None,
            delay=DEFAULT_GAME_COUNTDOWN, botManager=None, level=None):
        if self.botManager is not None:
            self.botManager.stop()
        self.botManager = botManager
        if level is None:
            if self.loadedMap:
                level = StandardLoadedLevel(self.loadedMap)
                self.loadedMap = None
            else:
                level = StandardRandomLevel()
        yield self.startLevel(level)

        if self.botManager:
            self.botManager.startingSoon()

    def delPlayer(self, player):
        if self.botManager:
            self.botManager.removingPlayer(player)
        super(ServerUniverse, self).delPlayer(player)

    @defer.inlineCallbacks
    def syncEverything(self):
        yield self.game.waitForEmptyCommandQueue()
        for player in self.players:
            player.resyncBegun()
        self.sendServerCommand(WorldResetMsg(repr(self.dumpEverything())))

    def requestTickNow(self):
        '''
        If this game is currently being viewed by the UI, and the UI needs
        another tick to prevent it from freezing, it will call this method.
        '''
        if self.level is None:
            # Tearing down or still setting up
            return

        if self._nextTick is not None:
            self._nextTick.cancel()
        self.tick()

    def tick(self):
        self._nextTick = None

        # Do our best to correct for any inaccuracies in call time, up to a
        # limit of one tick discrepancy.
        period = TICK_PERIOD
        if __debug__ and globaldebug.enabled:
            period = TICK_PERIOD * globaldebug.slowMotionFactor
        now = reactor.seconds()
        if self._expectedTickTime is None:
            delay = period
        else:
            delay = max(0, self._expectedTickTime + period - now)
        self._expectedTickTime = now + delay
        self._nextTick = WeakCallLater(delay, self, 'tick')

        if self.stillLoadingCentralPathFinding:
            loading = any(p.bot and p.team is not None for p in self.players)
        else:
            loading = False
        if loading != self.loading:
            self.sendServerCommand(WorldLoadingMsg(loading))

        if loading or len(self.players) == 0 or self.paused:
            return

        tickId = self._lastTickId = (self._lastTickId + 1) % TICK_LIMIT
        self.game.sendServerCommand(TickMsg(tickId))
        self.onServerTickComplete()

    def _startClock(self):
        if self._nextTick is not None:
            self._nextTick.cancel()
        delay = TICK_PERIOD
        if __debug__ and globaldebug.enabled:
            delay = TICK_PERIOD * globaldebug.slowMotionFactor
        self._nextTick = WeakCallLater(delay, self, 'tick')

    def _stopClock(self):
        if self._nextTick is not None:
            self._nextTick.cancel()
            self._nextTick = None

    def stop(self):
        super(ServerUniverse, self).stop()
        if self.level is not None:
            self.level.tearDownLevel()
            self.level = None

        self._stopClock()

    @TickMsg.handler
    def tickReceived(self, msg):
        super(ServerUniverse, self).tickReceived(msg)

        for region in self.regions:
            region.tick()


class Region(object):
    '''
    Base class for regions for use as event triggers. Regions must be
    registered with the ServerUniverse to have effect.
    '''
    def __init__(self, world):
        self.world = world
        self.players = set()
        self.onEnter = Event(['player'])
        self.onExit = Event(['player'])

    def debug_draw(self, viewManager, screen):
        pass

    def tick(self):
        players = set(p for p in self.world.players if self.check(p))
        for p in players - self.players:
            self.onEnter(p)
        for p in self.players - players:
            self.onExit(p)
        self.players = players

    def check(self, player):
        raise NotImplementedError('{}.check', self.__class__.__name__)


class RectRegion(Region):
    def __init__(self, world, rect, zoneDef=None):
        super(RectRegion, self).__init__(world)
        self.rect = pygame.Rect(rect)
        if zoneDef is not None:
            self.rect.left += zoneDef.pos[0]
            self.rect.top += zoneDef.pos[1]

    def check(self, player):
        return self.rect.collidepoint(player.pos)

    def debug_draw(self, viewManager, screen):
        from trosnoth.trosnothgui.ingame.utils import mapPosToScreen

        import pygame.draw

        focus = viewManager._focus
        area = viewManager.sRect

        topleft = mapPosToScreen(self.rect.topleft, focus, area)
        bottomright = mapPosToScreen(self.rect.bottomright, focus, area)
        size = (bottomright[0] - topleft[0], bottomright[1] - topleft[1])

        s = pygame.Surface(size)
        s.set_alpha(128)
        s.fill((0, 255, 255))
        screen.blit(s, topleft)

        # pygame.draw.rect(screen, (255, 0, 0, 0.5), pygame.Rect(topleft, size))


class PlayerProximityRegion(Region):
    def __init__(self, world, player, dist):
        super(PlayerProximityRegion, self).__init__(world)
        self.player = player
        self.distance = dist

    def check(self, player):
        d = distance(player.pos, self.player.pos)
        return d <= self.distance


class ZoneRegion(Region):
    def __init__(self, zone):
        super(ZoneRegion, self).__init__(zone.world)
        self.zone = zone

    def check(self, player):
        return player in self.zone.players
