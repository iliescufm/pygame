import logging
from math import atan2

import pygame

from trosnoth.gui.framework import framework
from trosnoth.messages import UpdatePlayerStateMsg, AimPlayerAtMsg, ShootMsg

log = logging.getLogger(__name__)


class TickInstructions(object):
    def __init__(self):
        self.state = {}
        self.angleFacing = None
        self.ghostThrust = None
        self.firedGun = False

    def updateState(self, key, value):
        self.state[key] = value

    def lookAt(self, angle, thrust):
        self.angleFacing = angle
        self.ghostThrust = thrust

    def applyTo(self, player):
        for key, value in self.state.iteritems():
            if player.getState(key) == value:
                if not value:
                    continue
                player.updateState(key, False)
            player.updateState(key, value)

        if self.angleFacing is not None:
            player.lookAt(self.angleFacing, self.ghostThrust)

        if self.firedGun:
            player.weaponDischarged()


class PlayerInterface(framework.Element):
    '''Interface for controlling a player.'''

    # The virtual keys we care about.
    state_vkeys = frozenset(['left', 'right', 'jump', 'down'])

    NO_GHOST_THRUST_MOUSE_RADIUS = 30       # pixels
    FULL_GHOST_THRUST_MOUSE_RADIUS = 150    # pixels

    def __init__(self, app, gameInterface):
        super(PlayerInterface, self).__init__(app)

        world = gameInterface.world
        self.gameInterface = gameInterface
        self.keyMapping = None
        self._stateKeys = None
        self.keyMappingUpdated()

        self.receiving = True

        self.world = world
        self.worldGui = gameInterface.gameViewer.worldgui

        self.mousePos = (0, 0)
        pygame.mouse.get_rel()

        # Make sure the viewer is focusing on this player.
        self.gameInterface.gameViewer.setTarget(self.playerSprite)

    def keyMappingUpdated(self):
        self.keyMapping = self.gameInterface.keyMapping
        self._stateKeys = {
            (self.keyMapping.getkey(vkey), vkey) for vkey in self.state_vkeys}

    def getTickId(self):
        return self.world.lastTickId

    def stop(self):
        pass

    @property
    def player(self):
        return self.gameInterface.localState.player

    @property
    def playerSprite(self):
        return self.worldGui.getPlayerSprite(self.player.id)

    def tick(self, deltaT):
        pos = pygame.mouse.get_pos()
        spritePos = self.playerSprite.rect.center
        self.mousePos = (pos[0] - spritePos[0], pos[1] - spritePos[1])
        self.updatePlayerViewAngle()
        if self.player.canShoot():
            if self.player.machineGunner and self.player.machineGunner.firing:
                self._fireShot()

        # Sometimes Pygame seems to miss some keyboard events, so double
        # check here.
        if not self.gameInterface.detailsInterface.chatBox.isOpen():
            keys = pygame.key.get_pressed()
            desiredState = {code: keys[key] for key, code in self._stateKeys}
            changes = self.player.buildStateChanges(desiredState)
            for code, value in changes:
                self.gameInterface.sendRequest(UpdatePlayerStateMsg(
                    value, stateKey=code, tickId=self.getTickId()))
                log.critical('Sent missing player state update: %r / %r',
                    code, value)

    def updatePlayerViewAngle(self):
        '''Updates the viewing angle of the player based on the mouse pointer
        being at the position pos. This gets its own method because it needs
        to happen as the result of a mouse motion and of the viewManager
        scrolling the screen.'''
        dx, dy = self.mousePos
        pos = (self.playerSprite.rect.center[0] + dx,
               self.playerSprite.rect.center[1] + dy)

        if self.playerSprite.rect.collidepoint(pos):
            return

        # Angle is measured clockwise from vertical.
        theta = atan2(dx, -dy)
        dist = (dx ** 2 + dy ** 2) ** 0.5

        # Calculate a thrust value based on distance.
        if dist < self.NO_GHOST_THRUST_MOUSE_RADIUS:
            thrust = 0.0
        elif dist > self.FULL_GHOST_THRUST_MOUSE_RADIUS:
            thrust = 1.0
        else:
            span = (
                self.FULL_GHOST_THRUST_MOUSE_RADIUS -
                self.NO_GHOST_THRUST_MOUSE_RADIUS)
            thrust = (dist - self.NO_GHOST_THRUST_MOUSE_RADIUS) / span

        self.gameInterface.sendRequest(
            AimPlayerAtMsg(theta, thrust, tickId=self.getTickId()))

    def processEvent(self, event):
        '''Event processing works in the following way:
        1. If there is a prompt on screen, the prompt will either use the
        event, or pass it on.
        2. If passed on, the event will be sent back to the main class, for it
        to process whether player movement uses this event. If it doesn't use
        the event, it will pass it back.
        3. If so, the hotkey manager will see if the event means anything to
        it.  If not, that's the end, the event is ignored.
        '''

        # Handle events specific to in-game.
        di = self.gameInterface.detailsInterface
        if self.player:
            if event.type == pygame.KEYDOWN:
                self.processKeyEvent(event, True)
            elif event.type == pygame.KEYUP:
                self.processKeyEvent(event, False)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    if self.player.dead:
                        di.doAction('respawn')
                    elif self.player.machineGunner:
                        self.player.machineGunner.firing = True
                    elif di.trajectoryOverlay.isActive():
                        di.doAction('activate upgrade')
                    else:
                        # Fire a shot.
                        self._fireShot()
                elif event.button == 3:
                    di.trajectoryOverlay.setEnabled(True)
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    if self.player.machineGunner:
                        self.player.machineGunner.firing = False
                elif event.button == 3:
                    di.trajectoryOverlay.setEnabled(False)

            else:
                return event

    def processKeyEvent(self, event, keyDown):
            try:
                stateKey = self.keyMapping[event.key]
            except KeyError:
                return event

            if stateKey not in self.state_vkeys:
                return event

            self.gameInterface.sendRequest(UpdatePlayerStateMsg(
                keyDown, stateKey=stateKey,
                tickId=self.getTickId()))

    def _fireShot(self):
        '''Fires a shot in the direction the player's currently looking.'''
        self.gameInterface.sendRequest(ShootMsg(self.getTickId()))
