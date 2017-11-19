import copy
import logging
from math import sin, cos, atan2, sqrt

from trosnoth.const import SHOT_DEATH, GRENADE_DEATH
from trosnoth.model.unit import Unit, Bouncy, PredictedBouncyTrajectory
from trosnoth.utils.collision import collideTrajectory

log = logging.getLogger('shot')

GRENADE_BLAST_RADIUS = 448


class LocalSprite(object):
    '''
    Mixin for representing the local player's shots and grenades.
    These go slowly until their real counterpart catches up.
    '''

    def __init__(self, *args, **kwargs):
        super(LocalSprite, self).__init__(*args, **kwargs)
        self.nextPos = None
        self.localTicks = 0
        self.realTicks = 0
        self.realShotStarted = False
        self.realShotCaughtUp = False

    def advance(self):
        if self.realShotCaughtUp:
            super(LocalSprite, self).advance()
            return

        if self.realShotStarted:
            self.realTicks += 1

        if self.nextPos:
            self.pos = self.nextPos
            self.nextPos = None
            self.localTicks += 1
            if self.realTicks >= self.localTicks:
                self.realShotCaughtUp = True
        else:
            super(LocalSprite, self).advance()
            self.nextPos = self.pos
            self.pos = (
                0.5 * self.pos[0] + 0.5 * self.oldPos[0],
                0.5 * self.pos[1] + 0.5 * self.oldPos[1],
            )


class GrenadeShot(Bouncy):
    '''
    This will make the grenade have the same physics as a player without
    control and features of player movement
    '''

    HALF_WIDTH = 5
    HALF_HEIGHT = 5

    def __init__(self, world, player, duration, *args, **kwargs):
        Bouncy.__init__(self, world, *args, **kwargs)
        self.player = player
        self.timeLeft = duration

        # Place myself.
        self.pos = self.oldPos = player.pos
        angle = player.angleFacing
        self.xVel = self.world.physics.grenadeInitVel * sin(angle)
        self.yVel = -self.world.physics.grenadeInitVel * cos(angle)

    def getGravity(self):
        return self.world.physics.grenadeGravity

    def getMaxFallVel(self):
        return self.world.physics.grenadeMaxFallVel

    def advance(self):
        super(GrenadeShot, self).advance()
        self.timeLeft -= self.world.tickPeriod
        if self.timeLeft <= 0:
            xpos, ypos = self.pos
            self.propagateExplosionEvent()

            for player in self.world.players:
                if (
                        player.isFriendsWith(self.player) or player.phaseshift
                        or player.isInvulnerable() or player.turret
                        or player.dead):
                    continue
                dist = ((player.pos[0] - xpos) ** 2 +
                        (player.pos[1] - ypos) ** 2) ** 0.5
                if dist <= GRENADE_BLAST_RADIUS:
                    # Account for possibility player has left game
                    killer = (
                        self.player if self.player in self.world.players
                        else None)
                    player.zombieHit(killer, None, GRENADE_DEATH)
            self.removeGrenade()

    def propagateExplosionEvent(self):
        self.world.onGrenadeExplosion(self.pos, GRENADE_BLAST_RADIUS)

    def removeGrenade(self):
        self.world.removeGrenade(self)


class LocalGrenade(LocalSprite, GrenadeShot):
    def __init__(self, localState, *args, **kwargs):
        super(LocalGrenade, self).__init__(*args, **kwargs)
        self.localState = localState

    def propagateExplosionEvent(self):
        pass

    def removeGrenade(self):
        self.localState.grenadeRemoved()


class PredictedGrenadeTrajectory(PredictedBouncyTrajectory):

    HALF_WIDTH = GrenadeShot.HALF_WIDTH
    HALF_HEIGHT = GrenadeShot.HALF_HEIGHT

    def __init__(self, world, player, duration):
        PredictedBouncyTrajectory.__init__(self,
                                           world,
                                           player,
                                           duration,
                                           world.physics.grenadeInitVel,
                                           world.physics.grenadeGravity,
                                           world.physics.grenadeMaxFallVel)

    def explosionRadius(self):
        return GRENADE_BLAST_RADIUS


class Shot(Unit):

    NORMAL = 'normal'
    TURRET = 'turret'
    RICOCHET = 'ricochet'

    HALF_WIDTH = 5
    HALF_HEIGHT = 5

    playerCollisionTolerance = 20

    def __init__(
            self, world, id, team, player, pos, velocity, kind, lifetime,
            *args, **kwargs):
        super(Shot, self).__init__(world, *args, **kwargs)

        self.id = id
        self.team = team
        self.pos = tuple(pos)
        self.futurePositions = []
        self.futureVelocities = []
        self.futureBounce = None
        self.originatingPlayer = player
        self.vel = tuple(velocity)
        self.timeLeft = lifetime
        self.kind = kind
        self.expired = False
        self.justFired = True
        self.hasBounced = False

    def isSolid(self):
        return self.kind != Shot.TURRET

    def checkCollision(self, player):
        if player.isFriendsWith(self.originatingPlayer):
            return False
        return self.checkCollisionsWithPoints(player.oldPos, player.pos)

    def checkCollisionsWithPoints(self, oldPos, newPos, ticksInFuture=0):
        '''
        Checks whether a player moving between the given points will collide
        with this shot. If futureTicks is given, it is the number of ticks
        in the future (for this shot) that we are checking these points.
        '''
        oldShotPos, newShotPos = self.getFuturePoints(ticksInFuture)
        if oldShotPos is None:
            # Shot has expired
            return False

        # Check both player colliding with us and us colliding with player
        if collideTrajectory(
                newPos, oldShotPos,
                (newShotPos[0] - oldShotPos[0], newShotPos[1] - oldShotPos[1]),
                self.playerCollisionTolerance):
            return True

        deltaX = newPos[0] - oldPos[0]
        deltaY = newPos[1] - oldPos[1]
        if collideTrajectory(
                newShotPos, oldPos, (deltaX, deltaY),
                self.playerCollisionTolerance):
            return True
        return False

    def collidedWithPlayer(self, player):
        self.expired = True
        player.onHitByShot(self)
        self.originatingPlayer.onShotHitSomething(self)
        if player.turret or player.isInvulnerable() or player.phaseshift:
            return
        player.zombieHit(self.originatingPlayer, self, SHOT_DEATH)
        self.originatingPlayer.onShotHurtPlayer(player, self)

    def getFuturePoints(self, ticksInFuture=0):
        '''
        @return: (oldPos, newPos) for a tick the given number of ticks in
            the future, or (None, None) if the shot has expired by that
            time. Calls extendFuturePositions() if needed.
        '''
        if self.expired:
            return None, None
        if ticksInFuture == 0:
            return self.oldPos, self.pos
        ticksLeft = self.timeLeft // self.world.tickPeriod
        if ticksInFuture > ticksLeft:
            return None, None

        while len(self.futurePositions) < ticksInFuture:
            if self.futureHasExpired():
                return None, None
            self.extendFuturePositions()

        if ticksInFuture < 2:
            assert ticksInFuture == 1
            oldPos = self.pos
        else:
            oldPos = self.futurePositions[ticksInFuture - 2]
        newPos = self.futurePositions[ticksInFuture - 1]
        if newPos is None:
            oldPos = None
        return oldPos, newPos

    def futureHasExpired(self):
        if self.expired:
            return True
        return self.futurePositions and self.futurePositions[-1] is None

    def getFutureVelocity(self):
        if self.futureVelocities:
            return self.futureVelocities[-1]
        return self.vel

    def extendFuturePositions(self):
        unit = copy.copy(self)
        unit.oldPos, unit.pos = self.getFuturePoints(len(self.futurePositions))
        unit.vel = self.getFutureVelocity()

        deltaT = self.world.tickPeriod
        dX, dY = self.vel[0] * deltaT, self.vel[1] * deltaT
        obstacle = self.world.physics.moveUnit(unit, dX, dY)

        bouncing = False
        expired = False
        if obstacle is not None:
            if self.kind == Shot.RICOCHET:
                self.rebound(unit, obstacle)
                bouncing = True
            else:
                expired = True

        self.futurePositions.append(unit.pos)
        self.futureVelocities.append(unit.vel)
        if expired:
            self.futurePositions.append(None)
            self.futureVelocities.append(unit.vel)
        if bouncing and self.futureBounce is None:
            self.futureBounce = len(self.futurePositions)

    def advance(self):
        '''
        Called by the universe when this shot should update its position.
        '''
        if self.expired:
            return
        self.justFired = False

        deltaT = self.world.tickPeriod

        # Shots have a finite lifetime.
        self.timeLeft = self.timeLeft - deltaT
        if self.timeLeft <= 0:
            self.expired = True
            return

        oldPos, pos = self.getFuturePoints(ticksInFuture=1)
        if self.futurePositions:
            self.futurePositions.pop(0)
            self.vel = self.futureVelocities.pop(0)
            if self.futureBounce is not None:
                self.futureBounce = max(0, self.futureBounce - 1)
                if self.futureBounce == 0:
                    self.hasBounced = True
        if pos is None:
            self.expired = True
        else:
            self.pos = pos

    def rebound(self, unit, obstacle):
        '''
        Shot is a ricochet shot and it's hit an obstacle.
        '''
        obsAngle = obstacle.getAngle()
        shotAngle = atan2(unit.vel[1], unit.vel[0])
        dif = shotAngle - obsAngle
        final = obsAngle - dif
        speed = sqrt(unit.vel[0] * unit.vel[0] + unit.vel[1] * unit.vel[1])
        unit.vel = (speed * cos(final), speed * sin(final))


class LocalShot(LocalSprite, Shot):
    def advance(self):
        self.justFired = False
        super(LocalShot, self).advance()
