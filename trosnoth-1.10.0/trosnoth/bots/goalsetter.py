import logging
import random
from twisted.internet import reactor

from trosnoth.bots.base import Bot
from trosnoth.bots.pathfinding import EAST, WEST, ORB
from trosnoth.messages import TickMsg
from trosnoth.utils.event import Event

log = logging.getLogger(__name__)


class GoalSetterBot(Bot):
    '''
    Base class for bots which mainly operate by setting high-level goals, which
    may themselves set subgoals.
    '''

    # Override this in subclasses to set the main goal for this bot to achieve
    MainGoalClass = None

    def start(self):
        super(GoalSetterBot, self).start()

        self.onTick = Event()
        self.onOrderFinished = Event()
        self.recentGoals = {}
        self.clearRecent = None
        self.mainGoal = self.MainGoalClass(self, None)

        self.mainGoal.start()

    def disable(self):
        super(GoalSetterBot, self).disable()
        self.mainGoal.stop()
        if self.clearRecent:
            self.clearRecent.cancel()
            self.clearRecent = None

    def showGoalStack(self):
        '''
        For debugging.
        '''
        log.error('Goal stack for %s:', self.player)
        curGoal = self.mainGoal
        while curGoal:
            log.error('  %s', curGoal)
            curGoal = curGoal.subGoal
        log.error('')

    def subGoalStopped(self, goal):
        # Record recent inactive goals so they can be reused if they come up
        # again.
        self.recentGoals[goal] = goal
        if self.clearRecent:
            self.clearRecent.cancel()
            self.clearRecent = None
        self.clearRecent = self.world.callLater(4, self.clearRecentGoals)

    def startingSubGoal(self, goal):
        if goal in self.recentGoals:
            del self.recentGoals[goal]

    def clearRecentGoals(self):
        self.clearRecent = None
        self.recentGoals.clear()

    def checkGoal(self, goal):
        result = self.recentGoals.get(goal, goal)
        result.parent = goal.parent
        return result

    @TickMsg.handler
    def handle_TickMsg(self, msg):
        self.onTick()
        super(GoalSetterBot, self).handle_TickMsg(msg)

    def orderFinished(self):
        super(GoalSetterBot, self).orderFinished()
        self.onOrderFinished()


class Goal(object):
    '''
    Represents something that the bot is trying to achieve.
    '''

    def __init__(self, bot, parent):
        self.bot = bot
        self.parent = parent
        self.subGoal = None

    def __str__(self):
        return self.__class__.__name__

    def start(self):
        '''
        Called when this goal should begin its work.
        '''
        self.reevaluate()

    def stop(self):
        '''
        Should disable any active components of this goal.
        '''
        if self.subGoal:
            self.subGoal.stop()
            self.subGoal = None

    def setSubGoal(self, goal):
        '''
        If the given goal is already the current sub-goal, does nothing.
        Otherwise, stops the current sub-goal, and starts the given one.
        '''
        if self.subGoal == goal:
            return
        if self.subGoal:
            self.subGoal.stop()
            self.subGoal.parent = None
            self.bot.subGoalStopped(goal)

        if goal:
            goal = self.bot.checkGoal(goal)
            self.subGoal = goal
            self.bot.startingSubGoal(goal)
            goal.start()
        else:
            self.subGoal = None

    def returnToParent(self):
        '''
        Call this method to tell the parent goal that this goal is either
        completed, or no longer relevant.
        '''
        if self.parent:
            reactor.callLater(0, self.parent.returnedFromChild, self)

    def returnedFromChild(self, child):
        '''
        Called by child's returnToParent() method. The default implementation
        checks that the returning child is this goal's subgoal, then calls
        reevaluate().
        '''
        if child is self.subGoal:
            self.reevaluate()
        else:
            self.bot.subGoalStopped(child)

    def reevaluate(self):
        '''
        Called by the default implementations of start() and
        returnedFromChild() to determine what this goal should do next.
        '''
        pass


class ZoneMixin(Goal):
    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return other.zone == self.zone

    def __str__(self):
        return '%s(%s)' % (self.__class__.__name__, self.zone)


class MessAroundInZone(Goal):
    '''
    Wander around in the zone the player is in at the time of construction.
    Mostly random, but has a slight tendency to move towards the orb.
    Aborts if the player dies or leaves the zone.
    '''

    def __init__(self, bot, parent):
        super(MessAroundInZone, self).__init__(bot, parent)
        self.zone = self.bot.player.getZone()

    def start(self):
        self.bot.onTick.addListener(self.tick)
        self.bot.standStill()
        super(MessAroundInZone, self).start()

    def stop(self):
        super(MessAroundInZone, self).stop()
        self.bot.onTick.removeListener(self.tick)

    def reevaluate(self):
        if self.bot.player.dead:
            self.returnToParent()
            return

        futurePlayer = self.bot.future.getPlayer()
        zone = futurePlayer.getZone()
        if zone != self.zone:
            self.returnToParent()
            return

        if self.bot.future.hasActions():
            return

        pathFinder = self.bot.world.map.layout.pathFinder
        if pathFinder is None:
            # Can't do anything without a path-finding database loaded
            log.warning('No pathfinding database loaded')
            self.stop()
            return

        if self.bot.player.attachedObstacle is None:
            self.bot.future.land()
            return

        if random.random() < 0.1:
            # Move towards the orb
            block = futurePlayer.getMapBlock()
            if block.defn.kind in ('top', 'btm'):
                exit = ORB
            elif block.defn.rect.centerx < zone.defn.pos[0]:
                exit = EAST
            else:
                exit = WEST
            edge = pathFinder.getExitEdge(self.bot.player, exit)
        else:
            # Move randomly
            edges = pathFinder.getAllEdges(self.bot.player)
            exit = None
            if edges:
                edge = random.choice(edges)
            else:
                edge = None

        if edge is None:
            self.returnToParent()
        else:
            self.bot.future.expandEdge(edge, exit)

    def tick(self):
        player = self.bot.player
        if player.dead:
            self.returnToParent()
            return

        if not self.bot.future.hasActions():
            self.reevaluate()


class RespawnNearZone(ZoneMixin, Goal):
    '''
    Respawns in a zone that's as close as possible to the given zone.
    '''

    def __init__(self, bot, parent, zone):
        super(RespawnNearZone, self).__init__(bot, parent)
        self.zone = zone

    def start(self):
        self.bot.world.onZoneTagged.addListener(self.zoneTagged)
        self.bot.onOrderFinished.addListener(self.orderFinished)
        super(RespawnNearZone, self).start()

    def stop(self):
        super(RespawnNearZone, self).stop()
        self.bot.world.onZoneTagged.removeListener(self.zoneTagged)
        self.bot.onOrderFinished.removeListener(self.orderFinished)

    def zoneTagged(self, *args, **kwargs):
        '''
        We may be waiting to respawn in a zone that's just changed ownership.
        '''
        self.reevaluate()

    def orderFinished(self):
        self.reevaluate()

    def reevaluate(self):
        player = self.bot.player
        if not player.dead:
            self.returnToParent()
            return

        bestZone = self.zone
        zones = [self.zone]
        seen = set()

        while zones:
            zone = zones.pop(0)
            seen.add(zone)
            if player.isZoneRespawnable(zone):
                bestZone = zone
                break
            adjacent = [
                z for z in zone.getUnblockedNeighbours() if z not in seen]
            random.shuffle(adjacent)
            zones.extend(adjacent)

        self.bot.respawn(zone=bestZone)
