from trosnoth.levels.base import playLevel
from trosnoth.levels.standard import StandardLevel
from trosnoth.model.map import ZoneLayout, ZoneStep


class DemoLevel(StandardLevel):
    '''
    Example of how to write a custom level.
    '''

    def setupMap(self):
        zones = ZoneLayout(symmetryEnforced=True)

        pos = zones.connectZone(zones.firstLocation, ZoneStep.NORTHEAST)
        pos = zones.connectZone(pos, ZoneStep.SOUTHEAST)
        pos = zones.connectZone(pos, ZoneStep.SOUTH)
        pos = zones.connectZone(pos, ZoneStep.SOUTHWEST)
        pos2 = zones.connectZone(pos, ZoneStep.NORTHWEST)
        zones.connectZone(pos2, ZoneStep.NORTH)

        pos = zones.connectZone(pos, ZoneStep.SOUTH)
        pos = zones.connectZone(pos, ZoneStep.SOUTHEAST)
        pos = zones.connectZone(pos, ZoneStep.NORTHEAST)
        pos = zones.connectZone(pos, ZoneStep.NORTH)
        zones.connectZone(pos, ZoneStep.NORTHWEST)

        pos = zones.connectZone(pos, ZoneStep.NORTHEAST)
        pos = zones.connectZone(pos, ZoneStep.NORTH)
        pos = zones.connectZone(pos, ZoneStep.NORTHWEST)
        zones.connectZone(pos, ZoneStep.SOUTHWEST)

        pos = zones.connectZone(pos, ZoneStep.NORTH)
        pos = zones.connectZone(pos, ZoneStep.NORTHWEST)
        pos = zones.connectZone(pos, ZoneStep.SOUTHWEST)
        zones.connectZone(pos, ZoneStep.SOUTH)

        layout = zones.createMapLayout(self.world.layoutDatabase)
        self.world.setLayout(layout)


if __name__ == '__main__':
    playLevel(DemoLevel(), aiCount=9)
