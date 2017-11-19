import logging
import random
import datetime
import pygame

from trosnoth.const import (
    MAP_TO_SCREEN_SCALE, COLLECTABLE_COIN_LIFETIME, TICK_PERIOD,
    DEFAULT_COIN_VALUE,
)
from trosnoth.gui.framework.basics import (
    AngledImageCollection, Animation, SingleImage,
)
from trosnoth.model.player import Player
from trosnoth.trosnothgui.common import setAlpha
from trosnoth.trosnothgui.ingame.nametag import (
    NameTag, CoinTally, HealthBar, CountDown,
)

log = logging.getLogger(__name__)


class UnitSprite(pygame.sprite.Sprite):
    def __init__(self, app, worldGUI, unit):
        super(UnitSprite, self).__init__()
        self.app = app
        self.worldGUI = worldGUI
        self.unit = unit

    @property
    def pos(self):
        return self.unit.tweenPos(self.worldGUI.tweenFraction)


class ShotSprite(UnitSprite):
    def __init__(self, app, worldGUI, shot):
        super(ShotSprite, self).__init__(app, worldGUI, shot)
        self.shot = shot
        self.shotAnimation = app.theme.sprites.shotAnimation(shot.team)
        # Need a starting one:
        self.image = self.shotAnimation.getImage()
        self.rect = self.image.get_rect()

    def update(self):
        self.image = self.shotAnimation.getImage()


class SingleAnimationSprite(pygame.sprite.Sprite):
    def __init__(self, app, pos):
        super(SingleAnimationSprite, self).__init__()
        self.app = app
        self.pos = pos
        self.animation = self.getAnimation()
        self.image = self.animation.getImage()
        self.rect = self.image.get_rect()

    def getAnimation(self):
        raise NotImplementedError('getAnimation')

    def update(self):
        self.image = self.animation.getImage()

    def isDead(self):
        return self.animation.isComplete()


class ExplosionSprite(SingleAnimationSprite):
    def getAnimation(self):
        return self.app.theme.sprites.explosion()


class ShoxwaveExplosionSprite(SingleAnimationSprite):
    def getAnimation(self):
        return self.app.theme.sprites.shoxwaveExplosion()


class TrosballExplosionSprite(SingleAnimationSprite):
    def getAnimation(self):
        return self.app.theme.sprites.trosballExplosion()


class GrenadeSprite(UnitSprite):
    def __init__(self, app, worldGUI, grenade):
        super(GrenadeSprite, self).__init__(app, worldGUI, grenade)
        self.grenade = grenade
        self.image = app.theme.sprites.teamGrenade(grenade.player.team)
        self.rect = self.image.get_rect()


class CollectableCoinSprite(UnitSprite):
    def __init__(self, app, worldGUI, coin):
        super(CollectableCoinSprite, self).__init__(app, worldGUI, coin)
        self.coin = coin
        if coin.value >= 2 * DEFAULT_COIN_VALUE:
            self.animation = app.theme.sprites.bigCoinAnimation()
        else:
            self.animation = app.theme.sprites.coinAnimation()
        self.image = self.animation.getImage()
        self.alphaImage = self.image.copy()
        self.rect = self.image.get_rect()

    def update(self):
        self.image = self.animation.getImage()
        tick = self.worldGUI.universe.getMonotonicTick()
        fadeTick = self.coin.creationTick + (
                COLLECTABLE_COIN_LIFETIME - 2) // TICK_PERIOD
        if tick >= fadeTick:
            alpha = random.randint(32, 192)
            self.image = self.image.copy()
            setAlpha(self.image, alpha, alphaSurface=self.alphaImage)


class TrosballSprite(pygame.sprite.Sprite):
    def __init__(self, app, worldGUI, world):
        super(TrosballSprite, self).__init__()
        self.app = app
        self.worldGUI = worldGUI
        self.world = world
        self.animation = app.theme.sprites.trosballAnimation()
        self.warningAnimation = app.theme.sprites.trosballWarningAnimation()
        # Need a starting one:
        self.image = self.animation.getImage()
        self.rect = self.image.get_rect()

    def update(self):
        self.image = self.animation.getImage()
        manager = self.world.trosballManager
        if manager.trosballPlayer is not None:
            trosballExplodeTick = manager.playerGotTrosballTick + (
                self.world.physics.trosballExplodeTime // TICK_PERIOD)
            warningTick = trosballExplodeTick - 2 // TICK_PERIOD
            if self.world.getMonotonicTick() > warningTick:
                self.image = self.warningAnimation.getImage()
        center = self.rect.center
        self.rect = self.image.get_rect()
        self.rect.center = center

    @property
    def pos(self):
        manager = self.world.trosballManager
        if manager.trosballUnit:
            x, y = manager.trosballUnit.tweenPos(self.worldGUI.tweenFraction)
        else:
            p = manager.trosballPlayer
            if p.id == self.worldGUI.localPlayerId:
                p = self.worldGUI.localPlayerSprite
            x, y = p.tweenPos(self.worldGUI.tweenFraction)
            x += 5 if p._faceRight else -5
        return (x, y)


class PlayerSprite(UnitSprite):
    # These parameters are used to create a canvas for the player sprite object
    canvasSize = (
        int(33 * MAP_TO_SCREEN_SCALE + 0.5),
        int(39 * MAP_TO_SCREEN_SCALE + 0.5))
    liveOffset = 3
    ghostOffset = 0

    def __init__(self, app, worldGUI, player, greyed=False, timer=None):
        super(PlayerSprite, self).__init__(app, worldGUI, player)
        if timer is None:
            timer = player.world.getMonotonicTime
        self.spriteTeam = player.team
        self.player = player
        self.nametag = NameTag(app, player.nick)
        self.countdown = CountDown(app, self.player)
        self._oldName = player.nick
        self.coinTally = CoinTally(app, 0)
        self.greyed = greyed
        self.healthBar = HealthBar(
            app,
            badColour=self.app.theme.colours.badHealth,
            fairColour=self.app.theme.colours.fairHealth,
            goodColour=self.app.theme.colours.goodHealth)
        self.shieldBar = HealthBar(
            app,
            badColour=self.app.theme.colours.badShield,
            fairColour=self.app.theme.colours.fairShield,
            goodColour=self.app.theme.colours.goodShield)

        sprites = app.theme.sprites
        self.greyVersion = None
        if greyed:
            sprites = sprites.greyed
        self.sprites = sprites
        self.gunImages = AngledImageCollection(
            self.getAngleFacing, *sprites.gunImages(self.player.team))
        self.machineGunImages = AngledImageCollection(
            self.getAngleFacing, *sprites.machineGunImages(self.player.team))
        self.ricoGunImages = AngledImageCollection(
            self.getAngleFacing, *sprites.ricoGunImages(self.player.team))
        self.shoxGunImages = SingleImage(sprites.shoxGun3)

        head = sprites.playerHead(self.player.team, self.player.bot)
        self.runningAnimation = [
            Animation(0.1, timer, *sprites.runningLegs),
            sprites.playerBody,
            head,
        ]
        self.ghostAnimation = sprites.ghostAnimation(self.player.team)
        self.blocker = [
            Animation(
                0.1, timer,
                sprites.blocker1, sprites.blocker1, sprites.blocker2),
            head,
        ]
        self.bomber = [
            head,
            Animation(0.08, timer, sprites.bomber1, sprites.bomber2),
        ]

        self.reversingAnimation = [
            sprites.playerBody,
            Animation(0.1, timer, *sprites.backwardsLegs),
            head,
        ]

        self.turretAnimation = [
            sprites.turretBase,
            sprites.playerBody,
            head,
        ]

        self.standingAnimation = [
            sprites.playerStanding,
            sprites.playerBody,
            head,
        ]

        self.jumpingAnimation = [
            sprites.playerJumping,
            sprites.playerBody,
            head,
        ]
        self.holdingAnimation = [
            sprites.playerBody,
            sprites.playerHolding(self.player.team),
            head,
        ]
        self.fallingAnimation = self.jumpingAnimation
        self.shieldAnimation = Animation(0.15, timer, *sprites.shieldImages)
        self.jammingHat = sprites.jammingHat()

        if self.app.displaySettings.perPixelAlpha:
            flags = pygame.SRCALPHA
            self.alphaImage = pygame.Surface(self.canvasSize, flags)
        else:
            flags = 0
            self.alphaImage = None

        self.image = pygame.Surface(self.canvasSize, flags)
        self.rect = self.image.get_rect()

        # This probably shouldn't be done here.
        _t = datetime.date.today()
        self.is_christmas = _t.day in (24, 25, 26) and _t.month == 12

    def getAngleFacing(self):
        return self.player.angleFacing

    @property
    def angleFacing(self):
        return self.player.angleFacing

    def __getattr__(self, attr):
        '''
        Proxy attributes through to the underlying player class.
        '''
        return getattr(self.player, attr)

    def update(self):
        if self.player.nick != self._oldName:
            self._oldName = self.player.nick
            self.nametag = NameTag(self.app, self.player.nick)

        self.setImage()

    def _isSlow(self):
        # Consider horizontal movement of player.
        xMotion = self.player.getXKeyMotion()
        if xMotion < 0:
            return self.player._faceRight
        if xMotion > 0:
            return not self.player._faceRight
        return False

    def setImage(self):
        if not self.app.displaySettings.perPixelAlpha:
            self.image.set_alpha(None)

        self.image.fill((127, 127, 127, 0))
        self.image.set_colorkey((127, 127, 127))

        if self.player.resyncing and not self.greyed:
            if self.greyVersion is None:
                self.greyVersion = PlayerSprite(
                    self.app, self.worldGUI, self.player, greyed=True)
            self.greyVersion.setImage()
            self.image.blit(self.greyVersion.image, (0, 0))
            return

        flip = None
        offset = self.liveOffset
        if self.player.dead:
            blitImages = self.ghostAnimation
            offset = self.ghostOffset
        elif self.player.turret:
            blitImages = self.turretAnimation
        elif self.player.bomber:
            if self.player.bomber.timeRemaining < 0.8:
                blitImages = self.bomber
            else:
                blitImages = self.blocker
        elif self.player.isAttachedToWall():
            blitImages = self.holdingAnimation
            if self.player.isAttachedToWall() == 'right':
                flip = False
            else:
                flip = True
        elif self.player.isOnGround():
            if self.player.getXKeyMotion() == 0:
                blitImages = self.standingAnimation
            elif self._isSlow():
                blitImages = self.reversingAnimation
            else:
                blitImages = self.runningAnimation
        else:
            if self.player.yVel > 0:
                blitImages = self.fallingAnimation
            else:
                blitImages = self.jumpingAnimation

        # Put the pieces together:
        for element in blitImages:
            self.image.blit(element.getImage(), (offset, 0))
        if not (
                self.player.dead or self.player.isAttachedToWall() or
                self.player.bomber):
            if self.player.machineGunner:
                weapon = self.machineGunImages
            elif self.player.hasRicochet:
                weapon = self.ricoGunImages
            elif self.player.shoxwave:
                weapon = self.shoxGunImages
            else:
                weapon = self.gunImages
            self.image.blit(weapon.getImage(), (offset, 0))
        if self.player.ninja:
            self.image.blit(
                self.sprites.ninjaHead.getImage(), (offset, 0))
        elif self.player.disruptive:
            self.image.blit(self.jammingHat.getImage(), (offset, 0))
        if self.player.hasElephant() and not self.player.dead:
            self.image.blit(
                self.sprites.elephant.getImage(), (offset, 0))
        if (not self.player.dead and not self.player.phaseshift and not
                self.player.ninja and self.is_christmas and not
                self.player.hasElephant()):
            self.image.blit(
                self.sprites.christmasHat.getImage(), (offset, 0))
        if not self.player._faceRight and flip is None or flip:
            self.image = pygame.transform.flip(self.image, True, False)
        if self.player.hasVisibleShield():
            img = self.shieldAnimation.getImage()
            if not (img.get_flags() & pygame.SRCALPHA):
                # The shield animation already uses per-pixel alphas so if they
                # are enabled we don't need per-surface alphas.
                img.set_alpha(128)
            self.image.blit(img, (offset, 0))

        # Flicker the sprite between different levels of transparency
        if self.player.phaseshift and self._canSeePhaseShift():
            self.setImageAlpha(random.randint(30, 150))
        elif self.player.dead:
            self.setImageAlpha(128)
        elif self.player.isInvulnerable():
            self.setImageAlpha(random.randint(30, 150))
        elif self.player.invisible:
            replay = self.worldGUI.gameViewer.replay
            if replay or self.player.isFriendsWith(self.getShownPlayer()):
                self.setImageAlpha(80)
            else:
                self.setImageAlpha(0)
        else:
            self.setImageAlpha(255)

    def setImageAlpha(self, alpha):
        setAlpha(self.image, alpha, alphaSurface=self.alphaImage)

    def getShownPlayer(self):
        return self.worldGUI.gameViewer.viewManager.target

    def _canSeePhaseShift(self):
        if self.worldGUI.gameViewer.replay:
            return True
        target = self.getShownPlayer()
        if not isinstance(target, Player):
            return False
        return self.player.isFriendsWith(target)
