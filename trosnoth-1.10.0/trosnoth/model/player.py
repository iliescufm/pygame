from __future__ import division

import copy
import logging
from math import sin, cos, pi, floor
import struct

from trosnoth.const import (
    OFF_MAP_DEATH, DEFAULT_RESYNC_MESSAGE,
    HOOK_ATTACHED, HOOK_SPEED, DEFAULT_COIN_VALUE,
    DEATH_TAX_RATE, DEATH_TAX_FREE_THRESHOLD, DEATH_MAX_COIN_COUNT,
    MOVEMENT_NORMAL,
)
from trosnoth.model.shot import Shot, PredictedGrenadeTrajectory
from trosnoth.model.trosball import PredictedTrosballTrajectory
from trosnoth.model.unit import Unit
from trosnoth.model.universe_base import NEUTRAL_TEAM_ID
from trosnoth.model.upgrades import (
    Grenade, ItemManager, Bomber, Turret, MachineGun, GrapplingHook, Shield,
    PhaseShift, Shoxwave, Ricochet, Ninja, MinimapDisruption,
)
from trosnoth.utils.event import Event
from trosnoth.utils.math import (
    distance, isNear, calculateConstantMovementTowardsPoint,
)

from trosnoth.messages import (
    PlayerUpdateMsg, ResyncPlayerMsg, ChatFromServerMsg, ResyncAcknowledgedMsg,
)

RESPAWN_CAMP_TIME = 1.0
MAX_RESYNC_TIME = 4     # seconds

log = logging.getLogger('player')


class Player(Unit):
    '''Maintaint the state of a player. This could be the user's player, a
    player on the network, or conceivably even a bot.
    '''

    HALF_WIDTH = 10
    HALF_HEIGHT = 19

    Y_MID_TO_SHOULDERS = 6
    X_MID_TO_BACKBONE = 3

    def __init__(
            self, world, nick, team, id, dead=False, bot=False,
            *args, **kwargs):
        super(Player, self).__init__(world, *args, **kwargs)

        self.world = world

        self.onDied = Event(['killer', 'deathType'])
        self.onKilled = Event(['target', 'deathType', 'hadItems'])
        self.onZombieHit = Event()  # (killer, shot, deathType)
        self.onCoinsChanged = Event(['oldCoins'])
        self.onNeutralisedSector = Event()  # (zoneCount)
        self.onTaggedZone = Event()         # (zone, previousOwner)
        self.onUsedUpgrade = Event()        # (upgrade)
        self.onUpgradeGone = Event()        # (upgrade)
        self.onShotFired = Event()          # (shot)
        self.onShotHurtPlayer = Event()     # (target, shot)
        self.onHitByShot = Event()          # (shot)
        self.onShieldDestroyed = Event()    # (shooter, deathType)
        self.onDestroyedShield = Event()    # (target, deathType)
        self.onPrivateChatReceived = Event()    # (text, sender)
        self.onGotTrosball = Event()
        self.onCoinsSpent = Event()         # (coins)
        self.onRespawned = Event([])
        self.onShotHitSomething = Event()   # (shot)
        self.onOverlayDebugHook = Event()   # (viewManager, screen, sprite)
        self.onTeamSet = Event()
        self.onRemovedFromGame = Event(['playerId'])

        # Identity
        self.nick = nick
        self.user = None      # If authenticated, this will have a value.
        self.agent = None
        self.team = team
        self.id = id
        self.bot = bot

        # Preferences during the voting phase.
        self.preferredTeam = ''
        self.readyToStart = False
        self.preferredSize = (0, 0)
        self.preferredDuration = 0

        # Input state
        self._state = {'left':  False,
                       'right': False,
                       'jump':  False,
                       'down': False,
        }

        # Physics
        self._alreadyJumped = False
        self._jumpTime = 0.0
        self.xVel = 0
        self.yVel = 0
        self.attachedObstacle = None
        self.motionState = 'fall'   # fall / ground / leftwall / rightwall
        self._unstickyWall = None
        self._ignore = None         # Used when dropping through a platform.
        self.angleFacing = 1.57
        self.ghostThrust = 0.0      # Determined by mouse position
        self._faceRight = True
        self.reloadTime = 0.0
        self.reloadFrom = 0.0
        self.respawnGauge = 0.0
        self.invulnerableUntil = None

        self.items = ItemManager(self)

        # Other state info
        self.coins = 0
        if dead:
            self.health = 0
        else:
            self.health = self.world.physics.playerRespawnHealth
        self.zombieHits = 0
        self._alreadyDead = dead
        self.resyncing = False
        self.resyncExpiry = None
        self.lastResyncMessageSent = None   # Server only

    def clone(self):
        '''
        Used to create the local representation of this player object.
        '''
        result = copy.copy(self)
        result._state = copy.copy(self._state)
        result.items = ItemManager(result)
        result.items.restore(self.items.dump())
        result.lastResyncMessageSent = None
        result.onDied = Event(['killer', 'deathType'])
        result.onKilled = Event(['target', 'deathType', 'hadItems'])
        result.onZombieHit = Event()
        result.onCoinsChanged = Event(['oldCoins'])
        result.onNeutralisedSector = Event()
        result.onTaggedZone = Event()
        result.onUsedUpgrade = Event()
        result.onUpgradeGone = Event()
        result.onShotFired = Event()
        result.onShotHurtPlayer = Event()
        result.onHitByShot = Event()
        result.onShieldDestroyed = Event()
        result.onDestroyedShield = Event()
        result.onPrivateChatReceived = Event()
        result.onGotTrosball = Event()
        result.onCoinsSpent = Event()
        result.onRespawned = Event([])
        result.onShotHitSomething = Event()
        result.onOverlayDebugHook = Event()
        result.onTeamSet = Event()
        result.onRemovedFromGame = Event(['playerId'])
        return result

    def dump(self):
        '''
        Returns a serialised dump of the player object for newly
        connected players
        '''
        return {
            'id': self.id,
            'teamId': self.teamId,
            'nick': self.nick,
            'bot': self.bot,
            'update': self.getPlayerUpdateArgs(),
            'items': self.items.dump(),
            'preferences': {
                'team': self.preferredTeam,
                'size': self.preferredSize,
                'duration': self.preferredDuration,
                'ready': self.readyToStart,
            }
        }

    def restore(self, data):
        '''
        Restores the player state based on the given serialised player dump
        :param data: Output of the player dump
        '''
        team = self.world.teamWithId[data['teamId']]
        bot = data['bot']
        update = data['update']
        preferences = data['preferences']

        self.nick = data['nick']
        self.team = team
        self.bot = bot

        self.items.restore(data['items'])

        self.applyPlayerUpdate(PlayerUpdateMsg(*update))

        self.preferredTeam = preferences['team']
        self.preferredSize = tuple(preferences['size'])
        self.preferredDuration = preferences['duration']
        self.readyToStart = preferences['ready']
        self.onTeamSet()

    def isCanonicalPlayer(self):
        return self in self.world.players

    @property
    def dead(self):
        realHealth = self.health - self.zombieHits
        shield = self.items.get(Shield)
        if shield:
            realHealth += shield.protections
        return realHealth <= 0

    @property
    def knowsItsDead(self):
        '''
        It's possible for a player to be dead and not know it (e.g. killed by
        grenade or shoxwave and hasn't yet received the network message). It
        this case the easiest way to keep the server and client in sync is by
        treating it as a ghost that moves like a living player.
        '''
        return self.health <= 0

    def isStatic(self):
        if self.oldPos != self.pos:
            return False
        if self.motionState == 'fall' and not self.knowsItsDead:
            return False
        if self.items.hasAny():
            return False
        if self.knowsItsDead and self.respawnGauge != 0:
            return False
        if self.knowsItsDead and self.ghostThrust != 0:
            return False
        if self.reloadTime != 0:
            return False
        return True

    def getXKeyMotion(self):
        if self._state['left'] and not self._state['right']:
            return -1
        if self._state['right'] and not self._state['left']:
            return 1
        return 0

    def hasTrosball(self):
        manager = self.world.trosballManager
        return (
            manager.enabled and manager.trosballPlayer
            and manager.trosballPlayer.id == self.id)

    @staticmethod
    def getObstacles(mapBlockDef):
        '''
        Return which obstacles in the given map block apply to this kind of
        unit.
        '''
        return mapBlockDef.obstacles + mapBlockDef.ledges

    @property
    def identifyingName(self):
        if self.user is None:
            return self.nick
        return self.user.username

    def hasProtectiveUpgrade(self):
        return self.items.has(Shield)

    def hasVisibleShield(self):
        shield = self.items.get(Shield)
        if not shield:
            return False
        return shield.protections > self.zombieHits

    @property
    def phaseshift(self):
        return self.items.get(PhaseShift)

    @property
    def turret(self):
        return self.items.get(Turret)

    @property
    def shoxwave(self):
        return self.items.get(Shoxwave)

    @property
    def machineGunner(self):
        return self.items.get(MachineGun)

    @property
    def hasRicochet(self):
        return self.items.get(Ricochet)

    @property
    def ninja(self):
        return self.items.get(Ninja)

    @property
    def disruptive(self):
        return self.items.get(MinimapDisruption)

    @property
    def bomber(self):
        return self.items.get(Bomber)

    @property
    def canMove(self):
        return not self.bomber

    @property
    def invisible(self):
        if self.ninja:
            if self.reloadTime != 0.0:
                return False
            if self.distanceFromCentre() > 200:
                return True
            zone = self.getZone()
            if zone and self.isFriendsWithTeam(zone.owner):
                return True
            return False
        return False

    @property
    def currentProjectileTrajectory(self):
        if self.dead:
            return None
        if self.hasTrosball():
            return PredictedTrosballTrajectory(self.world, self)
        return PredictedGrenadeTrajectory(
            self.world, self, Grenade.totalTimeLimit)

    def distanceFromCentre(self):
        zone = self.getZone()
        if not zone:
            return 2000
        return distance(zone.defn.pos, self.pos)

    def isAttachedToWall(self):
        '''
        Returns False if this player is not attached to a wall, otherwise
        returns 'left' or 'right' to indicate whether the wall is on the
        player's left or right.
        '''
        if self.motionState == 'leftwall':
            return 'left'
        elif self.motionState == 'rightwall':
            return 'right'
        return False

    def detachFromEverything(self):
        self.setAttachedObstacle(None)

    def isOnGround(self):
        '''
        Returns True iff this player is on the ground (whether that ground is a
        ledge or solid ground).
        '''
        return self.motionState == 'ground'

    def isOnPlatform(self):
        return self.isOnGround() and self.attachedObstacle.drop

    def isFriendsWith(self, other):
        '''
        Returns True iff self and other are on the same team.
        '''
        if other.id == self.id:
            return True
        return self.isFriendsWithTeam(other.team)

    def isFriendsWithTeam(self, team):
        if team is None:
            return False
        return self.team == team

    def inRespawnableZone(self):
        zone = self.getZone()
        return self.isZoneRespawnable(zone)

    def isZoneRespawnable(self, zone):
        if not zone:
            return False
        return self.team is None or zone.owner == self.team

    @property
    def teamId(self):
        if self.team is None:
            return NEUTRAL_TEAM_ID
        return self.team.id

    @property
    def teamName(self):
        if self.team is None:
            return self.world.rogueTeamName
        return self.team.teamName

    def isEnemyTeam(self, team):
        '''
        Returns True iff the given team is an enemy team of this player. It is
        not enough for the team to be neutral (None), it must actually be an
        enemy for this method to return True.
        '''
        if team is None:
            return False
        return self.team != team

    def isInvulnerable(self):
        iu = self.invulnerableUntil
        if iu is None:
            return False
        elif self.world.getMonotonicTime() > iu:
            self.invulnerableUntil = None
            return False
        return True

    @property
    def isMinimapDisrupted(self):
        for team in self.world.teams:
            if team != self.team and team.usingMinimapDisruption:
                return True
        return False

    @staticmethod
    def _leftValidator(obs):
        return obs.deltaPt[0] == 0 and obs.deltaPt[1] > 0

    @staticmethod
    def _rightValidator(obs):
        return obs.deltaPt[0] == 0 and obs.deltaPt[1] < 0

    @staticmethod
    def _groundValidator(obs):
        return obs.deltaPt[0] > 0

    def setPos(self, pos, attached):
        self.pos = self.oldPos = pos

        self._ignore = None
        if attached == 'f':
            obstacle = None
        elif attached == 'g':
            obstacle, dX, dY = self.world.physics.trimPathToObstacle(
                self, 0, 10, set())
        elif attached == 'l':
            obstacle, dX, dY = self.world.physics.trimPathToObstacle(
                self, -10, 0, set())
        elif attached == 'r':
            obstacle, dX, dY = self.world.physics.trimPathToObstacle(
                self, 10, 0, set())
        self.setAttachedObstacle(obstacle)

    def __str__(self):
        return self.nick

    def getDetailsForLeaderBoard(self):
        if self.id == -1:
            return {}

        pID = struct.unpack('B', self.id)[0]
        nick = self.nick
        team = self.teamId
        dead = self.dead
        coins = self.coins

        if self.world.scoreboard and self.world.scoreboard.playerScoresEnabled:
            score = self.world.scoreboard.playerScores[self]
        else:
            score = None

        return {
            'pID': pID,
            'nick': nick,
            'team': team,
            'dead': dead,
            'coins': coins,
            'bot': self.bot,
            'ready': self.readyToStart,
            'score': score,
        }

    def removeFromGame(self):
        '''Called by network client when server says this player has left the
        game.'''

        self.items.clear()

        if self.hasTrosball():
            self.world.trosballManager.playerDroppedTrosball()

    def isSolid(self):
        return not self.knowsItsDead

    def ignoreObstacle(self, obstacle):
        return self._ignore == obstacle

    def continueOffMap(self):
        if not self.dead:
            # Player is off the map: mercy killing.
            self.killOutright(OFF_MAP_DEATH, resync=False)
        return False

    def canEnterZone(self, newZone):
        if newZone == self.getZone():
            return True
        world = self.world
        if (not world.abilities.leaveFriendlyZones
                and newZone is None and self.dead):
            # Pre-game ghost cannot enter purple zones.
            return False

        if (newZone is not None and
                not world.abilities.leaveFriendlyZones
                and newZone.owner != self.team):
            # Disallowed zone change.
            return False

        return True

    def updateState(self, key, value):
        '''Update the state of this player. State information is information
        which is needed to calculate the motion of the player. For a
        human-controlled player, this is essentially only which keys are
        pressed. Keys which define a player's state are: left, right, jump and
        down.
        Shooting is processed separately.'''

        if self.resyncing:
            return

        if key == 'left' or key == 'right':
            self._unstickyWall = None

        # Ignore messages if we already know the answer.
        if self._state[key] == value:
            return
        if key == 'jump':
            self._alreadyJumped = False

        # Set the state.
        self._state[key] = value

    def getState(self, key):
        return self._state[key]

    def processJumpState(self):
        '''
        Checks the player's jump key state to decide whether to initiate a jump
        or stop a jump.
        '''
        jumpKeyDown = self._state['jump'] and self.canMove
        if jumpKeyDown:
            if self.motionState == 'fall':
                return
            if self._alreadyJumped:
                return

            # Otherwise, initiate the jump.
            self._jumpTime = self.world.physics.playerMaxJumpTime
            if self.isAttachedToWall():
                self._unstickyWall = self.attachedObstacle
            self.detachFromEverything()
            self._alreadyJumped = True
        elif self.yVel < 0:
            self.yVel = 0
            self._jumpTime = 0

    def lookAt(self, angle, thrust=None):
        '''Changes the direction that the player is looking.  angle is in
        radians and is measured clockwise from vertical.'''

        if self.resyncing:
            return

        if thrust is not None:
            self.ghostThrust = min(1, max(0, thrust))

        angle = (angle + pi) % (2 * pi) - pi
        if self.angleFacing == angle:
            return

        self.angleFacing = angle
        self._faceRight = angle > 0

    def isFacingRight(self):
        return self._faceRight

    def activateItemByCode(self, upgradeType, local=None):
        upgradeClass = self.world.getUpgradeType(upgradeType)
        return self.items.activate(upgradeClass, local)

    def updateGhost(self):
        deltaT = self.world.tickPeriod
        deltaX = (
            self.world.physics.playerMaxGhostVel * deltaT
            * sin(self.angleFacing) * self.ghostThrust)
        deltaY = (
            -self.world.physics.playerMaxGhostVel * deltaT
            * cos(self.angleFacing) * self.ghostThrust)

        self.world.physics.moveUnit(self, deltaX, deltaY)

        # Update respawn gauge based on Time:
        if self.respawnGauge >= 0:
            self.respawnGauge -= deltaT
            if self.respawnGauge < 0:
                self.respawnGauge = 0

    def getKeyPressXVelocity(self):
        '''
        Return the absolute value of the velocity the player should have
        (assuming the player is living), given the direction that the player is
        facing and the keys (left/right) being pressed.
        '''
        if not self.canMove:
            return 0

        # Consider horizontal movement of player.
        if self._state['left'] and not self._state['right']:
            if self._faceRight:
                return -self.world.physics.playerSlowXVel
            return -self.world.physics.playerXVel

        if self._state['right'] and not self._state['left']:
            if self._faceRight:
                return self.world.physics.playerXVel
            return self.world.physics.playerSlowXVel

        return 0

    def getGroundIntentionAndDirection(self):
        '''
        Returns intent, direction where direction is -1 for left and +1 for
        right, and intent is -1 for slow down, 0 for walk and 1 for run.
        '''
        if not self.canMove:
            keySpeed = 0
        elif self._state['left'] and not self._state['right']:
            if self._faceRight:
                keySpeed = -1
            else:
                keySpeed = -2
        elif self._state['right'] and not self._state['left']:
            if self._faceRight:
                keySpeed = +2
            else:
                keySpeed = +1
        else:
            keySpeed = 0

        if self.xVel < 0:
            dir = -1
        elif self.xVel > 0:
            dir = +1
        elif keySpeed < 0:
            dir = -1
        elif keySpeed > 0:
            dir = +1
        else:
            return 0, 0

        if dir * keySpeed == +2:
            intent = 1
        elif dir * keySpeed == +1:
            intent = 0
        else:
            intent = -1

        return intent, dir

    def getAirAcceleration(self):
        if not self.canMove:
            return 0, False

        physics = self.world.physics

        if self._state['left'] and not self._state['right']:
            if self.xVel > -physics.playerMaxAirDodgeSpeed:
                return -physics.playerAirAcceleration, False

        elif self._state['right'] and not self._state['left']:
            if self.xVel < physics.playerMaxAirDodgeSpeed:
                return physics.playerAirAcceleration, False

        else:
            deltaT = self.world.tickPeriod
            if self.xVel > 0:
                return -physics.playerAirAcceleration, True
            elif self.xVel < 0:
                return physics.playerAirAcceleration, True

        return 0, False

    def getCurrentVelocity(self):
        '''
        Used to decide how fast the Trosball should go if it's dropped.
        '''
        return (self.xVel, self.yVel)

    def dropThroughFloor(self):
        self._ignore = self.attachedObstacle
        self.detachFromEverything()

    def dropOffWall(self):
        self._unstickyWall = self.attachedObstacle
        self.detachFromEverything()

    def moveAlongGround(self, momentum):
        physics = self.world.physics
        deltaT = self.world.tickPeriod

        if not momentum:
            self.xVel = self.getKeyPressXVelocity()
        else:
            intent, dir = self.getGroundIntentionAndDirection()
            if intent > 0:
                if abs(self.xVel) < physics.playerXVel:
                    self.xVel = physics.playerXVel * dir
                self.xVel += dir * physics.playerRunAcceleration * deltaT
                self.xVel = min(self.xVel, physics.playerMaxRunSpeed)
                self.xVel = max(self.xVel, -physics.playerMaxRunSpeed)
            else:
                self.xVel -= dir * physics.playerRunDeceleration * deltaT
                if intent < 0:
                    if self.xVel * dir < 0:
                        self.xVel = 0
                else:
                    if self.xVel * dir < physics.playerSlowXVel:
                        self.xVel = dir * physics.playerSlowXVel

        if self.xVel == 0:
            return

        attachedObstacle = self.attachedObstacle
        for i in xrange(100):
            if deltaT <= 0:
                obstacle = None
                break

            oldPos = self.pos
            deltaX, deltaY = attachedObstacle.walkTrajectory(self.xVel, deltaT)
            nextSection, corner = attachedObstacle.checkBounds(
                self, deltaX, deltaY)

            # Check for collisions in this path.
            obstacle = physics.moveUnit(
                self, corner[0] - self.pos[0], corner[1] - self.pos[1],
                ignoreObstacles=attachedObstacle.subshape)
            if obstacle is not None:
                self.xVel = 0
                break
            if nextSection is None:
                obstacle = None
                self.setAttachedObstacle(None)
                break
            if nextSection == attachedObstacle:
                obstacle = None
                break

            self.attachedObstacle = attachedObstacle = nextSection
            nextSection.hitByPlayer(self)
            deltaT -= (
                (oldPos[0] - self.pos[0]) ** 2
                + (oldPos[1] - self.pos[1]) ** 2) ** 0.5 / abs(self.xVel)
        else:
            log.error(
                'Very very bad thing: motion loop did not terminate after '
                '100 iterations')

        if obstacle:
            if obstacle.jumpable:
                if self.isOnGround() and obstacle.grabbable:
                    # Running into a vertical wall while on the ground.
                    pass
                else:
                    self.setAttachedObstacle(obstacle)
            else:
                self.setAttachedObstacle(None)
            obstacle.hitByPlayer(self)

        self._ignore = None

    def setAttachedObstacle(self, obstacle):
        if obstacle and not obstacle.jumpable:
            log.warning('Cannot set attached obstacle to %s', obstacle)
            return
        self.attachedObstacle = obstacle
        self.motionState = self.getAttachedMotionState(obstacle)
        if obstacle:
            self.yVel = 0
        if self.motionState in ('leftwall', 'rightwall'):
            self.xVel = 0

    @staticmethod
    def getAttachedMotionState(obstacle):
        if obstacle is None:
            return 'fall'
        if obstacle.grabbable:
            if obstacle.deltaPt[1] < 0:
                return 'rightwall'
            return 'leftwall'
        return 'ground'

    def calculateJumpMotion(self):
        '''
        Returns (dx, dy, dt) where (dx, dy) is the trajectory due to the upward
        thrust of jumping, and dt is the time for which the upward thrust does
        not apply.
        '''
        deltaT = self.world.tickPeriod
        deltaY = 0
        deltaX = self.xVel * deltaT

        # If the player is jumping, calculate how much they jump by.
        if self._jumpTime > 0:
            thrustTime = min(deltaT, self._jumpTime)
            self.yVel = -self.world.physics.playerJumpThrust
            deltaY = thrustTime * self.yVel
            self._jumpTime = self._jumpTime - deltaT

            # Automatically switch off the jumping state if the player
            # has reached maximum time.
            if self._jumpTime <= 0:
                self._jumpTime = 0
            return deltaX, deltaY, deltaT - thrustTime
        return deltaX, deltaY, deltaT

    def getFallTrajectory(self, deltaX, deltaY, fallTime):
        # If player is falling, calculate how far they fall.

        # v = u + at
        vFinal = self.yVel + self.world.physics.playerGravity * fallTime
        if vFinal > self.world.physics.playerMaxFallVel:
            # Hit terminal velocity. Fall has two sections.
            deltaY = (
                deltaY + (
                    self.world.physics.playerMaxFallVel ** 2 - self.yVel ** 2
                ) / (2 * self.world.physics.playerGravity)
                + self.world.physics.playerMaxFallVel * (fallTime - (
                    self.world.physics.playerMaxFallVel - self.yVel
                ) / self.world.physics.playerGravity))

            self.yVel = self.world.physics.playerMaxFallVel
        else:
            # Simple case: s=ut+0.5at**2
            deltaY = (
                deltaY + self.yVel * fallTime + 0.5 *
                self.world.physics.playerGravity * fallTime ** 2)
            self.yVel = vFinal

        return deltaX, deltaY

    def fallThroughAir(self, momentum):
        if not momentum:
            self.xVel = self.getKeyPressXVelocity()
        else:
            xAccel, limited = self.getAirAcceleration()
            oldXVel = self.xVel
            self.xVel += self.world.tickPeriod * xAccel
            if limited and oldXVel * self.xVel < 0:
                self.xVel = 0

        deltaX, deltaY, fallTime = self.calculateJumpMotion()
        deltaX, deltaY = self.getFallTrajectory(deltaX, deltaY, fallTime)

        obstacle = self.world.physics.moveUnit(self, deltaX, deltaY)
        if obstacle:
            if obstacle == self._unstickyWall:
                targetPt = obstacle.unstickyWallFinalPosition(
                    self.pos, deltaX, deltaY)
            else:
                targetPt = obstacle.finalPosition(self, deltaX, deltaY)
            if targetPt is not None:
                deltaX = targetPt[0] - self.pos[0]
                deltaY = targetPt[1] - self.pos[1]
                obstacle = self.world.physics.moveUnit(self, deltaX, deltaY)

        if obstacle and obstacle.jumpable:
            self.setAttachedObstacle(obstacle)
        else:
            self.setAttachedObstacle(None)
        if obstacle:
            obstacle.hitByPlayer(self)

        self._ignore = None

    def updateLivingPlayer(self):
        momentum = (
            self.world.physics.movement == MOVEMENT_NORMAL and not self.bot)
        self.processJumpState()

        wall = self.isAttachedToWall()

        hook = self.items.get(GrapplingHook)
        if hook:
            self.items.get(GrapplingHook).updateHookPosition()

        if hook and hook.hookState == HOOK_ATTACHED:
            self.advanceWithHookAttached(hook)
        elif self.isOnPlatform() and self._state['down'] and self.canMove:
            # Allow falling through fall-through-able obstacles
            self.dropThroughFloor()
        elif self.isOnGround():
            self.moveAlongGround(momentum=momentum)
        elif wall:
            if (
                    self._state['down']
                    or (self._state['right'] and wall == 'left')
                    or (self._state['left'] and wall == 'right')
                    or not self.canMove
                    ):
                self.dropOffWall()
        else:
            self.fallThroughAir(momentum=momentum)

    def advance(self):
        '''Called by this player's universe when this player should update
        its position. deltaT is the time that's passed since its state was
        current, measured in seconds.'''

        if self.resyncing:
            return

        self.items.tick()
        self.reloadTime = max(0.0, self.reloadTime - self.world.tickPeriod)

        if self.knowsItsDead:
            self.updateGhost()
        else:
            self.updateLivingPlayer()

        if self.attachedObstacle:
            self.pos = self.attachedObstacle.discretise(Player, self.pos)
        else:
            self.pos = (floor(self.pos[0] + 0.5), floor(self.pos[1] + 0.5))

    def advanceWithHookAttached(self, hook):
        oldPos = self.pos
        self.pos = calculateConstantMovementTowardsPoint(
            self.pos, hook.hookTarget, HOOK_SPEED, self.world.tickPeriod)
        self.xVel = (self.pos[0] - oldPos[0]) / self.world.tickPeriod
        self.yVel = (self.pos[1] - oldPos[1]) / self.world.tickPeriod

    def isOnside(self, trosballPosition):
        onLeftOfBall = self.pos[0] < trosballPosition[0]
        onBlueTeam = self.team == self.world.teams[0]
        return onLeftOfBall == onBlueTeam

    def hitShield(self, shooter, deathType):
        '''
        Hits the shield for one point of damage, and returns True if the shield
        absorbed the damage, False if there was no shield.
        '''
        shield = self.items.get(Shield)
        if shield:
            return shield.wasHit(shooter, deathType)
        return False

    def zombieHit(self, shooter, shot, deathType):
        '''
        Called when the player has been hit, but the player's client may not
        realise that the player is dead yet.
        '''
        self.zombieHits += 1
        self.onZombieHit(shooter, shot, deathType)
        self.checkDeath(shooter, deathType)

    def properHit(self, shooter, deathType, hits=1):
        '''
        Called when the player has been hit AND the client is guaranteed to be
        the first one to notice it (because it relates to where the player
        thinks it is rather than where the server thinks the player is).
        '''
        if not self.hitShield(shooter, deathType):
            self.health -= hits
            self.checkDeath(shooter, deathType)

    def noticeZombieHit(self, shooter, deathType, hits=1):
        '''
        Called when the player notices that its past self has been hit.
        '''
        assert self.zombieHits >= 0
        self.zombieHits -= hits
        self.properHit(shooter, deathType)

    def killOutright(self, deathType, killer=None, resync=True):
        self.health = 0
        self.checkDeath(killer, deathType)

        # An outright kill cannot be detected by the client until it happens,
        # so the client will have mis-predicted where the player is going and
        # will need to resync.
        if resync and self.world.isServer:
            self.sendResync(reason='')

    def checkDeath(self, killer, deathType):
        if self.dead:
            if self.hasTrosball():
                self.world.trosballManager.playerDroppedTrosball()
            if self.hasElephant():
                self.world.elephantKill(killer)
            if self.isCanonicalPlayer() and not self._alreadyDead:
                self._alreadyDead = True
                self.world.playerHasDied(self, killer, deathType)

        if self.knowsItsDead:
            self.health = 0
            self.zombieHits = 0
            self.respawnGauge = self.world.physics.playerRespawnTotal
            self._jumpTime = 0
            hadItems = self.items.getActiveKinds()
            self.items.clear()
            self.setAttachedObstacle(None)
            if self.isCanonicalPlayer():
                if killer:
                    killer.onKilled(self, deathType, hadItems=hadItems)
                    self.world.onPlayerKill(killer, self, deathType)
                self.world.playerHasNoticedDeath(self, killer)
            self.onDied(killer, deathType)

    def returnToLife(self):
        self.setAttachedObstacle(None)
        self.health = self.world.physics.playerRespawnHealth
        self.zombieHits = 0
        self._alreadyDead = False
        self.respawnGauge = 0
        self.xVel = 0
        self.yVel = 0

    def respawn(self, zone=None):
        if self.resyncing:
            return
        self.returnToLife()
        self.invulnerableUntil = (
            self.world.getMonotonicTime() + RESPAWN_CAMP_TIME)
        self.teleportToZoneCentre(zone)
        if self.isCanonicalPlayer():
            self.world.onPlayerRespawn(self)
        self.onRespawned()

    def teleportToZoneCentre(self, zone=None):
        if zone is None:
            zone = self.getZone()
        self.setPos(zone.defn.pos, 'f')

    def incrementCoins(self, count):
        oldCoins = self.coins
        self.coins += count
        self.onCoinsChanged(oldCoins)

    def setCoins(self, count):
        oldCoins = self.coins
        self.coins = count
        self.onCoinsChanged(oldCoins)

    def getValueToDropOnDeath(self):
        taxableCoins = max(0, self.coins - DEATH_TAX_FREE_THRESHOLD)
        valueToDrop = int(taxableCoins * DEATH_TAX_RATE + 0.5)
        return valueToDrop

    def getCoinDisplayCount(self):
        valueToDrop = self.getValueToDropOnDeath()
        return min(DEATH_MAX_COIN_COUNT, int(valueToDrop / DEFAULT_COIN_VALUE))

    def getCoinsToDropOnDeath(self):
        valueToDrop = self.getValueToDropOnDeath()
        count = self.getCoinDisplayCount()

        if count == DEATH_MAX_COIN_COUNT:
            for i in range(count - 1):
                yield DEFAULT_COIN_VALUE
                valueToDrop -= DEFAULT_COIN_VALUE
            yield valueToDrop
        else:
            remaining = count
            while remaining:
                thisCoin = int(valueToDrop / remaining + 0.5)
                yield thisCoin
                valueToDrop -= thisCoin
                remaining -= 1

    def getShotType(self):
        '''
        Returns one of the following:
            None - if the player cannot currently shoot
            'N' - if the player can shoot normal shots
            'R' - if the player can shoot ricochet shots
            'T' - if the player can shoot turret shots
        '''
        if self.dead or self.phaseshift or not self.canMove:
            return None

        # While on a vertical wall, one canst not fire
        if self.reloadTime > 0 or self.isAttachedToWall():
            return None

        if self.hasRicochet:
            return Shot.RICOCHET
        if self.turret:
            if self.turret.overheated:
                return None
            return Shot.TURRET
        return Shot.NORMAL

    def setUser(self, user):
        if not self.bot:
            self.user = user

    def isElephantOwner(self):
        return self.user is not None and self.user.isElephantOwner()

    def hasElephant(self):
        playerWithElephant = self.world.playerWithElephant
        return playerWithElephant and playerWithElephant.id == self.id

    def canShoot(self):
        return self.getShotType() is not None

    def sendResync(self, reason=DEFAULT_RESYNC_MESSAGE, error=False):
        if not self.world.isServer:
            raise TypeError('Only servers can send resync messages')

        if self.resyncing and self.stateHasNotChangedSinceResyncSent():
             return

        args = self.getPlayerUpdateArgs(resync=bool(self.agent))
        globalMsg, resyncMsg = PlayerUpdateMsg(*args), ResyncPlayerMsg(*args)
        self.world.sendServerCommand(globalMsg)
        if self.agent:
            self.lastResyncMessageSent = resyncMsg
            self.agent.messageToAgent(resyncMsg)
            if reason:
                # Perhaps we should default to error=True, but these are too
                # common at present
                self.agent.messageToAgent(
                    ChatFromServerMsg(error=error, text=reason))
        self.resyncBegun()

    def stateHasNotChangedSinceResyncSent(self):
        if self.lastResyncMessageSent is None:
            return False
        comparison = ResyncPlayerMsg(*self.getPlayerUpdateArgs())
        return comparison.pack() == self.lastResyncMessageSent.pack()

    def resyncBegun(self):
        self.resyncing = True
        self.resyncExpiry = self.world.getMonotonicTick() + int(
            MAX_RESYNC_TIME / self.world.tickPeriod)

    def getPlayerUpdateArgs(self, resync=None):
        attached = self.motionState[0]

        if resync is None:
            resync = self.resyncing

        health = max(self.health - self.zombieHits, 0)

        return (
            self.id, self.pos[0], self.pos[1], self.xVel, self.yVel,
            self.angleFacing,
            self.ghostThrust, self._jumpTime, self.reloadTime,
            self.respawnGauge, attached, self.coins, health, resync,
            self._state['left'], self._state['right'], self._state['jump'],
            self._state['down'])

    def applyPlayerUpdate(self, msg):
        self._state['left'] = msg.leftKey
        self._state['right'] = msg.rightKey
        self._state['jump'] = msg.jumpKey
        self._state['down'] = msg.downKey

        self.yVel = msg.yVel
        self.lookAt(msg.angle, msg.ghostThrust)
        self.setPos((msg.xPos, msg.yPos), msg.attached)
        self._jumpTime = msg.jumpTime
        self.reloadTime = msg.gunReload
        self.respawnGauge = msg.respawn
        oldCoins = self.coins
        self.coins = msg.coins
        self.health = msg.health
        if self.health > 0:
            self._alreadyDead = False
        self.zombieHits = 0
        if msg.resync:
            self.resyncBegun()
        else:
            self.resyncing = False
        if oldCoins != self.coins:
            self.onCoinsChanged(oldCoins)

    def buildResyncAcknowledgement(self):
        health = max(self.health - self.zombieHits, 0)
        return ResyncAcknowledgedMsg(
            self.world.lastTickId, self.pos[0], self.pos[1],
            self.yVel, self.angleFacing, self.ghostThrust, health)

    def checkResyncAcknowledgement(self, msg):
        '''
        Checks whether the player position etc. matches the position encoded in
        the ResyncPlayerMsg or ResyncAcknowledgedMsg.
        '''
        return (
            isNear(self.pos[0], msg.xPos)
            and isNear(self.pos[1], msg.yPos)
            and isNear(self.yVel, msg.yVel)
            and isNear(self.angleFacing, msg.angle)
            and isNear(self.ghostThrust, msg.ghostThrust)
            and msg.health == max(self.health - self.zombieHits, 0))

    def weaponDischarged(self):
        '''
        Updates the player's reload time because the player has just fired a
        shot.
        '''
        world = self.world
        zone = self.getZone()
        if self.turret:
            reloadTime = self.turret.weaponDischarged()
        elif self.machineGunner:
            reloadTime = self.machineGunner.weaponDischarged()
        elif self.shoxwave:
            reloadTime = world.physics.playerShoxwaveReloadTime
        elif self.team is None:
            reloadTime = world.physics.playerNeutralReloadTime
        elif world.trosballManager.enabled:
            if (
                    abs(self.pos[0] - world.trosballManager.getPosition()[0])
                    < 1e-5):
                reloadTime = world.physics.playerNeutralReloadTime
            # If self is on blue, and on the left of the trosball; or
            # completely vice versa
            elif self.isOnside(world.trosballManager.getPosition()):
                reloadTime = world.physics.playerOwnDarkReloadTime
            else:
                reloadTime = world.physics.playerEnemyDarkReloadTime
        elif zone and zone.owner == self.team and zone.dark:
            reloadTime = world.physics.playerOwnDarkReloadTime
        elif zone and not zone.dark:
            reloadTime = world.physics.playerNeutralReloadTime
        else:
            reloadTime = world.physics.playerEnemyDarkReloadTime
        self.reloadTime = self.reloadFrom = reloadTime

    def createShot(self, shotId=None, shotClass=Shot):
        '''
        Factory function for building a Shot object.
        '''
        # Shots take some fraction of the player's current velocity, but we
        # still want the shots to always go directly towards where the user
        # clicked, so we take the component of player velocity in the direction
        # of the shot.
        f = self.world.physics.fractionOfPlayerVelocityImpartedToShots
        xVel = (self.pos[0] - self.oldPos[0]) / self.world.tickPeriod
        yVel = (self.pos[1] - self.oldPos[1]) / self.world.tickPeriod
        shotVel = self.world.physics.shotSpeed + f * (
            xVel * sin(self.angleFacing) - yVel * cos(self.angleFacing))

        velocity = (
            shotVel * sin(self.angleFacing),
            -shotVel * cos(self.angleFacing),
        )

        kind = self.getShotType()
        lifetime = self.world.physics.shotLifetime
        x = self.pos[0]
        if self.isFacingRight():
            x -= self.X_MID_TO_BACKBONE
        else:
            x += self.X_MID_TO_BACKBONE
        y = self.pos[1]
        y -= self.Y_MID_TO_SHOULDERS

        team = self.team
        shot = shotClass(
            self.world, shotId, team, self, (x, y), velocity, kind, lifetime)
        return shot

    def getPathFindingNodeKey(self):
        '''
        Helper for navigating the bot path finding graph.Returns the key
        for the current path finding node.
        '''
        from trosnoth.bots.pathfinding import RunTimeMapBlockPaths

        if not self.attachedObstacle:
            return None

        return RunTimeMapBlockPaths.buildNodeKey(self)

    def placeAtNodeKey(self, mapBlockDef, nodeKey):
        '''
        Helper for bot simulations. Places this player at the given node key
        within the given map block.
        '''
        obstacleId, posIndex = nodeKey
        obstacle = mapBlockDef.getObstacleById(obstacleId)

        self.pos = obstacle.getPositionFromIndex(Player, posIndex)
        self.setAttachedObstacle(obstacle)

    def buildStateChanges(self, desiredState):
        result = []
        for k, v in self._state.items():
            desired = desiredState.get(k, False)
            if v != desired:
                result.append((k, desired))
        return result
