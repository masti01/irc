#! /usr/bin/env python
#
# Example program using irc.bot.
#
# Joel Rosdahl <joel@rosdahl.net>

"""A simple example bot.

This is an example bot that uses the SingleServerIRCBot class from
irc.bot.  The bot enters a channel and listens for commands in
private messages and channel traffic.  Commands in channel messages
are given by prefixing the text by the bot name followed by a colon.
It also responds to DCC CHAT invitations and echos data sent in such
sessions.

The known commands are:

    stats -- Prints some channel information.

    disconnect -- Disconnect the bot.  The bot will try to reconnect
                  after 60 seconds.

    die -- Let the bot cease to exist.

    dcc -- Let the bot invite you to a DCC CHAT connection.
"""
from pytz import utc

import irc.bot
import irc.strings
from irc.client import ip_numstr_to_quad, ip_quad_to_numstr
import re
import datetime
import pywikibot
import urllib
from sqlalchemy import create_engine, text
import sqlalchemy



class TestBot(irc.bot.SingleServerIRCBot):
    def __init__(self, channel, nickname, server, port, engine):
        irc.bot.SingleServerIRCBot.__init__(self, [(server, port)], nickname, nickname, '')
        self.channel = channel
        self.engine = engine
        self.site = pywikibot.Site('pl', fam='wikipedia')
        self.lang = 'pl'
        self.apiURL = u'https://' + self.lang + u'.' + self.site.family.name + u'.org/w/api.php?action=query&meta=siteinfo&siprop=statistics&format=xml'
        # self.logname = u'ircbot/artnos' + self.lang + u'-test.log'
        self.logname = 'artnos' + self.lang + u'-test.log'
        self.re_edit = re.compile(
            r'^C14\[\[^C07(?P<page>.+?)^C14\]\]^C4 (?P<flags>.*?)^C10 ^C02(?P<url>.+?)^C ^C5\*^C ^C03(?P<user>.+?)^C ^C5\*^C \(?^B?(?P<bytes>[+-]?\d+?)^B?\) ^C10(?P<summary>.*)^C'.replace(
                '^B', '\002').replace('^C', '\003').replace('^U', '\037'))
        self.re_move = re.compile(
            r'^C14\[\[^C07(?P<page>.+?)^C14]]^C4 move^C10 ^C02^C ^C5\*^C ^C03(?P<user>.+?)^C ^C5\*^C  ^C10(?P<action>.+?) \[\[^C02(?P<frompage>.+?)^C10]] to \[\[(?P<topage>.+?)]]((?P<summary>.*))?^C'.replace(
                '^C', '\003'))

    def on_nicknameinuse(self, c, e):
        c.nick(c.get_nickname() + "_")

    def on_welcome(self, c, e):
        c.join(self.channel)

    def on_privmsg(self, c, e):
        self.do_command(e, e.arguments[0])

    def on_pubmsg(self, c, e):
        """
        a = e.arguments[0].split(":", 1)
        if len(a) > 1 and irc.strings.lower(a[0]) == irc.strings.lower(
            self.connection.get_nickname()
        ):
            self.do_command(e, a[1].strip())
        """
        match = self.re_edit.match(e.arguments[0])
        matchmove = self.re_move.match(e.arguments[0])

        if matchmove:
            mvpagefrom = matchmove.group('frompage')
            mvpageto = matchmove.group('topage')
            mvaction = matchmove.group('action')
            if matchmove.group('summary'):
                mvsummary = matchmove.group('summary')
            else:
                mvsummary = ''
            mvuser = matchmove.group('user')
            currtime = datetime.datetime.now(utc).strftime("%Y-%m-%d %H:%M:%S")

            pywikibot.output(u'MOVE->F:%s:T:%s:AT:%s:S:%s:SU:%s:T:%s' % (
                mvpagefrom, mvpageto, mvaction, mvuser, mvsummary, currtime))

            frompage = pywikibot.Page(self.site, mvpagefrom)
            topage = pywikibot.Page(self.site, mvpageto)

            if topage.namespace() in [0] and frompage.namespace not in [0]:

                req = urllib.request.Request(self.apiURL)
                with urllib.request.urlopen(req) as response:
                    text = str(response.read())
                artsR = re.compile(r'articles="(?P<arts>.*?)"')
                match = artsR.search(text)
                arts = match.group('arts')

                ctime = datetime.datetime.strftime(topage.oldest_revision[
                                                       'timestamp'],
                                                   "%Y-%m-%d %H:%M:%S")

                self.logline(self.lang, arts, currtime, ctime, mvpageto, 'M')

        elif match:
            mpage = match.group('page')
            mflags = match.group('flags')
            murl = match.group('url')
            muser = match.group('user')
            mbytes = match.group('bytes')
            msummary = match.group('summary')
            currtime = datetime.datetime.now(utc).strftime("%Y-%m-%d %H:%M:%S")
            page = pywikibot.Page(self.site, mpage)
            newArt = 'N' in mflags

            ctime = datetime.datetime.strftime(page.oldest_revision[
                                                   'timestamp'],
                                               "%Y-%m-%d %H:%M:%S")

            if newArt and (page.namespace() in [0]):
            # if (page.namespace() in [0]):
                req = urllib.request.Request(self.apiURL)
                with urllib.request.urlopen(req) as response:
                    text = str(response.read())

                artsR = re.compile(r'articles="(?P<arts>.*?)"')
                match = artsR.search(text)
                arts = match.group('arts')

                pywikibot.output(
                    'P:[[%s]]:F:[%s]:U:[[user:%s]]:B:%s:S:%s:URL:[%s] :T:%s: NS:%i I:%s' % (
                    mpage, ','.join(mflags), muser, mbytes, msummary, murl, currtime,
                    page.namespace(), ctime))

                pywikibot.output(u'Liczba artykułów:%i' % int(arts))

                self.logline(self.lang, arts, currtime, ctime, mpage, 'A')

            else:
                pywikibot.output(u'Skipping:%s' % page.title())
        else:
            return

        return

    def logline(self, lang, arts, currtime, ctime, mpage, action):
        logfile = open(self.logname, "a")
        logline = f'{arts};{currtime};{ctime};{action};{mpage}\n'
        logfile.write(logline)
        logfile.close()

        # artnum int, event timestamp, creation timestamp, type char, title varchar
        with self.engine.connect() as conn:
            conn.execute(
            text("INSERT INTO history (lang, artnum, event, creation, type, title) "
                "VALUES (:lang, :artnum, :event, :creation, :type, :title)"),
                {"lang": lang,
                 "artnum": arts,
                 "event": currtime,
                 "creation": ctime,
                 "type": action,
                 "title": mpage
                }
            )


    def on_dccmsg(self, c, e):
        # non-chat DCC messages are raw bytes; decode as text
        text = e.arguments[0].decode('utf-8')
        c.privmsg("You said: " + text)

    def on_dccchat(self, c, e):
        if len(e.arguments) != 2:
            return
        args = e.arguments[1].split()
        if len(args) == 4:
            try:
                address = ip_numstr_to_quad(args[2])
                port = int(args[3])
            except ValueError:
                return
            self.dcc_connect(address, port)

    def do_command(self, e, cmd):
        nick = e.source.nick
        c = self.connection

        if cmd == "disconnect":
            self.disconnect()
        elif cmd == "die":
            self.die()
        elif cmd == "stats":
            for chname, chobj in self.channels.items():
                c.notice(nick, "--- Channel statistics ---")
                c.notice(nick, "Channel: " + chname)
                users = sorted(chobj.users())
                c.notice(nick, "Users: " + ", ".join(users))
                opers = sorted(chobj.opers())
                c.notice(nick, "Opers: " + ", ".join(opers))
                voiced = sorted(chobj.voiced())
                c.notice(nick, "Voiced: " + ", ".join(voiced))
        elif cmd == "dcc":
            dcc = self.dcc_listen()
            c.ctcp(
                "DCC",
                nick,
                "CHAT chat %s %d"
                % (ip_quad_to_numstr(dcc.localaddress), dcc.localport),
            )
        else:
            c.notice(nick, "Not understood: " + cmd)


def main():
    import sys

    if len(sys.argv) != 4:
        print("Usage: testbot <server[:port]> <channel> <nickname>")
        sys.exit(1)

    s = sys.argv[1].split(":", 1)
    server = s[0]
    if len(s) == 2:
        try:
            port = int(s[1])
        except ValueError:
            print("Error: Erroneous port.")
            sys.exit(1)
    else:
        port = 6667
    channel = sys.argv[2]
    nickname = sys.argv[3]

    # engine = create_engine("mariadb://articles:Articles999@192.168.1.250/articles", echo=True)
    engine = create_engine("mariadb://articles:Articles999@172.17.02.2/articles",
                           echo=True)
    print(engine)
    with engine.connect() as conn:
        try:
            conn.execute(text("CREATE TABLE history ("
                              "lang char(10), "
                              "artnum int, "
                              "event timestamp, "
                              "creation timestamp, "
                              "type char, "
                              "title varchar(3000)"
                              ");"))
        except sqlalchemy.exc.OperationalError as e:
            print(e)



    bot = TestBot(channel, nickname, server, port, engine)
    bot.start()


if __name__ == "__main__":
    main()
