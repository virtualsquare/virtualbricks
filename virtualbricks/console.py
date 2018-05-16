# -*- test-case-name: virtualbricks.tests.test_console -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2018 Virtualbricks team

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import os
import textwrap

from twisted.internet import interfaces, utils
from twisted.protocols import basic
from zope.interface import implementer
from virtualbricks import __version__, bricks, errors, log, settings
import six

logger = log.Logger()
socket_error = log.Event("Error on socket")
qemu_not_vde = log.Event("Qemu but not VDE plug")
invalid_brick = log.Event("Not a Qemu Plug")
conn_ok = log.Event("Connection ok")
conn_failed = log.Event("Connection failed")
quit_loop = log.Event("Quitting command loop")

if False:  # pyflakes
    _ = str


class _Error(Exception):
    """Please don't use."""


class String(str):

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return str.__eq__(self, other)

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return str.__hash__(self)


class VbShellCommand(String):

    def perform(self, factory):
        parse(factory, self)


class ShellCommand(String):

    def perform(self, factory):
        return utils.getProcessValue("sh", ("-c", self), os.environ)


@implementer(interfaces.ITransport)
class NullTransportAdapter:

    write = writeSequence = lambda s, d: None
    __init__ = loseConnection = getPeer = getHost = lambda s: None


def parse(factory, command, console=None):
    protocol = VBProtocol(factory)
    transport = interfaces.ITransport(console, NullTransportAdapter())
    protocol.makeConnection(transport)
    protocol.lineReceived(command)


class Protocol(basic.LineOnlyReceiver):

    def __init__(self, factory):
        self.factory = factory
        self.sub_protocols = {}

    def lineReceived(self, line):
        parts = line.split()
        if parts:
            handler = getattr(self, "do_" + parts[0], None)
            if handler is not None:
                try:
                    handler(*parts[1:])
                except TypeError:
                    self.sendLine("invalid number of arguments")
                except Exception as e:
                    self.sendLine(str(e))
            else:
                self.default(line)

    def default(self, line):
        pass

    def connectionMade(self):
        for protocol in six.itervalues(self.sub_protocols):
            protocol.makeConnection(self.transport)
        

    def connectionLost(self, reason):
        for protocol in six.itervalues(self.sub_protocols):
            protocol.connectionLost(reason)


class VBProtocol(Protocol):
    """\
    Base commands -----------------------------------------------------
    h[elp]                  print this help
    ps                      List of active process
    n[ew] TYPE NAME         Create a new TYPE brick with NAME
    list                    List of bricks already created
    socks                   List of connections available for bricks
    conn[ections]           List of connections for each bricks
    reset                   Remove all the bricks and events
    quit                    Stop virtualbricks
    event *args             TODO
    brick *args             TODO

    Brick configuration command ---------------------------------------
    BRICK_NAME show         List parameters of BRICK_NAME brick
    BRICK_NAME on           Starts BRICK_NAME
    BRICK_NAME off          Stops BRICK_NAME
    BRICK_NAME remove       Delete BRICK_NAME
    BRICK_NAME config PARM=VALUE    Configure a parameter of BRICK_NAME
    BRICK_NAME connect NICK Connect BRICK_NAME to a Sock
    BRICK_NAME disconnect   Disconnect BRICK_NAME to a sock
    BRICK_NAME help         Help about parameters of BRICK_NAME
    """

    # _is_first = False
    delimiter = "\n"
    prompt = "virtualbricks> "
    intro = ("Virtualbricks, version {version}\n"
        "Copyright (C) 2018 Virtualbricks team\n"
        "This is free software; see the source code for copying conditions.\n"
        "There is ABSOLUTELY NO WARRANTY; not even for MERCHANTABILITY or\n"
        "FITNESS FOR A PARTICULAR PURPOSE.  For details, type `warranty'.\n\n")

    def __init__(self, factory):
        Protocol.__init__(self, factory)
        imgp = ImagesProtocol(factory)
        self.sub_protocols["images"] = imgp
        cfgp = ConfigurationProtocol(factory)
        self.sub_protocols["config"] = cfgp

    def connectionMade(self):
        Protocol.connectionMade(self)
        # if not self._is_first:
        #     self._is_first = True
        #     intro = self.intro.format(version=virtualbricks.version.short())
        #     self.transport.write(intro)
        intro = self.intro.format(version=__version__)
        self.transport.write(intro)
        self.transport.write(self.prompt)

    def lineReceived(self, line):
        Protocol.lineReceived(self, line)
        if line != "python":  # :-(
            self.transport.write(self.prompt)

    def brick_action(self, obj, cmd):
        """brick action dispatcher"""

        if cmd[0] == "on":
            obj.poweron()
        elif cmd[0] == "off":
            obj.poweroff()
        elif cmd[0] == "remove":
            if obj.get_type() == "Event":
                self.factory.del_event(obj)
            elif isinstance(obj, bricks.Brick):
                self.factory.del_brick(obj)
            else:
                raise errors.UnmanagedTypeError("Unknown type %s",
                                                obj.__class__.__name__)
        elif cmd[0] == "config":
            obj.configure(cmd[1:])
        elif cmd[0] == "show":
            obj.config.dump(self.sendLine)
        elif cmd[0] == "connect" and len(cmd) == 2:
            if self.connect_to(obj, cmd[1].rstrip("\n")) is not None:
                logger.info(conn_ok)
            else:
                logger.info(conn_failed)
        elif cmd[0] == "disconnect":
            obj.disconnect()

    def default(self, line):
        # line = line.strip()
        args = line.split()
        obj = self.factory.get_brick_by_name(args[0])
        if obj is None:
            obj = self.factory.get_event_by_name(args[0])
            if obj is None:
                self.sendLine("Invalid console command '%s'" % line)
                return
        self.brick_action(obj, args[1:])

    def do_quit(self):
        self.factory.quit()
        logger.info(quit_loop)

    def do_help(self):
        line = textwrap.dedent(self.__doc__)
        self.sendLine(line)

    def do_event(self, name, *args):
        event = self.factory.get_event_by_name(name)
        if event is not None:
            self.brick_action(event, *args)
        else:
            self.sendLine("No such event '%s'" % name)

    def do_brick(self, name, *args):
        brick = self.factory.get_brick_by_name(name)
        if brick is not None:
            self.brick_action(brick, *args)
        else:
            self.sendLine("No such event '%s'" % name)

    def do_ps(self):
        """List of active processes"""

        procs = [b for b in self.factory.bricks if b.proc]
        if not procs:
            self.sendLine("No process running")
        else:
            self.sendLine("PID\tType\tName")
            self.sendLine("-" * 24)
            for b in procs:
                self.sendLine("%d\t%s\t%s" % (b.pid, b.get_type(), b.name))

    def do_reset(self):
        self.factory.reset()

    def do_new(self, typ, name):
        """Create a new brick or event"""

        if typ == "event":
            self.factory.new_event(name)
        else:
            try:
                self.factory.new_brick(typ, name)
            except (errors.InvalidTypeError, errors.InvalidNameError) as e:
                self.sendLine(str(e))

    def do_list(self):
        """List of bricks already created"""
        self.sendLine("Bricks")
        self.sendLine("-" * 20)
        for obj in self.factory.bricks:
            self.sendLine("%s (%s)" % (obj.name, obj.get_type()))
        self.sendLine("\nEvents")
        self.sendLine("-" * 20)
        for obj in self.factory.events:
            self.sendLine("%s (%s)" % (obj.name, obj.get_type()))
        # self.sendLine("End of list.")

    def do_config(self, *args):
        self.sub_protocols["config"].lineReceived(" ".join(args))

    def do_images(self, *args):
        self.sub_protocols["images"].lineReceived(" ".join(args))

    def do_socks(self):
        """List of connections available for bricks"""
        # XXX: if brick is not a switch this raise an exception
        for s in self.factory.socks:
            if s.brick is not None:
                self.sendLine("%s - port on %s %s - %d available" % (
                    s.nickname, s.brick.get_type(), s.brick.name,
                    s.get_free_ports()))
            else:
                self.sendLine("%s, not configured." % s.nickname)

    def do_connections(self):
        """List of connections for each brick"""
        for b in iter(self.factory.bricks):
            self.sendLine("Connections from %s brick:" % b.name)
            for sk in b.socks:
                if b.get_type() == "Qemu":
                    s = "\tsock connected to %s with an %s (%s) card"
                    self.sendLine(s % (sk.nickname, sk.model, sk.mac))
            for pl in b.plugs:
                if b.get_type() == "Qemu":
                    if pl.mode == "vde":
                        s = "\tlink connected to %s with a %s (%s) card"
                        self.sendLine(s % (pl.sock.nickname, pl.model,
                                               pl.mac))
                    else:
                        s = "\tuserlink connected with a %s (%s) card"
                        self.sendLine(s % (pl.model, pl.mac))
                elif (pl.sock is not None):
                    self.sendLine("\tlink: %s " % pl.sock.nickname)

    # easter eggs
    def do_warranty(self):
        self.sendLine("NotImplementedError")

    do_q = do_quit
    do_h = do_help
    do_n = do_new
    do_cfg = do_config
    do_i = do_images
    do_conn = do_connections


class ImagesProtocol(Protocol):

    def do_list(self):
        for img in self.factory.disk_images:
            self.sendLine("%s, %s" % (img.name, img.path))

    # def do_files(self):
    #     dirname = settings.get("baseimages")
    #     for image_file in os.listdir(dirname):
    #         if os.path.isfile(dirname + "/" + image_file):
    #             self.sendLine(image_file)

    # def do_add(self, name):
    #     basepath = settings.get("baseimages")
    #     name = name.replace(".", "_")
    #     name = name.replace("/", "_")
    #     self.factory.new_disk_image(name, basepath + "/" + name)

    # def do_del(self, name):
    #     image = self.factory.get_image_by_name(name)
    #     if image is not None:
    #         self.factory.remove_disk_image(image)

    # def do_base(self, cmd="", base=""):
    #     if not cmd or cmd == "show":
    #         self.sendLine(settings.get("baseimages"))
    #     elif cmd == "set" and base:
    #         settings.set("baseimages", base)


class ConfigurationProtocol(Protocol):

    def do_get(self, name):
        # if name:
            if settings.has_option(name):
                self.sendLine("%s = %s" % (name, settings.get(name)))
            else:
                self.sendLine("No such option %s" % name)
        # elif len(args) == 0:
        #     pass  # TODO: show all settings

    def do_set(self, name, value):
        if settings.has_option(name):
            settings.set(name, value)
        else:
            self.sendLine("No such option %s" % name)
