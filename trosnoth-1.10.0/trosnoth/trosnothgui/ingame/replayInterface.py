from trosnoth.gui.framework import framework
import pygame


class ViewControlInterface(framework.Element):
    '''Interface for controlling the replay view.'''

    # The virtual keys we care about.
    state_vkeys = frozenset(['left', 'right', 'jump', 'down'])

    def __init__(self, app, gameInterface):
        super(ViewControlInterface, self).__init__(app)

        world = gameInterface.world
        self.gameInterface = gameInterface
        self.keyMapping = gameInterface.keyMapping

        self.world = world
        self._state = dict([(k, False) for k in self.state_vkeys])

        self.vx = 0
        self.vy = 0

    def updateState(self, state, enabled):
        self._state[state] = enabled
        if self._state['left'] and not self._state['right']:
            self.vx = -1000
        elif self._state['right'] and not self._state['left']:
            self.vx = 1000
        else:
            self.vx = 0

        if self._state['jump'] and not self._state['down']:
            self.vy = -1000
        elif self._state['down'] and not self._state['jump']:
            self.vy = 1000
        else:
            self.vy = 0

    def tick(self, deltaT):
        if self.vx != 0 or self.vy != 0:
            x, y = self.gameInterface.gameViewer.viewManager.getTargetPoint()
            x += self.vx * deltaT
            y += self.vy * deltaT
            self.gameInterface.gameViewer.setTarget((x, y))

    def processEvent(self, event):
        '''
        Event processing works in the following way:
        1. If there is a prompt on screen, the prompt will either use the
        event, or pass it on.
        2. If passed on, the event will be sent back to the main class, for it
        to process whether player movement uses this event. If it doesn't use
        the event, it will pass it back.
        3. If so, the hotkey manager will see if the event means anything to
        it. If not, that's the end, the event is ignored.
        '''

        # Handle events specific to in-game.
        if event.type == pygame.KEYDOWN:
            try:
                stateKey = self.keyMapping[event.key]
            except KeyError:
                return event

            if stateKey not in self.state_vkeys:
                return event

            self.updateState(stateKey, True)
        elif event.type == pygame.KEYUP:
            try:
                stateKey = self.keyMapping[event.key]
            except KeyError:
                return event

            if stateKey not in self.state_vkeys:
                return event

            self.updateState(stateKey, False)
        else:
            return event
