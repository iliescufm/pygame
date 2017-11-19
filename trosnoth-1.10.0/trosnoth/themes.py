'''
themes.py
This module defines the interface to the various different themes.
'''

import functools
import logging
import os
from random import randrange

import pygame
import pygame.transform

from trosnoth import data
import trosnoth.data.themes     # noqa
from trosnoth.const import BODY_BLOCK_SCREEN_SIZE, INTERFACE_BLOCK_SCREEN_SIZE
from trosnoth.gui.fonts.font import Font, ScaledFont
from trosnoth.gui.framework.basics import SingleImage, Animation
from trosnoth.trosnothgui.common import setAlpha
from trosnoth.utils.unrepr import unrepr
from trosnoth.model.universe_base import NEUTRAL_TEAM_ID
from trosnoth.model.upgrades import Upgrade
from trosnoth.utils.utils import timeNow

BLOCK_BACKGROUND_COLOURKEY = (224, 192, 224)
x1 = INTERFACE_BLOCK_SCREEN_SIZE[0]
x2 = x1 + BODY_BLOCK_SCREEN_SIZE[0]
y = BODY_BLOCK_SCREEN_SIZE[1]
BLOCK_OFFSETS = {
    'top': (-x1, 0),
    'btm': (-x1, -y),
    'fwd': ((-x2, -y), (0, 0)),
    'bck': ((-x2, 0), (0, -y)),
}
del x1, x2, y

log = logging.getLogger('themes')


def setToRed(surface):
    '''Inverts the colors of a pygame Screen'''
    surface.lock()

    for x in range(surface.get_width()):
        for y in range(surface.get_height()):
            r, g, b, a = surface.get_at((x, y))
            greyscale = r * 0.298 + g * 0.587 + b * 0.114
            surface.set_at((x, y), (greyscale, 0, 0, a))

    surface.unlock()


def teamColour(colourId):
    def colourFunction(self, team):
        return self.getTeamColour(team, colourId)
    return colourFunction


class ThemeColours(object):
    def getTeamColour(self, team, colourId):
        if team is None:
            teamNum = 0
        else:
            teamNum = ord(team.id) - 64
        return getattr(
            self, 'team%d%s' % (teamNum, colourId),
            getattr(self, 'team0%s' % (colourId,)))

    chatColour = teamColour('chat')
    miniMapTrosballTargetColour = teamColour('Mn_trosball')
    miniMapDarkZoneColour = teamColour('Mn_zone')
    miniMapLightZoneColour = teamColour('Mn_mk')
    miniMapPlayerColour = teamColour('Mn_pl')
    miniMapGhostColour = teamColour('Mn_gh')
    miniMapZoneHighlight = teamColour('Mn_highlight')
    leaderboard = teamColour('Leaderboard')


def cachedProperty(fn):
    @functools.wraps(fn)
    def spriteFunction(self):
        try:
            return self._store[fn]
        except KeyError:
            self._store[fn] = fn(self)
            return self._store[fn]
    return property(spriteFunction)


def cached(fn):
    @functools.wraps(fn)
    def spriteFunction(self, *args):
        try:
            return self._store[fn, args]
        except KeyError:
            self._store[fn, args] = fn(self, *args)
            return self._store[fn, args]
    return spriteFunction


def image(path, **kwargs):
    def imageFunction(self):
        return self.theme.loadSprite(path, sprites=self, **kwargs)
    imageFunction.__name__ = path
    return cachedProperty(imageFunction)


def images(paths, **kwargs):
    def imageFunction(self):
        return self.theme.loadSprites(paths, sprites=self, **kwargs)
    imageFunction.__name__ = ', '.join(paths)
    return cachedProperty(imageFunction)


def wrappedImage(path, **kwargs):
    def imageFunction(self):
        return SingleImage(self.theme.loadSprite(path, sprites=self, **kwargs))
    imageFunction.__name__ = path
    return cachedProperty(imageFunction)


def getTeamId(team):
    if team is None:
        return NEUTRAL_TEAM_ID
    return team.id


class ThemeSpritesBase(object):
    def __init__(self, theme):
        self.theme = theme
        self._store = {}

    def clearCache(self):
        self._store = {}

    smallCoin = image('smallstar.png')
    coin = image('star0.png')
    coinImages = images([
        'star0.png', 'star1.png', 'star2.png', 'star3.png',
        'star4.png', 'star3.png', 'star2.png', 'star1.png',
    ])
    bigCoinImages = images([
        'bigCoin0.png', 'bigCoin1.png', 'bigCoin2.png', 'bigCoin3.png',
        'bigCoin4.png', 'bigCoin3.png', 'bigCoin2.png', 'bigCoin1.png',
    ])
    grenade = image('grenade.png')
    neutralOrb = image('greyOrb.png')
    scenery = image('scenery.png', colourkey=None)
    shoxGun3 = image('shoxgun-3.png')

    gunIcon = wrappedImage('gun.png')
    playerBody = wrappedImage('backbone.png', borders=(0, 0, 1))
    elephant = wrappedImage('elephant.png')
    christmasHat = wrappedImage('christmas.png')
    turretBase = wrappedImage('legs-turret.png')
    playerStanding = wrappedImage('legs-s.png')
    playerJumping = wrappedImage('legs-r3.png')
    ninjaHead = wrappedImage('ninjahead.png')
    blocker1 = image('blocker-1.png')
    blocker2 = image('blocker-2.png')
    bomber1 = image('bomber-1.png')
    bomber2 = image('bomber-2.png')
    jammingHatImage = image('jamminghat.png')
    jammingHatSparks = images([
        'jamminghat-spark1.png', 'jamminghat-spark2.png',
        'jamminghat-spark3.png'])

    runningLegs = images([
        'legs-r1.png', 'legs-r2.png', 'legs-r3.png', 'legs-r4.png'])
    backwardsLegs = images([
        'legs-w0.png', 'legs-w1.png', 'legs-w2.png', 'legs-w3.png'])

    shieldImages = images([
        'shieldImage1.png', 'shieldImage2.png', 'shieldImage3.png',
        'shieldImage2.png'])

    def coinAnimation(self):
        return Animation(0.07, timeNow, *self.coinImages)

    def bigCoinAnimation(self):
        return Animation(0.07, timeNow, *self.bigCoinImages)

    @cached
    def zoneHighlight(self, team, scale):
        colour = self.theme.colours.miniMapZoneHighlight(team)
        size = int(300. / scale + 0.5)
        result = pygame.Surface((2 * size, 2 * size))
        result.fill((0, 0, 0))
        result.set_colorkey((0, 0, 0))
        pygame.draw.circle(result, colour, (size, size), size)
        result.set_alpha(64)
        return result

    @cached
    def bigZoneLetter(self, letter):
        font = self.theme.app.screenManager.fonts.bigZoneFont
        result = font.render(
            self.theme.app, letter, True, self.theme.colours.bigZoneLetter)
        setAlpha(result, 128)
        return result

    @cached
    def ghostAnimation(self, team):
        if team is not None:
            frames = self.theme.loadTeamSprites(
                ['ghost1', 'ghost2', 'ghost3', 'ghost4', 'ghost3', 'ghost2'],
                team.id, self)
        else:
            lts = functools.partial(self.theme.loadTeamSprite, sprites=self)
            frames = [
                lts('ghost1', 'A'), lts('ghost2', 'B'), lts('ghost3', 'A'),
                lts('ghost4', 'B'), lts('ghost3', 'A'), lts('ghost2', 'B')]
        return [Animation(0.25, timeNow, *frames)]

    @cached
    def ghostIcon(self, team):
        return SingleImage(self.theme.loadTeamSprite(
            'ghost1', getTeamId(team), self))

    @cached
    def trosballAnimation(self):
        frame0 = self.theme.loadSprite('trosball.png', sprites=self)
        scale = 25. / max(frame0.get_size())
        frames = []
        for theta in xrange(0, 360, 15):
            frames.append(pygame.transform.rotozoom(frame0, -theta, scale))
        return Animation(0.05, timeNow, *frames)

    @cached
    def trosballWarningAnimation(self):
        frame0 = self.theme.loadSprite('trosball.png', sprites=self)
        scale = 25. / max(frame0.get_size())
        frames = []
        for theta in xrange(0, 360, 15):
            surface = pygame.transform.rotozoom(frame0, -theta, scale)
            # Every 90 degrees, invert the colours
            if (theta / 45) % 2 < 1:
                setToRed(surface)
            frames.append(surface)
        return Animation(0.05, timeNow, *frames)

    def explosion(self):
        return Animation(
            0.07, timeNow, *(self.explosionFrame(i) for i in xrange(4)))

    def shoxwaveExplosion(self):
        return Animation(
            0.05, timeNow, *(self.shoxwaveFrame(i) for i in xrange(3)))

    def trosballExplosion(self):
        return Animation(0.07, timeNow, self.explosionFrame(0))

    def jammingHat(self):
        images = []
        for spark in self.jammingHatSparks:
            images.append(spark)
            images.extend([self.jammingHatImage] * randrange(5, 15))
        return Animation(0.05, timeNow, *images)

    @cached
    def explosionFrame(self, frame):
        return self.theme.loadSprite(
            'explosion%d.png' % (frame + 1,), sprites=self)

    @cached
    def shoxwaveFrame(self, frame):
        return self.theme.loadSprite(
            'shoxwave%d.png' % (frame + 1,), sprites=self)

    @cached
    def playerHolding(self, team):
        return SingleImage(self.theme.loadTeamSprite(
            'hold', getTeamId(team), self, borders=(0, 0, 1)))

    @cached
    def machineGunImages(self, team):
        return self.theme.loadTeamSprites([
            'machinegun-0', 'machinegun-1', 'machinegun-2',
            'machinegun-3', 'machinegun-4', 'machinegun-5',
            'machinegun-6', 'machinegun-7', 'machinegun-8'
        ], getTeamId(team), self, borders=(0, 0, 1))

    @cached
    def ricoGunImages(self, team):
        return self.theme.loadTeamSprites([
            'ricogun-0', 'ricogun-1', 'ricogun-2',
            'ricogun-3', 'ricogun-4', 'ricogun-5',
            'ricogun-6', 'ricogun-7', 'ricogun-8'
        ], getTeamId(team), self, borders=(0, 0, 1))

    @cached
    def gunImages(self, team):
        return self.theme.loadTeamSprites([
            'gun-0', 'gun-1', 'gun-2',
            'gun-3', 'gun-4', 'gun-5',
            'gun-6', 'gun-7', 'gun-8'
        ], getTeamId(team), self, borders=(0, 0, 1))

    @cached
    def playerHead(self, team, bot):
        teamId = getTeamId(team)
        if teamId == 'A':
            path = 'blue'
        elif teamId == 'B':
            path = 'red'
        elif teamId == NEUTRAL_TEAM_ID:
            path = 'white'
        else:
            path = 'team' + teamId + 'Head'
        if bot:
            path += '-bot'
        return SingleImage(self.theme.loadSprite(path + '.png', sprites=self))

    def teamGrenade(self, team):
        teamId = getTeamId(team)
        if teamId == 'A':
            path = 'blueGrenade.png'
        elif teamId == 'B':
            path = 'redGrenade.png'
        else:
            return self.grenade
        return self.theme.loadSprite(path, sprites=self)

    @cached
    def zoneBackground(self, team):
        if team is None:
            path = 'greyzone.png'
        elif team.id == 'A':
            path = 'bluezone.png'
        elif team.id == 'B':
            path = 'redzone.png'
        else:
            return self.zoneBackground(None)
        return self.theme.loadSprite(path, sprites=self)

    @cached
    def upgradeImage(self, upgradeType):
        assert issubclass(upgradeType, Upgrade)
        path = upgradeType.iconPath
        if path is None:
            path = 'upgrade-unknown.png'
        return self.theme.loadSprite(
            path, colourkey=upgradeType.iconColourKey, sprites=self)

    def blockBackground(self, block):
        bd = block.defn

        def zoneOwnerId(zone):
            if zone.owner and zone.dark:
                return zone.owner.id
            else:
                return NEUTRAL_TEAM_ID

        if bd.kind in ('top', 'btm'):
            if bd.zone is None:
                return None
            owners = (zoneOwnerId(block.zone),)
        else:
            if bd.zone1 is None:
                owner1 = None
            else:
                owner1 = zoneOwnerId(block.zone1)
            if bd.zone2 is None:
                owner2 = None
            else:
                owner2 = zoneOwnerId(block.zone2)
            owners = (owner1, owner2)
        result = self._getBlockFromStoreOrBuild(bd.kind, owners)
        return result

    def _getBlockFromStoreOrBuild(self, kind, owners):
        try:
            return self._store['blockBackground', kind, owners]
        except KeyError:
            self._buildBlockBackgrounds()
            return self._store['blockBackground', kind, owners]

    def getFilledBlockBackground(self, block, owner):
        ownerId = owner.id if owner is not None else NEUTRAL_TEAM_ID
        if block.defn.kind in ('top', 'btm'):
            if block.defn.zone is None:
                return None
            else:
                owners = (ownerId,)
        else:
            owner1 = ownerId if block.zone1 is not None else None
            owner2 = ownerId if block.zone2 is not None else None
            owners = (owner1, owner2)
        return self._getBlockFromStoreOrBuild(block.defn.kind, owners)

    def _buildBlockBackgrounds(self):
        '''
        Loads and caches zone backgrounds for all combinations of block owners.
        '''

        filename = 'zone.png'
        flags = self.theme.app.displaySettings.getSurfaceFlagsHack()

        zonePics = self.getZonePics(filename)

        def storePic(kind, owners, pic):
            self._store['blockBackground', kind, owners] = pic

        if self.theme.app.displaySettings.paralaxBackgrounds:
            fillColour = (0, 0, 0, 0)
        else:
            fillColour = BLOCK_BACKGROUND_COLOURKEY

        for kind in ('top', 'btm'):
            for ownerId, zonePic in zonePics.iteritems():
                pic = pygame.Surface(BODY_BLOCK_SCREEN_SIZE, flags)
                pic.fill(fillColour)
                pic.blit(zonePic, BLOCK_OFFSETS[kind])
                storePic(kind, (ownerId,), pic)
        for kind in ('fwd', 'bck'):
            for oid1 in (None, NEUTRAL_TEAM_ID, 'A', 'B'):
                for oid2 in (None, NEUTRAL_TEAM_ID, 'A', 'B'):
                    pic = pygame.Surface(
                        INTERFACE_BLOCK_SCREEN_SIZE, flags)
                    pic.fill(fillColour)
                    if oid1 is not None:
                        pic.blit(
                            zonePics[oid1], BLOCK_OFFSETS[kind][0])
                    if oid2 is not None:
                        pic.blit(
                            zonePics[oid2], BLOCK_OFFSETS[kind][1])
                    storePic(kind, (oid1, oid2), pic)

    def getZonePics(self, filename):
        return {
            NEUTRAL_TEAM_ID: self.theme.loadSprite(
                'grey%s' % (filename,), sprites=self),
            'A': self.theme.loadSprite('blue%s' % (filename,), sprites=self),
            'B': self.theme.loadSprite('red%s' % (filename,), sprites=self),
        }

    @cached
    def orb(self, team):
        teamId = getTeamId(team)
        if teamId == 'A':
            path = 'blueOrb.png'
        elif teamId == 'B':
            path = 'redOrb.png'
        else:
            return self.neutralOrb
        return self.theme.loadSprite(path, sprites=self)

    @cached
    def netOrb(self):
        return self.theme.loadSprite('netOrb.png', sprites=self)

    @cached
    def shotAnimation(self, team):
        teamId = getTeamId(team)

        if teamId == 'A':
            colour = 'blue'
        elif teamId == 'B':
            colour = 'red'
        elif teamId == NEUTRAL_TEAM_ID:
            colour = 'default'
        else:
            colour = 'team' + teamId
        return self.theme.makeShot(colour, self)


class ThemeSprites(ThemeSpritesBase):
    def __init__(self, theme):
        super(ThemeSprites, self).__init__(theme)
        self.greyed = GreyedSprites(self)

    def doTransform(self, img):
        return img

    def clearCache(self):
        super(ThemeSprites, self).clearCache()
        self.greyed.clearCache()


class GreyedSprites(ThemeSpritesBase):
    def __init__(self, sprites):
        super(GreyedSprites, self).__init__(sprites.theme)

    def doTransform(self, img):
        grey_colour = (100, 100, 100)
        result = pygame.Surface(img.get_size())
        result.fill(grey_colour)
        setAlpha(img, 32)
        result.blit(img, (0, 0))
        result.set_colorkey(grey_colour)
        return result


class Theme(object):
    def __init__(self, app):
        self.app = app
        self.paths = []
        self.colours = ThemeColours()
        self.sprites = ThemeSprites(self)
        self.setTheme("default")
#        self.setTheme(app.displaySettings.theme)

        # Building the different zone backgrounds takes time, so do it once on
        # startup.
        self.sprites._buildBlockBackgrounds()

        app.displaySettings.onDetailLevelChanged.addListener(
            self.detailChanged)

    def detailChanged(self):
        self.sprites.clearCache()
        self.sprites._buildBlockBackgrounds()

    def setTheme(self, themeName):
        '''
        Sets the theme to the theme with the given name.
        '''
        self.name = themeName
        self.paths = [data.getPath(data.user), data.getPath(data)]

        def insertPath(p):
            if os.path.exists(p):
                self.paths.insert(0, p)
        insertPath(data.getPath(data.themes, themeName))
        insertPath(data.getPath(data.user, 'themes', themeName))
        self.initFonts()
        self.initSounds()
        self.initColours()

    def initColours(self):
        colourPath = self.getPath('config', 'colours.cfg')
        colourData = self._getColourData(colourPath)
        defaultColours = self._getColourData(data.getPath(data))

        for colourName, colour in defaultColours.iteritems():
            if colourName in colourData:
                colour = colourData[colourName]
            setattr(self.colours, colourName, colour)

    def initSounds(self):
        self.app.soundPlayer.addSound('buyUpgrade.ogg', 'buyUpgrade')
        self.app.soundPlayer.addSound('gameLose.ogg', 'gameLose', channel=0)
        self.app.soundPlayer.addSound('startGame.ogg', 'startGame', channel=0)
        self.app.soundPlayer.addSound('shoot.ogg', 'shoot')
        self.app.soundPlayer.addSound('turret.ogg', 'turret')
        self.app.soundPlayer.addSound('explodeGrenade.ogg', 'explodeGrenade')
        self.app.soundPlayer.addSound('goal.ogg', 'goal', channel=0)
        self.app.soundPlayer.addSound('ownGoal.ogg', 'ownGoal', channel=0)
        self.app.soundPlayer.addSound('bell.ogg', 'gotCoin')

    def initFonts(self):
        fontData = self._getFontData()

        for fontName, defaultDetails in DEFAULT_FONTS.iteritems():
            if fontName in fontData:
                fontFile, size, bold = fontData[fontName]
            else:
                fontFile, size, bold = defaultDetails.unpack()

            if fontName in UNSCALED_FONTS:
                font = Font(fontFile, size, bold)
            else:
                font = ScaledFont(fontFile, size, bold)
            self.app.fonts.addFont(fontName, font)

    def _getFontData(self):
        try:
            fontLines = open(self.getPath('config', 'fonts.cfg')).readlines()
        except IOError:
            return {}

        result = {}
        for line in fontLines:
            bits = line.split("=")
            bits[2] = bits[2].strip()
            # Perform basic checks
            if len(bits) != 3 or not bits[2].isdigit():
                log.warning('Invalid font config line: %r', line)
            else:
                result[bits[0]] = (bits[1], int(bits[2]))
        return result

    def _getColourData(self, filepath):
        try:
            lines = open(self.getPath('config', 'colours.cfg')).readlines()
        except IOError:
            return {}

        result = {}
        for line in lines:
            line = line.strip()
            if line == '' or line.startswith('#'):
                continue
            bits = line.split("=", 1)
            # Perform basic checks
            invalid = False
            if len(bits) != 2:
                invalid = True
            else:
                try:
                    colour = unrepr(bits[1])
                    if type(colour) is str:
                        colour = colour.strip("'")
                except:
                    invalid = True
                else:
                    if colour in result.keys():
                        colour = result[colour]
                    else:
                        if (not isinstance(colour, tuple) or len(colour) < 3 or
                                len(colour) > 4):
                            invalid = True
            if invalid:
                log.warning('Invalid colour config line: %r', line)
            else:
                result[bits[0].strip()] = colour
        return result

    def getPath(self, *pathBits):
        '''
        Returns a path to the given themed file, looking in the following
        locations:
         1. User theme files for the current theme.
         2. Built-in theme files for the current theme.
         3. Default files.
        '''
        for path in self.paths:
            path = os.path.join(path, *pathBits)
            if os.path.isfile(path):
                return path
        raise IOError('file not found: %s' % (os.path.join(*pathBits),))

    def loadSprite(
            self, filename, colourkey=None, sprites=None,
            borders=(127, 127, 127)):
        '''
        Loads the sprite with the given name. A colour key of None may be given
        to disable colourkey transparency.
        '''
        filepath = self.getPath('sprites', filename)
        image = pygame.image.load(filepath)

        alpha = (colourkey is None)
        if alpha:
            image = image.convert_alpha()

            if not self.app.displaySettings.perPixelAlpha:
                # Create a surface that doesn't have the per-pixel alpha
                result = pygame.Surface(image.get_size())
                result.fill(borders)
                result.blit(image, (0, 0))
                result.set_colorkey(borders)
                image = result
        else:
            image = image.convert()
            image.set_colorkey(colourkey)

        if sprites:
            image = sprites.doTransform(image)

        return image

    def loadSprites(self, filenames, sprites, **kwargs):
        images = []
        for filename in filenames:
            images.append(self.loadSprite(filename, sprites=sprites, **kwargs))
        return images

    def makeShot(self, colour, sprites):
        '''
        Creates the shot sprite / animation. This is here because the Pirate
        theme needs the shot to spin, which it does not normally do.
        '''
        shotImg = self.loadSprite('%sShot.png' % (colour,), sprites=sprites)

        if self.name != 'pirate':
            return SingleImage(shotImg)

        numShotImages = 5
        degree = (360 / numShotImages)

        shots = [
            pygame.transform.rotate(shotImg, degree * i)
            for i in range(0, numShotImages)]
        return Animation(0.07, timeNow, *shots)

    def loadTeamSprite(self, filename, teamId, sprites, **kwargs):
        '''
        teamId must be 'A' or 'B'.
        If teamId is 'A', grabs <filename>.png
        If teamId is 'B', grabs <filename>b.png if it exists, or <filename>.png
            otherwise.
        '''
        if teamId == 'B':
            fullFilename = '%sb.png' % (filename,)
            try:
                filepath = self.getPath('sprites', fullFilename)
                if not os.path.isfile(filepath):
                    fullFilename = '%s.png' % (filename,)
            except IOError:
                fullFilename = '%s.png' % (filename,)
        else:
            fullFilename = '%s.png' % (filename,)

        return self.loadSprite(fullFilename, sprites=sprites, **kwargs)

    def loadTeamSprites(self, filenames, teamId, sprites, **kwargs):
        images = []
        for filename in filenames:
            images.append(self.loadTeamSprite(
                filename, teamId, sprites, **kwargs))
        return images


class F(object):

    def __init__(self, fontFile, size, bold=False):
        self.fontFile = fontFile
        self.size = size
        self.bold = bold

    def unpack(self):
        return (self.fontFile, self.size, self.bold)

DEFAULT_FONTS = {
    'default': F('Junction.ttf', 24),
    'defaultTextBoxFont': F('Junction.ttf', 20),
    'unobtrusivePromptFont': F('Junction.ttf', 28),
    'chatFont': F('Junction.ttf', 25),
    'newChatFont': F('Vera.ttf', 14, True),

    'winMessageFont': F('Junction.ttf', 32),

    'nameFont': F('Junction.ttf', 20),
    'countdownFont': F('Junction.ttf', 16),

    'hugeMenuFont': F('Junction.ttf', 54),
    'bigMenuFont': F('Junction.ttf', 36),
    'mainMenuFont': F('Junction.ttf', 36),
    'serverListFont': F('Junction.ttf', 24),
    'timerFont': F('Junction.ttf', 32),
    'consoleFont': F('orbitron-light.ttf', 20),
    'ampleMenuFont': F('Junction.ttf', 40),
    'mediumMenuFont': F('Junction.ttf', 36),
    'menuFont': F('Junction.ttf', 30),
    'smallMenuFont': F('Junction.ttf', 20),
    'ingameMenuFont': F('FreeSans.ttf', 12),
    'gameInfoFont': F('FreeSans.ttf', 14),
    'gameInfoTitleFont': F('FreeSans.ttf', 20),
    'coinsDisplayFont': F('FreeSans.ttf', 20),
    'versionFont': F('Junction.ttf', 16),
    'scrollingButtonsFont': F('Junction.ttf', 24),
    'zoneBarFont': F('Junction.ttf', 24),
    'dialogButtonFont': F('KLEPTOCR.TTF', 50),
    'serverSelectionCheckboxesFont': F('Junction.ttf', 28),

    'messageFont': F('Junction.ttf', 20),
    'leaderboardFont': F('FreeSans.ttf', 14),

    'smallNoteFont': F('Junction.ttf', 22),
    'labelFont': F('Junction.ttf', 32),
    'captionFont': F('Junction.ttf', 35),
    'keymapFont': F('Junction.ttf', 20),
    'keymapInputFont': F('Junction.ttf', 20),

    'achievementTitleFont': F('orbitron-light.ttf', 21),
    'achievementNameFont': F('Junction.ttf', 18),

    'connectionFailedFont': F('Junction.ttf', 32),

    'creditsFont': F('Junction.ttf', 24),
    'creditsH2': F('KLEPTOCR.TTF', 48),
    'creditsH1': F('KLEPTOCR.TTF', 60),

    'bigZoneFont': F('VeraBd.ttf', 164),
}

UNSCALED_FONTS = set([
    'nameFont',
    'ingameMenuFont',
    'gameInfoFont',
    'gameInfoTitleFont',
    'leaderboardFont',
    'newChatFont',
    'winMessageFont',
    'bigZoneFont',
])
