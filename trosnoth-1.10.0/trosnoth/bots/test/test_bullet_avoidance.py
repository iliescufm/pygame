import logging
import os
import zipfile
from functools import partial

from mock import NonCallableMock, Mock

from trosnoth.model.map import MapLayout

from trosnoth.bots import pathfinding

from trosnoth.bots.base import Bot
from trosnoth.bots.orders import BotOrder
from trosnoth.bots.pathfinding import (
    PreCalculatedMapBlockPaths, RunTimePathFinder,
    RunTimeMapBlockPaths, JumpUp,
    PreCalculatedMapBlockCombination, SOUTH, NORTH, EAST, WEST,
    FallDown, PreCalculatedNode, JumpLeft, FallLeft, MoveRight, Drop,
    FallRight, FallPartwayDown, MoveLeft)
from trosnoth.messages import AimPlayerAtMsg
from trosnoth.messages import TickMsg
from trosnoth.messages import UpdatePlayerStateMsg
from trosnoth.model.mapLayout import LayoutDatabase
from trosnoth.model.player import Player
from trosnoth.model.universe import Universe
from trosnoth.utils import globaldebug

logging.basicConfig(level=logging.INFO)

MAX_TICKS = 1000

log = logging.getLogger(__name__)


class MapSimulator(object):
    '''
    Creates a simulation world that only contains certain provided map
    blocks. This can then be used for simulating bot behaviour.
    '''

    def __init__(self):
        self.layoutDb = LayoutDatabase()
        self.world = Universe(self.layoutDb)
        self.world.setLayout(MapLayout(3, 4, False))
        self.blockDefs = []
        self.blockCombos = []

    def actualKind(self, blockLayout):
        if blockLayout.reversed:
            if blockLayout.kind == 'fwd':
                return 'bck'
            if blockLayout.kind == 'bck':
                return 'fwd'
        return blockLayout.kind

    def loadBlock(
                self, mapBlockName, reversedBlock, nextTo=None, upwards=False):
        dataStore = self.layoutDb.datastores[0]
        layout = dataStore.layoutsByFilename[mapBlockName + '.block']
        assert not layout.reversed
        if reversedBlock:
            layout = layout.mirrorLayout

        layoutKind = self.actualKind(layout)
        if layoutKind == 'fwd':
            i, j = 2, 2
        elif layoutKind == 'bck':
            i, j = 2, 1
        elif layoutKind == 'top':
            i, j = 1, 1
        else:
            i, j = 1, 2

        if nextTo:
            assert self.actualKind(nextTo.layout) != layoutKind
            j0, i0 = nextTo.indices
            if i0 == i:
                # Same vertical column.
                if upwards:
                    j = j0 - 1
                else:
                    j = j0 + 1
            elif j0 != j:
                # If you shift by two horizontally and one vertically,
                # you get to the same map block kind.
                assert abs(j0 - j) == 1
                j = j0
                if i < i0:
                    i += 2
                else:
                    i -= 2

        blockDef = self.world.map.layout.blocks[j][i]
        layout.applyTo(blockDef)
        self.blockDefs.append(blockDef)
        log.info(
            'Added block %s (%s, %s)', blockDef, layoutKind,
            os.path.basename(layout.filename))
        log.info('%s', blockDef.pos)
        return blockDef

    def loadTransition(
            self, fromBlock, fromReversed, toBlock, toReversed, upwards=False):
        blockDef1 = self.loadBlock(fromBlock, fromReversed)
        blockDef2 = self.loadBlock(
            toBlock, toReversed, nextTo=blockDef1, upwards=upwards)
        self.blockCombos.append((blockDef1, blockDef2))
        assert blockDef1 != blockDef2, 'both given layouts are the same kind'

    def createPlayer(self, startNodeKey):
        player = Player(self.world, 'Testing', None, None)
        obstacleId, posIndex = startNodeKey
        obstacle = self.blockDefs[0].getObstacleById(obstacleId)
        player.pos = obstacle.getPositionFromIndex(Player, posIndex)
        player.setAttachedObstacle(obstacle)
        return player

    def sendRequest(self, player, msg):
        if isinstance(msg, UpdatePlayerStateMsg):
            player.updateState(msg.stateKey, msg.value)
            log.info('update state: %r -> %r', msg.stateKey, msg.value)
        elif isinstance(msg, AimPlayerAtMsg):
            player.lookAt(msg.angle, msg.thrust)
            log.info('looking at %.2f', msg.angle)
        else:
            assert False, 'unexpected msg %s' % (msg,)

    def initPathFinder(self):
        if self.world.map.layout.pathFinder is not None:
            return

        pathFinder = RunTimePathFinder(self.world.map.layout)
        self.world.map.layout.pathFinder = pathFinder

        blockCache = {}
        comboCache = {}
        with zipfile.ZipFile(pathfinding.DB_FILENAME, 'r') as z:
            for blockDef in self.blockDefs:
                self.loadPathFindingForBlockDef(
                    blockDef, z, pathFinder, blockCache)

            for blockDef1, blockDef2 in self.blockCombos:
                self.loadPathFindingForBlockCombo(
                    blockDef1, blockDef2, z, pathFinder, comboCache)

    def loadPathFindingForBlockCombo(
            self, blockDef1, blockDef2, z, pathFinder, comboCache):
        blockPaths1 = pathFinder.blocks[blockDef1]
        blockPaths2 = pathFinder.blocks[blockDef2]

        j1, i1 = blockDef1.indices
        j2, i2 = blockDef2.indices
        if i1 == i2:
            assert j1 != j2
            if j1 < j2:
                dir1, dir2 = SOUTH, NORTH
            else:
                dir1, dir2 = NORTH, SOUTH
        else:
            assert j1 == j2
            if i1 < i2:
                dir1, dir2 = EAST, WEST
            else:
                dir1, dir2 = WEST, EAST

        arc = PreCalculatedMapBlockCombination.getArcName(
            blockDef1, blockDef2, dir1)
        if arc not in comboCache:
            PreCalculatedMapBlockCombination._loadCombinationData(
                blockDef1, blockDef2, dir1, z, arc, comboCache)
        blockPaths1.applyDataToCombination(comboCache[arc], blockPaths2, dir1)

        arc = PreCalculatedMapBlockCombination.getArcName(
            blockDef2, blockDef1, dir2)
        if arc not in comboCache:
            PreCalculatedMapBlockCombination._loadCombinationData(
                blockDef2, blockDef1, dir2, z, arc, comboCache)
        blockPaths2.applyDataToCombination(comboCache[arc], blockPaths1, dir2)

    def loadPathFindingForBlockDef(self, blockDef, z, pathFinder, blockCache):
        arcName = PreCalculatedMapBlockPaths.getArcName(blockDef.layout)
        PreCalculatedMapBlockPaths._loadPathData(
            blockDef, z, arcName, blockCache)
        pathData = blockCache[arcName]
        paths = RunTimeMapBlockPaths(blockDef, pathData)
        pathFinder.blocks[blockDef] = paths

    def runActions(self, start, sequence):
        globaldebug.enabled = False
        self.initPathFinder()

        player = self.createPlayer(start)

        agent = NonCallableMock()
        agent.sendRequest.side_effect = partial(self.sendRequest, player)
        agent.localState.serverDelay = 1
        player.agent = agent

        bot = Bot(self.world, player, agent)
        bot.pauseBetweenActions = 0
        order = PredefinedActionsOrder(bot, sequence)
        bot.currentOrder = order
        order.start()

        log.info('start key: %r', player.getPathFindingNodeKey())
        tickId = 1
        while bot.currentOrder is order:
            tickMsg = TickMsg(tickId)

            player.reset()
            player.advance()
            order.setCurrentTick(tickId)
            log.info('tick %r: %r', tickId, player.pos)

            bot.handle_TickMsg(tickMsg)

            tickId += 1
            assert tickId < MAX_TICKS, 'execution took too long'

        log.info('advance() final block: %s', player.getMapBlock().defn)
        log.info('advance() final key: %s', player.getPathFindingNodeKey())

    def runSimulation(
            self, startNodeKey, actionKinds, endNodeKey=None,
            expectNoResults=False):
        '''
        Uses PreCalculatedNode.findOutcomes() to find and return the
        simulated (cost, orbCost) for following the given actions from the
        given starting node key.
        '''
        obstacleId, posIndex = startNodeKey
        obstacle = self.blockDefs[0].getObstacleById(obstacleId)
        pos = obstacle.getPositionFromIndex(Player, posIndex)

        blockPaths = NonCallableMock(spec=PreCalculatedMapBlockPaths)

        def getExitNode(fromBlockDef, toBlockDef):
            return ('exit node', fromBlockDef, toBlockDef)
        blockPaths.getExitNode = Mock(side_effect=getExitNode)

        def nodeFromPS(player):
            if player.getPathFindingNodeKey() == endNodeKey:
                return 'correct end node'
            return 'incorrect end node: %r' % (player.getPathFindingNodeKey(),)
        blockPaths.nodeFromPlayerState = Mock(side_effect=nodeFromPS)

        node = PreCalculatedNode(
            blockPaths, block=self.blockDefs[0],
            obstacle=obstacle, posIndex=posIndex)

        log.info('Simulating all actions')
        if len(self.blockDefs) > 1:
            endBlockPaths = blockPaths
        else:
            endBlockPaths = None
        outcomes = list(node.findOutcomes(
            self.world, self.blockDefs[0], self.blockDefs[-1], actionKinds,
            endBlockPaths=endBlockPaths))
        if expectNoResults:
            assert len(outcomes) == 0
            cost = orbTagCost = None
        else:
            assert len(outcomes) == 1
            steps, finalNode, cost, orbTagCost = outcomes[0]
            assert finalNode == 'correct end node'
            assert steps == actionKinds
            log.info('  Cost: %r  orbTagCost: %r', cost, orbTagCost)

        theseActions = actionKinds[:-1]
        while theseActions:
            log.info('Simulating %s + ...', ','.join(
                aK.__name__ for aK in theseActions))
            outcomes = list(node.findOutcomes(
                self.world, self.blockDefs[0], self.blockDefs[-1],
                theseActions, endBlockPaths=blockPaths))

            for steps, finalNode, thisCost, thisOrbCost in outcomes:
                if steps == actionKinds:
                    assert not expectNoResults, 'path unexpectedly found'
                    assert finalNode == 'correct end node'
                    assert thisCost == cost
                    assert thisOrbCost == orbTagCost
                    break
            else:
                assert expectNoResults, 'path not found'

            theseActions.pop()
        return cost, orbTagCost


class PredefinedActionsOrder(BotOrder):
    def __init__(self, bot, sequence):
        super(PredefinedActionsOrder, self).__init__(bot)
        self.sequence = sequence
        self.lastResult = None
        self.dbDuration = None
        self.currentTick = 0
        self.startTick = 0
        self.done = False

    def setCurrentTick(self, tick):
        self.currentTick = tick

    def start(self):
        super(PredefinedActionsOrder, self).start()
        self.bot.future.clear()

    def requestMoreFuture(self):
        if self.done:
            if not self.bot.future.hasActions():
                self.bot.orderFinished()
            return

        log.info('More future requested')
        if self.lastResult is not None:
            log.info('Checking prediction from actions...')
            nodeKey = self.bot.future.getPlayer().getPathFindingNodeKey()
            assert nodeKey == self.lastResult, 'future mismatch'

        futureTick = self.currentTick + sum(
            len(ar.simulator.positions) - 1
            for ar in self.bot.future.actionRecords)
        log.info(
            'tick is %r, predicted until %r', self.currentTick, futureTick)
        log.info('Future predictions:')
        for record in self.bot.future.actionRecords:
            log.info('  %r', record.simulator.positions)
        if self.dbDuration is not None:
            simulatedDuration = futureTick - self.startTick
            assert simulatedDuration == self.dbDuration

        if not self.sequence:
            self.done = True
            return

        actionKinds, result = self.sequence.pop(0)
        self.lastResult = result
        self.startTick = futureTick
        actionsData = [aK.__name__ for aK in actionKinds]
        log.info('Feeding actions: %r', actionsData)

        futurePlayer = self.bot.future.getPlayer()

        pathFinder = self.bot.world.map.layout.pathFinder
        blockPaths = pathFinder.getBlockPaths(futurePlayer.getMapBlock().defn)
        nodeKey = blockPaths.buildNodeKey(futurePlayer)
        assert nodeKey
        node = blockPaths.getNodeFromKey(nodeKey)
        exitDir = None
        for edge in node['edges']:
            if edge['actions'] == actionsData:
                break
        else:
            for exitDir, edge in node['targets'].iteritems():
                if edge['actions'] == actionsData:
                    break
            else:
                assert False, 'path from here not in DB'

        self.bot.future.expandEdge(edge, exitDir)
        if edge['target'] is not None:
            if result is not None:
                assert edge['target'] == result, 'DB and test mismatch'
            else:
                self.lastResult = edge['target']

            self.dbDuration = edge['cost']
        else:
            self.dbDuration = None


def test_open_empty_edge_glitch():
    '''
    The "bckOpenEmpty" map block used to have a glitch where the
    pathfinding database thinks that you can transition from the top corner
    across, but in actual fact you rarely can, because you come so close to
    the top of the map block that you catch on things in the map block above.
    This test checks the simulator (used in database generation) for this.
    '''
    simulator = MapSimulator()
    simulator.loadTransition(
        fromBlock='bckOpenEmpty', fromReversed=False,
        toBlock='topBlockedEmpty', toReversed=False,
    )
    simulator.runSimulation(
        startNodeKey=(11, -2),
        actionKinds=[JumpLeft, FallLeft],
        expectNoResults=True,
    )


def test_database_mismatch():
    simulator = MapSimulator()
    #simulator.loadBlock('bckOpenEmpty', reversedBlock=True)
    simulator.loadTransition(
        fromBlock='bckOpenEmpty', fromReversed=True,
        toBlock='bckOpenEmpty', toReversed=False,
        upwards=False,
    )
    simulator.runActions(start=(6, 5), sequence=[
        ([MoveLeft], (6, 1)),
    ])
