from ctypes import (
    Structure, c_uint32, c_float, c_wchar, c_char, sizeof, c_char_p, CDLL,
)
import mmap
import os
import sys

import simplejson


WIN32 = sys.platform == 'win32'

if WIN32:
    from ctypes import windll
    FILE_MAP_ALL_ACCESS = 0xF001F
    FALSE = 0
else:
    try:
        librt = CDLL('librt.so')    # Linux
    except:
        try:
            librt = CDLL('/usr/lib/libSystem.dylib')    # OSX
        except:
            librt = None
    S_IRUSR = 0o400
    S_IWUSR = 0o200


class MumbleLinkedMem(Structure):
    _fields_ = [
        ('uiVersion', c_uint32),
        ('uiTick', c_uint32),
        ('fAvatarPosition', c_float * 3),
        ('fAvatarFront', c_float * 3),
        ('fAvatarTop', c_float * 3),
        ('name', c_wchar * 256),
        ('fCameraPosition', c_float * 3),
        ('fCameraFront', c_float * 3),
        ('fCameraTop', c_float * 3),
        ('identity', c_wchar * 256),
        ('context_len', c_uint32),
        ('context', c_char * 256),
        ('description', c_wchar * 2048),
    ]


class MumbleUpdater(object):
    mapUnitsPerMetre = 1000

    def __init__(self):
        self.lm = None
        self.mapScale = 1. / self.mapUnitsPerMetre
        self.lastPlayerDetails = None

        if WIN32:
            # TODO: test this on windows
            hMapObject = windll.kernel32.OpenFileMappingW(
                FILE_MAP_ALL_ACCESS, FALSE, u'MumbleLink')
            if hMapObject == 0:
                return

            address = windll.kernel32.MapViewOfFile(
                hMapObject, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(MumbleLinkedMem))
            if address == 0:
                windll.kernel32.CloseHandle(hMapObject)
                return
            self.lm = MumbleLinkedMem.from_address(address)

        elif librt:
            memname = c_char_p('/MumbleLink.%d' % (os.getuid(),))
            shmfd = librt.shm_open(memname, os.O_RDWR, S_IRUSR | S_IWUSR)
            if shmfd < 0:
                # Shared memory does not exist, because Mumble is not running
                return

            self.lm = MumbleLinkedMem.from_buffer(
                mmap.mmap(shmfd, sizeof(MumbleLinkedMem)))

    def scalePoint(self, (x, y)):
        return (x * self.mapScale, -y * self.mapScale, 0)

    def update(self, player, cameraPos, serverId):
        if self.lm is None:
            return

        if self.lm.uiVersion != 2:
            self.lm.name = 'Trosnoth'
            self.lm.description = 'Trosnoth network platformer'
            self.lm.uiVersion = 2
            self.lastPlayerDetails = None

        self.lm.uiTick += 1

        self.lm.fAvatarFront = self.lm.fCameraFront = (0, 0, 1)
        self.lm.fAvatarTop = self.lm.fCameraTop = (0, 1, 0)
        if player:
            self.lm.fAvatarPosition = self.scalePoint(player.pos)
            playerDetails = (player.teamId, player.id)
        else:
            self.lm.fAvatarPosition = (0, 0, 0)
            playerDetails = []

        self.lm.fCameraPosition = self.scalePoint(cameraPos)

        self.lm.context = serverId
        self.lm.context_len = len(serverId)

        if playerDetails != self.lastPlayerDetails:
            self.lastPlayerDetails = playerDetails
            self.lm.identity = simplejson.dumps(playerDetails)


mumbleUpdater = MumbleUpdater()
