# This file is in the public domain
import compiler


def getObj(s):
    s = "a=" + s
    return compiler.parse(s).getChildren()[1].getChildren()[0].getChildren()[1]


class UnknownType(Exception):
    pass


class Builder:

    def build(self, o):
        m = getattr(self, 'build_'+o.__class__.__name__, None)
        if m is None:
            raise UnknownType(o.__class__.__name__)
        return m(o)

    def build_List(self, o):
        return map(self.build, o.getChildren())

    def build_Const(self, o):
        return o.value

    def build_Dict(self, o):
        d = {}
        i = iter(map(self.build, o.getChildren()))
        for el in i:
            d[el] = i.next()
        return d

    def build_Tuple(self, o):
        return tuple(self.build_List(o))

    def build_Name(self, o):
        if o.name == 'None':
            return None
        if o.name == 'True':
            return True
        if o.name == 'False':
            return False
        raise UnknownType('Name')

    def build_Add(self, o):
        real, imag = map(self.build_Const, o.getChildren())
        try:
            real = float(real)
        except TypeError:
            raise UnknownType('Add')
        if not isinstance(imag, complex) or imag.real != 0.0:
            raise UnknownType('Add')
        return real+imag

    def build_UnarySub(self, o):
        (child,) = o.getChildren()
        return -self.build(child)


def unrepr(s):
    return Builder().build(getObj(s))
