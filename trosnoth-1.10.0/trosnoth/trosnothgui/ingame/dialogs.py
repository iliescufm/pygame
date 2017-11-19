from trosnoth.gui.framework.dialogbox import (
    DialogBox, DialogResult, DialogBoxAttachedPoint,
)
from trosnoth.gui.common import ScaledSize, Area, ScaledLocation, Location
from trosnoth.gui.framework import elements, prompt


SpectateResult = object()


class JoinGameDialog(DialogBox):
    def __init__(self, app, controller, world):
        super(JoinGameDialog, self).__init__(
            app, ScaledSize(512, 314), 'Join Game')
        self.result = None
        self.controller = controller
        self.selectedTeam = None

        fonts = self.app.screenManager.fonts
        self.nickBox = prompt.InputBox(
            self.app,
            Area(
                DialogBoxAttachedPoint(self, ScaledSize(0, 40), 'midtop'),
                ScaledSize(200, 60), 'midtop'),
            '',
            font=fonts.menuFont,
            maxLength=30,
        )
        self.nickBox.onClick.addListener(self.setFocus)
        self.nickBox.onTab.addListener(lambda sender: self.clearFocus())
        name = app.identitySettings.nick
        if name is not None:
            self.nickBox.setValue(name)

        colours = app.theme.colours
        self.cantJoinYet = elements.TextElement(
            self.app,
            '',
            fonts.ingameMenuFont,
            ScaledLocation(256, 115, 'center'),
            colours.cannotJoinColour,
        )

        teamA = world.teams[0]
        teamB = world.teams[1]

        self.elements = [
            elements.TextElement(
                self.app,
                'Please enter your nick:',
                fonts.smallMenuFont,
                Location(
                    DialogBoxAttachedPoint(self, ScaledSize(0, 10), 'midtop'),
                    'midtop'),
                colours.black,
            ),
            self.nickBox,
            self.cantJoinYet,
            elements.TextElement(
                self.app,
                'Select team:',
                fonts.smallMenuFont,
                Location(
                    DialogBoxAttachedPoint(self, ScaledSize(0, 130), 'midtop'),
                    'midtop'),
                colours.black,
            ),

            elements.TextButton(
                self.app,
                Location(
                    DialogBoxAttachedPoint(
                        self, ScaledSize(-25, 160), 'midtop'),
                    'topright'),
                str(teamA),
                fonts.menuFont,
                colours.team1msg,
                colours.white,
                onClick=lambda obj: self.joinTeam(teamA)
            ),
            elements.TextButton(
                self.app,
                Location(
                    DialogBoxAttachedPoint(
                        self, ScaledSize(25, 160), 'midtop'),
                    'topleft'),
                str(teamB),
                fonts.menuFont,
                colours.team2msg,
                colours.white,
                onClick=lambda obj: self.joinTeam(teamB)
            ),
            elements.TextButton(
                self.app,
                Location(
                    DialogBoxAttachedPoint(
                        self, ScaledSize(-25, 210), 'midtop'),
                    'topright'),
                'Automatic',
                fonts.menuFont,
                colours.inGameButtonColour,
                colours.white,
                onClick=lambda obj: self.joinTeam()
            ),
            elements.TextButton(
                self.app,
                Location(
                    DialogBoxAttachedPoint(
                        self, ScaledSize(25, 210), 'midtop'),
                    'topleft'),
                'Spectator',
                fonts.menuFont,
                colours.inGameButtonColour,
                colours.white,
                onClick=lambda obj: self.spectate()
            ),

            elements.TextButton(
                self.app,
                Location(
                    DialogBoxAttachedPoint(
                        self, ScaledSize(0, -10), 'midbottom'),
                    'midbottom'),
                'Cancel',
                fonts.menuFont,
                colours.inGameButtonColour,
                colours.white,
                onClick=self.cancel
            )
        ]
        self.setColours(
            colours.joinGameBorderColour,
            colours.joinGameTitleColour,
            colours.joinGameBackgroundColour)
        self.setFocus(self.nickBox)

    def joinTeam(self, team=None):
        self.selectedTeam = team
        self.cantJoinYet.setText('')

        nick = self.nickBox.value
        if nick == '' or nick.isspace():
            # Disallow all-whitespace nicks
            return

        self.result = DialogResult.OK
        self.close()

    def spectate(self):
        self.selectedTeam = None
        self.cantJoinYet.setText('')

        self.result = SpectateResult
        self.close()

    def cancel(self, sender):
        self.result = DialogResult.Cancel
        self.close()


class JoiningDialog(DialogBox):
    def __init__(self, app, controller):
        super(JoiningDialog, self).__init__(
            app, ScaledSize(530, 180), 'Trosnoth')
        colours = app.theme.colours
        self.controller = controller

        fonts = self.app.screenManager.fonts
        self.text = elements.TextElement(
            self.app,
            '',
            fonts.menuFont,
            Location(
                DialogBoxAttachedPoint(self, ScaledSize(0, 40), 'midtop'),
                'midtop'),
            colour=colours.joiningColour,
        )

        self.elements = [
            self.text,
            elements.TextButton(
                self.app,
                Location(
                    DialogBoxAttachedPoint(
                        self, ScaledSize(0, -10), 'midbottom'),
                    'midbottom'),
                'Cancel',
                fonts.menuFont,
                colours.inGameButtonColour,
                colours.white,
                onClick=controller.cancelJoin,
            ),
        ]
        self.setColours(
            colours.joinGameBorderColour,
            colours.joinGameTitleColour,
            colours.joinGameBackgroundColour)

    def show(self, nick):
        self.text.setText('Joining as %s...' % (nick,))
        DialogBox.show(self)
