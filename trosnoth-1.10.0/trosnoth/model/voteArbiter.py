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

import random
import logging

from twisted.internet import defer

from trosnoth.messages import RemovePlayerMsg
from trosnoth.const import DEFAULT_TEAM_NAME_1, DEFAULT_TEAM_NAME_2

log = logging.getLogger(__name__)


class VoteArbiter(object):
    def __init__(self, universe):
        self.universe = universe
        self.gameStartMethod = universe._startGame

    def getPlayers(self):
        return [p for p in self.universe.players if not p.bot]

    def getTeams(self):
        return self.universe.teams

    def startNewGameIfReady(self):
        if self.readyForScratchMatch():
            if self.playersWantHvM():
                self.startHumansVsMachinesGame()
            elif len(self.getPlayers()) >= 2:
                self.startNewGame()

    def playersWantHvM(self):
        players = self.getPlayers()
        totalPlayers = len(players)

        inFavour = len([p for p in players if '[HvM]' in p.preferredTeam])
        return inFavour > 0.5 * totalPlayers

    def readyForScratchMatch(self):
        players = self.getPlayers()
        totalPlayers = len(players)

        readyPlayerCount = len([p for p in players if p.readyToStart])
        return readyPlayerCount >= 0.7 * totalPlayers

    def assignTeamNames(self, teamName1, teamName2):
        # Set team names.
        self.getTeams()[0].teamName = teamName1
        self.getTeams()[1].teamName = teamName2

    def assignPlayersToTeams(self, players1, players2):
        for i, players in [(0, players1), (1, players2)]:
            team = self.getTeams()[i]
            for player in players:
                player.team = team

    def bootPlayers(self, players):
        for player in players:
            self.universe.sendServerCommand(RemovePlayerMsg(player.id))

    def startHumansVsMachinesGame(self, level=None):
        teamName1 = 'Humans'
        teamName2 = 'Machines'
        players = self.getPlayers()
        reverse = random.choice([True, False])
        botManager = HumansVsMachinesBotManager(
            self.universe, reverse=reverse)

        if reverse:
            self.assignTeamNames(teamName2, teamName1)
            self.assignPlayersToTeams([], players)
        else:
            self.assignTeamNames(teamName1, teamName2)
            self.assignPlayersToTeams(players, [])

        self.gameStartMethod(botManager=botManager, level=level)

    def startNewGame(self, level=None):
        result = self._getNewTeams()
        if result is None:
            return
        teamName1, players1, teamName2, players2 = result

        self.assignTeamNames(teamName1, teamName2)
        self.assignPlayersToTeams(players1, players2)
        self.gameStartMethod(level=level)

    def _getNewTeams(self):
        '''
        Returns (teamName1, players1, teamName2, players2) based on what teams
        people have selected as their preferred teams. Bots will not be put on
        any team.
        '''
        teamName1, players1, teamName2, players2, others = (
                self._getRelevantTeamPreferences())

        totalPlayers = len(self.getPlayers())
        fairLimit = (totalPlayers + 1) // 2
        if len(players1) == totalPlayers:
            # Don't start if everyone's on one team.
            return None

        if len(players1) > fairLimit:
            # Require every player on the disadvantaged team to be ready.
            for player in players2 + others:
                if not player.readyToStart:
                    return None

        random.shuffle(others)
        for player in others:
            count1 = len(players1)
            count2 = len(players2)
            if count1 > count2:
                players2.append(player)
            elif count2 > count1:
                players1.append(player)
            else:
                random.choice([players1, players2]).append(player)

        return teamName1, players1, teamName2, players2

    def _getRelevantTeamPreferences(self):
        '''
        Returns (teamName1, players1, teamName2, players2, otherPlayers) based
        on what teams people have selected as their preferred teams. Players who
        have not selected one of the two most popular teams will be in the
        otherPlayers collection.
        '''
        desiredTeams = self._getDesiredTeams()
        others = []
        if desiredTeams[0][0] == '':
            teamName, players = desiredTeams.pop(0)
            others.extend(players)

        if desiredTeams:
            teamName1, players1 = desiredTeams.pop(0)
        else:
            teamName1, players1 = '', []

        if desiredTeams:
            teamName2, players2 = desiredTeams.pop(0)
        else:
            teamName2, players2 = '', []

        for teamName, players in desiredTeams:
            others.extend(players)

        if teamName1 == '':
            teamName1 = (DEFAULT_TEAM_NAME_1 if teamName2 != DEFAULT_TEAM_NAME_1
                    else DEFAULT_TEAM_NAME_2)
        if teamName2 == '':
            teamName2 = (DEFAULT_TEAM_NAME_1 if teamName1 != DEFAULT_TEAM_NAME_1
                    else DEFAULT_TEAM_NAME_2)

        return teamName1, players1, teamName2, players2, others

    def _getDesiredTeams(self):
        '''
        Returns a sorted sequence of doubles of the form (teamName, players)
        where teamName is a unicode/string and players is a list of players. The
        sequence will be sorted from most popular to least popular.
        '''
        results = {}
        for player in self.getPlayers():
            teamName = player.preferredTeam
            if '[HvM]' not in teamName:
                results.setdefault(teamName, []).append(player)
        items = results.items()
        items.sort(key=lambda (teamName, players): (len(players), teamName))
        items.reverse()
        return items


BOTS_PER_HUMAN = 1  # Option exists for debugging with many bots


class HumansVsMachinesBotManager(object):
    '''
    Injects bots into the game as needed for a humans vs. machines game.
    '''
    def __init__(self, universe, reverse):
        self.universe = universe

        self.enabled = False
        self.botSurplus = 0
        self.detachingAgents = set()

        if reverse:
            self.botTeam = universe.teams[0]
            self.humanTeam = universe.teams[1]
        else:
            self.botTeam = universe.teams[1]
            self.humanTeam = universe.teams[0]

        self.agents = set()

    @defer.inlineCallbacks
    def startingSoon(self):
        self.enabled = True
        bots = len([p for p in self.universe.players if p.bot])
        humans = len(self.universe.players) - bots
        self.botSurplus = bots - humans * BOTS_PER_HUMAN
        yield self._addBots()

    @defer.inlineCallbacks
    def playerAdded(self, player):
        if not self.enabled:
            return
        if player.bot:
            if player.agent not in self.agents:
                # Someone's directly added a different bot
                self.botSurplus += 1
                self._removeBots()
        else:
            self.botSurplus -= BOTS_PER_HUMAN
            yield self._addBots()

    @defer.inlineCallbacks
    def removingPlayer(self, player):
        if not self.enabled:
            return

        if player.bot:
            if player.agent in self.agents:
                # Bot was booted, not by us
                self.agents.discard(player.agent)
                player.agent.stop()
                self.universe.game.detachAgent(player.agent)

            if player.agent in self.detachingAgents:
                self.detachingAgents.discard(player.agent)
            else:
                self.botSurplus -= 1
                yield self._addBots()
        else:
            self.botSurplus += BOTS_PER_HUMAN
            self._removeBots()

    @defer.inlineCallbacks
    def _addBots(self):
        while self.botSurplus < 0:
            agent = yield self.universe.game.addBot(
                'ranger', team=self.botTeam)
            self.agents.add(agent)
            self.botSurplus += 1

    def _removeBots(self):
        while self.botSurplus > 0:
            if not self.agents:
                return
            agent = random.choice(list(self.agents))
            self.agents.discard(agent)
            self.detachingAgents.add(agent)
            self.botSurplus -= 1
            agent.stop()
            self.universe.game.detachAgent(agent)

    def getTeamToJoin(self, preferredTeam, bot):
        if bot:
            return self.botTeam
        return self.humanTeam

    def stop(self):
        self.enabled = False
        while self.agents:
            agent = self.agents.pop()
            agent.stop()
            self.universe.game.detachAgent(agent)
