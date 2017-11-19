from trosnoth.bots.base import Bot
from trosnoth.bots.goalsetter import GoalSetterBot, MessAroundInZone, Goal
from trosnoth.utils.event import Event


class OneZoneBot(GoalSetterBot):
    nick = 'Bothersome'
    playable = True

    class MainGoalClass(Goal):
        def reevaluate(self):
            self.setSubGoal(MessAroundInZone(self.bot, self))


    def start(self):
        super(OneZoneBot, self).start()

        self.setDodgesBullets(False)
        self.setUpgradePolicy(None)


BotClass = OneZoneBot
