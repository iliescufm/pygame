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

class Team(object):
    '''Represents a team of the game'''
    def __init__(self, world, teamID):
        self.world = world
        self.numZonesOwned = 0
        self.orbScore = 0

        self.usingMinimapDisruption = False

        if (not isinstance(teamID, str)) or len(teamID) != 1:
            raise TypeError, 'teamID must be a single character'
        self.id = teamID

        if teamID == 'A':
            self.teamName = 'Blue players'
        elif teamID == 'B':
            self.teamName = 'Red players'
        else:
            self.teamName = '%s Team' % (teamID,)

    def __str__(self):
        return self.teamName

    def zoneLost(self):
        '''Called when a orb belonging to this team has been lost'''
        self.numZonesOwned -= 1
        self.opposingTeam.gainPoint()

    def zoneGained(self, score=0):
        '''Called when a orb has been attributed to this team'''
        self.numZonesOwned += 1
        self.gainPoint()

    def resetScore(self):
        self.orbScore = 0
        self.world.onTeamScoreChanged()

    def gainPoint(self):
        self.orbScore += 1
        self.world.onTeamScoreChanged()

    def isLoser(self):
        '''Returns whether the team has lost the game (True = Lost Game)'''
        return self.numZonesOwned == 0

    @staticmethod
    def setOpposition(teamA, teamB):
        teamA.opposingTeam = teamB
        teamB.opposingTeam = teamA
