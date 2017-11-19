'''viewManager.py - defines the ViewManager class which deals with drawing the
state of a universe to the screen.'''

import math
import logging
import random

import pygame

from trosnoth.const import (
    MAP_TO_SCREEN_SCALE, BODY_BLOCK_SCREEN_SIZE, INTERFACE_BLOCK_SCREEN_SIZE,
    HOOK_NOT_ACTIVE)
from trosnoth.model.player import Player
from trosnoth.model.upgrades import Bomber, GrapplingHook, Shield
from trosnoth.utils import globaldebug
from trosnoth.utils.utils import timeNow
from trosnoth.themes import BLOCK_BACKGROUND_COLOURKEY
from trosnoth.trosnothgui.ingame.minimap import MiniMap
from trosnoth.trosnothgui.ingame.utils import (
    mapPosToScreen, screenToMapPos, viewRectToMap,
)
from trosnoth.gui.framework import framework
from trosnoth.trosnothgui.ingame.leaderboard import LeaderBoard
from trosnoth.trosnothgui.ingame.statusBar import (
    ZoneProgressBar, FrontLineProgressBar)
from trosnoth.trosnothgui.ingame.gameTimer import GameTimer
from trosnoth.trosnothgui.ingame.sprites import PlayerSprite
from trosnoth.trosnothgui.ingame.universegui import UniverseGUI
from trosnoth.model.map import MapLayout
from trosnoth.model.utils import getZonesInRect, getBlocksInRect
from trosnoth.mumble import mumbleUpdater

ZONE_SIZE = (2048, 768)

log = logging.getLogger('viewManager')


class ViewManager(framework.Element):
    '''A ViewManager object takes a given universe, and displays a screenfull
    of the current state of the universe on the specified screen object.  This
    class displays only a section of the universe and no other information
    (scores, menu etc.).

    Note: self._focus represents the position that the ViewManager is currently
    looking at.  self.target is what the ViewManager should be trying to look
    at.

    self.target = None - the ViewManager will use its algorithm to follow a
        point of action.
    self.target = (x, y) - the ViewManager will look at the specified point.
    self.target = player - the ViewManager will follow the specified player.
    '''

    # The fastest speed that the viewing position can shift in pixels per sec
    maxSpeed = 1800
    acceleration = 1080

    # How far ahead of the targeted player we should look.
    lengthFromPlayer = 125

    def __init__(self, app, parent, universe, target=None, replay=False):
        '''
        Called upon creation of a ViewManager object.  screen is a pygame
        screen object.  universe is the Universe object to draw.  target is
        either a point, a PlayerSprite object, or None.  If target is None, the
        view manager will follow the action, otherwise it will follow the
        specified point or player.
        '''
        super(ViewManager, self).__init__(app)
        self.universe = universe
        self.parent = parent
        self.replay = replay

        # self._focus represents the point where the viewManager is currently
        # looking.
        self._focus = (
            universe.map.layout.centreX, universe.map.layout.centreY)
        self._oldTargetPt = self._focus
        self.lastUpdateTime = timeNow()
        self.autoFocusInfo = (0, set(), set())
        self.speed = 0          # Speed that the focus is moving.

        self.loadingScreen = None
        self.loadingPlayer = None
        self.backgroundDrawer = BackgroundDrawer(app, universe)
        self.sRect = None

        # Now fill the backdrop with what we're looking at now.
        self.appResized()
        self.setTarget(target)

    def reset(self):
        if self.target is None:
            if self.autoFocusInfo == [0, set(), set()]:
                self._focus = (
                    self.universe.map.layout.centreX,
                    self.universe.map.layout.centreY)

    def stop(self):
        self.backgroundDrawer.stop()

    def tick(self, deltaT):
        if not self.active:
            return
        super(ViewManager, self).tick(deltaT)
        self.updateMumble()

    def updateMumble(self):
        mumbleUpdater.update(
            self.getTargetPlayer(), self.getTargetPoint(), serverId='')

    def appResized(self):
        self.loadingScreen = None
        self.sRect = sRect = pygame.Rect((0, 0), self.app.screenManager.size)
        centre = sRect.center
        if not self.replay:
            settings = self.app.displaySettings
            sRect.width = min(settings.maxViewportWidth, sRect.width)
            sRect.height = min(settings.maxViewportHeight, sRect.height)
        sRect.center = centre

    def setTarget(self, target):
        '''Makes the viewManager's target the specified value.'''
        self.target = target
        if isinstance(self.target, PlayerSprite):
            # Move directly to looking at player.
            self._focus = target.pos
        elif isinstance(self.target, (tuple, list)):
            self.target = self.trimTargetToMap(self.target)
        else:
            countdown, players, zones = self.autoFocusInfo
            if not players and not zones:
                self._oldTargetPt = self._focus

    def getTargetPlayer(self):
        if isinstance(self.target, PlayerSprite):
            return self.target
        return None

    def getTargetPoint(self):
        '''Returns the position of the current target.'''
        if self.target is None:
            return self._focus
        return getattr(self.target, 'pos', self.target)

    def drawLoading(self, screen):
        if self.loadingPlayer is None:
            player = Player(self.universe.universe, 'Loading...', None, '')
            player.motionState = 'ground'
            player.updateState('right', True)
            self.loadingPlayer = PlayerSprite(
                self.app, self.universe, player, timer=timeNow)

        if self.loadingScreen is None:
            self.loadingScreen = pygame.Surface(screen.get_size())
            self.loadingScreen.fill((255, 255, 255))

            font = self.app.screenManager.fonts.mainMenuFont
            colour = self.app.theme.colours.mainMenuColour
            text = font.render(
                self.app, 'Loading...', True, colour, (255, 255, 255))
            r = text.get_rect()
            r.center = self.loadingScreen.get_rect().center
            self.loadingScreen.blit(text, r)

            self.loadingPlayer.rect.midbottom = r.midtop

        if random.random() < 0.03:
            self.loadingPlayer.unit.lookAt(random.random() * 2 * math.pi)

        screen.blit(self.loadingScreen, (0, 0))
        self.loadingPlayer.update()
        screen.fill((255, 255, 255), self.loadingPlayer.rect)
        screen.blit(self.loadingPlayer.image, self.loadingPlayer.rect)

    def draw(self, screen, drawCoins=True):
        '''Draws the current state of the universe at the current viewing
        location on the screen.  Does not call pygame.display.flip()'''

        if self.universe.universe.loading:
            self.drawLoading(screen)
            return

        # Update where we're looking at.
        self.updateFocus()

        if self.sRect.topleft != (0, 0):
            screen.fill((0, 0, 0))

        oldClip = screen.get_clip()

        screen.set_clip(self.sRect)
        self.backgroundDrawer.draw(screen, self.sRect, self._focus, drawCoins)
        self._drawSprites(screen)
        self.drawOverlay(screen)
        screen.set_clip(oldClip)

    def drawOverlay(self, screen):
        area = self.sRect

        target = self.getTargetPlayer()
        if target is not None:
            physics = target.world.physics
            gunRange = physics.shotLifetime * physics.shotSpeed
            radius = int(gunRange * MAP_TO_SCREEN_SCALE + 0.5)
            pygame.draw.circle(screen, (192, 64, 64), area.center, radius, 1)

    def _drawSprites(self, screen):
        focus = self._focus
        area = self.sRect

        # Go through and update the positions of the players on the screen.
        ntGroup = set()
        visPlayers = set()

        for player in self.universe.iterPlayers():
            self.addSpritesForPlayer(player, visPlayers, ntGroup)
            hook = player.items.get(GrapplingHook)
            if hook and hook.hookState != HOOK_NOT_ACTIVE:
                pygame.draw.line(screen, (255,0,0),
                    mapPosToScreen(player.pos, focus, area),
                    mapPosToScreen(hook.hookPosition, focus, area), 5)

        # Draw the on-screen players and nametags.
        for s in visPlayers:
            s.update()
            screen.blit(s.image, s.rect)
        for s in ntGroup:
            screen.blit(s.image, s.rect)

        def drawSprite(sprite, pos=None):
            # Calculate the position of the sprite.
            if pos is None:
                pos = sprite.pos
            sprite.rect.center = mapPosToScreen(pos, focus, area)
            if sprite.rect.colliderect(area):
                sprite.update()
                screen.blit(sprite.image, sprite.rect)

        # Draw the shots.
        for shot in self.universe.iterShots():
            drawSprite(shot)

        for coin in self.universe.iterCollectableCoins():
            drawSprite(coin)

        try:
            # Draw the grenades.
            for grenade in self.universe.iterGrenades():
                drawSprite(grenade)
        except Exception as e:
            log.exception(str(e))

        for sprite in self.universe.iterExtras():
            drawSprite(sprite)

        if __debug__ and globaldebug.enabled:
            if globaldebug.showSpriteCircles:
                for pos, radius in globaldebug.getSpriteCircles():
                    screenPos = mapPosToScreen(pos, focus, area)
                    pygame.draw.circle(
                        screen, (255, 255, 0), screenPos, radius, 2)

            for sprite in visPlayers:
                sprite.player.onOverlayDebugHook(self, screen, sprite)

            for region in self.universe.universe.regions:
                region.debug_draw(self, screen)

    def addSpritesForPlayer(self, player, visPlayers, ntGroup):
        focus = self._focus
        area = self.sRect

        targetPlayer = self.getTargetPlayer()
        showPlayer = (
            not player.invisible or targetPlayer is None
            or player.isFriendsWith(targetPlayer.player))

        if showPlayer:
            # Calculate the position of the player.
            if player is targetPlayer:
                player.rect.center = area.center
            else:
                player.rect.center = mapPosToScreen(player.pos, focus, area)

            # Check if this player needs its nametag shown.
            if player.rect.colliderect(area):
                visPlayers.add(player)

                if ntGroup is None:
                    return

                if player.unit.items.has(Bomber):
                    player.countdown.update()
                    player.countdown.rect.midbottom = player.rect.midtop
                    ntGroup.add(player.countdown)

                lastPoint = player.rect.midbottom

                shield = player.unit.items.get(Shield)
                if shield:
                    shieldBar = player.shieldBar
                    shieldBar.setHealth(
                        shield.protections,
                        shield.maxProtections)
                    if shieldBar.visible:
                        ntGroup.add(shieldBar)
                        shieldBar.rect.midtop = lastPoint
                        lastPoint = shieldBar.rect.midbottom

                healthBar = player.healthBar
                healthBar.setHealth(
                    player.unit.health,
                    player.unit.world.physics.playerRespawnHealth)
                if healthBar.visible:
                    ntGroup.add(healthBar)
                    healthBar.rect.midtop = lastPoint
                    lastPoint = healthBar.rect.midbottom

                player.nametag.rect.midtop = lastPoint

                # Check that entire nametag's on screen.
                if player.nametag.rect.left < area.left:
                    player.nametag.rect.left = area.left
                elif player.nametag.rect.right > area.right:
                    player.nametag.rect.right = area.right
                if player.nametag.rect.top < area.top:
                    player.nametag.rect.top = area.top
                elif player.nametag.rect.bottom > area.bottom:
                    player.nametag.rect.bottom = area.bottom
                ntGroup.add(player.nametag)

                if not player.dead:
                    # Place the coin rectangle below the nametag.
                    mx, my = player.nametag.rect.midbottom
                    player.coinTally.setCoins(player.getCoinDisplayCount())
                    player.coinTally.rect.midtop = (mx, my - 5)
                    ntGroup.add(player.coinTally)

    def updateFocus(self):
        '''Updates the location that the ViewManager is focused on.  First
        calculates where it would ideally be focused, then moves the focus
        towards that point. The focus cannot move faster than self.maxSpeed
        pix/s, and will only accelerate or decelerate at self.acceleration
        pix/s/s. This method returns the negative of the amount scrolled by.
        This is useful for moving the backdrop by the right amount.
        '''

        # Calculate where we should be looking at.
        if isinstance(self.target, PlayerSprite):
            # Take into account where the player's looking.
            targetPt = self.target.pos

            # If the player no longer exists, look wherever we want.
            if not self.universe.hasPlayer(self.target.player):
                self.setTarget(None)
        elif isinstance(self.target, (tuple, list)):
            targetPt = self.target
        else:
            targetPt = self.followAction()

        # Calculate time that's passed.
        now = timeNow()
        deltaT = now - self.lastUpdateTime
        self.lastUpdateTime = now

        # Calculate distance to target.
        self._oldTargetPt = targetPt
        sTarget = sum(
            (targetPt[i] - self._focus[i]) ** 2 for i in (0, 1)) ** 0.5

        if sTarget == 0:
            return (0, 0)

        if self.target is not None:
            s = sTarget
        else:
            # Calculate the maximum velocity that will result in deceleration
            # to reach target. This is based on v**2 = u**2 + 2as
            vDecel = (2. * self.acceleration * sTarget) ** 0.5

            # Actual velocity is limited by this and maximum velocity.
            self.speed = min(
                self.maxSpeed, vDecel, self.speed + self.acceleration * deltaT)

            # Distance travelled should never overshoot the target.
            s = min(sTarget, self.speed * deltaT)

        # How far does the backdrop need to move by?
        #  (This will be negative what the focus moves by.)
        deltaBackdrop = tuple(
            -s * (targetPt[i] - self._focus[i]) / sTarget
            for i in (0, 1))

        # Calculate the new focus.
        self._focus = tuple(
            round(self._focus[i] - deltaBackdrop[i], 0) for i in (0, 1))

    def getZoneAtPoint(self, pt):
        x, y = screenToMapPos(pt, self._focus, self.sRect)

        i, j = MapLayout.getMapBlockIndices(x, y)
        try:
            return self.universe.map.zoneBlocks[i][j].getZoneAtPoint(x, y)
        except IndexError:
            return None

    def followAction(self):
        # Follow the action.
        countdown, players, zones = self.autoFocusInfo
        targetPt = tuple(self._focus)

        if self.universe.getPlayerCount() == 0:
            # No players anywhere. No change.
            self.autoFocusInfo = (0, set(), set())
            return targetPt

        # First check for non-existent players.
        for p in list(players):
            if not self.universe.hasPlayer(p):
                players.remove(p)

        # Every 10 iterations recheck for players that have entered
        # view area.
        r = pygame.Rect(self.sRect)
        r.width //= MAP_TO_SCREEN_SCALE
        r.height //= MAP_TO_SCREEN_SCALE
        r.center = self._oldTargetPt
        if countdown <= 0:
            players.clear()
            for p in self.universe.iterPlayers():
                if r.collidepoint(p.pos):
                    players.add(p)

            zones.clear()
            for z in self.universe.map.zones:
                if r.collidepoint(z.defn.pos):
                    if any(t != z.owner for t in z.teamsAbleToTag()):
                        zones.add(z)
            countdown = 10
        else:
            # Keep track of which players are still visible.
            for p in list(players):
                if not r.collidepoint(p.pos):
                    players.remove(p)
            countdown -= 1

        if len(players) + len(zones) <= 1:
            # Nothing interesting in view. Look for action.
            maxP = 0
            curZone = None
            for z in self.universe.zones:
                count = len(self.universe.getPlayersInZone(z))
                if any(t != z.owner for t in z.teamsAbleToTag()):
                    count += 2
                if count > maxP:
                    maxP = count
                    curZone = z
            if curZone is None:
                players = set()
            else:
                players = set(self.universe.getPlayersInZone(curZone))

            countdown = 20

        # Look at centre-of-range of these players.
        if players or zones:
            interestingPoints = []
            for p in players:
                interestingPoints.append(p.pos)
            for z in zones:
                interestingPoints.append(z.defn.pos)
            minPos = [
                min(pt[i] for pt in interestingPoints) for i in (0, 1)]
            maxPos = [
                max(pt[i] for pt in interestingPoints) for i in (0, 1)]
            targetPt = [0.5 * (minPos[i] + maxPos[i]) for i in (0, 1)]

        # No need to ever look beyond the boundary of the map
        targetPt = self.trimTargetToMap(targetPt)
        r.center = targetPt

        self.autoFocusInfo = (countdown, players, zones)
        return targetPt

    def trimTargetToMap(self, targetPt):
        # No need to ever look beyond the boundary of the map
        mapRect = pygame.Rect((0, 0), self.universe.map.layout.worldSize)
        r = pygame.Rect(self.sRect)
        r.width //= MAP_TO_SCREEN_SCALE
        r.height //= MAP_TO_SCREEN_SCALE
        r.center = targetPt
        if r.width > mapRect.width:
            r.centerx = mapRect.centerx
        else:
            r.right = min(r.right, mapRect.right)
            r.left = max(r.left, mapRect.left)
        if r.height > mapRect.height:
            r.centery = mapRect.centery
        else:
            r.bottom = min(r.bottom, mapRect.bottom)
            r.top = max(r.top, mapRect.top)
        return r.center


class BackgroundDrawer(object):
    def __init__(self, app, universe):
        self.app = app
        self.scenery = Scenery(app, universe)
        self.sBackgrounds = SolidBackgrounds(app, universe)
        self.orbs = OrbDrawer(app, universe)
        self.debugs = DebugDrawer(app, universe)

        app.displaySettings.onDetailLevelChanged.addListener(
            self.detailLevelChanged)

    def stop(self):
        self.app.displaySettings.onDetailLevelChanged.removeListener(
            self.detailLevelChanged)

    def detailLevelChanged(self):
        self.sBackgrounds.bkgCache.clear()

    def draw(self, screen, sRect, focus, drawCoins=True):
        if drawCoins:
            self.scenery.draw(screen, sRect, focus)
        self.sBackgrounds.draw(screen, sRect, focus)
        self.orbs.draw(screen, sRect, focus)
        self.debugs.draw(screen, sRect, focus)


class Scenery(object):
    def __init__(self, app, universe, distance=3):
        self.app = app
        self.universe = universe
        self.image = app.theme.sprites.scenery
        self.scale = 1. / distance

    def draw(self, screen, area, focus):
        worldRect = viewRectToMap(focus, area)

        regions = []
        for block in getBlocksInRect(self.universe, worldRect):
            bd = block.defn
            pos = mapPosToScreen(bd.pos, focus, area)
            if bd.kind in ('top', 'btm'):
                if bd.zone is None:
                    regions.append(pygame.Rect(pos, BODY_BLOCK_SCREEN_SIZE))
                    continue
            elif bd.zone1 is None or bd.zone2 is None:
                regions.append(pygame.Rect(pos, INTERFACE_BLOCK_SCREEN_SIZE))
                continue

        x0, y0 = mapPosToScreen((0, 0), focus, area)
        if area.top < y0:
            r = pygame.Rect(area)
            r.bottom = y0
            regions.append(r)
        if area.left < x0:
            r = pygame.Rect(area)
            r.right = x0
            regions.append(r)

        x1, y1 = mapPosToScreen(
            self.universe.map.layout.worldSize, focus, area)
        if area.bottom > y1:
            r = pygame.Rect(area)
            r.top = y1
            regions.append(r)
        if area.right > x1:
            r = pygame.Rect(area)
            r.left = x1
            regions.append(r)

        clip = screen.get_clip()
        for region in regions:
            region = region.clip(clip)
            screen.set_clip(region)
            self.drawRegion(screen, region, worldRect.topleft)
        screen.set_clip(clip)

    def drawRegion(self, screen, area, focus):
        if not self.app.displaySettings.paralaxBackgrounds:
            screen.fill(BLOCK_BACKGROUND_COLOURKEY, area)
            return

        w, h = self.image.get_size()
        x = area.left - (int(round(focus[0] * self.scale + area.left)) % w)
        y0 = y = area.top - (int(round(focus[1] * self.scale + area.top)) % h)

        while x < area.right:
            while y < area.bottom:
                screen.blit(self.image, (x, y))
                y += h
            x += w
            y = y0


class OrbDrawer(object):
    def __init__(self, app, world):
        self.app = app
        self.universe = world

    def draw(self, screen, area, focus):
        worldRect = viewRectToMap(focus, area)

        for zone in getZonesInRect(self.universe, worldRect):
            pic = self.app.theme.sprites.bigZoneLetter(zone.defn.label)
            r = pic.get_rect()
            r.center = mapPosToScreen(zone.defn.pos, focus, area)
            screen.blit(pic, r)

            if (self.universe.universe.uiOptions.showNets and zone.defn in
                    self.universe.map.layout.getTrosballTargetZones()):
                pic = self.app.theme.sprites.netOrb()
            else:
                pic = self.app.theme.sprites.orb(zone.owner)
            r = pic.get_rect()
            r.center = mapPosToScreen(zone.defn.pos, focus, area)
            screen.blit(pic, r)


class DebugDrawer(object):
    def __init__(self, app, world):
        self.app = app
        self.universe = world

    def draw(self, screen, area, focus):
        if not self.app.displaySettings.showObstacles:
            return

        from trosnoth.model.obstacles import Obstacle, Corner

        player = self.universe.universe.getPlayer(globaldebug.localPlayerId)
        attachedObstacle = player.attachedObstacle if player else None

        worldRect = viewRectToMap(focus, area)
        for block in getBlocksInRect(self.universe, worldRect):
            for obs in block.defn.obstacles:
                if isinstance(obs, Obstacle):
                    pt1 = mapPosToScreen(obs.pt1, focus, area)
                    pt2 = mapPosToScreen(obs.pt2, focus, area)
                    c = (0, 255, 0) if obs is attachedObstacle else (255, 0, 0)
                    pygame.draw.line(screen, c, pt1, pt2, 2)
                elif isinstance(obs, Corner):
                    pt1 = mapPosToScreen(
                        [obs.pt[i] - obs.offset[i] * 10 for i in (0, 1)],
                        focus, area)
                    pt2 = mapPosToScreen([
                        obs.pt[i] - (obs.offset[i] + obs.delta[i]) * 10
                        for i in (0, 1)], focus, area)
                    c = (0 if obs is attachedObstacle else 255, 255, 0)
                    pygame.draw.line(screen, c, pt1, pt2, 2)
                    pt2 = (int(pt2[0]), int(pt2[1]))
                    pygame.draw.circle(screen, c, pt2, 3, 0)


class SolidBackgrounds(object):
    def __init__(self, app, universe):
        self.app = app
        self.universe = universe
        self.bkgCache = BackgroundCache(app, universe)

    def draw(self, screen, area, focus):
        frontLine = self.universe.universe.uiOptions.getFrontLine()
        if frontLine is not None:
            self.drawShiftingBackground(screen, area, focus, frontLine)
        else:
            self.drawStandardBackground(screen, area, focus)

    def drawStandardBackground(self, screen, area, focus):
        worldRect = viewRectToMap(focus, area)
        for block in getBlocksInRect(self.universe, worldRect):
            pic = self.bkgCache.get(block)
            if pic is not None:
                screen.blit(pic, mapPosToScreen(block.defn.pos, focus, area))

    def drawShiftingBackground(self, screen, area, focus, trosballLocation):
        worldRect = viewRectToMap(focus, area)

        for block in getBlocksInRect(self.universe, worldRect):
            blueBlock = self.bkgCache.getForTeam(0, block)
            redBlock = self.bkgCache.getForTeam(1, block)
            if blueBlock is None or redBlock is None:
                continue

            blockHorizontalPosition = block.defn.pos[0]
            relativeLocation = trosballLocation - blockHorizontalPosition
            blockWidth = block.defn._getWidth()
            relativeLocation = max(0, min(blockWidth, relativeLocation))

            x = int(relativeLocation * MAP_TO_SCREEN_SCALE + 0.5)
            topleft = mapPosToScreen(block.defn.pos, focus, area)

            r = blueBlock.get_rect()
            r.width = x
            screen.blit(blueBlock, topleft, r)

            r = redBlock.get_rect()
            r.left = x
            screen.blit(redBlock, (topleft[0] + x, topleft[1]), r)


class BackgroundCache(object):
    def __init__(self, app, universe, capacity=30):
        self.app = app
        self.universe = universe
        self.capacity = capacity
        self.cache = {}
        self.order = []

    def clear(self):
        self.cache = {}
        self.order = []

    def getForTeam(self, teamId, block):
        backgroundPicTeam = self.app.theme.sprites.getFilledBlockBackground(
            block, self.universe.teams[teamId])
        if backgroundPicTeam is None:
            return None
        return self._getForegroundOnBackground(backgroundPicTeam, block)

    def get(self, block):
        backgroundPic = self.app.theme.sprites.blockBackground(block)
        return self._getForegroundOnBackground(backgroundPic, block)

    def _getForegroundOnBackground(self, backgroundPic, block):
        if block.defn.graphics is not None:
            foregroundPic = block.defn.graphics.getGraphic(self.app)
        else:
            foregroundPic = None

        if (backgroundPic, foregroundPic) in self.cache:
            self.order.remove((backgroundPic, foregroundPic))
            self.order.insert(0, (backgroundPic, foregroundPic))
            return self.cache[backgroundPic, foregroundPic]

        pic = self._makePic(backgroundPic, foregroundPic)
        self.cache[backgroundPic, foregroundPic] = pic
        self.order.insert(0, (backgroundPic, foregroundPic))
        if len(self.order) > self.capacity:
            del self.cache[self.order.pop(-1)]
        return pic

    def _makePic(self, backgroundPic, foregroundPic):
        if backgroundPic is None:
            return foregroundPic
        if foregroundPic is None:
            return backgroundPic
        pic = backgroundPic.copy()
        pic.blit(foregroundPic, (0, 0))
        return pic


class GameViewer(framework.CompoundElement):
    '''The gameviewer comprises a viewmanager and a minimap, which can be
    switched on or off.'''

    zoneBarHeight = 25

    def __init__(self, app, gameInterface, game, replay):
        super(GameViewer, self).__init__(app)
        self.replay = replay
        self.interface = gameInterface
        self.game = game
        self.world = game.world
        self.worldgui = UniverseGUI(app, self, self.world)
        self.app = app

        self.viewManager = ViewManager(
            self.app, self, self.worldgui, replay=replay)

        self.timerBar = GameTimer(app, game)

        self.miniMap = None
        self.leaderboard = None
        self.zoneBar = None
        self.makeWidgets()

        self.elements = [self.viewManager]
        self._screenSize = tuple(app.screenManager.size)

        self.teamsDisrupted = set()

        self.storedState = None

        self.toggleInterface()
        self.toggleLeaderBoard()

        self.world.uiOptions.onChange.addListener(self.uiOptionsChanged)

    def stop(self):
        self.viewManager.stop()
        self.worldgui.stop()
        self.world.uiOptions.onChange.removeListener(self.uiOptionsChanged)

    def uiOptionsChanged(self):
        self.reset(rebuildMiniMap=False)

    def getZoneAtPoint(self, pos):
        '''
        Returns the zone at the given screen position. This may be on the
        minimap or the main view.
        '''
        zone = self.miniMap.getZoneAtPoint(pos)
        if zone is None:
            zone = self.viewManager.getZoneAtPoint(pos)
        return zone

    def resizeIfNeeded(self):
        '''
        Checks whether the application has resized and adjusts accordingly.
        '''
        if self._screenSize == self.app.screenManager.size:
            return
        self._screenSize = tuple(self.app.screenManager.size)

        self.viewManager.appResized()
        # Recreate the minimap.
        self.reset()

    def reset(self, rebuildMiniMap=True):
        showHUD = self.miniMap is not None and self.miniMap in self.elements
        showLeader = (
            self.leaderboard is not None and self.leaderboard in self.elements)
        self.makeWidgets(rebuildMiniMap)
        if showHUD:
            self.toggleInterface()
        if showLeader:
            self.toggleLeaderBoard()
        self.viewManager.reset()

    def makeWidgets(self, rebuildMiniMap=True):
        if rebuildMiniMap:
            self.miniMap = MiniMap(
                self.app, 20, self.worldgui, self.viewManager)
        if self.world.uiOptions.getFrontLine() is not None:
            self.zoneBar = FrontLineProgressBar(self.app, self.world, self)
            self.leaderboard = None
        else:
            self.zoneBar = ZoneProgressBar(self.app, self.world, self)

        self.leaderboard = LeaderBoard(self.app, self.game, self)

        self.elements = [self.viewManager]

    def setTarget(self, target):
        'Target should be a player, a point, or None.'
        self.viewManager.setTarget(target)

    def tick(self, deltaT):
        if not self.active:
            return
        self.resizeIfNeeded()
        self.worldgui.setTweenFraction(self.app.tweener.uiTick(deltaT))

        target = self.viewManager.target
        if isinstance(target, PlayerSprite) and target.isMinimapDisrupted:
            self.miniMap.disrupted()
            self.zoneBar.disrupt = True
        else:
            self.miniMap.endDisruption()
            self.zoneBar.disrupt = False

        super(GameViewer, self).tick(deltaT)

    def toggleInterface(self):
        if self.miniMap in self.elements:
            self.elements.remove(self.zoneBar)
            self.elements.remove(self.timerBar)
            self.elements.remove(self.miniMap)
        else:
            self.elements.append(self.zoneBar)
            self.elements.append(self.timerBar)
            self.elements.append(self.miniMap)

    def toggleLeaderBoard(self):
        if self.leaderboard is not None and self.leaderboard in self.elements:
            self.elements.remove(self.leaderboard)
        else:
            self.elements.append(self.leaderboard)