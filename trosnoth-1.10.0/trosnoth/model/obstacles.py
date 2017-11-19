from math import atan2, sin, cos, pi, floor
import logging

from trosnoth.const import PATH_FINDING_DISCRETISATION_UNIT as D_UNIT
from trosnoth.utils import math

log = logging.getLogger(__name__)


class Obstaclish(object):
    ground = False
    drop = False
    jumpable = False
    grabbable = False
    isObstacle = False

    obstacleId = None

    def getAngle(self):
        '''
        Must return the angle of this obstacle. Used when a shot bounces off
        this obstacle.
        '''

    def collide(self, unit, deltaX, deltaY):
        '''
        Called to see whether the given unit would collide with this obstacle
        given its trajectory. Returns the original (deltaX, deltaY) if the unit
        would not collide with the obstacle, or if the unit would collide with
        the obstacle, returns the new (deltaX, deltaY) to bring the unit into
        contact with the obstacle.
        '''

    def finalPosition(self, unit, deltaX, deltaY):
        '''
        Returns the final position of the given unit which is attempting to
        travel along the given displacement.  May assume that the object hits
        this obstacle on the way.  If the final position is simply the
        collision point, should return None.
        '''
        return None

    def hitByPlayer(self, player):
        pass

    def walkTrajectory(self, vel, deltaTime):
        '''
        Returns the displacement that a player would be going on this
        surface if they would travel, given an absolute velocity and an amount
        of time.

        Only relevant if ground is True.
        '''
        raise NotImplementedError(
            '%s.walkTrajectory' % (self.__class__.__name__,))

    def checkBounds(self, unit, deltaX, deltaY):
        '''
        Checks whether the given point is beyond the bounds of this piece of
        ground. Returns (obstacle, pos) where obstacle is this or another
        ground obstacle that the player has walked to, or None if the player
        has walked off the ground altogether.

        Only relevant if ground is True.
        '''

    def getPosition(self):
        '''
        Should return a point approximately at the centre of this obstacle.
        '''

    def discretise(self, unit, pos):
        '''
        Used for AI path-finding. Should return a position that's approximately
        equal to the given position. Only relevant if jumpable is True.
        '''
        return self.getPositionFromIndex(
            unit, self.getPositionIndex(unit, pos))

    def getPositionIndex(self, unit, pos):
        '''
        Also used for AI path-finding. Should return an integer indicating
        how far along this obstacle the given position lies. Only relevant if
        jumpable is True.
        '''
        raise NotImplementedError(
            '%s.getPositionIndex' % (self.__class__.__name__),)

    def getPositionFromIndex(self, unit, posIndex):
        '''
        Should convert from the given position index to the corresponding
        discretised position. Only relevant if jumpable is True.
        '''
        raise NotImplementedError(
            '%s.getPositionFromIndex' % (self.__class__.__name__),)

    def getPositionIndexBounds(self, unit):
        '''
        Only relevant if jumpable is True. Returns (minIndex, maxIndex) showing
        the bounds on valid position indices for this obstacle.
        '''
        raise NotImplementedError(
            '%s.getPositionIndexBounds' % (self.__class__.__name__),)

    def setId(self, obstacleId):
        '''
        Gives this obstacle an index that is unique within the map block
        layout.
        '''
        self.obstacleId = obstacleId


class Obstacle(Obstaclish):
    '''Represents an obstacle which can't be passed by player or shot.'''
    isObstacle = True

    def __init__(self, pt1, deltaPt):
        self._angle = None
        self.pt1 = pt1
        self.deltaPt = deltaPt

        if deltaPt[0] > 0:
            y = +1
        elif deltaPt[0] < 0:
            y = -1
        else:
            y = 0
        if deltaPt[1] > 0:
            x = -1
        elif deltaPt[1] < 0:
            x = +1
        else:
            x = 0
        self._unitCornerOffset = (x, y)

    @property
    def pt2(self):
        return (self.pt1[0] + self.deltaPt[0],
                self.pt1[1] + self.deltaPt[1])

    def getPosition(self):
        return (self.pt1[0] + 0.5 * self.deltaPt[0],
                self.pt1[1] + 0.5 * self.deltaPt[1])

    def getAngle(self):
        if self._angle is None:
            self._angle = atan2((self.deltaPt[1] + 0.), (self.deltaPt[0] + 0.))
        return self._angle

    def collide(self, unit, deltaX, deltaY, soft=False):
        '''
        Called to see whether the given unit would collide with this obstacle
        given its trajectory. Returns the original (deltaX, deltaY) if the unit
        would not collide with the obstacle, or if the unit would collide with
        the obstacle, returns the new (deltaX, deltaY) to bring the unit into
        contact with the obstacle.
        '''
        unitCorner = (
            unit.pos[0] + self._unitCornerOffset[0] * unit.HALF_WIDTH,
            unit.pos[1] + self._unitCornerOffset[1] * unit.HALF_HEIGHT)
        result = collideTrajectory(
            self.pt1, self.deltaPt, unitCorner, deltaX, deltaY,
            soft=soft, radius=unit.HALF_WIDTH)
        if result is None:
            return deltaX, deltaY
        return result


def joinObstacles(obs1, obs2):
    '''
    Takes two Obstacle objects which are to be joined in a clockwise direction.
    Sets whatever attributes are required to join them, and returns a (possibly
    empty) collection of Corner objects which need to be added in order for
    this join to occur.
    '''
    def getQuadrant(obs):
        dX, dY = obs.deltaPt
        if dY > 0:
            if dX > 0:
                return 1
            elif dX == 0:
                return 1.5
            else:
                return 2
        elif dY < 0:
            if dX < 0:
                return 3
            elif dX == 0:
                return 3.5
            else:
                return 4
        else:
            if dX < 0:
                return 2.5
            else:
                return 0.5

    q1 = getQuadrant(obs1)
    q2 = getQuadrant(obs2)
    pt = obs2.pt1

    if q1 == q2 and (q1 == 4 or q1 == 1):
        obs1.rightGround = obs2
        obs2.leftGround = obs1
        return []

    d = (q1 - q2) % 4
    if d < 2:
        # Concave.
        return []

    if q1 == q2:
        if ((obs1.getAngle() - obs2.getAngle()) % (2 * pi)) < pi:
            # Also concave.
            return []

    result = []
    if q1 in (2, 2.5, 3, 3.5) and q2 in (3.5, 4, 0.5, 1):
        result.append(Corner(pt, (1, -1), (0, 2)))
    if q1 in (3, 3.5, 4, 0.5) and q2 in (0.5, 1, 1.5, 2):
        c = CornerTop(pt)
        result.append(c)
        if obs1.deltaPt[0] > 0:
            obs1.rightGround = c
            c.leftGround = obs1
            assert isinstance(obs1, GroundObstacle)
        if obs2.deltaPt[0] > 0:
            c.rightGround = obs2
            obs2.leftGround = c
            assert isinstance(obs2, GroundObstacle)
    if q1 in (4, 0.5, 1, 1.5) and q2 in (1.5, 2, 2.5, 3):
        result.append(Corner(pt, (-1, 1), (0, -2)))
    if q1 in (1, 1.5, 2, 2.5) and q2 in (2.5, 3, 3.5, 4):
        result.append(Corner(pt, (-1, -1), (2, 0)))
    return result


class Corner(Obstaclish):
    '''
    Note that offset and delta are defined for Corners in the reverse of the
    way in which they are defined for obstacles. This is because Corner
    collision detection collides the corner with the unit rather than the other
    way around.
    '''

    def __init__(self, pt, offset, delta):
        self.pt = pt
        self.offset = offset
        self.delta = delta
        self._angle = atan2((-offset[1] + 0.), (-offset[0] + 0.))

    def getPosition(self):
        return self.pt

    def getAngle(self):
        '''
        Must return the angle of this obstacle. Used when a shot bounces off
        this obstacle.
        '''
        return self._angle

    def collide(self, unit, deltaX, deltaY):
        if self.delta == (0, 2):
            if deltaX <= 0:
                return deltaX, deltaY
        elif self.delta == (0, -2):
            if deltaX >= 0:
                return deltaX, deltaY
        elif self.delta == (2, 0):
            if deltaY >= 0:
                return deltaX, deltaY
        elif self.delta == (-2, 0):
            if deltaY <= 0:
                return deltaX, deltaY

        oPt1 = (unit.pos[0] + self.offset[0] * unit.HALF_WIDTH,
                unit.pos[1] + self.offset[1] * unit.HALF_HEIGHT)
        oDeltaPt = (
            self.delta[0] * unit.HALF_WIDTH,
            self.delta[1] * unit.HALF_HEIGHT)

        result = collideTrajectory(
            oPt1, oDeltaPt, self.pt, -deltaX, -deltaY,
            radius=2, soft=True)
        if result is not None:
            deltaX, deltaY = result
            return -deltaX, -deltaY
        return deltaX, deltaY

    def hitByPlayer(self, player):
        # Stop any upward motion of the player.
        player.yVel = max(player.yVel, 0)
        player._jumpTime = 0

    def finalPosition(self, unit, deltaX, deltaY):
        if self.delta[0] == 0:
            return unit.pos[0], unit.pos[1] + (deltaY / 2)

        if deltaY == 0:
            return None
        return unit.pos[0], unit.pos[1] + deltaY


def playerHitJumpable(self, player):
    '''This obstacle has been hit by player.'''
    if player.world.physics.playerBounce:
        player._jumpTime = player.world.physics.playerMaxJumpTime
        player.yVel = -player.yVel
        player.detachFromEverything()
    else:
        player._jumpTime = 0
        player.yVel = 0


class CornerTop(Corner):
    ground = True
    jumpable = True

    def __init__(self, pt):
        Corner.__init__(self, pt, (1, 1), (-2, 0))
        self.rightGround = None
        self.leftGround = None
        self.subshape = ()

    def checkBounds(self, unit, deltaX, deltaY):
        '''
        Only relevant for the ground section.
        '''
        pt1x = self.pt[0] - unit.HALF_WIDTH
        pt1y = self.pt[1] - unit.HALF_HEIGHT
        pt2x = self.pt[0] + unit.HALF_WIDTH
        pt2y = pt1y

        posX = unit.pos[0] + deltaX
        posY = unit.pos[1] + deltaY
        return checkGroundBounds(
            self, (pt1x, pt1y), (pt2x, pt2y), (posX, posY))

    def walkTrajectory(self, vel, deltaTime):
        return (vel * deltaTime, 0)

    hitByPlayer = playerHitJumpable

    def finalPosition(self, unit, deltaX, deltaY):
        return None

    def getPositionIndex(self, unit, pos):
        return int(floor((pos[0] - self.pt[0]) / D_UNIT + 0.5))

    def getPositionFromIndex(self, unit, posIndex):
        x = self.pt[0] + posIndex * D_UNIT
        minX = self.pt[0] - unit.HALF_WIDTH + 0.1
        maxX = self.pt[0] + unit.HALF_HEIGHT - 0.1
        x = min(maxX, max(minX, x))
        y = self.pt[1] - unit.HALF_HEIGHT
        return (x, y)

    def getPositionIndexBounds(self, unit):
        y = 0   # Doesn't matter because of how discretise() works
        minI = self.getPositionIndex(unit, (self.pt[0] - unit.HALF_HEIGHT, y))
        maxI = self.getPositionIndex(unit, (self.pt[0] + unit.HALF_HEIGHT, y))
        return (minI, maxI)


class JumpableObstacle(Obstacle):
    '''Represents an obstacle that is not a wall.'''
    jumpable = True
    hitByPlayer = playerHitJumpable


class GroundObstacle(JumpableObstacle):
    '''Represents an obstacle that players are allowed to walk on.'''
    ground = True

    def __init__(self, pt1, deltaPt):
        super(GroundObstacle, self).__init__(pt1, deltaPt)
        angle = self.getAngle()
        self.ratio = (cos(angle), sin(angle))
        self.leftGround = None
        self.rightGround = None
        self.subshape = ()

    def walkTrajectory(self, vel, deltaTime):
        '''Returns the displacement that a player would be going on this
        surface if they would travel, given an absolute velocity and an amount
        of time.'''
        return tuple([vel * deltaTime * self.ratio[i] for i in (0, 1)])

    def checkBounds(self, unit, deltaX, deltaY):
        pt1x = self.pt1[0] - self._unitCornerOffset[0] * unit.HALF_WIDTH
        pt1y = self.pt1[1] - self._unitCornerOffset[1] * unit.HALF_HEIGHT
        pt2x = pt1x + self.deltaPt[0]
        pt2y = pt1y + self.deltaPt[1]

        posX = unit.pos[0] + deltaX
        posY = unit.pos[1] + deltaY

        return checkGroundBounds(
            self, (pt1x, pt1y), (pt2x, pt2y), (posX, posY))

    def finalPosition(self, unit, deltaX, deltaY):
        '''Returns the final position of the given unit
        trying to travel a displacement of [deltaX, deltaY], given
        that it collides with this obstacle.
        This routine takes into account that if the object is travelling
        upwards, it may slide up the obstacle. Returns None if no sliding is
        going on, to indicate that the object hits the ground.'''

        if deltaY > -0.001 or self.deltaPt[1] == 0:
            return None

        # We collided with the floor while jumping.
        pt1x = self.pt1[0] - self._unitCornerOffset[0] * unit.HALF_WIDTH
        pt1y = self.pt1[1] - self._unitCornerOffset[1] * unit.HALF_HEIGHT

        # Go to the y position we would have gone to.
        y = unit.pos[1] + deltaY

        # Calculate where this lies on the slope.
        x = pt1x + (y - pt1y) * (
            self.deltaPt[0] / (self.deltaPt[1] + 0.))

        return x, y

    def getPositionIndex(self, unit, pos):
        # TODO: maybe calculate from the middle, not the corner
        pt1x = self.pt1[0] - self._unitCornerOffset[0] * unit.HALF_WIDTH
        pt1y = self.pt1[1] - self._unitCornerOffset[1] * unit.HALF_HEIGHT

        dist = math.distance((pt1x, pt1y), pos)
        fullDist = math.distance((0, 0), self.deltaPt)
        midPoint = 0.5 * fullDist
        return int(floor((dist - midPoint) / D_UNIT + 0.5))

    def getPositionFromIndex(self, unit, posIndex):
        pt1x = self.pt1[0] - self._unitCornerOffset[0] * unit.HALF_WIDTH
        pt1y = self.pt1[1] - self._unitCornerOffset[1] * unit.HALF_HEIGHT
        fullDist = math.distance((0, 0), self.deltaPt)
        midPoint = 0.5 * fullDist

        u = midPoint + posIndex * D_UNIT
        f = min(0.999, max(0.001, u / fullDist))
        x = pt1x + f * self.deltaPt[0]
        y = pt1y + f * self.deltaPt[1]
        return (x, y)

    def getPositionIndexBounds(self, unit):
        minX = self.pt1[0] - self._unitCornerOffset[0] * unit.HALF_WIDTH
        minY = self.pt1[1] - self._unitCornerOffset[1] * unit.HALF_HEIGHT
        maxX = minX + self.deltaPt[0]
        maxY = minY + self.deltaPt[1]
        minI = self.getPositionIndex(unit, (minX, minY))
        maxI = self.getPositionIndex(unit, (maxX, maxY))
        return (minI, maxI)


class LedgeObstacle(GroundObstacle):
    drop = True

    def collide(self, unit, deltaX, deltaY):
        unitCorner = (
            unit.pos[0] + self._unitCornerOffset[0] * unit.HALF_WIDTH,
            unit.pos[1] + self._unitCornerOffset[1] * unit.HALF_HEIGHT)
        result = collideTrajectory(
            self.pt1, self.deltaPt, unitCorner, deltaX, deltaY)
        if result is None:
            return deltaX, deltaY
        return result


class RoofObstacle(Obstacle):
    def __init__(self, pt1, deltaPt):
        super(RoofObstacle, self).__init__(pt1, deltaPt)

    def finalPosition(self, unit, deltaX, deltaY):
        '''Returns the final position of a point-sized object at the specified
        position trying to travel a displacement of [deltaX, deltaY], given
        that it collides with this obstacle.'''
        # If an object collides with a roof obstacle while falling, it still
        #  falls.

        if deltaY > 0 and deltaX != 0 and self.deltaPt[1] != 0:
            # We collided with the roof while falling.
            # New position is where the roof is at the correct y-position.

            pt1x = self.pt1[0] - self._unitCornerOffset[0] * unit.HALF_WIDTH
            pt1y = self.pt1[1] - self._unitCornerOffset[1] * unit.HALF_HEIGHT

            x = (pt1x + (unit.pos[1] + deltaY - pt1y) *
                 self.deltaPt[0] / (0. + self.deltaPt[1]) -
                 ((deltaX / abs(deltaX)) * 0.1))
            y = unit.pos[1] + deltaY
            # Note: the above statement should only ever cause a division by
            #  zero if someone has been silly enough to put a piece of
            #  horizontal roof in upside down (impassable from above not below)
            return x, y

        # Normal case:
        return None

    def hitByPlayer(self, player):
        # Stop any upward motion of the player.
        player.yVel = max(player.yVel, 0)
        player._jumpTime = 0


class FillerRoofObstacle(RoofObstacle):
    '''Represents an obstacle that would be used as an obstacleEdge;
    its endpoint calculations are less precise (that being they
    don't exist), but are able to be so due to their usage.'''

    def finalPosition(self, unit, deltaX, deltaY):
        if self.deltaPt[0] == 0:
            return unit.pos[0], unit.pos[1] + (deltaY / 2)
        else:
            super(FillerRoofObstacle, self).finalPosition(unit, deltaX, deltaY)

    def collide(self, unit, deltaX, deltaY, soft=True):
        '''Returns how far a point-sized object at the specified position
        could travel if it were trying to travel a displacement of
        [deltaX, deltaY].
        '''
        # Note: This routine is deliberately slightly different to the default
        # collide() in that it has less tolerance for rounding error around
        # corners.
        return super(FillerRoofObstacle, self).collide(
            unit, deltaX, deltaY, soft=True)


class VerticalWall(JumpableObstacle):
    '''Represents a vertical wall that players can cling to and climb.'''
    drop = True
    grabbable = True

    def __init__(self, pt1, deltaPt):
        assert deltaPt[0] == 0

        # Can drop off a vertical wall, so drop is always set to True
        super(VerticalWall, self).__init__(pt1, deltaPt)

    def unstickyWallFinalPosition(self, pt, deltaX, deltaY):
        '''Returns the final position of a point-sized object at the specified
        position trying to travel a displacement of [deltaX, deltaY], given
        that it collides with this obstacle.'''
        # If an object collides with a roof obstacle while falling, it still
        #  falls.

        if deltaY == 0:
            return None

        return pt[0], pt[1] + deltaY

    def getPositionIndex(self, unit, pos):
        x = self.pt1[0]
        if self.deltaPt[1] > 0:
            x += unit.HALF_WIDTH
        else:
            x -= unit.HALF_WIDTH

        midPoint = self.pt1[1] + 0.5 * self.deltaPt[1]
        return int(floor((pos[1] - midPoint) / D_UNIT + 0.5))

    def getPositionFromIndex(self, unit, posIndex):
        x = self.pt1[0]
        if self.deltaPt[1] > 0:
            x += unit.HALF_WIDTH
        else:
            x -= unit.HALF_WIDTH

        y2 = self.pt1[1] + self.deltaPt[1]
        minY = min(self.pt1[1], y2) + 0.1
        maxY = max(self.pt1[1], y2) - 0.1

        midPoint = self.pt1[1] + 0.5 * self.deltaPt[1]
        y = midPoint + posIndex * D_UNIT
        y = min(maxY, max(minY, y))

        return (x, y)

    def getPositionIndexBounds(self, unit):
        x = 0   # Doesn't matter because of how discretise() works
        y2 = self.pt1[1] + self.deltaPt[1]
        minY = min(self.pt1[1], y2)
        maxY = max(self.pt1[1], y2)
        minI = self.getPositionIndex(unit, (x, minY))
        maxI = self.getPositionIndex(unit, (x, maxY))
        return (minI, maxI)


def collideTrajectory(
        obstaclePt1, obstacleDeltaPt, pt, deltaX, deltaY,
        soft=False, radius=0):
    '''
    Calculates whether the trajectory specified by pt, deltaX and deltaY would
    hit the given obstacle.

    @param soft: if true, there's less tolerance for rounding errors around
            corners, making it harder to hit the corners of the obstacle.
    @param radius: this parameter is used to simulate the moving point having
            actual size. If the give point is just on the "solid" side of the
            given obstacle, then providing a radius will ensure that the point
            does not continue to fall through that obstacle.
    @returns: None if no collision would occur, (deltaX, deltaY) otherwise.
    '''

    if soft:
        epsilon = 0
    else:
        epsilon = 1e-10

    ax, ay = obstaclePt1
    bx, by = pt
    dX1, dY1 = obstacleDeltaPt

    # Check if the lines are parallel.
    denom = dX1 * deltaY - deltaX * dY1
    if denom <= epsilon:
        # We can go through it in this direction.
        return None

    # Calculate whether the line segments intersect.
    if deltaX == 0 and deltaY == 0:
        return None
    elif radius > 0:
        minT = radius / (deltaX ** 2 + deltaY ** 2) ** 0.5
    else:
        minT = 0

    t = (dX1 * (ay - by) - dY1 * (ax - bx)) / denom
    if t < (-minT - 1e-10) or t > (1. + 1e-10):
        return None

    if t < -1e10:
        epsilon = 0

    s = (deltaX * (ay - by) - deltaY * (ax - bx)) / denom
    # Take into account floating point error.
    if s <= -epsilon or s >= (1. + epsilon):
        # Past the end of the obstacle.
        return None

    # Calculate the actual collision point.
    x = bx + t * deltaX
    y = by + t * deltaY

    # Calculate the allowed change in position.
    resultX, resultY = x - pt[0], y - pt[1]

    # Ensure that the tollerance doesn't make us go in the opposite direction
    # to the way we're trying to move.
    if resultX * deltaX < 0 or resultY * deltaY < 0:
        return 0, 0
    return resultX, resultY


def checkGroundBounds(obstaclish, pt1, pt2, unitPos):
    pt1x, pt1y = pt1
    pt2x, pt2y = pt2

    posX, posY = unitPos

    if posX < pt1x:
        if obstaclish.leftGround is None:
            return None, (posX, posY)
        return obstaclish.leftGround, (pt1x, pt1y)
    elif posX > pt2x:
        if obstaclish.rightGround is None:
            return None, (posX, posY)
        return obstaclish.rightGround, (pt2x, pt2y)
    return obstaclish, (posX, posY)
