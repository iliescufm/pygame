# Trosnoth (UberTweak Platform Game)
# Copyright (C) 2006-2013 Joshua D Bartlett
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# version 2 as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.

import __builtin__

from rlcompleter import Completer

from trosnoth.utils.twist import WeakCallLater

from twisted.conch import manhole


class Manhole(manhole.ColoredManhole):

    tabCount = 0

    def sayHello(self):
        self.terminal.reset()
        self.terminal.write("\x1b[97mWelcome to \x1b[36mTrosnoth!")
        self.terminal.nextLine()
        helper = self.namespace['helper']
        for line in helper.getBanner():
            self.terminal.write(line)
            self.terminal.nextLine()
        self.terminal.write('>>> ')

    def connectionMade(self):
        super(Manhole, self).connectionMade()
        WeakCallLater(0.1, self, 'sayHello')

    def keystrokeReceived(self, keyID, modifier):
        super(Manhole, self).keystrokeReceived(keyID, modifier)
        self.tabCount += 1 if keyID == "\t" else 0

    def handle_TAB(self):
        text = "".join(self.lineBuffer).split(' ')[-1]
        if len(text) == 0:
            # Bell character
            self.terminal.write("\a")
            return

        completer = Completer(self.namespace)

        if completer.complete(text, 0):
            allMatches = list(set(completer.matches))

            # Get rid of a bunch of cruft
            builtins = __builtin__.keys()
            matches = [x for x in allMatches
                       if x.strip('(') not in builtins and "__" not in x]
            matches.sort()

            # If there are no matches, ring the terminal bell
            # If there's only one match, autocomplete it
            # If there's more than one match, print a list of matches
            if len(matches) == 0:
                self.terminal.write("\a")
                return
            elif len(matches) == 1:
                length = len(text)
                self.lineBuffer = self.lineBuffer[:-length]
                self.lineBuffer.extend(matches[0])
                self.lineBufferIndex = len(self.lineBuffer)
            else:
                # Remove text before the last dot, for brevity
                if "." in matches[0]:
                    matches = [x[x.rfind(".") + 1:] for x in matches]
                self.terminal.nextLine()
                self.terminal.write(repr(matches))
                self.terminal.nextLine()
                self.terminal.write("%s%s" % (self.ps[self.pn], ""))

            self.terminal.eraseLine()
            self.terminal.cursorBackward(self.lineBufferIndex + 5)
            self.terminal.write(
                "%s%s" % (self.ps[self.pn], "".join(self.lineBuffer)))

        else:
            self.terminal.write("\a")
