import logging
import mimetypes

from django.contrib.staticfiles import finders
from twisted.internet import defer, reactor
from twisted.web import resource
from twisted.web.server import Site
from twisted.web.static import File
from twisted.web.wsgi import WSGIResource


from trosnoth.server.wsgi import application
from trosnoth.utils.twist import WeakLoopingCall
from trosnoth.web.site import PageSet, ServerState, Resources


log = logging.getLogger(__name__)

pages = PageSet()


@pages.addPage('scoreboard')
@defer.inlineCallbacks
def homepipe(state, request):
    sendData = state.getInitialEvents()
    request.write(sendData)
    while True:
        s = yield state.waitForEvent()
        if s is not None:
            request.write(s)


class WebServer(ServerState):
    def __init__(self, authFactory, serverPort):
        ServerState.__init__(self, pages)
        self.authFactory = authFactory
        self.serverPort = serverPort
        self.nextEventListeners = []
        self._loop = WeakLoopingCall(self, 'keepEventPipeAlive')
        self._loop.start(5, False)

        self.gameServer = None
        self.authFactory.onPrimaryGameChanged.addListener(
                self.gameServerChanged)

    def gameServerChanged(self, gameServer):
        if self.gameServer:
            world = self.gameServer.game.world
            world.onPlayerAdded.removeListener(self.playerCountChanged)
            world.onPlayerRemoved.removeListener(self.playerCountChanged)
            world.onStartMatch.removeListener(self.levelChanged)
            world.onTeamScoreChanged.removeListener(self.teamScoreChanged)
        self.gameServer = gameServer
        if gameServer:
            world = gameServer.game.world
            world.onPlayerAdded.addListener(self.playerCountChanged)
            world.onPlayerRemoved.addListener(self.playerCountChanged)
            world.onStartMatch.addListener(self.levelChanged)
            world.onTeamScoreChanged.addListener(self.teamScoreChanged)

        self.transmitEvent(self.getInitialEvents())

    def inLobby(self):
        game = self.gameServer.game
        return game.world.uiOptions.showReadyStates

    def getPlayerCount(self):
        game = self.gameServer.game
        return len([p for p in game.world.players if not p.bot])

    def playerCountChanged(self, *args, **kwargs):
        if self.inLobby():
            playerCount = self.getPlayerCount()
            playersString = '1 player' if playerCount == 1 else '%d players' % (
                    playerCount,)
            self.transmitEvent('message("%s in lobby.");' % (playersString,))

    def levelChanged(self, *args, **kwargs):
        self.transmitEvent(self.getInitialEvents())

    def getInitialEvents(self):
        if self.gameServer is None:
            return 'hideScoreboard();message("No running games on server.");\n'

        if self.inLobby():
            playerCount = self.getPlayerCount()
            return 'hideScoreboard();message("%d players in lobby.");\n' % (
                    playerCount,)

        return 'hideMessage();%s\n' % (self.getScoreMessage(),)

    def teamScoreChanged(self, *args, **kwargs):
        self.transmitEvent(self.getScoreMessage())

    def getScoreMessage(self):
        world = self.gameServer.game.world
        blueTeam, redTeam = world.teams[:2]
        blueZones = blueTeam.numZonesOwned
        redZones = redTeam.numZonesOwned
        totalZones = len(world.zones)
        neutralZones = totalZones - blueZones - redZones

        return 'score(%d,%d,%d,%d,%d);' % (
            blueTeam.orbScore,
            redTeam.orbScore,
            blueZones,
            neutralZones,
            redZones,
        )

    def waitForEvent(self):
        d = defer.Deferred()
        self.nextEventListeners.append(d)
        return d

    def transmitEvent(self, jsCommand):
        listeners = self.nextEventListeners
        self.nextEventListeners = []
        for d in listeners:
            d.callback(jsCommand + '\n')

    def keepEventPipeAlive(self):
        '''
        To make sure that a reverse proxy doesn't close connections due to
        inactivity.
        '''
        self.transmitEvent('')


class WSGIRoot(resource.Resource):
    def __init__(self, wsgi, *args, **kwargs):
        resource.Resource.__init__(self)
        self.wsgi = wsgi

    def getChild(self, child, request):
        request.prepath.pop()
        request.postpath.insert(0, child)
        return self.wsgi

    def render(self, request):
        return self.wsgi.render(request)


class DjangoStatic(resource.Resource):
    isLeaf = True

    def render_GET(self, request):
        localPath = finders.find('/'.join(request.postpath))
        if not localPath:
            return File.childNotFound.render(request)

        return File(localPath).render_GET(request)


def startWebServer(authFactory, port):
    mimetypes.types_map.update({
        '.trosrepl': 'application/octet-stream',
    })

    root = WSGIRoot(
        WSGIResource(reactor, reactor.getThreadPool(), application))
    root.putChild('static', DjangoStatic())
    root.putChild('poll', Resources(WebServer(authFactory, None)))
    factory = Site(root)
    reactor.listenTCP(port, factory)
