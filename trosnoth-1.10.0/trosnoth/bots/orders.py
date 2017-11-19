'''
This module contains the classes used by the main Bot base class in order to
follow orders like moving to an orb or attacking an enemy.
'''

import heapq
import logging
import random
from math import atan2

from trosnoth.bots.pathfinding import (
    NORTH, SOUTH, EAST, WEST, RunTimeMapBlockPaths,
    ORB)
from trosnoth.const import ZONE_CAP_DISTANCE
from trosnoth.messages import AimPlayerAtMsg, RespawnRequestMsg
from trosnoth.model.player import Player
from trosnoth.utils.math import distance

log = logging.getLogger(__name__)


class BotOrder(object):
    '''
    Base class for the simple bot orders.
    '''

    def __init__(self, bot):
        self.bot = bot

    def start(self):
        pass

    def restart(self):
        self.start()

    def tick(self):
        pass

    def playerDied(self):
        pass

    def playerRespawned(self):
        pass

    def requestMoreFuture(self):
        '''
        Called when the bot movement system wants to know more of this
        player's movements, after all the actions in bot.future. If this
        method does not call bot.future.expandEdge(), the BotFuture objecta
        may assume that this order will be complete at the end of the
        actions already projected.
        '''
        return None


class StandStill(BotOrder):
    '''
    This is the default order. It does not tell the bot to do anything.
    '''

    def __eq__(self, other):
        return self.__class__ == other.__class__ and self.bot == other.bot

    def playerDied(self):
        self.bot.orderFinished()

    def playerRespawned(self):
        self.bot.orderFinished()


class MoveGhostToPoint(BotOrder):
    '''
    Points the ghost towards the given point, stopping when it reaches that
    point or when it enters the given zone, whichever happens first.
    '''

    def __init__(self, bot, pos, stopOnZoneEntry=None):
        super(MoveGhostToPoint, self).__init__(bot)
        self.pos = pos
        self.stopOnZoneEntry = stopOnZoneEntry

    def start(self):
        self._doAim()

    def _doAim(self):
        playerPos = self.bot.player.pos
        dx = self.pos[0] - playerPos[0]
        dy = self.pos[1] - playerPos[1]
        theta = atan2(dx, -dy)

        self.bot.sendRequest(
            AimPlayerAtMsg(theta, 1.0, self.bot.world.lastTickId))

    def tick(self):
        if self.bot.player.ghostThrust == 0:
            self._doAim()

        if self.stopOnZoneEntry:
            if self.bot.player.getZone() == self.stopOnZoneEntry:
                self.bot.orderFinished()
                return
        else:
            if distance(self.bot.player.pos, self.pos) < ZONE_CAP_DISTANCE:
                self.bot.orderFinished()
                return


class PathFindingOrder(BotOrder):
    '''
    Base class for orders that need to do path finding through the map.
    '''

    def __init__(self, *args, **kwargs):
        super(PathFindingOrder, self).__init__(*args, **kwargs)
        self.giveUp = False
        self.giveUpCounter = 10
        self.futureMapBlockSteps = []

    def checkOrderCompletion(self, player):
        '''
        Checks whether the given player object would fulfill the completion
        conditions of this order (e.g. it has reached the orb or the target
        position.)
        Should be overridden by subclasses.
        '''
        return False

    def restart(self):
        self.giveUp = False
        self.futureMapBlockSteps = []

    def start(self):
        self.bot.future.clear()

    def tick(self):
        if self.checkOrderCompletion(self.bot.player):
            self.bot.orderFinished()
        elif self.giveUp and not self.bot.future.hasActions():
            self.giveUpCounter -= 1
            if self.giveUpCounter <= 0:
                self.bot.orderFinished()

    def playerDied(self):
        self.bot.orderFinished()

    def _getTarget(self):
        '''
        Subclasses should override this to provide the path-finding node key
        that we're aiming for. Must return (mapBlockDef, nodeKey).
        '''
        raise NotImplementedError(
            '{}._getTarget'.format(self.__class__.__name__))

    def requestMoreFuture(self):
        if self.giveUp:
            return

        futurePlayer = self.bot.future.getPlayer()
        if futurePlayer.getPathFindingNodeKey() is None:
            self.bot.future.land()
        elif self._isInWrongMapBlock(futurePlayer):
            if not self.futureMapBlockSteps:
                self._rebuildMapBlockPath()
                if not self.futureMapBlockSteps:
                    self._noPathFound()
                    return
            self._extendFutureTowardsMapBlock(futurePlayer)
        else:
            self._extendFutureWithinMapBlock(futurePlayer)

    def _isInWrongMapBlock(self, futurePlayer):
        '''
        Should return True if there's still map block navigation to be done.
        Subclasses may override.
        '''
        futureBlockDef = futurePlayer.getMapBlock().defn
        targetMapBlockDef, targetKey = self._getTarget()
        return futureBlockDef != targetMapBlockDef

    def _extendFutureTowardsMapBlock(self, futurePlayer):
        '''
        Returns the edge in the path-finding graph that corresponds to the
        best path for the given futurePlayer towards the given map block.
        '''
        futureBlockDef = futurePlayer.getMapBlock().defn
        if self.futureMapBlockSteps[0][0] != futureBlockDef:
            # Bot is no longer in the mapblock it was trying to leave
            self.futureMapBlockSteps.pop(0)
            if (
                    not self.futureMapBlockSteps or
                    self.futureMapBlockSteps[0][0] != futureBlockDef):
                log.warning('Unexpected step in map block path!')
                self._rebuildMapBlockPath()
                if not self.futureMapBlockSteps:
                    self._noPathFound()
                    return

        blockDef, scoreKey = self.futureMapBlockSteps[0]
        pathFinder = self.bot.world.map.layout.pathFinder
        blockPaths = pathFinder.getBlockPaths(blockDef)
        if blockPaths is None:
            return
        nodeKey = blockPaths.buildNodeKey(futurePlayer)
        node = blockPaths.getNodeFromKey(nodeKey)
        nextEdge, exitDir = blockPaths.getBestEdgeAndExit(node, scoreKey)

        if not nextEdge:
            # Path-finding database has no path from here in that direction
            self._noPathFound()
            return

        self.bot.future.expandEdge(nextEdge, exitDir)

        if exitDir == ORB:
            # An orb tag. Signal the end of the order.
            self.giveUp = True

    def _noPathFound(self):
        self.giveUp = True

    def _extendFutureWithinMapBlock(self, futurePlayer):
        '''
        Perform A* using a heuristic calculated from exit distances.
        '''
        pathFinder = self.bot.world.map.layout.pathFinder
        blockDef, targetKey = self._getTarget()
        assert futurePlayer.getMapBlock().defn == blockDef
        blockPaths = pathFinder.getBlockPaths(blockDef)
        if blockPaths is None or targetKey is None:
            return
        targetScores = blockPaths.getNodeFromKey(targetKey)['scores']
        startKey = futurePlayer.getPathFindingNodeKey()

        def heuristic(key):
            nodeScores = blockPaths.getNodeFromKey(key)['scores']
            diffs = [
                nodeScores[d] - targetScores[d]
                for d in targetScores if d in nodeScores]
            if not diffs:
                # No points of comparison, probably impossible to get between
                # them.
                return 10000
            return max(diffs)

        heap = []
        seen = set()

        heapq.heappush(heap, (0, 0, startKey, None))

        while heap:
            score, cost, nodeKey, path = heapq.heappop(heap)
            if nodeKey in seen:
                continue
            seen.add(nodeKey)

            if nodeKey == targetKey:
                break

            node = blockPaths.getNodeFromKey(nodeKey)
            for edge in node['edges']:
                nextKey = edge['target']
                if nextKey in seen:
                    continue
                nextCost = cost + edge['cost']
                nextScore = nextCost + heuristic(nextKey)
                nextPath = (edge, path)
                heapq.heappush(heap, (nextScore, nextCost, nextKey, nextPath))
        else:
            self._noPathFound()
            return

        # Found solution
        edges = []
        while path is not None:
            edge, path = path
            edges.insert(0, edge)

        for edge in edges:
            self.bot.future.expandEdge(edge, exitDir=None)

    def _rebuildMapBlockPath(self):
        '''
        Populates self.futureMapBlockSteps with a path to the map block
        needed. On error, leaves mapBlockSteps empty.
        '''
        targetNodes = self._getTargetMapBlockNodes()

        if not targetNodes:
            self.futureMapBlockSteps = []
            return

        self.futureMapBlockSteps = self._calculatePath(targetNodes) or []

    def _getTargetMapBlockNodes(self):
        '''
        Returns the map block nodes that we are trying to reach. May be
        overridden by subclasses.
        '''
        pathFinder = self.bot.world.map.layout.pathFinder
        targetBlockDef, targetKey = self._getTarget()
        blockPaths = pathFinder.getBlockPaths(targetBlockDef)
        if blockPaths is None or targetKey is None:
            return None

        targetNodes = set()

        # Find out which ways the given player can exit the map block
        targetExitDirections = set()

        runtimeNode = blockPaths.getNodeFromKey(targetKey)
        for direction in [NORTH, SOUTH, EAST, WEST]:
            if direction in runtimeNode['scores']:
                targetExitDirections.add(direction)

        for direction in targetExitDirections:
            paths = blockPaths.getMapBlockNode(direction).getIncomingPaths()
            for node, cost in paths:
                targetNodes.add(node)

        return targetNodes

    def _calculatePath(self, targetNodes):
        '''
        Use Dijkstra's algorithm to calculate the shortest path through the map
        blocks based on the approximate traversal costs of the map blocks.

        targetNodes is a collection of RunTimeMapBlockNodes for where we are
        trying to get to.

        Returns None on failure, otherwise a list of (blockDef, scoreKey)
        tuples.
        '''
        steps = []

        pathFinder = self.bot.world.map.layout.pathFinder
        if pathFinder is None:
            # Path-finding database not yet loaded
            return None

        futurePlayer = self.bot.future.getPlayer()
        futureBlockDef = futurePlayer.getMapBlock().defn
        blockPaths = pathFinder.getBlockPaths(futureBlockDef)
        if blockPaths is None:
            # Possibly not yet finished loading paths
            return None

        futureKey = blockPaths.buildNodeKey(futurePlayer)
        nextNode = blockPaths.getNodeFromKey(futureKey)

        targets = {}
        for direction, score in nextNode['scores'].items():
            targets[blockPaths.getMapBlockNode(direction)] = score

        heap = []
        seen = set()
        finished = object()

        for node in targetNodes:
            heapq.heappush(heap, (0, None, node))

        while heap:
            cost, path, node = heapq.heappop(heap)
            if node in seen:
                continue
            seen.add(node)
            if node is finished:
                break
            if node in targets:
                stepCost = targets[node]
                heapq.heappush(heap, (cost + stepCost, (node, path), finished))
                continue

            for child, stepCost in node.getIncomingPaths():
                heapq.heappush(heap, (cost + stepCost, (node, path), child))

        else:
            # No path found!
            return None

        while path is not None:
            node, path = path
            steps.append((node.blockDef, node.scoreKey))
        return steps


class MoveToOrb(PathFindingOrder):
    '''
    Moves the given live player towards the given orb, stopping after touching
    the orb, or upon entering the zone if stopOnEntry is True.
    '''

    def __init__(self, bot, zone, stopOnEntry=False):
        super(MoveToOrb, self).__init__(bot)
        self.zone = zone
        self.stopOnEntry = stopOnEntry

    def __repr__(self):
        return 'MoveToOrb({bot}, {zone}{stopOnEntry})'.format(
            bot=self.bot,
            zone=self.zone,
            stopOnEntry=', stopOnEntry=True' if self.stopOnEntry else '',
        )

    def checkOrderCompletion(self, player):
        playerZone = player.getZone()
        if self.stopOnEntry:
            if playerZone == self.zone and player.attachedObstacle:
                return True
        elif distance(player.pos, self.zone.defn.pos) < ZONE_CAP_DISTANCE:
            return True
        return False

    def _isInWrongMapBlock(self, futurePlayer):
        # Only map block navigation is required to reach orb
        return True

    def _getTargetMapBlockNodes(self):
        pathFinder = self.bot.world.map.layout.pathFinder
        return pathFinder.getOrbNodes(self.zone)


class RespawnInZone(BotOrder):
    '''
    If the specified zone was not respawnable when the order was given, waits
    until it is. If it was but the zone becomes unrespawnable, the order is
    considered completed.
    '''

    def __init__(self, bot, zone):
        super(RespawnInZone, self).__init__(bot)
        self.zone = zone
        self.wasRespawnable = self.bot.player.isZoneRespawnable(zone)
        self.nextCheckTime = 0

    def start(self):
        self._reAim()

    def _reAim(self):
        now = self.bot.world.getMonotonicTime()
        dist = distance(self.bot.player.pos, self.zone.defn.pos)

        if dist < 100:
            if self.bot.player.ghostThrust:
                self.bot.sendRequest(
                    AimPlayerAtMsg(0, 0, self.bot.world.lastTickId))
        elif dist < 300 or self.nextCheckTime < now:
            playerPos = self.bot.player.pos
            zonePos = self.zone.defn.pos
            dx = zonePos[0] - playerPos[0]
            dy = zonePos[1] - playerPos[1]
            theta = atan2(dx, -dy)
            thrust = min(1, distance(playerPos, zonePos) / 300.)

            self.bot.sendRequest(
                AimPlayerAtMsg(theta, thrust, self.bot.world.lastTickId))

            now = self.bot.world.getMonotonicTime()
            self.nextCheckTime = now + 0.5

    def tick(self):
        player = self.bot.player

        zoneRespawnable = self.bot.player.isZoneRespawnable(self.zone)
        if self.wasRespawnable and not zoneRespawnable:
            self.bot.orderFinished()
            return

        playerZone = player.getZone()
        if player.ghostThrust or playerZone != self.zone:
            self._reAim()

        if not player.world.abilities.respawn:
            return
        if player.respawnGauge > 0:
            return

        if playerZone != self.zone:
            return
        if not zoneRespawnable:
            return
        if playerZone.frozen:
            return
        self.bot.sendRequest(
            RespawnRequestMsg(self.bot.world.lastTickId))

    def playerRespawned(self):
        self.bot.orderFinished()


class FollowPlayer(PathFindingOrder):
    '''
    Follows the given target player until that player dies or this player dies.
    If attack is True, shoots at the player.
    '''

    def __init__(self, bot, player, attack=False):
        super(FollowPlayer, self).__init__(bot)
        self.target = None, None
        self.targetPlayer = player
        self.attack = attack
        self.nextCheckTime = 0
        self.targetObstacle = None
        self.targetPos = None
        self.targetMapBlockDefn = player.getMapBlock().defn

    def restart(self):
        self._recalculateTarget()
        super(FollowPlayer, self).restart()

    def start(self):
        self._recalculateTarget()
        super(FollowPlayer, self).start()

    def checkOrderCompletion(self, player):
        if self.targetPlayer.dead:
            return True
        return False

    def tick(self):
        if self.attack and self.bot.canHitPlayer(self.targetPlayer):
            self.bot.fireShotAtPoint(self.targetPlayer.pos)

        now = self.bot.world.getMonotonicTime()
        recalculate = False
        if self.targetPlayer.attachedObstacle:
            # In case the target jumps in the future, register a point on an
            # obstacle to move towards until they land.
            self.targetObstacle = self.targetPlayer.attachedObstacle
            self.targetPos = self.targetPlayer.pos
            self.targetMapBlockDefn = self.targetPlayer.getMapBlock().defn
            if self.targetMapBlockDefn != self.target[0]:
                recalculate = True

        if not self.bot.future.hasActions() or (
                self.nextCheckTime <= now and
                self.targetMapBlockDefn ==
                    self.targetPlayer.getMapBlock().defn):
            recalculate = True

        if recalculate:
            self._recalculateTarget()
            self.futureMapBlockSteps = []
            self.bot.future.clear()
            self.nextCheckTime = now + 0.5

        super(FollowPlayer, self).tick()

    def _noPathFound(self):
        # We'll be rechecking when the target player moves, so don't finish the
        # order just because we can't find a path right now.
        pass

    def _getTarget(self):
        return self.target

    def _recalculateTarget(self):
        if self.targetPos is None:
            # Player hasn't landed since we started trying to follow them
            self.target = self.targetMapBlockDefn, None
            return
        nodeKey = RunTimeMapBlockPaths.buildNodeKeyFromObstacle(
            self.targetObstacle, self.targetPos)
        self.target = self.targetMapBlockDefn, nodeKey


class MoveToPoint(PathFindingOrder):

    def __init__(self, bot, pos):
        super(MoveToPoint, self).__init__(bot)
        self.pos = pos
        self.target = None

    def checkOrderCompletion(self, player):
        if self.target is None:
            return False
        targetBlockDef, targetNodeKey = self.target
        if targetNodeKey is None:
            return (
                player.getMapBlock().defn == targetBlockDef and
                player.attachedObstacle is not None)

        nodeKey = player.getPathFindingNodeKey()
        if nodeKey and (player.getMapBlock().defn, nodeKey) == self.target:
            return True
        return False

    def _getTarget(self):
        if self.target:
            return self.target
        self.target = self._calculateTargetNode(self.pos)
        return self.target

    def _calculateTargetNode(self, targetPos):
        world = self.bot.world
        physics = world.physics
        mapBlock = world.map.getMapBlockAtPoint(targetPos)
        pathFinder = world.map.layout.pathFinder
        blockPaths = pathFinder.getBlockPaths(mapBlock.defn)
        if blockPaths is None:
            return mapBlock, None

        fakePlayer = Player(world, 'PathFinding', None, None)
        fakePlayer.pos = targetPos

        # Try to find a nearby obstacle
        obstacleAttempts = [
            (0, 2 * Player.HALF_HEIGHT),
            (-2 * Player.HALF_WIDTH, 0),
            (2 * Player.HALF_WIDTH, 0),
            (0, 10 * Player.HALF_HEIGHT),
        ]
        for dX, dY in obstacleAttempts:
            obstacle, dX, dY = physics.trimPathToObstacle(
                fakePlayer, dX, dY, ())
            if obstacle and obstacle.jumpable:
                newPos = (targetPos[0] + dX, targetPos[1] + dY)
                newMapBlock = world.map.getMapBlockAtPoint(newPos)
                if newMapBlock != mapBlock:
                    continue

                nodeKey = blockPaths.buildNodeKeyFromObstacle(obstacle, newPos)
                break
        else:
            # No obstacle found.
            nodeKey = None

        self.target = (mapBlock.defn, nodeKey)
        return self.target


class CollectTrosball(MoveToPoint):
    '''
    Moves towards the trosball until someone picks it up or this player dies.
    '''

    def __init__(self, bot):
        pos = bot.world.trosballManager.getPosition()
        super(CollectTrosball, self).__init__(bot, pos)
        self.nextCheckTime = 0

    def restart(self):
        self._recalculateTarget()
        super(CollectTrosball, self).restart()

    def start(self):
        self._recalculateTarget()
        super(CollectTrosball, self).start()

    def checkOrderCompletion(self, player):
        if self.bot.world.trosballManager.trosballPlayer is not None:
            return True
        return False

    def tick(self):
        now = self.bot.world.getMonotonicTime()
        if not self.bot.future.hasActions() or self.nextCheckTime <= now:
            self._recalculateTarget()
            self.futureMapBlockSteps = []
            self.bot.future.clear()
            self.nextCheckTime = now + 0.5

        super(CollectTrosball, self).tick()

    def _noPathFound(self):
        # We'll be rechecking when the trosball moves, so don't finish the
        # order just because we can't find a path right now.
        pass

    def _getTarget(self):
        return self.target

    def _recalculateTarget(self):
        x, y = self.bot.world.trosballManager.getPosition()
        blockDef, nodeKey = self._calculateTargetNode((x, y))
        for i in range(5):
            if nodeKey is not None:
                break
            x += 10 * (2 * random.random() - 1)
            y += 10 * (2 * random.random() - 1)
            blockDef, nodeKey = self._calculateTargetNode((x, y))
        self.target = blockDef, nodeKey
