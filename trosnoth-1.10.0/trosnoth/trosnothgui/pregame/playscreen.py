import logging

import pygame
from twisted.internet import defer
from twisted.internet.error import ConnectError
from twisted.protocols import amp

from trosnoth.gui.common import (Region, Canvas, Location, ScaledSize)
from trosnoth.gui.framework import framework
from trosnoth.gui.framework.dialogbox import DialogBox, OkBox
from trosnoth.gui.framework.elements import (TextElement, SolidRect, TextButton)
from trosnoth.network.lobby import (Lobby, AuthenticationCancelled,
        IncorrectServerVersion)
from trosnoth.network import authcommands
from trosnoth.network.client import ConnectionFailed
from trosnoth.utils.event import Event
from trosnoth.trosnothgui.pregame.authServerLoginBox import (PasswordGUI,
        PasswordGUIError)


log = logging.getLogger('playscreen')

class PlayAuthScreen(framework.CompoundElement):
    passwordGUIFactory = PasswordGUI

    def __init__(self, app, onSucceed=None, onFail=None):
        super(PlayAuthScreen, self).__init__(app)
        self.onSucceed = Event(listener=onSucceed)
        self.onFail = Event(listener=onFail)
        self.lobby = None
        self.badServers = set()

        if app.displaySettings.alphaOverlays:
            alpha = 192
        else:
            alpha = None
        bg = SolidRect(app, app.theme.colours.playMenu, alpha,
                Region(centre=Canvas(512, 384), size=Canvas(924, 500)))

        colour = app.theme.colours.mainMenuColour
        font = app.screenManager.fonts.consoleFont
        self.logBox = LogBox(app, Region(size=Canvas(900, 425),
                midtop=Canvas(512, 146)), colour, font)

        font = app.screenManager.fonts.bigMenuFont
        cancel = TextButton(app, Location(Canvas(512, 624), 'midbottom'),
                'Cancel', font, app.theme.colours.secondMenuColour,
                app.theme.colours.white, onClick=self.cancel)
        self.cancelled = False
        self.elements = [bg, self.logBox, cancel]
        self._passwordGetter = None

    @property
    def passwordGetter(self):
        if self._passwordGetter is None:
            self._passwordGetter = self.passwordGUIFactory(self.app)
        return self._passwordGetter

    @defer.inlineCallbacks
    def begin(self, servers, canHost=True):
        self.cancelled = False
        self.passwordGetter.cancelled = False
        self.badServers = set()
        if self.lobby is None:
            self.lobby = Lobby(self.app)

        # Removes the third item (http) from the tuple since we don't care about
        # it.
        servers = [ (server[:2] if isinstance(server, tuple) else server)
                for server in servers ]

        for server in servers:
            if self.cancelled:
                break

            if server == 'self':
                if self.app.server is not None:
                    self.onSucceed.execute()
                    self.app.interface.connectToLocalServer()
                    return

            elif isinstance(server, tuple):
                if server in self.badServers:
                    continue

                self.logBox.log('Requesting games from %s:%d...' % server)
                connected = yield self.attemptServerConnect(
                        self.lobby.getGames, server)
                if connected:
                    return

            elif server == 'others':
                for server in servers:
                    if (server in self.badServers or not isinstance(server,
                            tuple)):
                        continue

                    self.logBox.log('Asking %s:%d about other games...' %
                            server)
                    connected = yield self.attemptServerConnect(
                            self.lobby.getOtherGames, server)
                    if connected:
                        return

            elif server == 'lan':
                self.logBox.log('Asking local network for other games...')
                games = yield self.lobby.getMulticastGames()
                for game in games:
                    joinSuccessful = yield self.attemptJoinGame(game)
                    if joinSuccessful:
                        return

            elif server == 'create':
                for server in servers:
                    if server in self.badServers or not isinstance(server,
                            tuple):
                        continue
                    self.logBox.log('Asking to create game on %s...' %
                            (server[0],))

                    joinSuccessful = yield self.attemptCreateGame(server)
                    if joinSuccessful:
                        return

        if canHost:
            if not self.cancelled:
                result = yield HostGameQuery(self.app).run()

                if not result:
                    self.onFail.execute()
                    return

                self.app.startServer(2, 1)

                # Notify remaining auth servers of this game.
                for server in servers:
                    if server in self.badServers or not isinstance(server,
                            tuple):
                        continue
                    self.logBox.log('Registering game with %s...' %
                            (server[0],))
                    try:
                       result = yield self.lobby.registerGame(server,
                               self.app.server)
                    except ConnectError:
                        self.logBox.log('Unable to connect.')
                    if not result:
                        self.logBox.log('Registration failed.')

                self.onSucceed.execute()
                self.app.interface.connectToLocalServer()
        else:
            if not self.cancelled:
                box = OkBox(self.app, ScaledSize(450, 150), 'Trosnoth',
                        'Connection unsuccessful.')
                box.onClose.addListener(self.onFail.execute)
                box.show()

    @defer.inlineCallbacks
    def attemptServerConnect(self, getGamesList, server):
        '''
        Attempts to connect to a game on the server, returned by
        getGamesList(server).
        '''
        try:
           games = yield getGamesList(server)
        except ConnectError:
            self.logBox.log('Unable to connect.')
            self.badServers.add(server)
        except amp.UnknownRemoteError:
            self.logBox.log('Error on remote server.')
        except amp.RemoteAmpError, e:
            self.logBox.log('Error on remote server.')
            log.exception(str(e))
        except IOError, e:
            self.logBox.log('Error connecting to remote server.')
            log.exception(str(e))
            self.badServers.add(server)
        else:
            if len(games) == 0:
                self.logBox.log('No running games.')

            for game in games:
                joinSuccessful = yield self.attemptJoinGame(game)
                if joinSuccessful:
                    defer.returnValue(True)
                    return

        defer.returnValue(False)

    @defer.inlineCallbacks
    def attemptCreateGame(self, server):
        '''
        Attempts to create a game on the given server.
        '''
        try:
           result = yield self.lobby.startGame(server,
                   self.passwordGetter)
        except (ConnectError, ConnectionFailed):
            self.logBox.log('Unable to connect.')
            self.badServers.add(server)
        except authcommands.CannotCreateGame:
            self.logBox.log('Server will not create game.')
        except IncorrectServerVersion:
            self.logBox.log('Wrong server version to create games.')
        except AuthenticationCancelled:
            pass
        except authcommands.NotAuthenticated:
            self.logBox.log('Authentication failure.')
        except authcommands.GameDoesNotExist:
            self.logBox.log('Error connecting to newly-created game.')
        except amp.UnknownRemoteError:
            self.logBox.log('Error on remote server.')
        except amp.RemoteAmpError, e:
            self.logBox.log('Error on remote server.')
            log.exception(str(e))
        except IOError, e:
            self.logBox.log('Error connecting to remote server.')
            log.exception(str(e))
        else:
            self.logBox.log('Game created and joined.')
            self._joined(result)
            defer.returnValue(True)
            return

        defer.returnValue(False)

    @defer.inlineCallbacks
    def attemptJoinGame(self, game):
        '''
        Attempts to join the given game.
        '''
        try:
            self.logBox.log('Found game: joining.')
            result = yield game.join(self.passwordGetter)
        except authcommands.GameDoesNotExist:
            pass
        except AuthenticationCancelled:
            pass
        except authcommands.NotAuthenticated:
            self.logBox.log('Authentication failure.')
        except amp.UnknownRemoteError:
            self.logBox.log('Error on remote server.')
        except amp.RemoteAmpError, e:
            self.logBox.log('Error on remote server.')
            log.exception(str(e))
        except ConnectionFailed:
            self.logBox.log('Could not connect.')
        except IOError, e:
            self.logBox.log('Error connecting to remote server.')
            log.exception(str(e))
        else:
            self._joined(result)
            defer.returnValue(True)
            return

        defer.returnValue(False)

    def _joined(self, result):
        self.onSucceed.execute()
        self.app.interface.connectedToGame(*result)

    def cancel(self, element):
        self.cancelled = True
        self.passwordGetter.cancelled = True
        self.onFail.execute()

    def processEvent(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.onFail.execute()
        else:
            return super(PlayAuthScreen, self).processEvent(event)

class LogBox(framework.Element):
    '''
    Draws a canvas and adds text to the bottom of it, scrolling the canvas
    upwards.
    '''
    def __init__(self, app, region, colour, font):
        super(LogBox, self).__init__(app)
        self.image = None
        self.region = region
        self.colour = colour
        self.font = font

    def draw(self, screen):
        r = self.region.getRect(self.app)
        if self.image is not None:
            screen.blit(self.image, r.topleft)

    def log(self, text):
        t = self.font.render(self.app, text, False, self.colour,
                (255, 255, 255))
        t.set_colorkey((255, 255, 255))
        r = self.region.getRect(self.app)
        img = pygame.Surface(r.size)
        img.fill((255, 255, 255))
        img.set_colorkey((255, 255, 255))
        h = t.get_rect().height
        r.topleft = (0, h)
        if self.image is not None:
            img.blit(self.image, (0, 0), r)
        img.blit(t, (0, r.height - h))
        self.image = img


class HostGameQuery(DialogBox):
    def __init__(self, app):
        size = Canvas(384, 150)
        DialogBox.__init__(self, app, size, 'Host game?')
        self._deferred = None

        font = app.screenManager.fonts.defaultTextBoxFont
        btnColour = app.theme.colours.dialogButtonColour
        highlightColour = app.theme.colours.black
        labelColour = app.theme.colours.dialogBoxTextColour
        btnFont = app.screenManager.fonts.bigMenuFont

        self.elements = [
            TextElement(app, 'No games found. Host a game?', font,
                Location(self.Relative(0.5, 0.4), 'center'), labelColour),

            TextButton(app,
                Location(self.Relative(0.3, 0.85), 'center'),
                'Yes', btnFont, btnColour, highlightColour,
                onClick=self.yesClicked),
            TextButton(app,
                Location(self.Relative(0.7, 0.85), 'center'),
                'No', btnFont, btnColour, highlightColour,
                onClick=self.noClicked),
        ]

    def processEvent(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_KP_ENTER, pygame.K_RETURN):
                self.yesClicked()
                return None
            elif event.key == pygame.K_ESCAPE:
                self.noClicked()
                return None
        else:
            return DialogBox.processEvent(self, event)

    def yesClicked(self, element=None):
        self.close()
        self._deferred.callback(True)

    def noClicked(self, element=None):
        self.close()
        self._deferred.callback(False)

    def run(self):
        if self.showing:
            raise PasswordGUIError('HostGameQuery already showing')
        self.show()
        result = self._deferred = defer.Deferred()
        return result

