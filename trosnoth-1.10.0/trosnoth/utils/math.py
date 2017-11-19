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


def distance(pt1, pt2):
    return ((pt1[0] - pt2[0]) ** 2 + (pt1[1] - pt2[1]) ** 2) ** 0.5


def fadeValues(val1, val2, interval):
    return val2 * interval + val1 * (1 - interval)


def fadeColours(c1, c2, interval):
    return (
        fadeValues(c1[0], c2[0], interval),
        fadeValues(c1[1], c2[1], interval),
        fadeValues(c1[2], c2[2], interval),
    )


def isNear(v1, v2, epsilon=1e-3):
    '''
    Compares two floating point values for approximate equality.
    '''
    return abs(v1 - v2) < epsilon


def calculateConstantMovementTowardsPoint(origin, target, speed, deltaT):
    maxMoveDistance = speed * deltaT
    distanceFromTarget = distance(origin, target)
    if distanceFromTarget < maxMoveDistance:
        return target
    else:
        # calculate fraction of total distance to move this tick
        fractionToMove = maxMoveDistance / distanceFromTarget
        return (
            origin[0] + fractionToMove * (target[0] - origin[0]),
            origin[1] + fractionToMove * (target[1] - origin[1])
        )