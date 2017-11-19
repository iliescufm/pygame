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

'''
xmpp.py - an XMPP client that can be used to broadcast messages to all its
contacts.

>>> xmppclient = NotificationClient('username@gmail.com', 'password')
>>> xmppclient.startService()
>>> reactor.callLater(3, xmppclient.broadcast, 'Why hello there!')

>>> reactor.run()
'''
import logging

from twisted.words.xish import domish
from wokkel.xmppim import (MessageProtocol, AvailablePresence,
        RosterClientProtocol, PresenceClientProtocol)
from twisted.words.protocols.jabber.jid import internJID
from wokkel.client import XMPPClient
from twisted.internet import reactor

log = logging.getLogger('xmpp')

class NotificationClient(XMPPClient):
    def __init__(self, jidString, password, host=None, port=5222):
        XMPPClient.__init__(self, internJID(jidString), password, host=host,
                port=port)
        self.logTraffic = False

        self.messagebot = MessageBot()
        self.messagebot.setHandlerParent(self)

        self.rosterManager = RosterManager()
        self.rosterManager.setHandlerParent(self)

    @property
    def onlineContacts(self):
        return self.rosterManager.onlineContacts

    def broadcast(self, message):
        for contact in self.onlineContacts:
            try:
                self.sendChat(contact.userhostJID(), message)
            except:
                log.error('Error sending message', exc_info=True)

    def sendChat(self, user, body):
        log.debug('Sending message %r', body)
        msg = domish.Element((None, 'message'))
        msg['to'] = user.full()
        msg['from'] = self.jid.full()
        msg['type'] = 'chat'
        msg.addElement('body', content=body)
        self.send(msg)

    def getNickname(self, jid):
        result = self.rosterManager.nicknames.get(jid.userhostJID())
        if not result:
            result = jid.userhost()
        return result


class RosterManager(RosterClientProtocol, PresenceClientProtocol):
    welcomeMessage = ('Welcome. I will send you notifications of events on '
        'play.trosnoth.org. If you send me messages, I will pass them on '
        'to everyone who is chatting with me. Your email may become visible '
        ' if you do this.')

    onlineContacts = None
    nicknames = None

    maxDelay = 300
    initialDelay = 1.0
    factor = 1.618

    delay = initialDelay
    retries = 0

    def connectionInitialized(self):
        RosterClientProtocol.connectionInitialized(self)
        PresenceClientProtocol.connectionInitialized(self)
        self.attemptGetRoster()

    def attemptGetRoster(self):
        self.getRoster().addCallback(self.gotRoster).addErrback(self.errRoster)

    def gotRoster(self, roster):
        log.debug('got roster')
        self.onlineContacts = set()
        self.nicknames = {}
        for name, item in roster.iteritems():
            jid = item.jid.userhostJID()
            self.nicknames[jid] = item.name or name

            if item.ask:
                self.approveSubscription(item.jid)
            if not item.subscriptionTo:
                self.subscribe(jid)

    def approveSubscription(self, jid):
        self.subscribed(jid)
        self.parent.sendChat(jid, self.welcomeMessage)

    def errRoster(self, reason):
        log.error('Error getting roster:')
        reason.printBriefTraceback()
        self.retry()

    def retry(self):
        self.retries += 1
        self.delay = min(self.delay * self.factor, self.maxDelay)
        reactor.callLater(self.delay, self.attemptGetRoster)

    def onRosterSet(self, item):
        log.debug('roster set: %r', item.jid.userhost())
        self.nicknames[item.jid.userhostJID()] = item.name

    def onRosterRemove(self, entity):
        log.debug('roster remove: %r', entity.userhost())
        if self.onlineContacts is not None:
            self.onlineContacts.discard(entity.userhostJID())

    def subscribeReceived(self, sender):
        '''
        Someone has tried to subscribe to our presence. Approve and subscribe to
        their presence.
        '''
        self.approveSubscription(sender)
        self.subscribe(sender.userhostJID())

    def availableReceived(self, sender, show=None, statuses=None, priority=0):
        '''
        One of our followers has come online.
        '''
        log.debug('online: %r', sender.userhost())
        self.onlineContacts.add(sender.userhostJID())

    def unavailableReceived(self, sender, statuses=None):
        '''
        One of our followers is no longer online.
        '''
        log.debug('offline: %r', sender.userhost())
        self.onlineContacts.discard(sender.userhostJID())

class MessageBot(MessageProtocol):
    def connectionMade(self):
        log.debug('Connected!')

        # send initial presence
        self.send(AvailablePresence())

    def connectionLost(self, reason):
        log.debug('Disconnected!')

    def onMessage(self, msg):
        if msg['type'] == 'chat' and hasattr(msg, 'body'):
            sender = internJID(msg['from'])
            body = msg.body
            self.onChatMessage(sender, body)

    def onChatMessage(self, sender, body):
        sender = sender.userhostJID()
        contents = '%s: %s' % (self.parent.getNickname(sender), body)
        for jid in self.parent.onlineContacts:
            jid = jid.userhostJID()
            if jid != sender:
                self.parent.sendChat(jid, contents)

