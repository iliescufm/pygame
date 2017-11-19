'''
This is the main entrypoint for accessing Trosnoth bots.
'''

import logging
import random
from math import atan2, pi
import os

from twisted.internet import defer

import trosnoth.bots
from trosnoth.bots.orders import (
    StandStill, MoveGhostToPoint, MoveToOrb, RespawnInZone, FollowPlayer,
    MoveToPoint, CollectTrosball,
)
from trosnoth.bots.pathfinding import (
    PathFindingAction, actionKindClasses, FallDown,
    ORB, SingleAction)
from trosnoth.const import (
    GAME_FULL_REASON, UNAUTHORISED_REASON, NICK_USED_REASON,
    USER_IN_GAME_REASON, ALREADY_JOINED_REASON, TICK_PERIOD,
)
from trosnoth.messages import ResyncPlayerMsg
from trosnoth.messages import (
    ShootMsg, TickMsg,
    CannotJoinMsg, UpdatePlayerStateMsg,
    AimPlayerAtMsg, BuyUpgradeMsg,
)
from trosnoth.model.agent import ConcreteAgent
from trosnoth.model.universe_base import NEUTRAL_TEAM_ID
from trosnoth.model.upgrades import Bomber
from trosnoth.utils import globaldebug
from trosnoth.utils.event import Event
from trosnoth.utils.math import distance
from trosnoth.utils.message import MessageConsumer
from trosnoth.utils.twist import WeakLoopingCall

log = logging.getLogger('ai')
log.setLevel(logging.ERROR)

LOOK_AHEAD_TICKS = 20
MIN_EVASION_TICKS = 5

EASY_BOTS = True
PAUSE_BETWEEN_ACTIONS = 5


if not EASY_BOTS:
    PAUSE_BETWEEN_ACTIONS = 0


class InconsistencyDetected(Exception):
    pass


def listAIs(playableOnly=False):
    '''
    Returns a list of strings of the available AI classes.
    '''
    results = []
    try:
        files = os.listdir(os.path.dirname(trosnoth.bots.__file__))
    except OSError:
        # Probably frozen in a zip. Use a standard list.
        aiNames = ['alpha', 'simple', 'john', 'test']
    else:
        aiNames = [os.path.splitext(f)[0] for f in files if f.endswith('.py')]

    for aiName in aiNames:
        try:
            c = __import__(
                'trosnoth.bots.%s' % (aiName,), fromlist=['BotClass'])
        except Exception as e:
            log.warning('Error loading AI %r: %s', aiName, e)
            continue
        if hasattr(c, 'BotClass') and (
                c.BotClass.playable or not playableOnly):
            results.append(aiName)
    return results


def makeAIAgent(game, aiName, fromLevel=False, nick=None):
    c = __import__('trosnoth.bots.%s' % (aiName,), fromlist=['BotClass'])
    return AIAgent(game, c.BotClass, fromLevel=fromLevel, nick=nick)


class AIAgent(ConcreteAgent):
    '''
    Base class for an AI agent.
    '''

    def __init__(self, game, aiClass, fromLevel, nick=None, *args, **kwargs):
        super(AIAgent, self).__init__(game=game, *args, **kwargs)
        self.aiClass = aiClass
        self.fromLevel = fromLevel
        self._initialisationNick = nick
        self.ai = None
        self.team = None
        self.requestedNick = None
        self._onBotSet = Event()
        self._loop = WeakLoopingCall(self, '_tick')

    def start(self, team=None):
        self.team = team
        self._loop.start(2)

    def stop(self):
        super(AIAgent, self).stop()
        self._loop.stop()
        if self.ai:
            self.ai.disable()
            self.ai = None

    def _tick(self):
        if self.ai is not None:
            return

        if self.fromLevel and self._initialisationNick:
            nick = self._initialisationNick
        else:
            nick = self.aiClass.nick

        if self.team is None:
            teamId = NEUTRAL_TEAM_ID
        else:
            teamId = self.team.id

        self._joinGame(nick, teamId)

    def _joinGame(self, nick, teamId):
        self.requestedNick = nick
        self.sendJoinRequest(teamId, nick, bot=True, fromLevel=self.fromLevel)

    @CannotJoinMsg.handler
    def _joinFailed(self, msg):
        r = msg.reasonId
        nick = self.requestedNick

        if r == GAME_FULL_REASON:
            message = 'full'
        elif r == UNAUTHORISED_REASON:
            message = 'not authenticated'
        elif r == NICK_USED_REASON:
            message = 'nick in use'
        elif r == USER_IN_GAME_REASON:
            message = 'user already in game'    # Should never happen
        elif r == ALREADY_JOINED_REASON:
            message = 'tried to join twice'     # Should never happen
        else:
            message = repr(r)

        log.error('Join failed for AI %r (%s)', nick, message)
        self.stop()

    def setPlayer(self, player):
        if player is None and self.ai:
            self.ai.disable()
            self.ai = None

        super(AIAgent, self).setPlayer(player)

        if player:
            self.requestedNick = None
            self.ai = self.aiClass(self.world, self.localState.player, self)

            self._onBotSet(self.ai)
            self._onBotSet.clear()

    def getBot(self):
        '''
        @return: a Deferred which fires with this agent's Bot object,
            as soon as it has one.
        '''
        d = defer.Deferred()
        if self.ai is not None:
            d.callback(self.ai)
        else:
            self._onBotSet.addListener(d.callback, weak=False)
        return d

    @TickMsg.handler
    def handle_TickMsg(self, msg):
        super(AIAgent, self).handle_TickMsg(msg)
        if self.ai:
            self.ai.consumeMsg(msg)

    @ResyncPlayerMsg.handler
    def handle_ResyncPlayerMsg(self, msg):
        super(AIAgent, self).handle_ResyncPlayerMsg(msg)
        if self.ai:
            self.ai.playerResynced()

    def defaultHandler(self, msg):
        super(AIAgent, self).defaultHandler(msg)
        if self.ai:
            self.ai.consumeMsg(msg)


class Bot(MessageConsumer):
    '''
    Base class for Trosnoth bots, provides functionality for basic orders like
    moving to points or zones, attacking enemies, and using upgrades.
    '''
    playable = False    # Change to True in playable subclasses
    pauseBetweenActions = PAUSE_BETWEEN_ACTIONS
    detectStuck = True
    STUCK_CHECK_INTERVAL = 1    # seconds

    def __init__(self, world, player, agent, *args, **kwargs):
        super(Bot, self).__init__(*args, **kwargs)
        self.world = world
        self.player = player
        self.agent = agent

        self.future = BotFuture(self)
        self.inconsistent = False
        self.currentOrder = StandStill(self)
        self.aggression = True
        self.dodgesBullets = True
        if EASY_BOTS:
            self.dodgesBullets = False
        self.upgradeChoice = None
        self.upgradeCoinBuffer = 0
        self.upgradeDelay = 0
        self.upgradeAlreadyWaited = 0
        self.stuckCall = None
        self.lastStuckCheckInfo = {}

        self.start()

    def sendRequest(self, msg):
        self.agent.sendRequest(msg)

    def applyStateChanges(self, changes):
        '''
        Sends messages to adjust this player's key state according to the
        given state changes. This is a utility method designed to be used by
        the bot movement system. Calling it directly from bot subclasses may
        interfere with bot motion and pathfinding.
        '''
        for key, value in changes:
            self.sendRequest(UpdatePlayerStateMsg(
                value, stateKey=key, tickId=self.world.lastTickId))

    def releaseMovementKeys(self):
        '''
        Updates the player's key state so that it is not pressing any of the
        keys. This method should not be called directly by subclasses. It
        should only be called by the bot movement system, otherwise it may
        interfere with other bot motion. To order the bot to stand still,
        use standStill() instead.
        '''
        changes = PathFindingAction.buildStateChanges(self.player, {})
        self.applyStateChanges(changes)

    def start(self):
        self.player.onDied.addListener(self._playerDied)
        self.player.onRespawned.addListener(self._playerRespawned)
        if not self.stuckCall:
            self.stuckCall = self.world.callLater(
                self.STUCK_CHECK_INTERVAL, self.doStuckCheck)
        if __debug__ and globaldebug.enabled and globaldebug.showPathFinding:
            self.agent.player.onOverlayDebugHook.addListener(
                self.showPathFinding)

    def disable(self):
        self.player.onDied.removeListener(self._playerDied)
        self.player.onRespawned.removeListener(self._playerRespawned)
        if self.stuckCall:
            self.stuckCall.cancel()
            self.stuckCall = None
        if __debug__ and globaldebug.enabled and globaldebug.showPathFinding:
            self.agent.player.onOverlayDebugHook.removeListener(
                self.showPathFinding)

    def doStuckCheck(self):
        if self.agent.stopped:
            log.error(
                'Bot loop running after stop: %r / %r', self, self.agent)
            self.stuckCall = None
            return

        self.stuckCall = self.world.callLater(
            self.STUCK_CHECK_INTERVAL, self.doStuckCheck)
        info = self.lastStuckCheckInfo
        if not self.detectStuck or self.player.dead or isinstance(
                self.currentOrder, StandStill):
            info['released'] = info['pos'] = info['yVel'] = None
            return
        if (
                info.get('pos') == self.player.pos
                and info.get('yVel') == self.player.yVel):
            if not info.get('released'):
                self.releaseMovementKeys()
                info['released'] = True
            elif not self.player.items.has(Bomber):
                self.sendRequest(
                    BuyUpgradeMsg(Bomber.upgradeType, self.world.lastTickId))
        else:
            info['released'] = False
            info['pos'] = self.player.pos
            info['yVel'] = self.player.yVel

    def showPathFinding(self, viewManager, screen, sprite):
        '''
        For debugging, displays the player's predicted path.
        '''
        import pygame.draw
        from trosnoth.trosnothgui.ingame.utils import mapPosToScreen

        if self.player.dead:
            return

        focus = viewManager._focus
        area = viewManager.sRect

        lastPos = mapPosToScreen(sprite.pos, focus, area)
        colour = (64, 255, 255)
        for record in self.future.actionRecords:
            for pos in record.simulator.positions:
                screenPos = mapPosToScreen(pos, focus, area)
                pygame.draw.circle(screen, colour, screenPos, 3)
                pygame.draw.line(screen, colour, lastPos, screenPos)
                lastPos = screenPos

    def defaultHandler(self, msg):
        pass

    def orderFinished(self):
        '''
        Called by an order when it is complete or cannot continue further. May
        be overridden by subclasses.
        '''
        self.standStill()

    #
    # ==== Order interface ====
    #

    def setOrder(self, order):
        '''
        Starts the given order. Generally, bots should use the methods below in
        preference to this one.
        '''
        self.currentOrder = order
        order.start()

    def standStill(self):
        '''
        Orders the bot to stop moving. If it's in the air, it will complete its
        current jump / fall motion.
        '''
        self.setOrder(StandStill(self))

    def moveToPoint(self, pos):
        '''
        Orders the bot to move as close as possible to the given point.
        '''
        if self.player.dead:
            self.setOrder(MoveGhostToPoint(self, pos))
        else:
            self.setOrder(MoveToPoint(self, pos))

    def moveToZone(self, zone):
        '''
        Orders the bot to move into the given zone.
        '''
        if self.player.dead:
            self.setOrder(MoveGhostToPoint(
                self, zone.defn.pos, stopOnZoneEntry=zone))
        else:
            self.setOrder(MoveToOrb(self, zone, stopOnEntry=True))

    def moveToOrb(self, zone):
        '''
        Orders the bot to touch the orb of the given zone.
        '''
        if self.player.dead:
            self.setOrder(MoveGhostToPoint(self, zone.defn.pos))
        else:
            self.setOrder(MoveToOrb(self, zone))

    def attackPlayer(self, player):
        '''
        Orders the bot to hunt down and kill the given player.
        '''
        if self.player.dead:
            raise RuntimeError('ghosts cannot attack')

        self.setOrder(FollowPlayer(self, player, attack=True))

    def followPlayer(self, player):
        '''
        Orders the bot to get as close as possible to the given player and stay
        there until either the player dies, or another order is given.
        '''
        if self.player.dead:
            raise RuntimeError('ghosts cannot follow players')

        self.setOrder(FollowPlayer(self, player))

    def collectTrosball(self):
        '''
        Orders the bot to move towards the trosball.
        '''
        if self.player.dead:
            raise RuntimeError('ghosts cannot collect Trosball')

        self.setOrder(CollectTrosball(self))

    def respawn(self, zone=None):
        '''
        Orders the bot to respawn, with an optional zone to move to first.
        '''
        if not self.player.dead:
            raise RuntimeError('living player cannot respawn')

        if zone is None:
            zone = self.player.getZone()
            if zone is None:
                raise RuntimeError('player is currently outside all zones')

        self.setOrder(RespawnInZone(self, zone))

    def setAggression(self, aggression):
        '''
        Determines whether the bot will, while carrying out its other orders,
        shoot at any enemies it sees.
        '''
        self.aggression = aggression

    def setDodgesBullets(self, dodgesBullets):
        '''
        Determines whether the bot will attempt to avoid enemy bullets
        @param dodgesBullets: Boolean
        '''
        self.dodgesBullets = dodgesBullets

    def setUpgradePolicy(self, upgrade, coinBuffer=0, delay=0):
        '''
        Tells this bot how to approach purchasing upgrades. This setting
        persists until it is changed with another call to this function.

        upgrade: which upgrade to purchase, or None to disable buying
        coinBuffer: how many surplus coins should there be before purchasing
        delay: how long should the bot wait after there are enough coins
        '''
        self.upgradeChoice = upgrade
        self.upgradeCoinBuffer = coinBuffer
        self.upgradeDelay = delay
        self.upgradeAlreadyWaited = 0

    #
    # ==== End order interface ====
    #

    def _playerDied(self, killer, deathType):
        self.future.playerDied()
        self.sendRequest(AimPlayerAtMsg(0, 0, self.world.lastTickId))
        self.currentOrder.playerDied()

    def _playerRespawned(self):
        self.future.clear(afterLanding=False)
        self.currentOrder.playerRespawned()

    def playerResynced(self):
        '''
        Called when the current player's position jumps due to a resync
        message.
        '''
        self.future.clear(afterLanding=False)
        self.currentOrder.restart()
        self.handle_TickMsg(None)

    @TickMsg.handler
    def handle_TickMsg(self, msg):
        if self.world.loading:
            return
        if self.inconsistent:
            self.inconsistent = False
            self.future.clear(afterLanding=False)
            self.currentOrder.restart()

        if self.future.evasiveActionKind is None:
            self.currentOrder.tick()

        if not self.player.dead:
            if self.aggression:
                self._shootAtEnemyIfPossible()

            if self.upgradeChoice:
                self._makeUpgradeDecision()

            try:
                self.future.step()
            except InconsistencyDetected:
                self.inconsistent = True

    def _shootAtEnemyIfPossible(self):
        for p in self.world.players:
            if self.player.isFriendsWith(p):
                continue
            if self.canHitPlayer(p):
                self.fireShotAtPoint(p.pos)

    def canHitPlayer(self, target):
        physics = self.world.physics
        gunRange = physics.shotLifetime * physics.shotSpeed

        if target.dead or target.invisible or target.turret:
            return False

        if distance(self.player.pos, target.pos) < gunRange:
            # Check if we can shoot without hitting obstacles
            shot = self.player.createShot()
            deltaX = target.pos[0] - self.player.pos[0]
            deltaY = target.pos[1] - self.player.pos[1]
            obstacle, dX, dY = physics.trimPathToObstacle(
                shot, deltaX, deltaY, ())
            if obstacle is None:
                return True

        return False

    def fireShotAtPoint(self, pos, error=0.15):
        thrust = 1.0
        x1, y1 = self.player.pos
        x2, y2 = pos
        angle = atan2(x2 - x1, -(y2 - y1))
        angle += error * (2 * random.random() - 1)
        self.sendRequest(AimPlayerAtMsg(angle, thrust, self.world.lastTickId))
        self.sendRequest(ShootMsg(self.world.lastTickId))

    def _makeUpgradeDecision(self):
        if self.player.items.has(Bomber):
            return

        coinThreshold = (
            self.upgradeChoice.requiredCoins + self.upgradeCoinBuffer)

        if self.player.coins >= coinThreshold:
            if self.upgradeAlreadyWaited >= self.upgradeDelay:
                self._purchaseUpgradeNow()
            else:
                self.upgradeAlreadyWaited += TICK_PERIOD
        else:
            self.upgradeAlreadyWaited = 0

    def _purchaseUpgradeNow(self):
        self.upgradeAlreadyWaited = 0
        self.sendRequest(BuyUpgradeMsg(
            self.upgradeChoice.upgradeType, self.world.lastTickId))


class FutureActionSimulator(object):
    def __init__(self, initialPlayer, actionKinds):
        self.player = initialPlayer.clone()
        self.player.nick = 'Simulation'
        self.positions = [self.player.pos]
        self.actionKinds = actionKinds
        self.actions = None
        self.popCount = 0

    def getNextPosition(self):
        if self.actions is None:
            self.actions = [actionKind() for actionKind in self.actionKinds]

        while self.actions:
            done, changes, faceRight = self.actions[0].prepNextStep(
                self.player)
            if done:
                self.actions.pop(0)
                continue

            for key, value in changes:
                self.player.updateState(key, value)
            if faceRight and not self.player.isFacingRight():
                self.player.lookAt(pi / 2)
            elif (not faceRight) and self.player.isFacingRight():
                self.player.lookAt(-pi / 2)

            self.player.reset()
            self.player.advance()
            if len(self.positions) >= 2:
                if (self.player.pos == self.positions[-1]
                        == self.positions[-2]):
                    log.warning('infinite simulation!')
                    return None

            self.positions.append(self.player.pos)
            return self.positions[-1]

        return None

    def popPosition(self, expectedPosition):
        if not self.positions:
            log.warning('No positions left to pop!')
            return

        self.popCount += 1
        pos = self.positions.pop(0)
        if distance(pos, expectedPosition) >= 0.5:
            log.warning('Bot simulation did not match actual position!')
            log.warning('actual: %s   simulated: %s  (%s)',
                      expectedPosition, pos,
                      ', '.join(actionKind.__name__
                                for actionKind in self.actionKinds))

            raise InconsistencyDetected()

        if not self.positions:
            # Ensure we always have at least one position recorded
            self.getNextPosition()

    def finish(self):
        while self.getNextPosition() is not None:
            pass

    def placePlayerAtFinish(self, player):
        '''
        Runs the full simulation for the given player, leaving it at the
        position where this action completes.
        '''
        self.finish()

        if self.player.attachedObstacle is None:
            # A half action, included in database only for orb touches
            player.pos = self.player.pos
            player.setAttachedObstacle(None)
            player._jumpTime = self.player._jumpTime
            player.yVel = self.player.yVel
            player.angleFacing = self.player.angleFacing
            player._faceRight = self.player._faceRight
        else:
            player.placeAtNodeKey(
                self.player.getMapBlock().defn,
                self.player.getPathFindingNodeKey())


class FutureActionRecord(object):
    def __init__(
            self, player, pathFindingEdge, actionKinds=None, exitDir=None,
            mayStartInAir=False):
        self.actions = None
        self.stepsTaken = 0
        self.DEBUG_initialBlockDef = player.getMapBlock().defn
        self.DEBUG_initalPos = player.pos
        self.DEBUG_initialNodeKey = player.getPathFindingNodeKey()
        self.DEBUG_exit = exitDir
        self.DEBUG_inconsistent = False
        self.DEBUG_initialPlayer = player.clone()

        if pathFindingEdge is None:
            self.actionKinds = list(actionKinds)
            self.expectedDuration = None
            self.finalNodeKey = None
            self.finalBlockDef = None
        else:
            assert actionKinds is None, (
                'Do not provide actionKinds and pathFindingEdge')
            actions = pathFindingEdge['actions']
            self.actionKinds = [
                actionKindClasses.getByString(a) for a in actions]
            if exitDir == ORB:
                self.expectedDuration = None
            else:
                self.expectedDuration = pathFindingEdge['cost']
            self.finalNodeKey = pathFindingEdge['target']
            assert self.finalNodeKey is not None

            if 'targetMapBlock' in pathFindingEdge:
                self.finalBlockDef = pathFindingEdge['targetMapBlock']
            else:
                self.finalBlockDef = player.getMapBlock().defn

            if self.finalNodeKey == (None, None):
                # Set the flags to indicate we don't know where this will
                # end up without doing a simulation run.
                self.finalBlockDef = None
                self.finalNodeKey = None

        self.simulator = FutureActionSimulator(player, self.actionKinds)
        if player.yVel != 0 and not mayStartInAir:
            log.warning(
                'Nonzero yVel at start of simulation: %r, %r',
                player.yVel, self.actionKinds)

    def step(self, bot):
        '''
        Called after one frame of this action has completed.
        '''
        if self.actions is None:
            self.actions = [actionKind() for actionKind in self.actionKinds]

        self.simulator.popPosition(bot.player.pos)

        while self.actions:
            done, changes, faceRight = self.actions[0].prepNextStep(bot.player)

            if not done:
                break
            self.actions.pop(0)
        else:
            self.checkFinalNodeKey(bot.player, stepped=True)
            return True

        bot.applyStateChanges(changes)

        if faceRight and not bot.player.isFacingRight():
            bot.sendRequest(AimPlayerAtMsg(pi / 2, 1.0, bot.world.lastTickId))
        elif (not faceRight) and bot.player.isFacingRight():
            bot.sendRequest(AimPlayerAtMsg(-pi / 2, 1.0, bot.world.lastTickId))

        self.stepsTaken += 1

        return False

    def checkFinalNodeKey(self, player, stepped=False):
        if self.DEBUG_inconsistent:
            return False

        error = False
        if self.finalBlockDef is not None:
            if self.finalBlockDef != player.getMapBlock().defn:
                log.warning('Ended in unexpected map block!')
                log.warning('  expected: %r', self.finalBlockDef)
                actualBlockDef = player.getMapBlock().defn
                log.warning('  actual: %r', actualBlockDef)
                log.warning(
                    '    map: %r / %r',
                    os.path.basename(actualBlockDef.layout.filename),
                    actualBlockDef.layout.reversed)
                log.warning('  actual key: %r', player.getPathFindingNodeKey())
                log.warning('  actual pos: %r', player.pos)

                error = True
            elif self.finalNodeKey != player.getPathFindingNodeKey():
                log.warning('Ended at unexpected node key!')
                log.warning('  expected: %r', self.finalNodeKey)
                log.warning('  actual: %r', player.getPathFindingNodeKey())
                log.warning('  actual pos: %r', player.pos)
                error = True
        if stepped and not error and self.expectedDuration is not None:
            if self.expectedDuration != self.stepsTaken:
                log.warning(
                    'Expected duration: %r  actual: %r',
                    self.expectedDuration, self.stepsTaken)
                error = True
        if error:
            if stepped:
                log.warning('  (from stepping)')
            else:
                log.warning('  (from getPositions)')
            log.warning('  actions: %r', self.actions)
            log.warning('  stepsTaken: %r', self.stepsTaken)
            log.warning('  actionKinds: %r', self.actionKinds)
            log.warning('  expectedDuration: %r', self.expectedDuration)
            log.warning('  expected finalNodeKey: %r', self.finalNodeKey)
            log.warning('  expected finalBlockDef: %r', self.finalBlockDef)
            if self.finalBlockDef:
                log.warning(
                    '    map: %r / %r',
                    os.path.basename(self.finalBlockDef.layout.filename),
                    self.finalBlockDef.layout.reversed)
            log.warning('  initialBlockDef: %r', self.DEBUG_initialBlockDef)
            log.warning(
                '    map: %r / %r',
                os.path.basename(self.DEBUG_initialBlockDef.layout.filename),
                self.DEBUG_initialBlockDef.layout.reversed)
            log.warning('  initialPos: %r', self.DEBUG_initalPos)
            log.warning('  initialNodeKey: %r', self.DEBUG_initialNodeKey)
            log.warning('  exit: %r', self.DEBUG_exit)
            log.warning(
                '  initial player: %r', self.DEBUG_initialPlayer.dump())
            log.warning(
                '  initial _alreadyJumped: %r',
                self.DEBUG_initialPlayer._alreadyJumped)
            log.warning(
                '  initial _unstickyWall: %r',
                self.DEBUG_initialPlayer._unstickyWall)
            log.warning(
                '  initial _ignore: %r', self.DEBUG_initialPlayer._ignore)
            self.DEBUG_inconsistent = True
        return not error

    def placePlayer(self, player):
        if self.finalBlockDef is None:
            self.simulator.placePlayerAtFinish(player)
            if self.expectedDuration is None:
                self.expectedDuration = len(self.simulator.positions) - 1
        else:
            player.placeAtNodeKey(self.finalBlockDef, self.finalNodeKey)


class BotFuture(object):
    '''
    Keeps track of the future behaviour of this bot. Used by order classes
    to add actions, and by the bullet avoidance code to predict where the
    bot will be in the future in relation to bullets.
    '''

    def __init__(self, bot):
        self.bot = bot
        self.futurePlayer = bot.player.clone()
        self.futurePlayer.nick = 'Future'
        self.actionRecords = []
        self.evasiveActionKind = None
        self.bulletDetector = BulletDetector(self)
        self.ticksUntilClear = 0

    def clear(self, afterLanding=True):
        '''
        Clears all future movement of this bot, optionally after the bot
        lands its current jump/fall.
        '''
        if afterLanding and self.bot.player.attachedObstacle is None:
            if self.actionRecords:
                self.actionRecords[1:] = []
                self.actionRecords[0].placePlayer(self.futurePlayer)
                return

        self.actionRecords = []
        self.futurePlayer = self.bot.player.clone()
        self.futurePlayer.nick = 'Future'
        self.evasiveActionKind = None
        self.bulletDetector.reset()
        self.ticksUntilClear = 0

    def playerDied(self):
        self.evasiveActionKind = None

    def getPlayer(self):
        return self.futurePlayer

    def hasActions(self):
        return bool(self.actionRecords)

    def setEvasiveActionKind(self, actionKind):
        '''
        Tells this BotFuture that we're in bullet evasion mode, and until
        told otherwise, we should use the given actionKind to generate new
        actions.

        :param actionKind: the action kind, or None to return to normal mode
        '''
        hadValue = self.evasiveActionKind is not None
        self.evasiveActionKind = actionKind
        if actionKind is None and hadValue:
            self.clear()
            self.bot.currentOrder.restart()

    def insertWait(self, ticksInFuture, ticksToWait):
        '''
        Inserts a pause into the future action queue. Called by bullet
        evasion code.

        :param ticksInFuture: when to insert the pause. Must be between
            action records, and all prior action records must have been
            fully simulated.
        :param ticksToWait: length of time to wait
        '''
        if ticksInFuture == 0:
            i = -1
            player = self.bot.player
        else:
            i, record = self.getPreviousAction(ticksInFuture)
            player = record.simulator.player

        waitRecord = FutureActionRecord(
            player, None, [WaitFactory(ticksToWait)])
        self.actionRecords.insert(i + 1, waitRecord)
        self.bulletDetector.forgetAfter(ticksInFuture)

    def replaceActionRecords(self, ticksInFuture, records):
        '''
        Truncates the current action queue at the given number of ticks,
        and instead inserts the given action records.

        :param ticksInFuture: when to truncate the action records. Must be
            between action records, and all prior action records must have
            been fully simulated.
        :param records: the ActionRecord instances to insert instead
        '''
        if ticksInFuture == 0:
            i = -1
        else:
            i, record = self.getPreviousAction(ticksInFuture)

        self.actionRecords[i + 1:] = records
        self.bulletDetector.forgetAfter(ticksInFuture)

        finalRecord = self.actionRecords[-1]
        finalRecord.simulator.finish()
        finalRecord.placePlayer(self.futurePlayer)

    def getPreviousAction(self, ticksInFuture):
        '''
        Finds the index in the action records after which the given time
        occurs.

        :param ticksInFuture: the time to search for. Must coincide exactly
            with the end of an action record, and all prior action records
            must have been fully simulated.
        :return: (index, record) for the record just before that time
        '''
        tick = 0
        for i, record in enumerate(self.actionRecords):
            tick += len(record.simulator.positions) - 1

            if tick == ticksInFuture:
                break
            if tick > ticksInFuture:
                raise ValueError('ticksInFuture must lie between records')
        else:
            raise ValueError('ticksInFuture must not lie beyond last record')
        return i, record

    def step(self):
        '''
        Should be called as the final action in the bot's tick handling.
        Sets the bot's key strokes correctly to carry out the next step in
        this simulated future.
        '''
        if self.evasiveActionKind is not None:
            if self.ticksUntilClear == 0 and self.bot.player.attachedObstacle:
                self.setEvasiveActionKind(None)

        if self.bot.dodgesBullets:
            self.bulletDetector.tick()
            if self.bulletDetector.deathPredicted():
                self.ticksUntilClear = MIN_EVASION_TICKS
                self._avoidTheBullets()
            else:
                self.ticksUntilClear = max(0, self.ticksUntilClear - 1)

        while True:
            if not self.actionRecords:
                self._requestMoreFuture()
                if not self.actionRecords:
                    # There are no action records left
                    self.bot.releaseMovementKeys()
                    self.clear(afterLanding=False)
                    break

            done = self.actionRecords[0].step(self.bot)
            if not done:
                break

            self.actionRecords.pop(0)

    def _requestMoreFuture(self):
        '''
        Tries to figure out at least one more action for the action queue,
        either by asking the current order (if we're not dodging bullets),
        or by using the current evasion method.
        '''
        if self.evasiveActionKind is not None:
            self.addActionRecord(FutureActionRecord(
                self.futurePlayer, None, [self.evasiveActionKind],
                mayStartInAir=True))
        else:
            self.bot.currentOrder.requestMoreFuture()

    def getPositions(self, steps):
        '''
        Returns a list of predicted future positions of this bot, containing
        the given number of steps, by calculating more steps if possible.
        '''
        result = []
        record = None
        i = 0
        while len(result) < steps + 1:
            recordCount = len(self.actionRecords)
            if i >= recordCount:
                self._requestMoreFuture()
                if len(self.actionRecords) <= recordCount:
                    break
            record = self.actionRecords[i]

            positions = record.simulator.positions
            if result and positions[0] != result[-1]:
                previousRecord = self.actionRecords[i - 1]
                if not previousRecord.DEBUG_inconsistent:
                    previousRecord.checkFinalNodeKey(
                        previousRecord.simulator.player)
                    log.warning('Consecutive actions do not join!')
                    log.warning(
                        '  %s -> %s (%s -> %s)', result[-1], positions[0],
                        ', '.join(actionKind.__name__
                                  for actionKind in self.actionRecords[
                                      i - 1].actionKinds),
                        ', '.join(actionKind.__name__
                                  for actionKind in record.actionKinds),
                    )
            oldLen = len(result)
            posLen = len(positions)
            positions = positions[1:2 + steps - len(result)]
            result.extend(positions)

            while len(result) < steps + 1:
                pos = record.simulator.getNextPosition()
                if pos is None:
                    break
                result.append(pos)
            else:
                break
            i += 1

        # No more actions: simulate falling to the ground and staying there
        simulator = FutureActionSimulator(self.futurePlayer, [FallDown])
        while len(result) < steps + 1:
            pos = simulator.getNextPosition()
            if pos is None:
                break
            result.append(pos)
        while len(result) < steps + 1:
            result.append(self.futurePlayer.pos)

        return result

    def _checkEdgeMatchesCurrentLocation(self, edgeToCheck, exitDir):
        # Check that the given edge exists for this location
        pathFinder = self.bot.world.map.layout.pathFinder
        blockPaths = pathFinder.getBlockPaths(
            self.futurePlayer.getMapBlock().defn)
        if self.futurePlayer.attachedObstacle is None:
            log.warning('attachedObstacle should not be None here!')
            return
        nodeKey = blockPaths.buildNodeKey(self.futurePlayer)
        assert nodeKey
        node = blockPaths.getNodeFromKey(nodeKey)

        if exitDir:
            if node['targets'].get(exitDir) is not edgeToCheck:
                log.warning('trying to expand exit edge from wrong location')
            return

        for edge in node['edges']:
            if edge is edgeToCheck:
                return
        log.warning('trying to expand edge from wrong location!')

    def expandEdge(self, pathFindingEdge, exitDir):
        if __debug__:
            self._checkEdgeMatchesCurrentLocation(pathFindingEdge, exitDir)

        record = FutureActionRecord(
            self.futurePlayer, pathFindingEdge, exitDir=exitDir)
        self.addActionRecord(record)
        if self.bot.pauseBetweenActions:
            self.addActionRecord(FutureActionRecord(self.futurePlayer, None, [
                WaitFactory(random.randrange(self.bot.pauseBetweenActions))]))

    def land(self):
        record = FutureActionRecord(
            self.futurePlayer, None, [FallDown], mayStartInAir=True)
        self.addActionRecord(record)

    def addActionRecord(self, record):
        self.actionRecords.append(record)
        record.placePlayer(self.futurePlayer)

    def _avoidTheBullets(self):
        EvasiveManeuvers(self).start()


class WaitFactory(object):
    __name__ = 'Wait'

    def __init__(self, duration):
        self.duration = duration

    def __call__(self):
        return Wait(self.duration)


class Wait(SingleAction):
    def __init__(self, duration):
        super(Wait, self).__init__()
        self.duration = duration

    def prepNextStep(self, player):
        stateChanges = self.buildStateChanges(player, {})
        self.duration -= 1
        done = (self.duration <= 0)
        return done, stateChanges, player.isFacingRight()


class KeyPressActionFactory(object):
    def __init__(self, keys):
        self.__name__ = 'KeyPressAction({})'.format(keys)
        self.keys = keys

    def __call__(self):
        return KeyPressAction(self.keys)


class KeyPressAction(SingleAction):
    def __init__(self, keys, duration=2):
        super(KeyPressAction, self).__init__()
        self.keys = keys
        self.duration = duration
        if keys.get('left', False):
            self.faceRight = False
        elif keys.get('right', False):
            self.faceRight = True
        else:
            self.faceRight = None

    def prepNextStep(self, player):
        stateChanges = self.buildStateChanges(player, self.keys)
        self.duration -= 1
        done = (self.duration <= 0)
        faceRight = self.faceRight
        if faceRight is None:
            faceRight = player.isFacingRight()
        return done, stateChanges, faceRight


class EvasiveManeuvers(object):
    def __init__(self, botFuture):
        self.botFuture = botFuture

    def start(self):
        bestOption = self._getBestWaitOption()

        if bestOption is None or not bestOption.perfect:
            otherOption = self._selectRandomOption()
            bestOption = max(bestOption, otherOption)

        if bestOption is not None:
            bestOption.apply(self.botFuture)

    def _getBestWaitOption(self):
        if self.botFuture.evasiveActionKind is not None:
            # If we're already dodging, we can't guarantee action finish
            # points will be in the air, and we've already considered waiting.
            return None

        bestOption = None
        bestDuration = -1
        for tick, attached in self._possibleWaitPoints():
            if not attached:
                continue
            option = self._getBestWaitOptionAtTime(tick)
            if option.safeUntil > bestDuration:
                bestOption = option
                bestDuration = option.safeUntil
                if bestDuration == LOOK_AHEAD_TICKS:
                    break

        if bestDuration < self.botFuture.bulletDetector.ticksToLive:
            return None

        return bestOption

    def _possibleWaitPoints(self):
        '''
        Yields (point, isAttached) for points in this bot's predicted future
        before the bullet collision tick, where the bot could potentially
        do something.
        '''
        TICK_STEP = 2

        target = self.botFuture.bulletDetector.ticksToLive - TICK_STEP
        attached = self.botFuture.bot.player.attachedObstacle is not None
        actionStarts = [(0, attached)]
        i = 0
        for record in self.botFuture.actionRecords:
            i += len(record.simulator.positions) - 1
            if i > target:
                break
            if i == 0:
                continue
            attached = record.simulator.player.attachedObstacle is not None
            actionStarts.append((i, attached))

        while actionStarts:
            i, attached = actionStarts.pop()
            if i > target:
                continue

            yield i, attached

            target = i - TICK_STEP

    def _getBestWaitOptionAtTime(self, tick):
        '''
        Checks whether waiting at the given time will avoid hitting a bullet.

        :param tick: the time to wait as number of ticks in the future
        :return: an EvasiveOption which avoids bullets for the greatest time
        '''
        WAIT_STEP = 5

        futurePositions = self.botFuture.getPositions(LOOK_AHEAD_TICKS)[tick:]
        startPos = futurePositions[0]

        bestOption = None
        bestHitTick = -1
        waitLength = 0
        while tick + waitLength <= LOOK_AHEAD_TICKS:
            waitLength += WAIT_STEP
            hitTick = self.botFuture.bulletDetector.checkPath(
                [startPos] * (waitLength + 1), startTick=tick)
            if hitTick is not None:
                if hitTick > bestHitTick:
                    bestOption = WaitEvasiveOption(tick, waitLength, hitTick)
                break

            futurePositions[LOOK_AHEAD_TICKS - waitLength - tick + 1:] = []
            hitTick = self.botFuture.bulletDetector.checkPath(
                futurePositions, startTick=tick + waitLength)
            if hitTick is None:
                hitTick = LOOK_AHEAD_TICKS
            else:
                hitTick += waitLength
            if hitTick > bestHitTick:
                bestOption = WaitEvasiveOption(tick, waitLength, hitTick)
                bestHitTick = hitTick

        return bestOption

    def _selectRandomOption(self):
        '''
        Returns an evasive option which presses and holds a random choice of
        keys at a random point where the player is stationary.
        '''
        choices = list(self._possibleWaitPoints())
        if not choices:
            return None

        startTick, attached = random.choice(choices)
        keys = {}
        keys.update(random.choice(
            [{'jump': True}, {'down': True}, {}]))
        keys.update(random.choice(
            [{'left': True}, {'right': True}, {}]))

        result = KeyPressEvasiveOption(self.botFuture, startTick, keys)
        if result.safeUntil < self.botFuture.bulletDetector.ticksToLive:
            return None
        return result


class EvasiveOption(object):
    def __init__(self, safeUntil):
        self.safeUntil = safeUntil
        self.perfect = safeUntil >= LOOK_AHEAD_TICKS

    def __cmp__(self, other):
        '''
        Ensures that max(options) returns the best option, even if one of
        the options is None.
        '''
        if other is None:
            return 1
        if not isinstance(other, EvasiveOption):
            raise TypeError('cannot compare {} and {}'.format(
                self.__class__.__name__, other.__class__.__name__))
        return cmp(self.safeUntil, other.safeUntil)

    def apply(self, botFuture):
        raise NotImplementedError('{}.apply'.format(self.__class__.__name__))


class WaitEvasiveOption(EvasiveOption):
    def __init__(self, startTick, waitLength, safeUntil):
        super(WaitEvasiveOption, self).__init__(safeUntil)
        self.startTick = startTick
        self.waitLength = waitLength

    def apply(self, botFuture):
        botFuture.insertWait(self.startTick, self.waitLength)


class KeyPressEvasiveOption(EvasiveOption):
    def __init__(self, botFuture, startTick, keys):
        self.startTick = startTick
        self.actionFactory = KeyPressActionFactory(keys)
        safeUntil, newRecords = self._forecast(botFuture)
        self.newRecords = newRecords
        super(KeyPressEvasiveOption, self).__init__(safeUntil)

    def _forecast(self, botFuture):
        if self.startTick == 0:
            player = botFuture.bot.player
        else:
            i, existingRecord = botFuture.getPreviousAction(self.startTick)
            player = existingRecord.simulator.player

        tick = self.startTick
        newRecords = []
        positions = [player.pos]

        while tick < LOOK_AHEAD_TICKS:
            record = FutureActionRecord(
                player, None, [self.actionFactory], mayStartInAir=True)
            newRecords.append(record)
            record.simulator.finish()
            player = record.simulator.player
            positions.extend(record.simulator.positions[1:])
            tick += len(record.simulator.positions) - 1

        startPos = positions[0]
        hitTick = botFuture.bulletDetector.checkPath(
            positions, startTick=self.startTick)
        if hitTick is None:
            hitTick = LOOK_AHEAD_TICKS
        return hitTick, newRecords

    def apply(self, botFuture):
        botFuture.replaceActionRecords(self.startTick, self.newRecords)
        botFuture.setEvasiveActionKind(self.actionFactory)


class BulletDetector(object):
    def __init__(self, botFuture):
        self.botFuture = botFuture
        self.world = botFuture.bot.world
        self.player = player = botFuture.bot.player
        self.shotsChecked = set()
        self.ticksToLive = None
        self.ticksAhead = 0

    def tick(self):
        if self.ticksToLive is not None:
            self.ticksToLive -= 1
            serverDelay = self.player.agent.localState.serverDelay
            if self.ticksToLive < -serverDelay - 1:
                # We somehow survived
                self.reset()

        self.ticksAhead = max(0, self.ticksAhead - 1)

        for shot in list(self.shotsChecked):
            if shot.expired or shot not in self.world.shots:
                self.shotsChecked.remove(shot)

        if self.ticksToLive is not None:
            ticksToPredict = min(LOOK_AHEAD_TICKS, self.ticksToLive)
        else:
            ticksToPredict = LOOK_AHEAD_TICKS

        futurePositions = self.botFuture.getPositions(ticksToPredict)
        serverDelay = self.player.agent.localState.serverDelay

        newShots = {
            shot for shot in self.world.shots
            if shot not in self.shotsChecked and not shot.expired and
            not self.player.isFriendsWith(shot.originatingPlayer)
            }
        self._checkAgainst(futurePositions, newShots)

        newPositions = futurePositions[self.ticksAhead:]
        self._checkAgainst(
            newPositions, self.shotsChecked, startTick=self.ticksAhead)

        self.ticksAhead = len(futurePositions) - 1
        self.shotsChecked.update(newShots)

    def reset(self):
        self.ticksToLive = None
        self.shotsChecked = set()
        self.ticksAhead = 0

    def forgetAfter(self, ticksInFuture):
        '''
        Performs a partial reset, forgetting any checks performed after the
        given number of ticks in the future.
        '''
        self.ticksAhead = min(self.ticksAhead, ticksInFuture)
        if self.ticksToLive is not None and self.ticksToLive > ticksInFuture:
            self.ticksToLive = None

    def deathPredicted(self):
        return self.ticksToLive is not None

    def checkPath(self, playerPositions, shotsToCheck=None, startTick=0):
        '''
        Checks the given shots against the given set of player positions.

        :param playerPositions: the positions to check
        :param shotsToCheck: the shots to check, or None to check all
            tracked shots.
        :param startTick: how many ticks in the future we're starting in
        :return: None if no collision occurs, or the number of ticks until
            the collision.
        '''
        if shotsToCheck is None:
            shotsToCheck = self.shotsChecked

        serverDelay = self.player.agent.localState.serverDelay
        result = None
        for shot in shotsToCheck:
            for i, playerOldPos in enumerate(playerPositions[:-1]):
                playerPos = playerPositions[i + 1]
                ticksInMyFuture = startTick + i

                # Note: the "+ 2" below accounts perfectly for additional
                # delay when the bots are running within the server process
                # (which they always do at the moment), but if we want to
                # spawn the bots out into their own process, we'll need to
                # check that it still results in accurate collision detection.
                if shot.checkCollisionsWithPoints(
                        playerOldPos, playerPos,
                        ticksInFuture=serverDelay + ticksInMyFuture + 2):

                    if result is None or ticksInMyFuture < result:
                        result = ticksInMyFuture
                    break   # continue to next shot
        return result

    def _checkAgainst(self, playerPositions, shotsToCheck, startTick=0):
        '''
        Check the given shots against the given set of playerPositions.
        '''
        hitTick = self.checkPath(playerPositions, shotsToCheck, startTick)
        if hitTick is None:
            return

        if self.ticksToLive is None or self.ticksToLive > hitTick:
            self.ticksToLive = hitTick
