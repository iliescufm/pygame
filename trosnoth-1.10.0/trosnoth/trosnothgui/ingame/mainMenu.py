# Trosnoth (UberTweak Platform Game)
# Copyright (C) 2006-2012 Joshua D Bartlett
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


from trosnoth.gui.framework.menu import MenuDisplay
from trosnoth.gui.menu.menu import MenuManager, Menu, MenuItem
from trosnoth.model.upgrades import allUpgrades
from trosnoth.gui.common import Size

class MainMenu(MenuDisplay):
    def __init__(self, app, location, interface, keymapping):
        font = app.screenManager.fonts.ingameMenuFont
        titleColour = (255, 255, 255)
        stdColour = (255, 255, 0)
        hvrColour = (0, 255, 255)
        backColour = (0, 64, 192)
        autosize = True
        hidable = True
        size = Size(175, 10)   # Height doesn't matter when autosize is set.

        self.ACCELERATION = 1000    # pix/s/s

        manager = MenuManager()
        upgrades = [MenuItem('%s (%s)' % (upgradeClass.name,
                upgradeClass.requiredCoins), upgradeClass.action) for
                upgradeClass in sorted(allUpgrades,
                key=lambda upgradeClass: upgradeClass.order)]
        self.buyMenu = Menu(name='Select Upgrade', listener=interface.doAction,
                items=upgrades + [
            MenuItem('Deselect upgrade', 'no upgrade'),
            MenuItem('Cancel', 'menu')
        ])

        self.moreMenu = Menu(name='More Actions', listener=interface.doAction,
                items=[
            MenuItem('Chat', 'chat'),
            MenuItem('Show/hide HUD', 'toggle interface'),
            MenuItem('Cancel', 'menu')
        ])
        self.quitMenu = Menu(name='Really Quit?', listener=interface.doAction,
                items=[
            MenuItem('Leave game', 'leave'),
            MenuItem('---'),
            MenuItem('Cancel', 'menu')
        ])
        self.playMenu = Menu(name='Menu', listener=interface.doAction, items=[
            MenuItem('Respawn', 'respawn'),
            MenuItem('Select upgrade...', 'select upgrade'),
            MenuItem('Activate upgrade', 'activate upgrade'),
            MenuItem('Pause / resume', 'pause'),
            MenuItem('Change nickname', 'change nickname'),
            MenuItem('Settings', 'settings'),
            MenuItem('More...', 'more actions'),
            MenuItem('---'),
            MenuItem('Leave game', 'maybeLeave')
        ])
        self.replayMenu = Menu(
            name='Menu', listener=interface.doAction,
            items=[
                MenuItem('Settings', 'settings'),
                MenuItem('---'),
                MenuItem('Quit', 'maybeLeave')
            ],
        )
        self.spectateMenu = Menu(
            name='Menu', listener=interface.doAction,
            items=[
                MenuItem('Join...', 'join'),
                MenuItem('Settings', 'settings'),
                MenuItem('---'),
                MenuItem('Quit', 'maybeLeave')
            ],
        )

        manager.setDefaultMenu(self.playMenu)

        super(MainMenu, self).__init__(app, location, size, font, manager,
                titleColour, stdColour, hvrColour, None, backColour, autosize,
                hidable, keymapping)

    def setMode(self, replay=False, spectate=False):
        if replay:
            self.manager.setDefaultMenu(self.replayMenu)
        elif spectate:
            self.manager.setDefaultMenu(self.spectateMenu)
        else:
            self.manager.setDefaultMenu(self.playMenu)
        self.manager.reset()

    def showBuyMenu(self):
        self.manager.reset()
        self.manager.showMenu(self.buyMenu)

    def showMoreMenu(self):
        self.manager.reset()
        self.manager.showMenu(self.moreMenu)

    def showQuitMenu(self):
        self.manager.reset()
        self.manager.showMenu(self.quitMenu)

    def escape(self):
        if self.hidden:
            # Just show the existing menu.
            self.hide()
        elif self.manager.menu == self.manager.defaultMenu:
            # Main menu is already selected. Hide it.
            self.hide()
        else:
            # Main menu is not selected. Return to it.
            self.manager.cancel()
