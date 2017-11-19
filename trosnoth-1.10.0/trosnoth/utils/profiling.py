# Based on https://people.gnome.org/~johan/lsprofcalltree.py
# lsprofcalltree.py: lsprof output which is readable by kcachegrind
# David Allouche
# Jp Calderone & Itamar Shtull-Trauring
# Johan Dahlin
# Modified by Joshua D Bartlett


def get_class_name(code):
    try:
        f = open(code.co_filename, 'rU')
    except IOError:
        return None

    cls = None
    num = 0
    for line in f:
        num += 1
        indent = len(line) - len(line.lstrip())
        if num == code.co_firstlineno:
            break
        if line.lstrip() != '' and indent == 0:
            if line.startswith('class '):
                i = j = len('class ')
                while line[j].isalnum() or line[j] == '_':
                    j += 1
                cls = line[i:j]
            else:
                cls = 0
    else:
        return None

    if indent == 4 and cls:
        return cls

    return None


def label(code):
    if isinstance(code, str):
        return '%s (built-in)' % (code,)
    else:
        classname = get_class_name(code)
        if classname:
            return '%s.%s %s:%d' % (
                classname, code.co_name, code.co_filename, code.co_firstlineno)
        else:
            return '%s %s:%d' % (
                code.co_name, code.co_filename, code.co_firstlineno)


class KCacheGrindOutputter(object):
    def __init__(self, profiler):
        self.data = profiler.getstats()
        self.out_file = None

    def output(self, out_file):
        self.out_file = out_file
        print >> out_file, 'events: Ticks'
        self._print_summary()
        for entry in self.data:
            self._entry(entry)

    def _print_summary(self):
        max_cost = 0
        for entry in self.data:
            totaltime = int(entry.totaltime * 1000)
            max_cost = max(max_cost, totaltime)
        print >> self.out_file, 'summary: %d' % (max_cost,)

    def _entry(self, entry):
        out_file = self.out_file

        code = entry.code
        if isinstance(code, str):
            print >> out_file, 'fi=~'
        else:
            print >> out_file, 'fi=%s' % (code.co_filename,)
        print >> out_file, 'fn=%s' % (label(code),)

        inlinetime = int(entry.inlinetime * 1000)
        if isinstance(code, str):
            print >> out_file, '0 ', inlinetime
        else:
            print >> out_file, '%d %d' % (code.co_firstlineno, inlinetime)

        # recursive calls are counted in entry.calls
        if entry.calls:
            calls = entry.calls
        else:
            calls = []

        if isinstance(code, str):
            lineno = 0
        else:
            lineno = code.co_firstlineno

        for subentry in calls:
            self._subentry(lineno, subentry)
        print >> out_file

    def _subentry(self, lineno, subentry):
        out_file = self.out_file
        code = subentry.code
        print >> out_file, 'cfn=%s' % (label(code),)
        if isinstance(code, str):
            print >> out_file, 'cfi=~'
            print >> out_file, 'calls=%d 0' % (subentry.callcount,)
        else:
            print >> out_file, 'cfi=%s' % (code.co_filename,)
            print >> out_file, 'calls=%d %d' % (
                subentry.callcount, code.co_firstlineno)

        totaltime = int(subentry.totaltime * 1000)
        print >> out_file, '%d %d' % (lineno, totaltime)
