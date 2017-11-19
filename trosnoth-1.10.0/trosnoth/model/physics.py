# Trosnoth (UberTweak Platform Game)
# Copyright (C) 2006-2012 Joshua D Bartlett
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# version 2 as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.

import logging

from trosnoth.model.map import MapLayout
from trosnoth.model.modes import PhysicsConstants

log = logging.getLogger(__name__)


class WorldPhysics(PhysicsConstants):
    def __init__(self, world):
        PhysicsConstants.__init__(self)
        self.world = world

    def moveUnit(self, unit, deltaX, deltaY, ignoreObstacles=()):
        '''
        Attempts to move the unit by the specified amount, taking into
        account the positions of walls. Also checks if the unit
        changes zones or changes map blocks.

        If the unit hit an obstacle, returns the obstacle.
        This routine only checks for obstacle collisions if unit.isSolid() is
        True.
        '''

        if unit.isSolid():
            lastObstacle, deltaX, deltaY = self.trimPathToObstacle(
                unit, deltaX, deltaY, ignoreObstacles)
        else:
            lastObstacle = None

        newX, newY = unit.pos[0] + deltaX, unit.pos[1] + deltaY
        i, j = MapLayout.getMapBlockIndices(newX, newY)
        zoneBlocks = self.world.zoneBlocks
        if i < 0 or j < 0 or i >= len(zoneBlocks) or j >= len(zoneBlocks[0]):
            if not unit.continueOffMap():
                return
        else:
            # Check for change of zones.
            newBlock = zoneBlocks[i][j]
            newZone = newBlock.getZoneAtPoint(newX, newY)
            if not unit.canEnterZone(newZone):
                return lastObstacle

        # Move the unit.
        unit.pos = (newX, newY)

        return lastObstacle

    def getNearbyObstacles(self, unit, deltaX, deltaY):
        '''
        Returns a superset of the obstacles which the given unit may collide
        with on the given path.
        '''
        def getObstacles(block):
            if block is None:
                return []
            return unit.getObstacles(block.defn)

        try:
            block = unit.getMapBlock()
        except IndexError:
            return []

        result = list(getObstacles(block))
        if deltaX < 0 and unit.pos[0] - block.defn.rect.left + deltaX < 0:
            result.extend(getObstacles(block.blockLeft))
        elif deltaX > 0 and unit.pos[0] - block.defn.rect.right + deltaX > 0:
            result.extend(getObstacles(block.blockRight))

        if deltaY < 0 and unit.pos[1] - block.defn.rect.top + deltaY < 0:
            result.extend(getObstacles(block.blockAbove))
        elif deltaY > 0 and unit.pos[1] - block.defn.rect.bottom + deltaY > 0:
            result.extend(getObstacles(block.blockBelow))

        return result

    def trimPathToObstacle(self, unit, deltaX, deltaY, ignoreObstacles):
        '''
        Takes the given trajectory and trims it down to the location where it
        collides with the nearest obstacle. Returns (obstacle, dx, dy) where
        obstacle is the obstacle hit or None, and (dx, dy) is the new
        trajectory.
        '''
        lastObstacle = None
        # Check for collisions with obstacles - find the closest obstacle.
        for obstacle in self.getNearbyObstacles(unit, deltaX, deltaY):
            if (unit.ignoreObstacle(obstacle) or obstacle in ignoreObstacles):
                continue
            dX, dY = obstacle.collide(unit, deltaX, deltaY)
            if (dX, dY) != (deltaX, deltaY):
                # Remember the last obstacle we hit.
                lastObstacle = obstacle
                deltaX = dX
                deltaY = dY
            if deltaX == 0 == deltaY:
                break

        return lastObstacle, deltaX, deltaY
