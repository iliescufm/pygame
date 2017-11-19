import logging
import os
import tempfile

from trosnoth.djangoapp.models import TrosnothServerSettings

log = logging.getLogger(__name__)


state = 'uninitialised'
murmur = None
createdRooms = []


def init(force=False):
    global state, murmur
    if state != 'uninitialised' and not force:
        return 'previously failed'

    try:
        settings = TrosnothServerSettings.get()
        if not settings.iceEnabled:
            state = 'disabled'
            return

        import Ice, IcePy

        proxyString = settings.iceProxyStringOverride
        if not proxyString:
            proxyString = 'Meta:tcp -h {host} -p {port} -t 1000'.format(
                host=settings.iceHost, port=settings.icePort)

        props = Ice.createProperties()
        props.setProperty('Ice.ImplicitContext', 'Shared')
        initData = Ice.InitializationData()
        initData.properties = props
        ice = Ice.initialize(initData)

        proxy = ice.stringToProxy(proxyString)
        op = IcePy.Operation(
            'getSlice', Ice.OperationMode.Idempotent,
            Ice.OperationMode.Idempotent, True, None, (), (), (),
            ((), IcePy._t_string, False, 0), ())

        sl = op.invoke(proxy, ((), None))
        fd, path  = tempfile.mkstemp(suffix='.ice')
        f = os.fdopen(fd, 'w')
        with f:
            f.write(sl)
            f.flush()

            Ice.loadSlice('', ['-I' + Ice.getSliceDir(), path])
        os.unlink(path)

        if settings.iceSecret:
            ice.getImplicitContext().put(
                'secret', settings.iceSecret.encode('ascii'))

        import Murmur
        murmur = Murmur.MetaPrx.checkedCast(proxy)
    except Exception:
        log.exception('Error initialising murmur connection')
        state = 'failed'
    else:
        state = 'initialised'
    return state


def setupRooms(teams, players):
    if state != 'initialised':
        return

    tearDownRooms()
    s = getServer()
    if not s:
        return

    teamToChannelId = {}
    for team in teams:
        channelId = s.addChannel(team.teamName, 0)
        createdRooms.append(channelId)
        teamToChannelId[team] = channelId

    users = {}
    for userState in s.getUsers().itervalues():
        users[userState.name.lower()] = userState

    for player in players:
        # Move the player into the appropriate channel
        if player.user is None:
            continue
        if player.team not in teams:
            continue
        key = player.user.username.lower()
        if key not in users:
            key = player.nick.lower()
            if key not in users:
                continue

        # Don't move this player again, even if it matches another player's
        # nick / username.
        userState = users.pop(key)

        userState.channel = teamToChannelId[player.team]
        s.setState(userState)


def tearDownRooms():
    if state != 'initialised':
        return
    s = getServer()
    if not s:
        return
    while createdRooms:
        roomId = createdRooms.pop()
        s.removeChannel(roomId)


def getServer():
    servers = murmur.getBootedServers()
    if servers:
        return servers[0]
    log.warning('Could not connect to murmur server via ICE')
    return None
