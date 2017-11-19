# coding: utf-8
from __future__ import division

from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.http import Http404
from django.shortcuts import render

from trosnoth.gamerecording.achievementlist import availableAchievements
from trosnoth.model.upgrades import upgradeOfType
from .models import (
    TrosnothServerSettings, TrosnothUser, GameRecord, PlayerKills,
    UpgradesUsedInGameRecord,
)

POINT_VALUES = {
    'kills': 10,
    'deaths': 1,
    'zoneTags': 20,
    'accuracy': 20,
    'coinsUsed': 3,
    'zoneAssists': 5,
}

def index(request):
    context = {
        'settings': TrosnothServerSettings.get(),
    }
    return render(request, 'trosnoth/index.html', context)


def userProfile(request, userId, nick=None):
    try:
        user = TrosnothUser.fromUser(pk=userId)
    except User.DoesNotExist:
        raise Http404('User not found')

    unlocked = []
    locked = []
    for a in user.achievementprogress_set.all():
        try:
            name, description = availableAchievements.getAchievementDetails(
                a.achievementId)
        except KeyError:
            if not a.unlocked:
                continue
            name = a.achievementId
            description = (
                'This achievement does not exist in this version of Trosnoth')

        if finders.find(
                'trosnoth/achievements/{}.png'.format(a.achievementId)):
            imageId = a.achievementId
        else:
            imageId = 'default'

        info = {
            'name': name,
            'description': description,
            'imageId': imageId,
        }
        if a.unlocked:
            unlocked.append(info)
        else:
            locked.append(info)
    unlocked.sort(key=lambda a: a['name'])
    locked.sort(key=lambda a: a['name'])

    context = {
        'settings': TrosnothServerSettings.get(),
        'trosnothUser': user,
        'unlocked': unlocked,
        'locked': locked,
    }
    return render(request, 'trosnoth/user.html', context)


def userList(request):
    context = {
        'settings': TrosnothServerSettings.get(),
        'users': TrosnothUser.objects.order_by('-lastSeen'),
    }
    return render(request, 'trosnoth/userlist.html', context)


def viewGame(request, gameId):
    game = GameRecord.objects.get(pk=gameId)

    data = []

    for player in game.gameplayer_set.all():
        entry = {
            'player': player,
            'nick': player.user.nick if player.user else player.botName,
            'accuracy': (100.0 * player.shotsHit / player.shotsFired
                ) if player.shotsFired else 0.,
            'score': 0,
            'kdr': u'{:2.2f}'.format(player.kills / player.deaths
                ) if player.deaths else u'∞',
            'adr': u'{:2.2f}'.format(player.timeAlive / player.timeDead
                ) if player.timeDead else u'∞',
        }

        for stat, value in POINT_VALUES.iteritems():
            if stat in entry:
                value = entry[stat]
            else:
                value = getattr(player, stat)
            entry['score'] += value

        data.append(entry)

    data.sort(key=(lambda entry: entry['score']), reverse=True)

    i = 1
    j = 0
    for entry in data:
        entry['index'] = j
        if entry['player'].bot:
            entry['rank'] = 'B'
        else:
            entry['rank'] = str(i)
            i += 1
        j += 1

    killData = {}
    for pkr in PlayerKills.objects.filter(killee__game=game):
        killData[pkr.killer, pkr.killee] = pkr.count

    killTable = []
    for killerEntry in data:
        killer = killerEntry['player']
        killRow = []
        maxKillCount = maxDeathCount = 0
        maxKill = maxDeath = '-'
        for killeeEntry in data:
            killee = killeeEntry['player']
            count = killData.get((killer, killee), 0)
            killRow.append(count)
            if count > maxKillCount:
                maxKillCount = count
                maxKill = '{} ({})'.format(killeeEntry['nick'], count)
            dieCount = killData.get((killee, killer), 0)
            if dieCount > maxDeathCount:
                maxDeathCount = dieCount
                maxDeath = '{} ({})'.format(killeeEntry['nick'], dieCount)
        killerEntry['maxKill'] = maxKill
        killerEntry['maxDeath'] = maxDeath

        killTable.append({
            'player': killerEntry['player'],
            'nick': killerEntry['nick'],
            'entries': killRow,
        })

    for i in xrange(len(killTable)):
        killTable[i]['entries'][i] = '-'

    otherKills = [
        killData.get((None, killeeEntry['player']), 0)
        for killeeEntry in data
    ]

    upgradeData = {}
    upgradeCodes = set()
    for ur in UpgradesUsedInGameRecord.objects.filter(gamePlayer__game=game):
        upgradeData[ur.gamePlayer, ur.upgrade] = ur.count
        upgradeCodes.add(ur.upgrade)

    if upgradeCodes:
        nameAndCode = []
        for code in upgradeCodes:
            if code in upgradeOfType:
                name = upgradeOfType[code].name
            else:
                name = '?{}?'.format(code)
            nameAndCode.append((name, code))

        nameAndCode.sort()
        upgradeList = [name for name, code in nameAndCode]
        upgradeTable = []
        for entry in data:
            entries = []
            maxUpgrade = '-'
            maxUpgradeCount = 0
            for name, code in nameAndCode:
                count = upgradeData.get((entry['player'], code), 0)
                entries.append(count)
                if count > maxUpgradeCount:
                    maxUpgrade = '{} ({})'.format(name, count)
                    maxUpgradeCount = count

            entry['maxUpgrade'] = maxUpgrade

            upgradeTable.append({
                'player': entry['player'],
                'nick': entry['nick'],
                'entries': entries,
            })
    else:
        upgradeList = []
        upgradeTable = []

    context = {
        'settings': TrosnothServerSettings.get(),
        'game': game,
        'playerData': data,
        'killTable': killTable,
        'otherKills': otherKills if any(otherKills) else None,
        'upgrades': upgradeList,
        'upgradeTable': upgradeTable,
    }
    return render(request, 'trosnoth/viewgame.html', context)


def gameList(request):
    context = {
        'settings': TrosnothServerSettings.get(),
        'games': GameRecord.objects.order_by('-started'),
    }
    return render(request, 'trosnoth/gamelist.html', context)
