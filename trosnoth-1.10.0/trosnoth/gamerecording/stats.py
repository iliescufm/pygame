from collections import defaultdict
import datetime
import json
import logging
import os

from trosnoth import dbqueue
from trosnoth.model.universe_base import NEUTRAL_TEAM_ID
from trosnoth.network.networkDefines import serverVersion
from trosnoth.utils.twist import WeakLoopingCall
from trosnoth.utils.utils import timeNow    # TODO: use game not real time

log = logging.getLogger(__name__)


# TODO: test the accuracy etc. achievements after fixing the stats to fit the
# event-based architecture

class PlayerStatKeeper(object):
    '''Maintains the statistics for a particular player object'''
    def __init__(self, gameRecorder, player):
        self.gameRecorder = gameRecorder
        self.player = player

        # A: Recorded [A]ll game (including post-round)
        # G: Recorded during the main [G]ame only
        # P: Recorded [P]ost-Game only
        self.kills = 0           # G Number of kills they've made
        self.deaths = 0          # G Number of times they've died
        self.zoneTags = 0        # G Number of zones they've tagged
        self.zoneAssists = 0     # G Number of zones they've been in when their
                                 #   team tags it
        self.shotsFired = 0      # A Number of shots they've fired
        self.shotsHit = 0        # A Number of shots that have hit a target
        self.coinsEarned = 0     # G Aggregate total of coins earned
        self.coinsUsed = 0       # G Aggregate total of coins used
        self.coinsLost = 0       # G Aggregate total of coins lost in any way
        self.roundsWon = 0       # . Number of rounds won
        self.roundsLost = 0      # . Number of rounds lost

        self.playerKills = defaultdict(int)    # A Number of kills against
                                               #   individual people
        self.playerDeaths = defaultdict(int)   # A Number of deaths from
                                               #   individual people
        self.upgradesUsed = defaultdict(int)   # G Number of each upgrade used

        self.timeAlive = 0.0     # G Total time alive
        self.timeDead = 0.0      # G Total time dead

        self.killStreak = 0      # G Number of kills made without dying
        self.currentKillStreak = 0
        self.tagStreak = 0       # G Number of zones tagged without dying
        self.currentTagStreak = 0
        self.aliveStreak = 0.0   # G Greatest time alive in one life
        self.lastTimeRespawned = None
        self.lastTimeDied = None
        self.lastTimeSaved = None

        self.player.onCoinsSpent.addListener(self.coinsSpent)
        self.player.onShotFired.addListener(self.shotFired)
        self.player.onDied.addListener(self.died)
        self.player.onRespawned.addListener(self.respawned)
        self.player.onKilled.addListener(self.killed)
        self.player.onShotHitSomething.addListener(self.shotHit)
        self.player.onUsedUpgrade.addListener(self.upgradeUsed)
        self.player.onCoinsChanged.addListener(self.coinsChanged)

    def stop(self):
        self.player.onCoinsSpent.removeListener(self.coinsSpent)
        self.player.onShotFired.removeListener(self.shotFired)
        self.player.onDied.removeListener(self.died)
        self.player.onRespawned.removeListener(self.respawned)
        self.player.onKilled.removeListener(self.killed)
        self.player.onShotHitSomething.removeListener(self.shotHit)
        self.player.onUsedUpgrade.removeListener(self.upgradeUsed)
        self.player.onCoinsChanged.removeListener(self.coinsChanged)

    def shotFired(self, *args, **kwargs):
        self.shotsFired += 1

        if self.shotsFired >= 100:
            accuracy = self.accuracy()
            if accuracy >= 0.10:
                self.sendAchievementProgress('accuracySmall')
            if accuracy >= 0.15:
                self.sendAchievementProgress('accuracyMedium')
            if accuracy >= 0.20:
                self.sendAchievementProgress('accuracyLarge')

        if self.totalPoints() >= 1337:
            self.sendAchievementProgress('statScore')

    def sendAchievementProgress(self, achievementId):
        if self.player.id == -1:
            # Player is no longer in game.
            return
        if not self.gameRecorder:
            return
        self.gameRecorder.game.achievementManager.triggerAchievement(
            self.player, achievementId)

    def _updateStreaks(self, updateAlive):
        '''
        updateAlive will be set to True in three situations:
          1. if the player has just died
          2. if the player was alive when the game ended
          3. if the player was alive when they disconnected
        '''
        self.killStreak = max(self.killStreak, self.currentKillStreak)
        self.tagStreak = max(self.tagStreak, self.currentTagStreak)

        time = timeNow()

        if updateAlive and self.lastTimeRespawned:
            lastLife = time - self.lastTimeRespawned
            self.aliveStreak = max(self.aliveStreak, lastLife)
            self.timeAlive += lastLife
            if lastLife >= 180:
                self.sendAchievementProgress('aliveStreak')

        elif self.lastTimeDied is not None:
            self.timeDead += time - self.lastTimeDied

        self.currentKillStreak = 0
        self.currentTagStreak = 0

    def died(self, killer, deathType):
        self.deaths += 1
        self.playerDeaths[killer] += 1

        time = timeNow()

        self._updateStreaks(True)

        self.lastTimeDied = time

        if self.timeAlive >= 1000:
            self.sendAchievementProgress('totalAliveTime')

        if self.timeAlive >= 300 and self.timeAlive >= (self.timeAlive +
                self.timeDead) * 0.75:
            self.sendAchievementProgress('stayingAlive')

    def respawned(self):
        time = timeNow()

        if self.lastTimeDied is not None:
            self.timeDead += (time - self.lastTimeDied)

        self.lastTimeRespawned = time

    def goneFromGame(self):
        self._updateStreaks(not self.player.dead)

    def gameOver(self, winningTeam):
        self._updateStreaks(not self.player.dead)
        if winningTeam is None:
            # Draw. Do nothing
            pass
        elif self.player.isEnemyTeam(winningTeam):
            self.roundsLost += 1
        else:
            self.roundsWon += 1

    def killed(self, victim, deathType, *args, **kwargs):
        self.kills += 1
        self.playerKills[victim] += 1
        self.currentKillStreak += 1

        self.killStreak = max(self.killStreak, self.currentKillStreak)

    def zoneTagged(self):
        self.zoneTags += 1
        self.currentTagStreak += 1

        self.tagStreak = max(self.tagStreak, self.currentTagStreak)

    def tagAssist(self):
        self.zoneAssists += 1

    def shotHit(self, *args, **kwargs):
        self.shotsHit += 1

    def coinsSpent(self, coins):
        self.coinsUsed += coins

        if self.coinsUsed >= 1000 and self.coinsUsed >= self.coinsEarned * 0.5:
            self.sendAchievementProgress('useCoinsEfficiently')

    def coinsChanged(self, oldCoins):
        if self.player.coins < oldCoins:
            self.coinsLost += oldCoins - self.player.coins
        else:
            self.coinsEarned += self.player.coins - oldCoins

    def upgradeUsed(self, upgrade):
        self.upgradesUsed[upgrade.upgradeType] += 1

    def totalPoints(self):
        points = 0
        points += self.kills        * 10
        points += self.deaths       * 1
        points += self.zoneTags     * 20
        points += self.zoneAssists  * 5
        points += self._accuracyPoints()

        return points

    def _accuracyPoints(self):
        if self.shotsFired == 0:
            return 0
        return ((self.shotsHit ** 2.) / self.shotsFired) * 30

    def accuracy(self):
        if self.shotsFired == 0:
            return 0
        return self.shotsHit * 1. / self.shotsFired

    def statDict(self):
        stats = {}
        for val in ('aliveStreak', 'deaths', 'killStreak', 'kills',
                'roundsLost', 'roundsWon', 'shotsFired', 'shotsHit',
                'coinsEarned', 'coinsUsed', 'tagStreak',
                'timeAlive', 'timeDead', 'upgradesUsed', 'zoneAssists',
                'zoneTags'):
            stats[val] = getattr(self, val)
        stats['bot'] = self.player.bot
        stats['team'] = self.player.teamId
        stats['username'] = (self.player.user.username if self.player.user
                else None)
        stats['coinsWasted'] = self.coinsLost - self.coinsUsed

        # We've stored these dicts as player objects (meaning rejoins may be
        # credited in two places)
        # Here, we combine them by aggregating on player nick (which should be
        # the same)
        for attribute in 'playerKills', 'playerDeaths':
            dictionary = getattr(self, attribute)
            newDict = {}
            for player, value in dictionary.iteritems():
                if player is None:
                    continue
                newDict[player.nick] = value
            stats[attribute] = newDict

        return stats

    def rejoined(self, player):
        self.player = player


class StatKeeper(object):

    def __init__(self, gameRecorder, world, filename):
        self.gameRecorder = gameRecorder
        self.world = world
        self.filename = filename
        # In case the server dies prematurely, it's nice
        # To at least have the file there so that
        # future games don't accidentally point to this one.
        if filename:
            with open(self.filename, 'w') as f:
                f.write('{}')

        # A mapping of player ids to statLists
        # (Contains only players currently in the game)
        self.playerStatList = {}
        # A list of all statLists
        # (regardless of in-game status)
        self.allPlayerStatLists = {}
        self.winningTeamId = None

        self.world.onZoneTagged.addListener(self.zoneTagged)
        self.world.onPlayerAdded.addListener(self.playerAdded)
        self.world.onPlayerRemoved.addListener(self.playerRemoved)
        self.world.onStandardGameFinished.addListener(self.gameOver)

        for player in self.world.players:
            self.playerAdded(player)

    def stop(self):
        self.save()
        self.world.onZoneTagged.removeListener(self.zoneTagged)
        self.world.onPlayerAdded.removeListener(self.playerAdded)
        self.world.onPlayerRemoved.removeListener(self.playerRemoved)
        self.world.onStandardGameFinished.removeListener(self.gameOver)
        for playerStats in self.allPlayerStatLists.values():
            playerStats.stop()

    def save(self):
        if not self.filename:
            return
        stats = {}
        stats['players'] = {}
        for playerStat in self.allPlayerStatLists.values():
            stats['players'][playerStat.player.nick] = playerStat.statDict()
        if self.winningTeamId != None:
            stats['winningTeamId'] = self.winningTeamId
        with open(self.filename, 'w') as f:
            json.dump(stats, f, indent=4)

    def zoneTagged(self, zone, player, previousOwner):
        if player is None:
            return
        self.playerStatList[player.id].zoneTagged()
        for assistant in zone.players:
            if assistant.dead:
                continue
            if assistant.team == player.team and assistant != player:
                self.playerStatList[assistant.id].tagAssist()

    def playerAdded(self, player):
        statkeeper = self.allPlayerStatLists.get(player.identifyingName)
        if statkeeper:
            statkeeper.rejoined(player)
        else:
            statkeeper = PlayerStatKeeper(self.gameRecorder, player)
            self.allPlayerStatLists[player.identifyingName] = statkeeper
        self.playerStatList[player.id] = statkeeper

    def playerRemoved(self, player, oldId):
        self.playerStatList[oldId].goneFromGame()
        # Just remove this from the list of current players
        # (retain in list of all stats)
        del self.playerStatList[oldId]

    def gameOver(self, team):
        self.winningTeamId = team.id if team else NEUTRAL_TEAM_ID
        # Only credit current players for game over
        for playerStat in self.playerStatList.values():
            playerStat.gameOver(team)
        self.save()


class ServerGameStats(object):
    def __init__(self, game):
        from trosnoth.djangoapp.models import GameRecord

        self.game = game
        self.world = game.world
        self.gameRecord = GameRecord(
            started=datetime.datetime.now(),
            serverVersion=serverVersion,
            blueTeamName=self.world.teams[0].teamName,
            redTeamName=self.world.teams[1].teamName,
            replayName=os.path.basename(game.gameRecorder.replayFilename),
            zoneCount=self.world.map.layout.getZoneCount(),
        )
        self.startGameTime = self.world.getMonotonicTime()
        self.statKeeper = StatKeeper(None, self.world, None)

    def stopAndSave(self):
        '''
        Saves the game stats to the server database.
        '''
        from trosnoth.djangoapp.models import (
            TrosnothUser, GamePlayer, PlayerKills, UpgradesUsedInGameRecord,
        )

        self.statKeeper.stop()
        for playerStat in self.statKeeper.playerStatList.values():
            playerStat._updateStreaks(not playerStat.player.dead)

        self.gameRecord.finished = datetime.datetime.now()
        self.gameRecord.gameSeconds = (
            self.world.getMonotonicTime() - self.startGameTime)

        winner = self.world.level.getWinner()
        winnerId = winner.id if winner is not None else ''
        self.gameRecord.winningTeam = winnerId
        dbqueue.add(self.gameRecord.save)

        playerRecords = {}
        for playerStat in self.statKeeper.allPlayerStatLists.itervalues():
            player = playerStat.player
            if player.user:
                user = TrosnothUser.fromUser(
                    username=player.user.username)
                bot = False
                botName = ''
            else:
                user = None
                bot = player.bot
                botName = player.nick

            record = GamePlayer(
                game=self.gameRecord,
                user=user, bot=bot, botName=botName,
                team=player.team.id if player.team else '',

                coinsEarned=playerStat.coinsEarned,
                coinsWasted=playerStat.coinsLost - playerStat.coinsUsed,
                coinsUsed=playerStat.coinsUsed,
                kills=playerStat.kills,
                deaths=playerStat.deaths,
                zoneTags=playerStat.zoneTags,
                zoneAssists=playerStat.zoneAssists,
                shotsFired=playerStat.shotsFired,
                shotsHit=playerStat.shotsHit,
                timeAlive=playerStat.timeAlive,
                timeDead=playerStat.timeDead,
                killStreak=playerStat.killStreak,
                tagStreak=playerStat.tagStreak,
                aliveStreak=playerStat.aliveStreak,
            )
            self.queueSaveWithAttrs(record, ['game'])
            playerRecords[player.identifyingName] = record

            for upgradeType, count in playerStat.upgradesUsed.iteritems():
                upgradeRecord = UpgradesUsedInGameRecord(
                    gamePlayer=record,
                    upgrade=upgradeType,
                    count=count,
                )
                self.queueSaveWithAttrs(upgradeRecord, ['gamePlayer'])

        for playerStat in self.statKeeper.allPlayerStatLists.itervalues():
            killeeRecord = playerRecords[playerStat.player.identifyingName]
            killEntries = {}
            for killer, count in playerStat.playerDeaths.iteritems():
                if killer:
                    killerRecord = playerRecords[killer.identifyingName]
                else:
                    killerRecord = None

                if killer in killEntries:
                    # Same killer after disconnect / reconnect
                    killRecord = killEntries[killer]
                else:
                    killRecord = PlayerKills(
                        killer=killerRecord,
                        killee=killeeRecord,
                    )
                    killEntries[killer] = killRecord

                killRecord.count += count

            for killRecord in killEntries.itervalues():
                self.queueSaveWithAttrs(killRecord, ['killee', 'killer'])

    def queueSaveWithAttrs(self, record, attrs):
        '''
        The Django ORM seems to store the ID of foreign key relationships when
        the attribute is first set, so if you set the relationship before the
        related object is first saved, saving will break. Getting and setting
        again just before the save is good enough to make Django happy.
        '''
        @dbqueue.add
        def saveEndOfGameStats():
            for attr in attrs:
                setattr(record, attr, getattr(record, attr))
            record.save()