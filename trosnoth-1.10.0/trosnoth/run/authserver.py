import datetime
from functools import partial
from hashlib import sha1
import logging
import os
import pickle
import random

from django.contrib.auth import authenticate
from django.core import management

from trosnoth import data
from trosnoth.data import getPath, makeDirs, user
from trosnoth import dbqueue
from trosnoth.djangoapp.models import (
    User, TrosnothUser, AchievementProgress, TrosnothServerSettings,
)
from trosnoth.game import LocalGame
from trosnoth.gamerecording.stats import ServerGameStats
from trosnoth import rsa
from trosnoth.levels.base import LobbyLevel, RandomLayoutHelper
from trosnoth.manholehelper import AuthServerManholeHelper
from trosnoth.model.mapLayout import LayoutDatabase
from trosnoth import murmur
from trosnoth.network import authcommands
from trosnoth.network.manhole import Manhole
from trosnoth.network.server import TrosnothServerFactory
from trosnoth.network.networkDefines import serverVersion
from trosnoth.settings import AuthServerSettings
from trosnoth.utils.event import Event
from trosnoth.utils.utils import timeNow, initLogging

from trosnoth.gamerecording.achievementlist import availableAchievements

from twisted.protocols import amp
from twisted.internet import reactor, defer
from twisted.internet.protocol import Factory, ClientCreator, Protocol
from twisted.internet.error import CannotListenError, ConnectError
from twisted.cred import portal, checkers
from twisted.conch import manhole_ssh
from twisted.conch.error import ConchError
from twisted.conch.ssh import keys

log = logging.getLogger('authserver')

MAX_GAMES = 1
GAME_KIND = 'Trosnoth1'

GAME_VERIFY_TIME = 60
REPLAY_SUB_PATH = os.path.join('authserver', 'public', 'trosnoth', 'replays')


class AuthenticationProtocol(amp.AMP):
    '''
    Trosnoth authentication server which is used when running a game server
    which keeps track of users.
    @param dataPath: path to the location for this authentication server to
        store its data. If not specified, $HOME/.trosnoth/authserver will be
        used. If the path does not exist, it will be created.
    '''

    def connectionMade(self):
        super(AuthenticationProtocol, self).connectionMade()
        self.user = None
        self.token = None
        log.info('New connection.')

    def connectionLost(self, reason):
        log.info('Connection lost.')

    @authcommands.GetPublicKey.responder
    def getPublicKey(self):
        return {
            'e': self.factory.pubKey['e'],
            'n': self.factory.pubKey['n'],
        }

    @authcommands.ListGames.responder
    def listGames(self):
        games = []
        for gameId in self.factory.servers.keys():
            games.append({
                'id': gameId,
                'game': GAME_KIND,
                'version': serverVersion,
            })

        return {'games': games}

    @authcommands.ListOtherGames.responder
    def listOtherGames(self):
        d = self.factory.getRegisteredGames()

        @d.addCallback
        def gotGames(rGames):
            result = []
            for rGame in rGames:
                result.append({
                    'game': rGame.game,
                    'version': rGame.version,
                    'ip': rGame.host,
                    'port': rGame.port,
                })
            return {
                'games': result,
            }
        return d

    @authcommands.RegisterGame.responder
    def registerGame(self, game, version, port):
        host = self.transport.getPeer().host
        self.factory.registerGame(game, version, host, port)
        return {}

    @authcommands.CreateGame.responder
    def createGame(self, game):
        if game != GAME_KIND:
            raise authcommands.CannotCreateGame()
        if len(self.factory.servers) >= MAX_GAMES:
            raise authcommands.CannotCreateGame()
        return {
            'id': self.factory.createGame(),
            'version': serverVersion,
        }

    @authcommands.ConnectToGame.responder
    def connectToGame(self, id):
        if self.user is None:
            raise authcommands.NotAuthenticated()
        try:
            server = self.factory.servers[id]
        except KeyError:
            raise authcommands.GameDoesNotExist()

        tag = server.authTagManager.newTag(self.user)
        nick = self.user.getNick()

        self.factory.broadcast('%s has joined the game' % (nick,))
        return {
            'port': server.getTCPPort(),
            'authTag': tag,
            'nick': nick,
        }

    @authcommands.GetSupportedSettings.responder
    def getSupportedSettings(self):
        settings = ['password']
        return {
            'result': settings,
        }

    @authcommands.SetPassword.responder
    def setUserPassword(self, password):
        if self.user is None:
            raise authcommands.NotAuthenticated()
        password = self._decodePassword(password)
        self.user.setPassword(password)
        return {}

    @authcommands.GetAuthToken.responder
    def getAuthToken(self):
        self.token = ''.join(str(random.randrange(256)) for i in range(16))
        return {
            'token': self.token
        }

    @authcommands.PasswordAuthenticate.responder
    def passwordAuthenticate(self, username, password):
        username = username.lower()
        password = self._decodePassword(password)
        if password is None:
            return {'result': False}    # Bad auth token used.

        d = self.factory.authManager.authenticateUser(username, password)

        @d.addCallback
        def authSucceeded(user):
            self.user = user
            return {'result': True}

        @d.addErrback
        def authFailed(failure):
            return {'result': False}

        return d

    @authcommands.CreateUserWithPassword.responder
    def createUserWithPassword(self, username, password):
        if self.factory.settings.allowNewUsers:
            nick = username
            username = username.lower()
            password = self._decodePassword(password)
            if password is None:
                return {'result': 'Authentication token failure.'}

            authMan = self.factory.authManager
            if authMan.checkUsername(username):
                return {'result': 'That username is taken.'}
            self.user = authMan.createUser(username, password, nick)
        else:
            return {'result': self.factory.settings.privateMsg}
        return {'result': ''}

    def _decodePassword(self, password):
        if self.token is None:
            return None
        token, self.token = self.token, None
        passwordData = rsa.decrypt(password, self.factory.privKey)
        if passwordData[:len(token)] != token:
            return None
        return passwordData[len(token):]

SALT = 'Trosnoth'


class AuthManager(object):
    '''
    Manages user accounts on the system.
    '''

    def __init__(self, dataPath):
        self.dataPath = dataPath
        self.tags = {}      # auth tag -> user id
        self.settings = AuthServerSettings(dataPath)

    def checkUsername(self, username):
        '''
        Returns True or False, depending on whether the given username is
        already in use.
        '''
        try:
            TrosnothUser.fromUser(username=username)
        except User.DoesNotExist:
            return False
        return True

    def newTagManager(self):
        '''
        Returns an authentication tag manager for this set of users.
        '''
        return AuthTagManager(self)

    def authenticateUser(self, username, password):
        '''
        If a username exists with the given password, returns the user,
        otherwise returns None.
        '''
        username = username.lower()
        try:
            trosnothUser = TrosnothUser.fromUser(username=username)
        except User.DoesNotExist:
            return defer.fail()

        if not trosnothUser.oldPasswordHash:
            # Just use Django auth
            djangoUser = authenticate(username=username, password=password)
            if djangoUser is None:
                return defer.fail(ValueError('Authentication failed'))
            if not djangoUser.is_active:
                return defer.fail(ValueError('User deactivated'))
            user = AuthenticatedUser(self, username)
        else:
            # Old Trosnoth auth, only exists for backward compatibility
            hash1 = sha1(SALT + password).digest()
            hash2 = bytes(trosnothUser.oldPasswordHash)
            if hash1 != hash2:
                return defer.fail(ValueError('Incorrect password'))

            # Put the password into Django
            trosnothUser.user.set_password(password)
            trosnothUser.user.save()
            trosnothUser.oldPasswordHash = ''
            trosnothUser.save()

            user = AuthenticatedUser(self, username)

        user.seen()
        return defer.succeed(user)

    def createUser(self, username, password, nick=None):
        username = username.lower()
        if self.checkUsername(username):
            raise ValueError('user %r already exists' % (username,))
        User.objects.create_user(username, password=password)

        user = AuthenticatedUser(self, username)
        user.setPassword(password)
        user.seen()
        if nick is not None:
            user.setNick(nick)
        return user

    def getNick(self, username):
        return TrosnothUser.fromUser(username=username).nick


class StandardLobbyLevel(LobbyLevel):
    def __init__(self, size):
        super(StandardLobbyLevel, self).__init__()
        self.size = size

    def setupMap(self):
        halfMapWidth, mapHeight = self.size
        layoutHelper = RandomLayoutHelper(self.world, halfMapWidth, mapHeight)
        layoutHelper.apply()


class AuthenticationFactory(Factory):
    protocol = AuthenticationProtocol
    authManagerClass = AuthManager

    def __init__(self, dataPath=None):
        if dataPath is None:
            dataPath = getPath(data.user, 'authserver')
        makeDirs(dataPath)
        self.dataPath = dataPath

        self.onPrimaryGameChanged = Event()
        self.primaryGameId = None

        self.authManager = self.authManagerClass(dataPath)
        self.pubKey, self.privKey = self.loadKeys()
        self.servers = {}     # Game id -> game.
        self.nextId = 0
        self.registeredGames = []
        self.gameStats = {}

        self.layoutDatabase = LayoutDatabase()

        self.notifier = self.settings.createNotificationClient()
        if self.notifier is not None:
            self.notifier.startService()

    @property
    def settings(self):
        return self.authManager.settings

    def getPlayerCount(self):
        '''
        Returns the total number of online players in all games.
        '''
        result = 0
        for server in self.servers.values():
            for p in server.game.world.players:
                if not p.bot:
                    result += 1
        return result

    def loadKeys(self):
        '''
        Loads public and private keys from disk or creates them and saves them.
        '''
        keyPath = os.path.join(self.dataPath, 'keys')
        try:
            pub, priv = pickle.load(open(keyPath, 'rb'))
        except IOError:
            pub, priv = rsa.newkeys(self.settings.keyLength)
            pickle.dump((pub, priv), open(keyPath, 'wb'), 2)

        return pub, priv

    def createGame(self):
        '''
        Creates a new game and returns the game id.
        '''
        gameId = self.nextId
        self.nextId += 1
        authTagMan = self.authManager.newTagManager()

        game = LocalGame(
            layoutDatabase=self.layoutDatabase,
            maxPerTeam=self.settings.maxPerTeam,
            authTagManager=authTagMan,
            saveReplay=True,
            gamePrefix='Server',
            replayPath=REPLAY_SUB_PATH,
            level=StandardLobbyLevel(self.settings.lobbySize),
        )
        server = TrosnothServerFactory(game, authTagMan)

        def onShutdown():
            server.stopListening()
            del self.servers[gameId]
            del self.gameStats[game]
            game.world.onSwitchStats.removeListener(switchGameStats)
            if gameId == self.primaryGameId:
                self.primaryGameId = None
                self.onPrimaryGameChanged(None)
        server.onShutdown.addListener(onShutdown)
        server.startListening()

        self.gameStats[game] = None
        switchGameStats = partial(self.switchGameStats, game=game)
        game.world.onSwitchStats.addListener(switchGameStats)

        if murmur.state == 'initialised':
            game.world.onChangeVoiceChatRooms.addListener(murmur.setupRooms)

        log.info('Created game (id=%d)' % (gameId,))
        self.servers[gameId] = server
        self.broadcast('a new game has been created')
        if self.primaryGameId is None:
            self.primaryGameId = gameId
            self.onPrimaryGameChanged(server)

        return gameId

    def switchGameStats(self, game, enabled):
        gameStats = self.gameStats[game]
        if gameStats and not enabled:
            # Stopping game
            gameStats.stopAndSave()
            self.gameStats[game] = None

        elif enabled and not gameStats:
            # Starting game
            self.gameStats[game] = ServerGameStats(game)

    def broadcast(self, message):
        if self.notifier is None:
            return
        try:
            self.notifier.broadcast('%s: %s' % (
                self.settings.hostName, message))
        except:
            log.error('Error broadcasting message', exc_info=True)

    @defer.inlineCallbacks
    def registerGame(self, game, version, host, port):
        '''
        Registers a remote game with this server.
        '''
        settings = TrosnothServerSettings.get()
        if not settings.allowRemoteGameRegistration:
            return

        rGame = RegisteredGame(game, version, host, port)
        result = yield rGame.verify()
        if result:
            log.info('Registered game on %s:%s', host, port)
            self.registeredGames.append(rGame)
        else:
            log.info('Failed to connect to game on %s:%s', host, port)
            raise authcommands.PortUnreachable()

    def getRegisteredGames(self):
        '''
        Returns a list of registered games which are running.
        '''
        if len(self.registeredGames) == 0:
            return defer.succeed([])

        result = []
        d = defer.Deferred()
        remaining = [len(self.registeredGames)]

        def gameVerified(success, rGame):
            if success:
                result.append(rGame)
            else:
                self.registeredGames.remove(rGame)

            remaining[0] -= 1
            if remaining[0] == 0:
                d.callback(result)

        for rGame in self.registeredGames:
            rGame.verify().addCallback(gameVerified, rGame)

        return d


class RegisteredGame(object):
    '''
    Represents a remote game that has been registered with this server.
    '''

    def __init__(self, game, version, host, port):
        self.game = game
        self.version = version
        self.host = host
        self.port = port
        self.lastVerified = 0
        self.running = True

    @defer.inlineCallbacks
    def verify(self):
        '''
        If more than GAME_VERIFY_TIME has passed since the last verification,
        connects to the game to check whether it is still running. Returns a
        deferred whose callback will be executed with True or False depending
        on whether the game is still running.
        '''
        t = timeNow()
        if t - self.lastVerified < GAME_VERIFY_TIME:
            defer.returnValue(self.running)
            return
        self.lastVerified = t

        try:
            yield ClientCreator(reactor, Protocol).connectTCP(
                self.host, self.port, timeout=5)
        except ConnectError:
            self.running = False
            defer.returnValue(False)
            return

        self.running = True
        defer.returnValue(True)


class AuthTagManager(object):
    '''
    Provides a gateway for the Validator to confirm that a player has
    authenticated and to check the player's userid.
    '''

    def __init__(self, authManager):
        self.authManager = authManager
        self.tags = {}      # auth tag -> user id

    def checkUsername(self, username):
        '''
        Returns True or False, depending on whether the given username is
        already in use.
        '''
        return self.authManager.checkUsername(username)

    def newTag(self, user):
        tag = random.randrange(1 << 64)
        self.tags[tag] = user
        return tag

    def checkAuthTag(self, tag):
        '''
        Returns the authenticated user corresponding to the auth tag, or
        None if the tag is not recognised.
        Don't forget to call discardAuthTag() when the authentication tag is no
        longer valid.
        '''
        return self.tags.get(tag, None)

    def discardAuthTag(self, tag):
        try:
            del self.tags[tag]
        except KeyError:
            pass


class AuthenticatedUser(object):
    '''
    Represents a user which has been authenticated on the system.
    '''

    def __init__(self, authManager, username):
        self.authManager = authManager
        self.username = username = username.lower()

    def __eq__(self, other):
        if (isinstance(other, AuthenticatedUser) and other.username ==
                self.username):
            return True
        return False

    def __hash__(self):
        return hash(self.username)

    def isElephantOwner(self):
        return self.username in self.authManager.settings.elephantOwners

    def getNick(self):
        return TrosnothUser.fromUser(username=self.username).nick

    def getDefaultTeam(self):
        # Not yet implemented. Could be used to set what tournament team this
        # player usually playes on.
        return ''

    def setNick(self, nick):
        @dbqueue.add
        def writeNickToDB():
            user = TrosnothUser.fromUser(username=self.username)
            if nick != user.nick:
                user.nick = nick
                user.save()

    def setPassword(self, password):
        # Don't put DB write in a queue as user will expect it to take place
        # immediately.
        user = User.objects.get(username=self.username)
        user.set_password(password)
        user.save()
        trosnothUser = TrosnothUser.fromUser(pk=user.pk)
        trosnothUser.oldPasswordHash = ''
        trosnothUser.save()

    def getAchievementRecord(self, achievementId):
        user = TrosnothUser.fromUser(username=self.username)
        try:
            achievement = AchievementProgress.objects.get(
                user=user, achievementId=achievementId)
        except AchievementProgress.DoesNotExist:
            achievement = AchievementProgress(
                user=user, achievementId=achievementId)
            achievement.save()
        return achievement

    def achievementUnlocked(self, achievementId):
        @dbqueue.add
        def writeUnlockedAchievementToDB():
            user = TrosnothUser.fromUser(username=self.username)
            try:
                achievement = AchievementProgress.objects.get(
                    user=user, achievementId=achievementId)
            except AchievementProgress.DoesNotExist:
                achievement = AchievementProgress(
                    user=user, achievementId=achievementId)
            if not achievement.unlocked:
                achievement.unlocked = True
                achievement.save()

    def seen(self):
        now = datetime.datetime.now()
        @dbqueue.add
        def writeSeenTimeToDB():
            user = TrosnothUser.fromUser(username=self.username)
            user.lastSeen = now
            user.save()


def startServer(
        port=6787, dataPath=None, manholePort=6799, password=None,
        webPort=None):

    # Ensure that the authserver directories exist
    authDir = getPath(user, 'authserver', 'accounts')
    makeDirs(authDir)

    # Ensure that any database migrations have happened
    management.call_command('migrate')

    # If murmur communication is enabled, try to connect
    if murmur.init() == 'initialised':
        reactor.addSystemEventTrigger(
            'before', 'shutdown', murmur.tearDownRooms)

    dbqueue.init()

    pf = AuthenticationFactory(dataPath)

    def getManholeFactory(namespace, password):
        realm = manhole_ssh.TerminalRealm()

        # If we don't do this, the server will generate an exception when
        # you resize the SSH window
        def windowChanged(self, size):
            pass
        realm.sessionFactory.windowChanged = windowChanged

        def getManhole(_):
            return Manhole(namespace)
        realm.chainedProtocolFactory.protocolFactory = getManhole
        p = portal.Portal(realm)

        # Username/Password authentication
        passwordDB = checkers.InMemoryUsernamePasswordDatabaseDontUse()
        passwordDB.addUser('trosnoth', password)
        p.registerChecker(passwordDB)

        factory = manhole_ssh.ConchFactory(p)

        privatePath = getPath(user, 'authserver', 'manhole_rsa')
        if os.path.isfile(privatePath):
            factory.privateKeys[b'ssh-rsa'] = keys.Key.fromFile(privatePath)
        publicPath = privatePath + '.pub'
        if os.path.isfile(publicPath):
            factory.publicKeys[b'ssh-rsa'] = keys.Key.fromFile(publicPath)

        return factory

    if password is None:
        password = ''.join(random.choice('0123456789') for i in range(6))

    namespace = {}
    namespace['authFactory'] = pf
    namespace['helper'] = AuthServerManholeHelper(pf)
    factory = getManholeFactory(namespace, password)

    try:
        reactor.listenTCP(manholePort, factory)
    except CannotListenError:
        log.error('Error starting manhole on port %d', manholePort)
    except ConchError as e:
        log.error('Error starting manhole on port %d: %s', manholePort, e.value)
    else:
        log.warning(
            'SSH manhole started on port %d with password %r',
            manholePort, password)

    if webPort is not None:
        from trosnoth.web.server import startWebServer
        startWebServer(pf, webPort)

    try:
        reactor.listenTCP(port, pf)
    except CannotListenError:
        log.error('Error listening on port %d.', port)
    else:
        log.info(
            'Started Trosnoth authentication server on port %d.', port)
        reactor.run()


def main():
    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option(
        '-p', '--port', action='store', dest='port', default=6787,
        help='which port to run the authentication server on')
    parser.add_option(
        '-D', '--datapath', action='store', dest='dataPath', default=None,
        help='where to store the authentication server data')
    parser.add_option(
        '-m', '--manhole', action='store', dest='manholePort',
        default=6799, help='which port to run the manhole on')
    parser.add_option(
        '--password', action='store', dest='manholePassword', default=None,
        help='the password to use for the manhole')
    parser.add_option(
        '-w', '--webport', action='store', dest='webPort', default='8080',
        help='the port on which to launch the web service. '
        'Default is 8080. To disable web service, use --webport= with no '
        'parameter.')
    parser.add_option(
        '-d', '--debug', action='store_true', dest='debug',
        help='show debug-level messages on console')
    parser.add_option(
        '-l', '--log-file', action='store', dest='logFile',
        help='file to write logs to')
    parser.add_option(
        '--profile', action='store_true', dest='profile',
        help='dump kcachegrind profiling data to trosnoth.log')

    options, args = parser.parse_args()
    if len(args) > 0:
        parser.error('no arguments expected')

    initLogging(options.debug, options.logFile)

    if not options.webPort:
        webPort = None
    else:
        try:
            webPort = int(options.webPort)
        except ValueError:
            options.error('Invalid port: %r' % (options.webPort,))

    kwargs = dict(
        port=int(options.port), dataPath=options.dataPath,
        manholePort=int(options.manholePort),
        password=options.manholePassword, webPort=webPort,
    )

    if options.profile:
        runWithProfiling(**kwargs)
    else:
        startServer(**kwargs)


def runWithProfiling(**kwargs):
    import cProfile
    from trosnoth.utils.profiling import KCacheGrindOutputter
    prof = cProfile.Profile()

    try:
        prof.runcall(startServer, **kwargs)
    except SystemExit:
        pass
    finally:
        kg = KCacheGrindOutputter(prof)
        with open('server.log', 'wb') as f:
            kg.output(f)



if __name__ == '__main__':
    main()
