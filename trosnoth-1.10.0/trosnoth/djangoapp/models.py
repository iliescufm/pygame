# coding: utf-8

from django.contrib.auth.models import User
from django.db import models
from django.utils.encoding import python_2_unicode_compatible


class TrosnothServerSettings(models.Model):
    serverName = models.TextField(default='My First Trosnoth Server')
    welcomeText = models.TextField(default=(
        'Congratulations! You have successfully installed your Trosnoth '
        'server. <a href="admin/trosnoth/trosnothserversettings/">'
        'Click here</a> to configure it.'))

    allowRemoteGameRegistration = models.BooleanField(default=True)

    iceEnabled = models.BooleanField(default=False)
    iceHost = models.TextField(default='127.0.0.1')
    icePort = models.IntegerField(default=6502)
    iceProxyStringOverride = models.TextField(default='', blank=True)
    iceSecret = models.TextField(default='', blank=True)

    @staticmethod
    def get():
        rows = TrosnothServerSettings.objects.all()
        if rows.count() == 0:
            result = TrosnothServerSettings()
            result.save()
        else:
            result = rows[0]
        return result

    class Meta:
        verbose_name_plural = 'Trosnoth server setting'


class TrosnothUser(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, primary_key=True)
    nick = models.TextField(unique=True)
    lastSeen = models.DateTimeField(null=True, blank=True)
    oldPasswordHash = models.BinaryField(default='')

    def __str__(self):
        return '{} ({})'.format(self.nick, self.user.username)

    @staticmethod
    def fromUser(**kwargs):
        user = User.objects.get(**kwargs)
        if hasattr(user, 'trosnothuser'):
            result = user.trosnothuser
        else:
            result = TrosnothUser(user=user, nick=user.username)
            result.save()
        return result


class AchievementProgress(models.Model):
    user = models.ForeignKey(TrosnothUser)
    achievementId = models.TextField()
    unlocked = models.BooleanField(default=False)
    progress = models.IntegerField(default=0)
    data = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = 'Achievement progress records'
        unique_together = ('user', 'achievementId')

    def __str__(self):
        return '{}: {}'.format(self.user.nick, self.achievementId)


@python_2_unicode_compatible
class GameRecord(models.Model):
    started = models.DateTimeField()
    finished = models.DateTimeField()
    gameSeconds = models.FloatField(default=0)
    serverVersion = models.TextField()
    blueTeamName = models.TextField()
    redTeamName = models.TextField()
    winningTeam = models.CharField(max_length=1, blank=True)
    replayName = models.TextField(default='', blank=True)
    zoneCount = models.IntegerField()

    def __str__(self):
        secs = self.gameSeconds
        mins, secs = divmod(secs, 60)
        if mins == 0:
            duration = '{} s'.format(secs)
        else:
            duration = '{}:{:02d}'.format(int(mins), int(secs))

        return u'Game {} ({} vs. {}, {}, {})'.format(
            self.pk,
            self.blueTeamName, self.redTeamName,
            self.getScoreString(),
            duration,
        )

    def getScoreString(self):
        if not self.winningTeam:
            scores = u'½-½'
        elif self.winningTeam == 'A':
            scores = '1-0'
        else:
            scores = '0-1'
        return scores


class GamePlayer(models.Model):
    game = models.ForeignKey(GameRecord)
    user = models.ForeignKey(TrosnothUser, null=True)
    bot = models.BooleanField(default=False)
    botName = models.TextField(blank=True, default='')
    team = models.CharField(max_length=1, blank=True)

    coinsEarned = models.IntegerField(default=0)
    coinsWasted = models.IntegerField(default=0)
    coinsUsed = models.IntegerField(default=0)
    kills = models.IntegerField(default=0)
    deaths = models.IntegerField(default=0)
    zoneTags = models.IntegerField(default=0)
    zoneAssists = models.IntegerField(default=0)
    shotsFired = models.IntegerField(default=0)
    shotsHit = models.IntegerField(default=0)
    timeAlive = models.FloatField(default=0)
    timeDead = models.FloatField(default=0)
    killStreak = models.IntegerField(default=0)
    tagStreak = models.IntegerField(default=0)
    aliveStreak = models.FloatField(default=0)

    class Meta:
        unique_together = ('game', 'user')

    def __str__(self):
        return '{}: {}'.format(self.nameStr(), self.game)

    def nameStr(self):
        if self.user:
            return '{}'.format(self.user)
        if self.bot:
            return '{} (bot)'.format(self.botName)
        return '{} (unregistered)'.format(self.botName)


class UpgradesUsedInGameRecord(models.Model):
    gamePlayer = models.ForeignKey(GamePlayer)
    upgrade = models.CharField(max_length=1)
    count = models.IntegerField(default=0)

    class Meta:
        unique_together = ('gamePlayer', 'upgrade')

    def __str__(self):
        return '{}: {}: {}'.format(self.gamePlayer, self.upgrade, self.count)


class PlayerKills(models.Model):
    killer = models.ForeignKey(GamePlayer, related_name='+', null=True)
    killee = models.ForeignKey(GamePlayer, related_name='+')
    count = models.IntegerField(default=0)

    class Meta:
        verbose_name_plural = 'Player kills records'
        unique_together = ('killer', 'killee')

    def __str__(self):
        return '{}: {} killed {}: {}'.format(
            self.getGame(),
            self.killer.nameStr() if self.killer else 'no-one',
            self.killee.nameStr(),
            self.count,
        )

    def getGame(self):
        return self.killee.game
