if __name__ == '__main__':
    # Just to make sure the correct one is imported if this is run directly
    import os, sys
    sys.path.insert(
        0, os.path.join(
            os.path.abspath(os.path.dirname(__file__)),
            '..', '..'))

import copy
import cPickle
import functools
import heapq
import logging
from math import pi
import os
import random
import zipfile

from twisted.internet import defer, reactor, threads

from trosnoth import data
from trosnoth.model.map import MapLayout
from trosnoth.model.mapLayout import LayoutDatabase
from trosnoth.model.player import Player
from trosnoth.model.universe import Universe

log = logging.getLogger(__name__)


DB_FILENAME = data.getPath(data, 'pathfinding.db')

NORTH = 'n'
SOUTH = 's'
EAST = 'e'
WEST = 'w'
ORB = 'o'

OPPOSITE_DIRECTION = {
    NORTH: SOUTH,
    SOUTH: NORTH,
    EAST: WEST,
    WEST: EAST,
}

ADJACENT_KINDS = {
    'topBlocked': {
        NORTH: [],
        SOUTH: ['btmBlocked', 'btmOpen'],
        EAST: ['bck'],
        WEST: ['fwd'],
    },
    'topOpen': {
        NORTH: ['btmBlocked', 'btmOpen'],
        SOUTH: ['btmBlocked', 'btmOpen'],
        EAST: ['bck'],
        WEST: ['fwd'],
    },
    'btmBlocked': {
        NORTH: ['topBlocked', 'topOpen'],
        SOUTH: [],
        EAST: ['fwd'],
        WEST: ['bck'],
    },
    'btmOpen': {
        NORTH: ['topBlocked', 'topOpen'],
        SOUTH: ['topBlocked', 'topOpen'],
        EAST: ['fwd'],
        WEST: ['bck'],
    },
    'fwd': {
        NORTH: ['bck'],
        SOUTH: ['bck'],
        EAST: ['topBlocked', 'topOpen'],
        WEST: ['btmBlocked', 'btmOpen'],
    },
    'bck': {
        NORTH: ['fwd'],
        SOUTH: ['fwd'],
        EAST: ['btmBlocked', 'btmOpen'],
        WEST: ['topBlocked', 'topOpen'],
    },
}


class ActionKindCollection(object):
    def __init__(self):
        self.store = {}

    def register(self, cls):
        key = cls.__name__
        if key in self.store:
            raise KeyError('Another %s already registered', key)
        self.store[key] = cls
        return cls

    def getByString(self, key):
        return self.store[key]

    def actionKindToString(self, actionKind):
        key = actionKind.__name__
        assert self.store[key] == actionKind
        return key

actionKindClasses = ActionKindCollection()


class PathFindingAction(object):
    '''
    Represents a possible action for player path-finding.
    '''

    def prepNextStep(self, player):
        '''
        Returns (done, stateChanges, faceRight) where done is a boolean
        indicating whether or not this action is complete, stateChanges
        is a list of (key, value) pairs indicating necessary changes to the
        player's getState() dict, and faceRight is whether or not the player
        should be facing right for this step.
        '''
        raise NotImplementedError(
            '%s.prepNextStep()' % (self.__class__.__name__,))

    @classmethod
    def buildStateChanges(cls, player, desiredState):
        return player.buildStateChanges(desiredState)


class SingleAction(PathFindingAction):

    class __metaclass__(type):
        def __repr__(cls):
            return cls.__name__


    def __init__(self):
        self.first = True

    @classmethod
    def simulate(cls, player, alsoAllowBlockDefs=()):
        '''
        Applies this action type to the given player object until it is
        complete or it leaves the current map block. (For the purposes of
        this calculation, "leaving" is defined as coming close enough to a
        map block that its obstacles might affect your path.

        Returns a tuple of the form (cost, orbTagCost, finalBlockDef).
        '''
        if player.attachedObstacle:
            startingPoint = str(player.getPathFindingNodeKey())
        else:
            startingPoint = str(player.pos)

        action = cls()

        orbTagCost = None

        startBlockDef = player.getMapBlock().defn
        finalBlockDef = startBlockDef
        cost = 0
        while True:
            done, stateChanges, faceRight = action.prepNextStep(player)
            if done:
                break
            for key, value in stateChanges:
                player.updateState(key, value)
            if faceRight and not player.isFacingRight():
                player.lookAt(pi / 2)
            elif (not faceRight) and player.isFacingRight():
                player.lookAt(-pi / 2)

            cost += 1
            oldPos = player.pos
            oldVel = player.yVel
            oldObstacle = player.attachedObstacle
            player.reset()
            player.advance()
            if (
                    oldPos == player.pos and oldVel == player.yVel and
                    oldObstacle is player.attachedObstacle is None):
                log.warning(
                    'Action %s from %s will go forever',
                    cls.__name__, startingPoint)
                return None, None, None

            zone = player.getZone()
            if (
                    orbTagCost is None and zone
                    and zone.playerIsWithinTaggingDistance(player)):
                orbTagCost = cost

            x, y = player.pos
            checks = [
                (x, y + player.HALF_HEIGHT),
                (x, y - player.HALF_HEIGHT),
                (x + player.HALF_WIDTH, y),
                (x - player.HALF_WIDTH, y),
                (x, y),
            ]
            skip = False
            for pos in checks:
                try:
                    blockDef = player.world.map.getMapBlockAtPoint(pos).defn
                except IndexError:
                    continue
                if (
                        blockDef != startBlockDef and
                        blockDef not in alsoAllowBlockDefs):
                    # We must end this simulation because the player is
                    # so near another map block that the other block's
                    # obstacles may interfere with the path.
                    skip = True
                    finalBlockDef = blockDef
                    break
            else:
                finalBlockDef = player.getMapBlock().defn

            if skip:
                break

            if cost >= 300:
                log.warning(
                    'Action %s from %s looks like it will go forever',
                    cls.__name__, startingPoint)
                return None, None, None

        return cost, orbTagCost, finalBlockDef


@actionKindClasses.register
class FallDown(SingleAction):
    def prepNextStep(self, player):
        stateChanges = self.buildStateChanges(player, {})
        done = not self.first and (
            player.isOnGround() or player.isAttachedToWall())
        self.first = False
        return done, stateChanges, player.isFacingRight()


@actionKindClasses.register
class FallPartwayDown(SingleAction):
    def __init__(self):
        super(FallPartwayDown, self).__init__()
        self.counter = 5

    def prepNextStep(self, player):
        stateChanges = self.buildStateChanges(player, {})
        done = not self.first and (
            player.isOnGround() or player.isAttachedToWall())
        done = done or self.counter <= 0
        self.counter -= 1
        self.first = False
        return done, stateChanges, player.isFacingRight()


@actionKindClasses.register
class FallLeft(SingleAction):
    def __init__(self):
        super(FallLeft, self).__init__()
        self.counter = 5

    def prepNextStep(self, player):
        stateChanges = self.buildStateChanges(player, {'left': True})
        done = not self.first and (
            player.isOnGround() or player.isAttachedToWall())
        done = done or self.counter <= 0
        self.counter -= 1
        self.first = False
        return done, stateChanges, False


@actionKindClasses.register
class FallRight(SingleAction):
    def __init__(self):
        super(FallRight, self).__init__()
        self.counter = 5

    def prepNextStep(self, player):
        stateChanges = self.buildStateChanges(player, {'right': True})
        done = not self.first and (
            player.isOnGround() or player.isAttachedToWall())
        done = done or self.counter <= 0
        self.counter -= 1
        self.first = False
        return done, stateChanges, True


@actionKindClasses.register
class Drop(SingleAction):
    def prepNextStep(self, player):
        stateChanges = self.buildStateChanges(player, {'down': True})
        done = not self.first
        self.first = False
        return done, stateChanges, player.isFacingRight()


@actionKindClasses.register
class JumpUp(SingleAction):
    def prepNextStep(self, player):
        if self.first:
            stateChanges = self.buildStateChanges(player, {}) + [
                ('jump', True)]
            done = False
        elif player.yVel < 0:
            stateChanges = self.buildStateChanges(player, {'jump': True})
            done = False
        else:
            stateChanges = self.buildStateChanges(player, {})
            done = True
        self.first = False
        return done, stateChanges, player.isFacingRight()


@actionKindClasses.register
class JumpLeft(SingleAction):
    def prepNextStep(self, player):
        if self.first:
            stateChanges = self.buildStateChanges(player, {'left': True}) + [
                ('jump', True)]
            done = False
        elif player.yVel < 0:
            stateChanges = self.buildStateChanges(
                player, {'left': True, 'jump': True})
            done = False
        else:
            stateChanges = self.buildStateChanges(player, {'left': True})
            done = True
        self.first = False
        return done, stateChanges, False


@actionKindClasses.register
class JumpRight(SingleAction):
    def prepNextStep(self, player):
        if self.first:
            stateChanges = self.buildStateChanges(player, {'right': True}) + [
                ('jump', True)]
            done = False
        elif player.yVel < 0:
            stateChanges = self.buildStateChanges(
                player, {'right': True, 'jump': True})
            done = False
        else:
            stateChanges = self.buildStateChanges(player, {'right': True})
            done = True
        self.first = False
        return done, stateChanges, True


@actionKindClasses.register
class MoveLeft(SingleAction):
    def prepNextStep(self, player):
        if self.first:
            stateChanges = self.buildStateChanges(player, {'left': True})
            done = False
        else:
            stateChanges = []
            done = True
        self.first = False
        return done, stateChanges, False


@actionKindClasses.register
class MoveRight(SingleAction):
    def prepNextStep(self, player):
        if self.first:
            stateChanges = self.buildStateChanges(player, {'right': True})
            done = False
        else:
            stateChanges = []
            done = True
        self.first = False
        return done, stateChanges, True


@actionKindClasses.register
class SlowStepLeft(SingleAction):
    def prepNextStep(self, player):
        if self.first:
            stateChanges = self.buildStateChanges(player, {'left': True})
            done = False
        else:
            stateChanges = []
            done = True
        self.first = False
        return done, stateChanges, True


@actionKindClasses.register
class SlowStepRight(SingleAction):
    def prepNextStep(self, player):
        if self.first:
            stateChanges = self.buildStateChanges(player, {'right': True})
            done = False
        else:
            stateChanges = []
            done = True
        self.first = False
        return done, stateChanges, False


class MultiActionPath(PathFindingAction):
    def __init__(self, actions):
        super(MultiActionPath, self).__init__()
        self.actions = [a() for a in actions]

    def prepNextStep(self, player):
        if not self.actions:
            return True, [], player.isFacingRight()
        while self.actions:
            done, stateChanges, faceRight = (
                self.actions[0].prepNextStep(player))

            if done:
                self.actions.pop(0)
            else:
                break
        return (len(self.actions) == 0), stateChanges, faceRight


class PathFindingStore(object):
    def __init__(self):
        self.blocks = {}
        self.combos = {}

    def build(self):
        log.info('Finding allowed nodes and edges...')

        layoutDb = LayoutDatabase()
        ds = layoutDb.datastores[0]
        for (kind, blocked), layouts in ds.layouts.iteritems():
            for layout in layouts:
                log.info('%s', os.path.basename(layout.filename))
                self.addBlock(layout, kind, blocked, layoutDb=layoutDb)

        log.info('Calculating walk scores within blocks...')
        for blockPaths in self.blocks.itervalues():
            blockPaths.calculateDefaultWalkScores()

        log.info('Calculating walk scores between blocks...')
        self.buildBlockCombinations(layoutDb=layoutDb)

        self.save()

    def addBlock(self, blockLayout, kind, blocked, layoutDb=None):
        '''
        Adds the given map block layout to the store and performs the initial
        pass of calculations.
        '''
        if blockLayout.key in self.blocks:
            raise KeyError('%s already in store' % (blockLayout.filename,))
        paths = PreCalculatedMapBlockPaths(blockLayout, kind, blocked)
        self.blocks[blockLayout.key] = paths
        paths.initialiseNodesAndEdges(layoutDb)

    def buildBlockCombinations(self, layoutDb=None):
        '''
        Goes through combinations of blocks which can fit together and
        calculates the costs of walking between the blocks.
        '''
        byKind = {}
        for blockPaths in self.blocks.itervalues():
            key = blockPaths.getKindKey()
            byKind.setdefault(key, []).append(blockPaths)

        total = len(list(self.iterBlockCombos(byKind)))
        count = 0
        for startBlockPaths, endBlockPaths, direction in self.iterBlockCombos(
                byKind):
            count += 1
            log.info('[ %s / %s ]', count, total)
            self.addCombo(
                startBlockPaths, endBlockPaths, direction, layoutDb=layoutDb)

    def iterBlockCombos(self, byKind):
        for startKind, blockPaths in byKind.iteritems():
            for startBlockPaths in blockPaths:
                for direction, allowedKinds in (
                        ADJACENT_KINDS[startKind].iteritems()):
                    for endKind in allowedKinds:
                        for endBlockPaths in byKind.get(endKind, []):
                            yield startBlockPaths, endBlockPaths, direction

    def addCombo(
            self, startBlockPaths, endBlockPaths, direction, layoutDb=None):
        combo = PreCalculatedMapBlockCombination(
            startBlockPaths, endBlockPaths, direction)
        key = startBlockPaths.layout.key, endBlockPaths.layout.key, direction
        self.combos[key] = combo
        combo.calculateConnections(layoutDb)
        combo.calculateWalkScores()

    def save(self):
        with zipfile.ZipFile(DB_FILENAME, 'w') as z:
            for block in self.blocks.itervalues():
                block.save(z)
            for combo in self.combos.itervalues():
                combo.save(z)


class RunTimePathFinder(object):

    def __init__(self, mapLayout):
        self.layout = mapLayout
        self.blocks = {}
        self.loading = False
        self.fullyLoaded = False
        self.centralDeferreds = []

    def waitForCentralData(self):
        '''
        Calls self.loadData(), and calls back when the data that's most
        important for bots to start the game (the data for central map
        columns) has been loaded.
        '''
        d = defer.Deferred()
        self.centralDeferreds.append(d)
        dataDeferred = self.loadData()
        @dataDeferred.addErrback
        def err(e):
            e.printTraceback()

        return d

    @defer.inlineCallbacks
    def loadData(self):
        '''
        This method loads from the path finding database, and yields every so
        often so that it can be used to load progressively.
        '''
        if self.loading or self.fullyLoaded:
            return

        self.loading = True
        self.fullyLoaded = False
        blockCache = {}
        comboCache = {}

        with zipfile.ZipFile(DB_FILENAME, 'r') as z:
            # Prioritise the spawning map blocks, then the centre column
            loaders = self._getPathFindingLoaders(blockCache, comboCache, z)
            for loaderFunction in loaders:
                yield loaderFunction()

                # Not sure if this is necessary
                d = defer.Deferred()
                reactor.callLater(0, d.callback, None)
                yield d

    def _getPathFindingLoaders(self, blockCache, comboCache, z):
        '''
        Returns loader functions for the map blocks and map block combinations
        in priority order. Prioritises the centre zones that the AIs will need
        early in the game.
        '''
        width = len(self.layout.blocks[0])
        centre = (width - 1) // 2

        # Blocks in spawn column
        for block in self._randomiseMapBlockColumn(centre - 2):
            yield functools.partial(self._loadBlockPaths, blockCache, z, block)
        # Interface between spawn column and centre column
        for block in self._randomiseMapBlockColumn(centre - 1):
            yield functools.partial(self._loadBlockPaths, blockCache, z, block)
        # Transitions from spawn column to interface
        for b1, dirn, b2 in self._getHorizontalBlockCombos(centre - 2):
            yield functools.partial(
                self._loadComboPaths, comboCache, z, b1, dirn, b2)
        # Transitions within interface column
        for b1, dirn, b2 in self._getVerticalBlockCombos(centre - 1):
            yield functools.partial(
                self._loadComboPaths, comboCache, z, b1, dirn, b2)
        yield self._signalCentreComplete

        # Blocks in centre column
        for block in self._randomiseMapBlockColumn(centre):
            yield functools.partial(self._loadBlockPaths, blockCache, z, block)
        # Transitions from interface to centre column
        for b1, dirn, b2 in self._getHorizontalBlockCombos(centre - 1):
            yield functools.partial(
                self._loadComboPaths, comboCache, z, b1, dirn, b2)
        # Transitions within centre column
        for b1, dirn, b2 in self._getVerticalBlockCombos(centre):
            yield functools.partial(
                self._loadComboPaths, comboCache, z, b1, dirn, b2)
        # Transitions within spawn column
        for b1, dirn, b2 in self._getVerticalBlockCombos(centre - 2):
            yield functools.partial(
                self._loadComboPaths, comboCache, z, b1, dirn, b2)

        # Go outwards through remaining columns
        for i in range(centre - 3, -1, -1):
            # Blocks
            for b in self._randomiseMapBlockColumn(i):
                yield functools.partial(self._loadBlockPaths, blockCache, z, b)
            # Transitions to this column
            for b1, dirn, b2 in self._getHorizontalBlockCombos(i):
                yield functools.partial(
                    self._loadComboPaths, comboCache, z, b1, dirn, b2)
            # Transitions within this column
            for b1, dirn, b2 in self._getVerticalBlockCombos(i):
                yield functools.partial(
                    self._loadComboPaths, comboCache, z, b1, dirn, b2)
        self.fullyLoaded = True
        self.loading = False

    def _signalCentreComplete(self):
        deferreds, self.centralDeferreds = self.centralDeferreds, []
        for d in deferreds:
            d.callback(None)

    def _randomiseMapBlockColumn(self, col):
        mirrorCol = len(self.layout.blocks[0]) - col - 1
        cols = [col] if mirrorCol == col else [col, mirrorCol]
        blockDefs = [
            row[i] for row in self.layout.blocks for i in cols
            if row[i].layout is not None]
        random.shuffle(blockDefs)
        return blockDefs

    def _getHorizontalBlockCombos(self, col):
        combos = []
        width = len(self.layout.blocks[0])
        for i in [col, width - col - 2]:
            for row in self.layout.blocks:
                blockDef1 = row[i]
                blockDef2 = row[i + 1]
                if blockDef1.layout is None or blockDef2.layout is None:
                    continue
                combos.append((blockDef1, EAST, blockDef2))
                combos.append((blockDef2, WEST, blockDef1))
        random.shuffle(combos)
        return combos

    def _getVerticalBlockCombos(self, col):
        combos = []
        mirrorCol = len(self.layout.blocks[0]) - col - 1
        cols = [col] if mirrorCol == col else [col, mirrorCol]

        for j, row1 in enumerate(self.layout.blocks[:-1]):
            row2 = self.layout.blocks[j + 1]
            for i in cols:
                blockDef1 = row1[i]
                blockDef2 = row2[i]
                if blockDef1.layout is None or blockDef2.layout is None:
                    continue
                combos.append((blockDef1, SOUTH, blockDef2))
                combos.append((blockDef2, NORTH, blockDef1))
        random.shuffle(combos)
        return combos

    @defer.inlineCallbacks
    def _loadBlockPaths(self, blockCache, z, blockDef):
        runTimePaths = yield (
            PreCalculatedMapBlockPaths.applyToBlock(blockDef, z, blockCache))
        if runTimePaths:
            self.blocks[blockDef] = runTimePaths

    def _loadComboPaths(self, comboCache, z, blockDef1, direction, blockDef2):
        if blockDef1 not in self.blocks or blockDef2 not in self.blocks:
            return None
        return self.blocks[blockDef1].updateForCombination(
            direction, self.blocks[blockDef2], z, comboCache)

    def getExitEdge(self, player, direction):
        blockDef = player.getMapBlock().defn
        if blockDef not in self.blocks:
            return None
        paths = self.blocks[blockDef]
        edge, _ = paths.getBestEdgeAndExit(paths.getNode(player), direction)
        return edge

    def getAllEdges(self, player):
        blockDef = player.getMapBlock().defn
        if blockDef not in self.blocks:
            return []
        return self.blocks[blockDef].getNode(player)['edges']

    def getOrbNodes(self, zone):
        '''
        Yields the RunTimeMapBlockNodes that lead to the given zone's orb,
        unless the map blocks in question have not yet been loaded.
        '''
        x, y = zone.defn.pos
        j, i = self.layout.getMapBlockIndices(x, y - 5)
        blockDef1 = self.layout.blocks[j][i]
        blockDef2 = self.layout.blocks[j + 1][i]
        if blockDef1 in self.blocks:
            yield self.blocks[blockDef1].getMapBlockNode(ORB)
        if blockDef2 in self.blocks:
            yield self.blocks[blockDef2].getMapBlockNode(ORB)

    def getBlockPaths(self, blockDef):
        '''
        Returns the RunTimeMapBlockPaths for the given blockDef or None if they
        have not yet been loaded.
        '''
        return self.blocks.get(blockDef)


class PreCalculatedMapBlockPaths(object):
    def __init__(self, blockLayout, kind, blocked):
        self.kind = kind
        self.blocked = blocked
        self.layout = blockLayout
        self.nodes = {}
        self.outbound = {
            NORTH: PreCalculatedNode(self),
            SOUTH: PreCalculatedNode(self),
            EAST: PreCalculatedNode(self),
            WEST: PreCalculatedNode(self),
        }
        self.orbEdges = set()

    def save(self, z):
        arcName = self.getArcName(self.layout)
        contents = cPickle.dumps({
            'nodes': [node.serialise() for node in self.nodes.itervalues()],
        }, protocol=cPickle.HIGHEST_PROTOCOL)
        z.writestr(arcName, contents, zipfile.ZIP_DEFLATED)

    @staticmethod
    @defer.inlineCallbacks
    def applyToBlock(blockDef, z, blockCache):
        arcName = PreCalculatedMapBlockPaths.getArcName(blockDef.layout)
        if arcName not in blockCache:
            yield threads.deferToThread(
                PreCalculatedMapBlockPaths._loadPathData,
                blockDef, z, arcName, blockCache)

        data = blockCache[arcName]
        if not data:
            defer.returnValue(None)

        defer.returnValue(RunTimeMapBlockPaths(blockDef, data))

    @staticmethod
    def getArcName(blockLayout):
        return 'blocks/' + '/'.join(str(i) for i in blockLayout.key)

    @staticmethod
    def _loadPathData(blockDef, z, arcName, blockCache):
        try:
            f = z.open(arcName)
        except KeyError:
            log.error(
                'No path finding data found for %s',
                os.path.basename(blockDef.layout.filename)
                + (' (reverse)' if blockDef.layout.reversed else ''),
            )
            blockCache[arcName] = None
            return

        with f:
            blockCache[arcName] = cPickle.load(f)

    def getWorldAndBlockDef(self, layoutDb=None):
        '''
        Creates and returns a dummy world and the block definition
        corresponding to this map block.
        '''
        if layoutDb is None:
            layoutDb = LayoutDatabase()

        world = Universe(layoutDb)
        mapLayout = MapLayout(3, 4, False)

        if self.layout.kind in ('fwd', 'bck'):
            i, j = 2, 1
        else:
            mapLayout.addZone(1, 1, 0)
            if self.layout.kind == 'top':
                i, j = 1, 1
            else:
                i, j = 1, 2

        world.setLayout(mapLayout)
        block = world.map.layout.blocks[j][i]
        self.layout.applyTo(block)

        return world, block

    def initialiseNodesAndEdges(self, layoutDb=None):
        world, block = self.getWorldAndBlockDef(layoutDb)

        for obstacle in block.obstacles + block.ledges:
            if not obstacle.jumpable:
                continue
            minI, maxI = obstacle.getPositionIndexBounds(Player)
            for i in xrange(minI, maxI + 1):
                node = PreCalculatedNode(self, block, obstacle, i)
                self.nodes[node.obstacleId, i] = node

        for node in self.nodes.itervalues():
            node.expandEdges(world, block)

        log.info(
            '  -> Nodes: %r  Edges: %r  Exits: %r  Orb caps: %r',
            len(self.nodes),
            sum(len(n.outbound) for n in self.nodes.itervalues()),
            sum(len(n.inbound) for n in self.outbound.itervalues()),
            len(self.orbEdges),
        )

    def nodeFromPlayerState(self, player):
        '''
        Finds and returns the node that the given player state is associated
        with.
        '''
        assert player.attachedObstacle.jumpable
        obstacleId = player.attachedObstacle.obstacleId
        posIndex = player.attachedObstacle.getPositionIndex(Player, player.pos)
        return self.nodes[obstacleId, posIndex]

    def getExitNode(self, startBlock, endBlock):
        x0, y0 = startBlock.pos
        x1, y1 = endBlock.pos
        if x1 == x0 and y1 < y0:
            return self.outbound[NORTH]
        if x1 == x0 and y1 > y0:
            return self.outbound[SOUTH]
        if x1 > x0 and y1 == y0:
            return self.outbound[EAST]
        if x1 < x0 and y1 == y0:
            return self.outbound[WEST]
        return None

    def calculateDefaultWalkScores(self):
        '''
        Calculates the minimum distance from each node to any possible way of
        exiting the zone in each direction.
        '''
        for d in [NORTH, SOUTH, EAST, WEST]:
            self.calculateWalkScores(self.outbound[d].inbound, d)
        self.calculateWalkScores(self.orbEdges, ORB, orbCosts=True)

    def calculateWalkScores(self, targetEdges, scoreKey, orbCosts=False):
        '''
        Uses Dijkstra's algorithm to calculate the minimum distance from each
        node in this block to complete any of the given target edges. Stores
        these minimum values using the given scoreKey. If orbCosts is True,
        uses the orb cost of the given edges rather than the actual cost.
        '''
        heap = []
        for edge in targetEdges:
            if orbCosts:
                cost = edge.orbTagCost
            else:
                cost = edge.cost
            heapq.heappush(heap, (cost, edge.startNode))

        seen = set()
        while heap:
            cost, node = heapq.heappop(heap)
            if node in seen:
                continue
            seen.add(node)
            node.setWalkScore(scoreKey, cost)
            for edge in node.inbound:
                if edge.startNode in seen:
                    continue
                heapq.heappush(heap, (cost + edge.cost, edge.startNode))
        log.info(
            '%s -> %s: Visited %r nodes (/%r)',
            os.path.basename(self.layout.filename), scoreKey,
            len(seen), len(self.nodes))

    def getKindKey(self):
        if self.kind in ('top', 'btm'):
            return '%s%s' % (self.kind, 'Blocked' if self.blocked else 'Open')
        return self.kind


class RunTimeMapBlockPaths(object):
    def __init__(self, blockDef, blockData):
        self.blockDef = blockDef

        # Calling copy.deepcopy() on the whole node data takes a long time, so
        # select the ones we're going to be mutating and copy them only.
        self.nodes = {
            data['key']: {
                'edges': data['edges'],     # does not need copying
                'targets': copy.deepcopy(data['targets']),
                'scores': copy.deepcopy(data['scores']),
            } for data in blockData['nodes']
        }

        self.mapBlockNodes = {
            k: RunTimeMapBlockNode(blockDef, k)
            for k in [NORTH, SOUTH, EAST, WEST, ORB]}

    @defer.inlineCallbacks
    def updateForCombination(self, direction, other, z, cache):
        '''
        Called during loading, to update this block's node data with
        information based on what map blocks are adjacent to this one.
        Directionality: if you travel in direction from self, you will get to
        other.
        '''
        # Load the data for the combination
        data = yield PreCalculatedMapBlockCombination.loadData(
            self.blockDef, other.blockDef, direction, z, cache)

        if data is None:
            return
        self.applyDataToCombination(data, other, direction)

    def applyDataToCombination(self, comboData, other, direction):
        for nodeKey, cost in comboData['scores'].iteritems():
            if cost is None:
                del self.nodes[nodeKey]['scores'][direction]
            else:
                self.nodes[nodeKey]['scores'][direction] = cost

        for edgeData in comboData['edges']:
            nodeKey = edgeData['source']
            self.nodes[nodeKey]['targets'][direction] = {
                'cost': edgeData['cost'],
                'actions': edgeData['actions'],
                'targetMapBlock': other.blockDef,
                'target': edgeData['target'],
            }

        if not comboData['transitions']:
            # The only case when it's ok for there to be no way to move
            # directly between adjacent map blocks is from the top of a zone to
            # the top corner - in this case it's ok to have to go down then
            # across then up.
            if not (
                    self.blockDef.layout.kind == 'top' and
                    other.blockDef.layout.kind in ('bck', 'fwd')):
                log.error(
                    'No transition data for %s -> %s: %s',
                    os.path.basename(self.blockDef.layout.filename),
                    direction,
                    os.path.basename(other.blockDef.layout.filename))

        # Link the high-level path-finding nodes
        for outDir, cost in comboData['transitions'].iteritems():
            other.mapBlockNodes[outDir].addInwardEdge(
                self.mapBlockNodes[direction], cost)

    @classmethod
    def buildNodeKey(cls, player):
        return cls.buildNodeKeyFromObstacle(
            player.attachedObstacle, player.pos)

    @classmethod
    def buildNodeKeyFromObstacle(cls, obstacle, pos):
        posIndex = obstacle.getPositionIndex(Player, pos)
        return (obstacle.obstacleId, posIndex)

    def getNode(self, player):
        return self.getNodeFromObstacle(player.attachedObstacle, player.pos)

    def getNodeFromObstacle(self, obstacle, pos):
        obstacleId = obstacle.obstacleId
        posIndex = obstacle.getPositionIndex(Player, pos)
        return self.nodes[obstacleId, posIndex]

    def getNodeFromKey(self, nodeKey):
        return self.nodes[nodeKey]

    def getBestEdgeAndExit(self, node, scoreKey):
        if scoreKey in node['targets']:
            return node['targets'][scoreKey], scoreKey

        def endNodeScore(edge):
            endNode = self.nodes[edge['target']]
            return endNode['scores'][scoreKey]

        def edgeScore(edge):
            return endNodeScore(edge) + edge['cost']

        edges = [
            e for e in node['edges']
            if scoreKey in self.nodes[e['target']]['scores']]
        if not edges:
            log.warning(
                'Pathfinding database has no path from here towards %r',
                scoreKey)
            return None, None

        best = min(edges, key=edgeScore)
        if endNodeScore(best) >= node['scores'].get(scoreKey, 10000):
            # Even the best action does not get us closer (should never happen)
            log.warning('Stuck in local minimum (should be impossible)')
            log.warning('Perhaps pathfinding DB needs regenerating.')
            log.warning(
                '(in %s, going to %r)',
                os.path.basename(self.blockDef.layout.filename),
                scoreKey)
            return None, None

        return best, None

    def getActions(self, player, scoreKey):
        if not player.attachedObstacle:
            return [Drop]
        edge, exit = self.getBestEdgeAndExit(self.getNode(player), scoreKey)
        if edge is None:
            return []
        return [actionKindClasses.getByString(a) for a in edge['actions']]

    def getMapBlockNode(self, scoreKey):
        return self.mapBlockNodes[scoreKey]


class RunTimeMapBlockNode(object):
    '''
    Used to calculate the fastest path through a map at run-time. Represents
    exiting the given block by following the given score key.
    '''

    def __init__(self, blockDef, entryDirection):
        self.blockDef = blockDef
        self.scoreKey = entryDirection
        self.inwardEdges = []

    def __str__(self):
        return '(%s from %s)' % (self.scoreKey, self.blockDef)

    def __repr__(self):
        return 'RunTimeMapBlockNode(%r, %r)' % (
            self.blockDef, self.scoreKey)

    def addInwardEdge(self, node, cost):
        '''
        Should be called only during setup.
        '''
        ownKey = self.scoreKey
        if ownKey == ORB:
            ownKey = NORTH if self.blockDef.kind == 'btm' else SOUTH
        if node.scoreKey == OPPOSITE_DIRECTION[ownKey]:
            # Don't bother with edges that loop forever
            return
        self.inwardEdges.append((node, cost))

    def getIncomingPaths(self):
        '''
        Yields (node, cost) for each RunTimeMapBlockNode that can traverse to
        this node.
        '''
        return iter(self.inwardEdges)


class PreCalculatedMapBlockCombination(object):
    def __init__(self, start, end, direction):
        self.start = start
        self.end = end
        self.direction = direction
        self.edges = {}     # start -> edge
        self.walkScores = {}
        # Note: transitionCosts is the average cost of transitioning through
        # the *end* block given that you came from this direction.
        self.transitionCosts = {}

    def save(self, z):
        arcName = 'combos/%s/%s/%s' % (
            '/'.join(str(i) for i in self.start.layout.key),
            self.direction,
            '/'.join(str(i) for i in self.end.layout.key))

        contents = cPickle.dumps({
            'scores': {
                node.serialiseKey(): cost
                for node, cost in self.walkScores.iteritems()
            },
            'edges': [
                edge.serialiseTargetEdge(self.direction, includeSource=True)
                for edge in self.edges.itervalues()],
            'transitions': self.transitionCosts,
        }, protocol=cPickle.HIGHEST_PROTOCOL)
        z.writestr(arcName, contents, zipfile.ZIP_DEFLATED)

    @staticmethod
    @defer.inlineCallbacks
    def loadData(blockDef1, blockDef2, direction, z, cache):
        arcName = PreCalculatedMapBlockCombination.getArcName(
            blockDef1, blockDef2, direction)

        if arcName not in cache:
            yield threads.deferToThread(
                PreCalculatedMapBlockCombination._loadCombinationData,
                blockDef1, blockDef2, direction, z, arcName, cache)

        defer.returnValue(cache[arcName])

    @staticmethod
    def getArcName(blockDef1, blockDef2, direction):
        return 'combos/%s/%s/%s' % (
            '/'.join(str(i) for i in blockDef1.layout.key),
            direction,
            '/'.join(str(i) for i in blockDef2.layout.key))

    @staticmethod
    def _loadCombinationData(
            blockDef1, blockDef2, direction, z, arcName, cache):
        try:
            f = z.open(arcName)
        except KeyError:
            warning = True
            if blockDef1.kind == 'top' and direction in (EAST, WEST):
                # It's ok for there to be no path from top map block to top
                # corners.
                warning = False
            elif blockDef1.blocked and blockDef1.kind in ('top', 'btm'):
                # We expect no path through a blocked map block
                if blockDef1.kind == 'top' and direction == NORTH:
                    warning = False
                elif blockDef1.kind == 'btm' and direction == SOUTH:
                    warning = False

            if warning:
                log.warning(
                    'No path finding data found for %s -> %s: %s',
                    os.path.basename(blockDef1.layout.filename)
                    + (' (reverse)' if blockDef1.layout.reversed else ''),
                    direction,
                    os.path.basename(blockDef2.layout.filename)
                    + (' (reverse)' if blockDef2.layout.reversed else ''),
                )

            cache[arcName] = None
            defer.returnValue(None)

        with f:
            cache[arcName] = cPickle.load(f)

    def getWorldAndBlockDefs(self, layoutDb=None):
        world, startBlockDef = self.start.getWorldAndBlockDef(layoutDb)

        if self.start.layout.kind in ('fwd', 'bck'):
            i, j = 2, 1
        elif self.start.layout.kind == 'top':
            i, j = 1, 1
        else:
            i, j = 1, 2

        if self.direction == NORTH:
            j -= 1
        elif self.direction == SOUTH:
            j += 1
        elif self.direction == EAST:
            i += 1
        else:
            assert self.direction == WEST
            i -= 1

        endBlockDef = world.map.layout.blocks[j][i]
        self.end.layout.applyTo(endBlockDef)

        return world, startBlockDef, endBlockDef

    def calculateConnections(self, layoutDb=None):
        '''
        Calculates all edges leaving the start block and ending up in an
        allowable place in the end block.
        '''
        log.info(
            '%s -> %s: %s',
            os.path.basename(self.start.layout.filename) + (
                ' (reverse)' if self.start.layout.reversed else ''),
            self.direction,
            os.path.basename(self.end.layout.filename) + (
                ' (reverse)' if self.end.layout.reversed else ''),
        )

        world, startBlockDef, endBlockDef = self.getWorldAndBlockDefs(layoutDb)

        partitions = {}
        edges = set()

        for edge in self.start.outbound[self.direction].inbound:
            for record in edge.startNode.findOutcomes(
                    world, startBlockDef, endBlockDef, edge.actions, self.end):
                steps, finalNode, cost, orbTagCost = record

                newEdge = PreCalculatedEdge(
                    edge.startNode, steps, finalNode, cost, orbTagCost)
                # Deliberately do not call newEdge.register() because the edge
                # belongs to this block combination, not just to the starting
                # block.
                edges.add(newEdge)
                directions = frozenset(finalNode.walkScores.iterkeys())
                partitions[directions] = partitions.get(directions, 0) + 1

        total = len(edges)
        self.edges = {}
        if edges:
            allDirections = frozenset(d for p in partitions for d in p)
            while allDirections not in partitions:
                worstPartition = min(partitions, key=partitions.get)
                log.warning(
                    '  WARNING: ignoring %r nodes exiting in %r',
                    partitions[worstPartition],
                    ''.join(sorted(worstPartition)))
                del partitions[worstPartition]
                allDirections = frozenset(d for p in partitions for d in p)

            bestPartition = allDirections

            for e in edges:
                if frozenset(e.endNode.walkScores.iterkeys()) == bestPartition:
                    oldEdge = self.edges.get(e.startNode)
                    if oldEdge is None or oldEdge.cost > e.cost:
                        self.edges[e.startNode] = e

            self.transitionCosts = {}
            for outDir in bestPartition:
                costs = [
                    e.endNode.walkScores[outDir]
                    for e in self.edges.itervalues()]
                self.transitionCosts[outDir] = (sum(costs) + 0.) / len(costs)

        log.info('  links: %r total, %r viable', total, len(edges))

    def calculateWalkScores(self):
        '''
        Calculates the walk scores for exiting the start block and ending up in
        the end block. Only stores values which differ from the default walk
        scores in the start block.
        '''

        heap = []
        for edge in self.edges.itervalues():
            heapq.heappush(heap, (edge.cost, edge.startNode))

        seen = set()
        while heap:
            cost, node = heapq.heappop(heap)
            if node in seen:
                continue
            seen.add(node)
            if cost != node.getWalkScore(self.direction):
                self.walkScores[node] = cost
            for edge in node.inbound:
                if edge.startNode in seen:
                    continue
                heapq.heappush(heap, (cost + edge.cost, edge.startNode))

        for node in self.start.nodes.itervalues():
            if node not in seen and self.direction in node.walkScores:
                self.walkScores[node] = None

        log.info(
            '  updated %r/%r nodes (/%r)', len(self.walkScores), len(seen),
            len(self.start.nodes))


class PreCalculatedNode(object):
    def __init__(self, blockPaths, block=None, obstacle=None, posIndex=None):
        self.blockPaths = blockPaths
        self.posIndex = posIndex

        if obstacle is None:
            self.obstacleId = None
            self.pos = None
        else:
            self.obstacleId = obstacle.obstacleId
            pos = obstacle.getPositionFromIndex(Player, posIndex)
            self.pos = (pos[0] - block.pos[0], pos[1] - block.pos[1])

        self.inbound = set()
        self.outbound = set()
        self.walkScores = {}

    def serialise(self):
        '''
        Returns an object that can be serialised using pickle, which contains
        all information about this node that is relevant at run-time.
        '''
        internalEdges = [
            e.serialise() for e in self.outbound
            if e.endNode.obstacleId is not None]

        targetEdges = {}
        orbEdges = [e for e in self.outbound if e.orbTagCost is not None]
        if orbEdges:
            bestOrbEdge = min(orbEdges, key=lambda e: e.orbTagCost)
            targetEdges[ORB] = bestOrbEdge.serialiseTargetEdge(ORB)

        return {
            'key': self.serialiseKey(),
            'edges': internalEdges,
            'targets': targetEdges,
            'scores': self.walkScores,
        }

    def serialiseKey(self):
        return (self.obstacleId, self.posIndex)

    def expandEdges(self, world, blockDef):
        assert not self.outbound

        obstacle = blockDef.getObstacleById(self.obstacleId)

        motionState = Player.getAttachedMotionState(obstacle)

        if motionState == 'fall':
            actionClasses = [FallPartwayDown, FallLeft, FallRight]
        elif motionState == 'leftwall':
            actionClasses = [Drop, JumpUp, JumpRight]
        elif motionState == 'rightwall':
            actionClasses = [Drop, JumpUp, JumpLeft]
        else:
            actionClasses = [
                JumpUp, JumpLeft, JumpRight,
                MoveLeft, MoveRight, SlowStepLeft, SlowStepRight]
            if obstacle.drop:
                actionClasses.append(Drop)

        for actionClass in actionClasses:
            self.expandAction(actionClass, world, blockDef)

    def expandAction(self, actionClass, world, blockDef):
        for steps, finalNode, cost, orbTagCost in self.findOutcomes(
                world, blockDef, blockDef, [actionClass]):
            edge = PreCalculatedEdge(self, steps, finalNode, cost, orbTagCost)
            edge.register()

    def findOutcomes(
            self, world, startBlockDef, endBlockDef, actionKinds,
            endBlockPaths=None):
        '''
        Simulate the possible outcome or outcomes that could arise from
        starting at this node and carrying out the given sequence of
        actionKinds, while staying within the given blockDefs.

        Yields tuples of the form (actionKinds, finalNode, cost, orbTagCost).
        Note that if startBlockDef and endBlockDef are the same, this routine
        will sometimes yield exit nodes as well as internal nodes.

        For calculations across different start and end map blocks, you must
        provide the blockPaths object for the final map block.
        '''
        startPlayer = self.makePlayerState(world, startBlockDef)
        assert startPlayer.attachedObstacle is not None
        blockDefs = {startBlockDef, endBlockDef}
        singleBlock = (startBlockDef == endBlockDef)
        if singleBlock:
            assert endBlockPaths is None
            endBlockPaths = self.blockPaths

        cost = 0
        orbTagCost = None
        for action in actionKinds[:-1]:
            newCost, newOrbCost, finalBlockDef = action.simulate(startPlayer)
            if finalBlockDef not in blockDefs:
                return
            if orbTagCost is None and newOrbCost is not None:
                orbTagCost = cost + newOrbCost
            cost += newCost

        options = [
            (actionKinds[:-1], actionKinds[-1], startPlayer, cost, orbTagCost),
        ]
        while options:
            steps, actionKind, player, curCost, curOrbCost = options.pop(0)
            cost, orbTagCost, finalBlockDef = actionKind.simulate(
                player, alsoAllowBlockDefs=blockDefs)

            if cost is None:
                # Never ending
                continue

            cost += curCost
            if curOrbCost is not None:
                orbTagCost = curOrbCost
            steps = steps + [actionKind]

            if finalBlockDef not in blockDefs:
                if not singleBlock:
                    continue
                finalNode = endBlockPaths.getExitNode(
                    startBlockDef, finalBlockDef)
                if finalNode is None:
                    # Ended up in a non-adjacent map block
                    continue

            elif player.motionState != 'fall':
                if finalBlockDef != endBlockDef:
                    # Did not land in the designated end block
                    continue
                finalNode = endBlockPaths.nodeFromPlayerState(player)

            else:
                # Player ended up in the air, so add options for each possible
                # way of falling from here.
                for nextActionKind in [FallPartwayDown, FallLeft, FallRight]:
                    options.append((
                        steps, nextActionKind, player.clone(),
                        cost, orbTagCost,
                    ))
                continue

            yield steps, finalNode, cost, orbTagCost

    def makePlayerState(self, world, blockDef):
        obstacle = blockDef.getObstacleById(self.obstacleId)

        player = Player(world, 'PathFinding', None, None)
        player.pos = (
            self.pos[0] + blockDef.pos[0], self.pos[1] + blockDef.pos[1])
        player.setAttachedObstacle(obstacle)
        return player

    def setWalkScore(self, scoreKey, cost):
        self.walkScores[scoreKey] = cost

    def getWalkScore(self, scoreKey):
        return self.walkScores[scoreKey]


class PreCalculatedEdge(object):
    def __init__(self, startNode, actions, endNode, cost, orbTagCost):
        self.startNode = startNode
        self.actions = actions
        self.endNode = endNode
        self.cost = cost
        self.orbTagCost = orbTagCost

    def register(self):
        self.startNode.outbound.add(self)
        self.endNode.inbound.add(self)
        if self.orbTagCost is not None:
            self.startNode.blockPaths.orbEdges.add(self)

    def serialise(self):
        return {
            'target': self.endNode.serialiseKey(),
            'cost': self.cost,
            'actions': [
                actionKindClasses.actionKindToString(a) for a in self.actions],
        }

    def serialiseTargetEdge(self, targetKey, includeSource=False):
        result = {
            'cost': self.orbTagCost if targetKey == ORB else self.cost,
            'actions': [
                actionKindClasses.actionKindToString(a) for a in self.actions],
            'target': self.endNode.serialiseKey(),
        }
        if includeSource:
            result['source'] = self.startNode.serialiseKey()
        return result

if __name__ == '__main__':
    from trosnoth.utils.utils import initLogging
    initLogging(debug=True)
    PathFindingStore().build()
else:
    log.setLevel(logging.ERROR)