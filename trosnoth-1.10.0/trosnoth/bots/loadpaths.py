import zipfile

from trosnoth.bots.pathfinding import (
    DB_FILENAME,
    PreCalculatedMapBlockCombination,
)


class FakeLayout(object):
    def __init__(self, rev):
        self.reversed = rev
        self.filename = '(fake)'


class FakeBlockDef(object):
    def __init__(self, kind, id, rev):
        self.kind = kind
        self.blocked = None
        self.layout = FakeLayout(rev)


def loadStore(suffix=''):
    fullFilename = DB_FILENAME + suffix
    with zipfile.ZipFile(fullFilename, 'r') as z:
        for info in z.infolist():
            fn = info.filename
            if fn.startswith('combos/'):
                cache = {}
                combos, kind1, id1, rev1, dir, kind2, id2, rev2 = fn.split('/')
                data = PreCalculatedMapBlockCombination._loadCombinationData(
                    FakeBlockDef(kind1, id1, rev1),
                    FakeBlockDef(kind2, id2, rev2),
                    dir,
                    z,
                    arcName=fn,
                    cache=cache,
                )
                yield cache[fn]


if __name__ == '__main__':
    import code
    code.interact(local=globals())