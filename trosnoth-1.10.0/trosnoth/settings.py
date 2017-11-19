import logging

import os

import pygame
from twisted.internet import reactor

from trosnoth.const import MAP_TO_SCREEN_SCALE
from trosnoth.data import getPath, user
from trosnoth.utils import unrepr
from trosnoth.utils.event import Event
import trosnoth.version

log = logging.getLogger('settings')


class SettingsObject(object):
    '''
    Base class for defining settings objects. Defines some functionality for
    loading and saving settings.

    Subclasses should, at a minimum, define the `attributes` member to be a
    sequence of (attrname, key, default) tuples. Attributes then become
    accessible directly on the settings object as python attributes.
    '''

    def __init__(self, app):
        self.app = app
        self.reset()

    def reset(self):
        '''
        Resets all attributes in self.attributes to the values stored on disk.
        '''
        data = self._loadSettingsFile()

        for attr, key, default in self.attributes:
            setattr(self, attr, data.get(key, default))

    def apply(self):
        '''
        Should be overridden by subclasses to perform actions needed to put
        settings changes into effect.
        '''
        pass

    def save(self):
        '''
        Writes the settings to file in a JSON-like format.
        '''
        # Write to file
        fn = getPath(user, self.dataFileName)
        f = open(fn, 'w')
        data = {}
        for attr, key, default in self.attributes:
            data[key] = getattr(self, attr)
        f.write(repr(data))
        f.close()

    def _getSettingsFilename(self):
        '''
        Returns the path to the file that should be used to save and load these
        settings. May be overridden by subclasses.
        '''
        return getPath(user, self.dataFileName)

    def _loadSettingsFile(self):
        '''
        Loads the data from the settings file and returns it in a dict.
        '''
        filename = self._getSettingsFilename()
        try:
            f = open(filename, 'r')
            d = unrepr.unrepr(f.read())
            if not isinstance(d, dict):
                d = {}
        except IOError:
            d = {}
        return d


class DisplaySettings(SettingsObject):
    '''
    Stores the Trosnoth display settings.
    '''
    DEFAULT_THEME = 'default'
    dataFileName = 'display'
    attributes = (
        ('size', 'size', None),
        ('fullScreen', 'fullscreen', False),
        ('_old_useAlpha', 'usealpha', True),
        ('_old_windowsTranslucent', 'windowsTranslucent', False),
        ('detailLevel', 'detailLevel', None),
        ('fsSize', 'fsSize', None),
        ('theme', 'theme', DEFAULT_THEME),
        ('showObstacles', 'showObstacles', False),
        ('showTimings', 'showTimings', False),
        ('cursor', 'cursor', 0),
    )

    DETAIL_LEVELS = ['lowest', 'shrunk', 'low', 'default', 'full']

    def __init__(self, *args, **kwargs):
        super(DisplaySettings, self).__init__(*args, **kwargs)
        self.onDetailLevelChanged = Event()
        self.pendingScreenResize = None
        reactor.callLater(0, self.subscribeToScreenResize)

    def subscribeToScreenResize(self):
        # This cannot be done directly during the __init__, because we need to
        # be able to load the display settings in order to initialise the
        # ScreenManager.
        self.app.screenManager.onResize.addListener(self.screenResized)

    def screenResized(self):
        if self.pendingScreenResize:
            self.pendingScreenResize.cancel()
        self.pendingScreenResize = reactor.callLater(
            1, self.processScreenResize)

    def processScreenResize(self):
        self.pendingScreenResize = None
        if self.app.screenManager.isFullScreen():
            return
        self.size = self.app.screenManager.size
        self.save()

    def reset(self):
        SettingsObject.reset(self)

        if self.size is None:
            nWidth, nHeight = max(pygame.display.list_modes())
            self.size = (min(nWidth, 1500), min(nHeight, 850))
        if self.fsSize is None:
            self.fsSize = max(pygame.display.list_modes())
        if self.detailLevel is None:
            if self._old_useAlpha and self._old_windowsTranslucent:
                self.detailLevel = 'full'
            elif self._old_useAlpha or self._old_windowsTranslucent:
                self.detailLevel = 'default'
            else:
                self.detailLevel = 'lowest'
        self.lastDetailLevel = self.detailLevel
        self.applyDetailLevel()
        self.applyCursor()

    def applyDetailLevel(self):
        self.perPixelAlpha = True
        self.alphaOverlays = True
        self.paralaxBackgrounds = True
        self.maxViewportWidth = int(1536 * MAP_TO_SCREEN_SCALE + 0.5)
        self.maxViewportHeight = int(960 * MAP_TO_SCREEN_SCALE + 0.5)
        if self.detailLevel == 'full':
            return

        self.paralaxBackgrounds = False
        if self.detailLevel == 'default':
            return

        self.perPixelAlpha = False
        if self.detailLevel == 'low':
            return

        self.maxViewportWidth = 1024
        self.maxViewportHeight = 768
        if self.detailLevel == 'shrunk':
            return

        # If we're going this low, we really want performance
        self.maxViewportWidth = 800
        self.maxViewportHeight = 600
        self.alphaOverlays = False

    def getSurfaceFlagsHack(self):
        # 2015-10-07 We have empirically determined that setting the flags to
        # pygame.SRCALPHA actually improves the frame rate when compared to
        # setting the flags to 0. Therefore we abandon common sense and just do
        # what works. It could be worth retesting this every so often to make
        # sure it's still the case.

        # return pygame.SRCALPHA if self.perPixelAlpha else 0
        return pygame.SRCALPHA

    def getSize(self):
        if self.fullScreen:
            return self.fsSize
        else:
            return self.size

    def apply(self):
        '''
        Apply the current settings.
        '''
        size = self.getSize()

        # Don't bother changing the screen if the settings that matter haven't
        # changed
        if (size != self.app.screenManager.size) or (
                self.fullScreen != self.app.screenManager.isFullScreen()):
            # Tell the main program to change its screen size.
            self.app.changeScreenSize(size, self.fullScreen)

        if self.lastDetailLevel != self.detailLevel:
            self.lastDetailLevel = self.detailLevel
            self.applyDetailLevel()
            self.onDetailLevelChanged()

        self.applyCursor()

    CURSORS = {
        0: ((32, 32), (15, 15)) + pygame.cursors.compile([
            ' XXXX                      XXXX ',
            'XXXXXX                    XXXXXX',
            'XX...XX                  XX...XX',
            'XX....XX                XX....XX',
            'XX.....XX              XX.....XX',
            ' XX.....XX            XX.....XX ',
            '  XX.....XX          XX.....XX  ',
            '   XX.....XX        XX.....XX   ',
            '    XX.....XX      XX.....XX    ',
            '     XX.....XX    XX.....XX     ',
            '      XX....XX    XX....XX      ',
            '       XX..XXX    XXX..XX       ',
            '        XXXXX      XXXXX        ',
            '         XXX        XXX         ',
            '                                ',
            '                                ',
            '                                ',
            '                                ',
            '         XXX        XXX         ',
            '        XXXXX      XXXXX        ',
            '       XX..XXX    XXX..XX       ',
            '      XX....XX    XX....XX      ',
            '     XX.....XX    XX.....XX     ',
            '    XX.....XX      XX.....XX    ',
            '   XX.....XX        XX.....XX   ',
            '  XX.....XX          XX.....XX  ',
            ' XX.....XX            XX.....XX ',
            'XX.....XX              XX.....XX',
            'XX....XX                XX....XX',
            'XX...XX                  XX...XX',
            'XXXXXX                    XXXXXX',
            ' XXXX                      XXXX ',
        ]),
    }

    def applyCursor(self):
        cursor = self.CURSORS.get(self.cursor, pygame.cursors.broken_x)
        pygame.mouse.set_cursor(*cursor)


class SoundSettings(SettingsObject):
    dataFileName = 'sound'
    attributes = (
        ('soundEnabled', 'playSound', False),
        ('musicEnabled', 'playMusic', True),
        ('musicVolume', 'musicVolume', 100),
        ('soundVolume', 'soundVolume', 100),
    )

    def apply(self):
        '''
        Apply the current settings.
        '''

        if self.musicEnabled != self.app.musicManager.isMusicPlaying():
            if self.musicEnabled:
                self.app.musicManager.playMusic()
            else:
                self.app.musicManager.stopMusic()

        self.app.musicManager.setVolume(self.musicVolume)

        if self.soundEnabled:
            self.app.soundPlayer.setMasterVolume(self.soundVolume / 100.)
        else:
            self.app.soundPlayer.setMasterVolume(0)


class IdentitySettings(SettingsObject):
    dataFileName = 'identity'
    attributes = (
        ('nick', 'nick', None),
        ('usernames', 'usernames', None),
        ('firstTime', 'firstTime', True),
    )

    def __init__(self, app):
        self.app = app
        self.reset()

    def reset(self):
        SettingsObject.reset(self)
        if self.usernames is None:
            self.usernames = {}

    def setNick(self, nick):
        self.nick = nick
        self.save()

    def notFirstTime(self):
        self.firstTime = False
        self.save()


class ConnectionSettings(SettingsObject):
    dataFileName = 'connection'
    attributes = (
        ('servers', 'servers', None),
        ('otherGames', 'otherGames', True),
        ('lanGames', 'lanGames', 'afterInet'),
        ('createGames', 'createGames', True),
    )

    def __init__(self, app):
        SettingsObject.__init__(self, app)
        if self.servers is None:
            self.servers = [('localhost', 6787, 'http://localhost:8080/')]
            if trosnoth.version.release:
                self.servers.append(
                    ('play.trosnoth.org', 6787, 'http://play.trosnoth.org/'))
        else:
            # For developers who have saved settings.
            for i, s in enumerate(self.servers):
                if s == ('localhost', 6787):
                    self.servers[i] = (
                        'localhost', 6787, 'http://localhost:8080/')
                elif len(s) == 2:
                    self.servers[i] = (s[0], s[1], 'http://%s/' % (s[0],))


class AuthServerSettings(SettingsObject):
    '''
    Stores general settings for the authentication server.
    '''
    attributes = (
        ('keyLength', 'keyLength', 512),
        ('lobbySize', 'lobbySize', (2, 1)),
        ('maxPerTeam', 'playersPerTeam', 100),
        ('allowNewUsers', 'allowNewUsers', True),
        ('privateMsg', 'privateMsg', None),
        ('elephantOwners', 'elephantOwners', ()),
        ('serverName', 'serverName', 'Trosnoth server'),
        ('homeUrl', 'homeUrl', None),
        ('hostName', 'hostName', None),
        ('xmppUsername', 'xmppUsername', None),
        ('xmppPassword', 'xmppPassword', None),
    )

    def __init__(self, dataPath):
        self.dataFileName = os.path.join(dataPath, 'settings')
        self.reset()

    def _getSettingsFilename(self):
        return self.dataFileName

    def reset(self):
        SettingsObject.reset(self)
        self.elephantOwners = set(p.lower() for p in self.elephantOwners)
        if self.privateMsg is None or len(self.privateMsg) == 0:
            self.privateMsg = 'This is a private server.'

    def createNotificationClient(self):
        '''
        Either returns an xmpp.NotificationClient or None.
        '''
        username = self.xmppUsername
        password = self.xmppPassword
        if (not username) or (not password):
            return None

        try:
            from trosnoth.network.xmpp import NotificationClient
        except ImportError, E:
            log.warning('Could not import xmpp notification client: %s', E)
            return None

        return NotificationClient(username, password)
