import logging
import random

from trosnoth.bots.goalsetter import (
    GoalSetterBot, Goal, RespawnNearZone, MessAroundInZone,
    ZoneMixin,
)
from trosnoth.const import (
    BOT_GOAL_HUNT_RABBITS, BOT_GOAL_SCORE_TROSBALL_POINT, BOT_GOAL_CAPTURE_MAP,
)
from trosnoth.model import upgrades
from trosnoth.utils.math import distance

log = logging.getLogger(__name__)


class ReachCurrentObjective(Goal):
    '''
    Notices what the current level's botGoal is and tries to achieve that goal.
    '''
    def start(self):
        self.bot.player.onRemovedFromGame.addListener(self.removedFromGame)
        self.bot.agent.localState.onGameInfoChanged.addListener(
            self.reevaluate)

    def stop(self):
        super(ReachCurrentObjective, self).stop()
        self.bot.agent.localState.onGameInfoChanged.removeListener(
            self.reevaluate)
        self.bot.player.onRemovedFromGame.removeListener(self.removedFromGame)

    def removedFromGame(self, playerId):
        self.returnToParent()

    def reevaluate(self):
        self.bot.setUpgradePolicy(None)
        botGoal = self.bot.agent.localState.botGoal
        if botGoal == BOT_GOAL_SCORE_TROSBALL_POINT:
            self.setSubGoal(ScoreTrosballPoint(self.bot, self))
        elif botGoal == BOT_GOAL_HUNT_RABBITS:
            # Rabbit hunt
            self.setSubGoal(HuntTheRabbits(self.bot, self))
        elif botGoal == BOT_GOAL_CAPTURE_MAP:
            self.setSubGoal(WinStandardTrosnothGame(self.bot, self))
        else:
            self.setSubGoal(RunAroundKillingHumans(self.bot, self))


class ScoreTrosballPoint(Goal):
    def start(self):
        self.bot.onOrderFinished.addListener(self.orderFinished)
        self.nextCheck = None
        super(ScoreTrosballPoint, self).start()

    def stop(self):
        self.bot.onOrderFinished.removeListener(self.orderFinished)
        if self.nextCheck:
            self.nextCheck.cancel()
        super(ScoreTrosballPoint, self).stop()

    def orderFinished(self):
        if self.subGoal is None:
            self.reevaluate()

    def reevaluate(self):
        if not self.bot.world.trosballManager.enabled:
            self.returnToParent()
            return
        player = self.bot.player
        world = self.bot.world

        if self.nextCheck:
            self.nextCheck.cancel()
        delay = 2.5 + random.random()
        self.nextCheck = world.callLater(delay, self.reevaluate)

        if player.dead:
            pos = world.trosballManager.getPosition()
            zone = world.map.getZoneAtPoint(pos)
            self.setSubGoal(RespawnNearZone(self.bot, self, zone))
        elif player.hasTrosball():
            zoneDef = world.trosballManager.getTargetZoneDefn(player.team)
            self.bot.moveToOrb(world.zoneWithDef[zoneDef])
        elif world.trosballManager.trosballPlayer:
            trosballPlayer = world.trosballManager.trosballPlayer
            if player.isFriendsWith(trosballPlayer):
                self.bot.followPlayer(trosballPlayer)
            else:
                self.bot.attackPlayer(trosballPlayer)
        else:
            self.bot.collectTrosball()


class RunAroundKillingThings(Goal):
    def start(self):
        self.nextCheck = None
        self.scheduleNextCheck()

    def stop(self):
        super(RunAroundKillingThings, self).stop()

    def scheduleNextCheck(self):
        self.cancelNextCheck()
        delay = 2.5 + random.random()
        self.nextCheck = self.bot.world.callLater(delay, self.reevaluate)

    def cancelNextCheck(self):
        if self.nextCheck:
            self.nextCheck.cancel()
            self.nextCheck = None

    def reevaluate(self, *args, **kwargs):
        self.cancelNextCheck()

        player = self.bot.player

        if player.dead:
            zone = self.selectZone()
            if zone is None:
                zone = player.getZone()
                if zone is None:
                    zone = random.choice(list(self.bot.world.zones))
            self.setSubGoal(RespawnNearZone(self.bot, self, zone))
            self.scheduleNextCheck()
            return

        if player.getZone() and self.zoneIsOk(player.getZone()):
            # There are enemies here
            self.setSubGoal(MessAroundInZone(self.bot, self))
            self.scheduleNextCheck()
            return

        zone = self.selectZone()
        if zone:
            self.bot.moveToOrb(zone)
        else:
            self.setSubGoal(MessAroundInZone(self.bot, self))
        self.scheduleNextCheck()

    def zoneIsOk(self, zone):
        return any(
            (not p.dead and not self.bot.player.isFriendsWith(p))
            for p in zone.players)

    def selectZone(self):
        options = []
        for zone in self.bot.world.zones:
            if self.zoneIsOk(zone):
                options.append(zone)
        if not options:
            return None
        return random.choice(options)


class RunAroundKillingHumans(RunAroundKillingThings):
    def zoneIsOk(self, zone):
        return any(
            (not p.dead and not self.bot.player.isFriendsWith(p) and not p.bot)
            for p in zone.players)


class HuntTheRabbits(Goal):
    def start(self):
        self.huntedPlayer = None
        self.bot.onOrderFinished.addListener(self.orderFinished)
        self.bot.player.onRespawned.addListener(self.respawned)
        super(HuntTheRabbits, self).start()

    def stop(self):
        self.bot.onOrderFinished.removeListener(self.orderFinished)
        self.bot.player.onRespawned.removeListener(self.respawned)
        super(HuntTheRabbits, self).stop()

    def orderFinished(self):
        if self.subGoal is None:
            self.reevaluate()

    def respawned(self):
        self.reevaluate()

    def isEnemyRabbit(self, p):
        if p.dead:
            return False
        if self.bot.player.isFriendsWith(p):
            return False
        return p.team is not None

    def reevaluate(self):
        if not (self.huntedPlayer and self.isEnemyRabbit(self.huntedPlayer)):
            rabbits = [
                p for p in self.bot.world.players if self.isEnemyRabbit(p)]
            if not rabbits:
                if self.bot.player.dead:
                    self.bot.respawn()
                    return

                # All survining rabbits are on this player's team
                self.setSubGoal(RunAway(self.bot, self))
                return
            self.huntedPlayer = random.choice(rabbits)

        if self.bot.player.dead:
            rabbitZone = self.huntedPlayer.getZone()
            if rabbitZone is None:
                self.bot.respawn()
            else:
                self.setSubGoal(RespawnNearZone(self.bot, self, rabbitZone))
            return

        self.bot.attackPlayer(self.huntedPlayer)


class RunAway(Goal):
    '''
    Used when this is the last rabbit alive. Selects the zone furthest from
    the player and moves to it.
    '''
    def start(self):
        self.bot.onOrderFinished.addListener(self.orderFinished)
        super(RunAway, self).start()

    def stop(self):
        self.bot.onOrderFinished.removeListener(self.orderFinished)
        super(RunAway, self).stop()

    def orderFinished(self):
        self.reevaluate()

    def reevaluate(self):
        if self.bot.player.dead:
            self.returnToParent()
            return

        playerPos = self.bot.player.pos
        targetZone = max(
            self.bot.world.zones,
            key=lambda z: distance(z.defn.pos, playerPos))
        self.bot.moveToOrb(targetZone)


class WinStandardTrosnothGame(Goal):
    '''
    Win the current game of Trosnoth by capturing all the zones.
    '''

    def start(self):
        self.bot.setUpgradePolicy(upgrades.Shield, delay=6)

        self.nextCheck = None
        self.scheduleNextCheck()

    def scheduleNextCheck(self):
        self.cancelNextCheck()
        delay = 2.5 + random.random()
        self.nextCheck = self.bot.world.callLater(delay, self.reevaluate)

    def cancelNextCheck(self):
        if self.nextCheck:
            self.nextCheck.cancel()
            self.nextCheck = None

    def stop(self):
        super(WinStandardTrosnothGame, self).stop()
        self.cancelNextCheck()

    def reevaluate(self, *args, **kwargs):
        '''
        Decide whether to stay in the current zone, or move to another.
        '''
        self.cancelNextCheck()

        player = self.bot.player
        myZone = player.getZone()

        # 1. If we're defending a borderline zone, stay in the zone
        if myZone and myZone.owner == player.team and myZone.isBorderline():
            self.setSubGoal(DefendZone(self.bot, self, myZone))
            self.scheduleNextCheck()
            return

        # 2. If we're attacking a capturable zone, stay in the zone
        if (
                myZone and myZone.owner != player.team
                and myZone.isCapturableBy(player.team)):
            self.setSubGoal(CaptureZone(self.bot, self, myZone))
            self.scheduleNextCheck()
            return

        # 3. Score other zones based on how helpful it would be to be there and
        #    how likely we are to get there in time.

        if player.dead or myZone is None:
            zone = self.getMostUrgentZone()
        else:
            zone = self.getMostLikelyUrgentZone(myZone)

        if zone is None:
            self.returnToParent()
        elif zone.owner == player.team:
            self.setSubGoal(DefendZone(self.bot, self, zone))
        else:
            self.setSubGoal(CaptureZone(self.bot, self, zone))

        self.scheduleNextCheck()

    def getMostUrgentZone(self):
        bestScore = 0
        bestOptions = []

        for zone in self.bot.world.zones:
            utility = self.getZoneUtility(zone)

            if not [
                    z for z in zone.getAdjacentZones()
                    if z.owner == zone.owner]:
                # This is the last remaining zone
                awesomeness = 5
            else:
                awesomeness = zone.consequenceOfCapture()

            score = utility * awesomeness
            if score == bestScore:
                bestOptions.append(zone)
            elif score > bestScore:
                bestOptions = [zone]
                bestScore = score

        if not bestOptions:
            return None

        return random.choice(bestOptions)

    def getMostLikelyUrgentZone(self, myZone):
        bestScore = 0
        bestOptions = []
        seen = set()
        pending = [(myZone, 1.0)]
        while pending:
            zone, likelihood = pending.pop(0)
            seen.add(zone)

            utility = self.getZoneUtility(zone)

            if not [
                    z for z in zone.getAdjacentZones()
                    if z.owner == zone.owner]:
                # This is the last remaining zone
                awesomeness = 5
            else:
                awesomeness = zone.consequenceOfCapture()

            score = likelihood * utility * awesomeness
            if score == bestScore:
                bestOptions.append(zone)
            elif score > bestScore:
                bestOptions = [zone]
                bestScore = score

            likelihood *= 0.7
            for other in zone.getUnblockedNeighbours():
                if other not in seen:
                    pending.append((other, likelihood))

        if not bestOptions:
            return None

        return random.choice(bestOptions)

    def getZoneUtility(self, zone):
        player = self.bot.player
        alreadyHere = player.getZone() == zone and not player.dead

        # Count the number of friendly players and players on the most
        # likely enemy team to tag the zone.
        enemy = friendly = 0
        for count, teams in zone.getPlayerCounts():
            if player.team in teams and not friendly:
                friendly = count
            if [t for t in teams if t != player.team] and not enemy:
                enemy = count
            if friendly and enemy:
                break

        if zone.owner == player.team:
            defence = min(3, friendly)
            if not alreadyHere:
                defence += 1
            if enemy == 0:
                utility = 0
            elif enemy > defence:
                # There's a slim chance you could shoot them before they
                # capture the zone.
                utility = 0.2 ** (enemy - defence)
            elif enemy == defence:
                # Being here will stop it being tagged
                utility = 1
            else:
                # There's a slim chance the enemy might shoot them
                utility = 0.2 ** (friendly - enemy)
        elif not zone.adjacentToAnotherZoneOwnedBy(player.team):
            # Cannot capture, have no adjacent zones
            utility = 0
        else:
            defence = min(3, enemy)
            if alreadyHere:
                friendly -= 1
            if friendly > defence:
                # Capturable without player, but there's a slim chance
                # teammates might die.
                utility = 0.2 ** (friendly - defence)
            elif friendly == defence:
                # Being here enables the zone tag
                utility = 1
            else:
                # There's a slim chance you could shoot them and capture
                utility = 0.2 ** (friendly - enemy)
        return utility


class CaptureZone(ZoneMixin, Goal):
    '''
    Respawns if necessary, moves to the given zone, messes around until it's
    capturable, and captures it. If the player dies, respawns and tries again.
    Returns if the zone is captured or becomes uncapturable by virtue of having
    no adjacent zones owned by the team.
    '''

    def __init__(self, bot, parent, zone):
        super(CaptureZone, self).__init__(bot, parent)
        self.zone = zone

    def start(self):
        self.bot.onOrderFinished.addListener(self.orderFinished)
        super(CaptureZone, self).start()

    def stop(self):
        super(CaptureZone, self).stop()
        self.bot.onOrderFinished.removeListener(self.orderFinished)

    def orderFinished(self):
        self.reevaluate()

    def reevaluate(self):
        player = self.bot.player
        if self.zone.owner == player.team:
            self.returnToParent()
            return

        if not self.zone.adjacentToAnotherZoneOwnedBy(player.team):
            self.returnToParent()
            return

        if player.dead:
            self.setSubGoal(RespawnNearZone(self.bot, self, self.zone))
            return

        playerZone = player.getZone()
        if playerZone == self.zone:
            if self.zone.isCapturableBy(player.team):
                self.bot.moveToOrb(self.zone)
            else:
                self.setSubGoal(KillEnemyInZone(self.bot, self))
        else:
            self.bot.moveToZone(self.zone)


class DefendZone(ZoneMixin, Goal):
    '''
    Respawns if necessary, moves to the given zone and messes around there.
    If the player dies, respawns and continues. Returns if the zone is
    captured or neutralised.
    '''

    def __init__(self, bot, parent, zone):
        super(DefendZone, self).__init__(bot, parent)
        self.zone = zone

    def reevaluate(self):
        player = self.bot.player
        if self.zone.owner != player.team:
            self.returnToParent()
            return

        if player.dead:
            self.setSubGoal(RespawnNearZone(self.bot, self, self.zone))
            return

        playerZone = player.getZone()
        if playerZone == self.zone:
            teamsWhoCanTag = self.zone.teamsAbleToTag() - {player.team}
            if teamsWhoCanTag:
                # Our only hope is to kill someone
                self.setSubGoal(KillEnemyInZone(self.bot, self))
            else:
                self.setSubGoal(MessAroundInZone(self.bot, self))
        else:
            self.bot.moveToOrb(self.zone)


class KillEnemyInZone(Goal):
    '''
    Tries to kill the nearest enemy while staying in the current zone.
    Completes if the number of players in the zone changes. Aborts if the
    player dies or leaves the zone.
    '''

    def __init__(self, bot, parent):
        super(KillEnemyInZone, self).__init__(bot, parent)
        self.zone = self.bot.player.getZone()
        self.playersInZone = set(p for p in self.zone.players if not p.dead)
        self.nextCheck = None

    def start(self):
        super(KillEnemyInZone, self).start()
        self.scheduleNextCheck()

    def stop(self):
        super(KillEnemyInZone, self).stop()
        self.cancelNextCheck()

    def scheduleNextCheck(self):
        self.cancelNextCheck()
        delay = 1
        self.nextCheck = self.bot.world.callLater(delay, self.reevaluate)

    def cancelNextCheck(self):
        if self.nextCheck:
            self.nextCheck.cancel()
            self.nextCheck = None

    def reevaluate(self):
        if self.bot.player.dead:
            self.returnToParent()
            return

        zone = self.bot.player.getZone()
        if zone != self.zone:
            self.returnToParent()
            return

        playersInZone = set(p for p in zone.players if not p.dead)
        if playersInZone != self.playersInZone:
            self.returnToParent()
            return

        enemiesInZone = [
            p for p in playersInZone if not p.isFriendsWith(self.bot.player)]
        if not enemiesInZone:
            self.returnToParent()
            return

        target = min(
            enemiesInZone, key=lambda p: distance(p.pos, self.bot.player.pos))
        self.bot.attackPlayer(target)


class RangerBot(GoalSetterBot):
    nick = 'RangerBot'
    playable = True

    MainGoalClass = ReachCurrentObjective


BotClass = RangerBot
