# -*- test-case-name: virtualbricks.tests.test_console -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2013 Virtualbricks team

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
import select
import socket
import hashlib
import threading
import StringIO
import textwrap

from twisted.internet import interfaces, utils
from twisted.protocols import basic
from twisted.python import components
from zope.interface import implements

import virtualbricks
from virtualbricks import errors, _compat, settings


log = _compat.getLogger(__name__)

if False:  # pyflakes
    _ = str


class _Error(Exception):
    """Please don't use."""


class VbShellCommand(str):

    def perform(self):
        return parse(self.factory, self)


class ShellCommand(str):

    def perform(self):
        return utils.getProcessValue("sh", self, os.environ)


class RemoteHostConnectionInstance(threading.Thread):

    def __init__(self, remotehost, factory):
        self.host = remotehost
        self.factory = factory
        threading.Thread.__init__(self)

    def run(self):
        if not self.host.connected:
            return

        self.host.post_connect_init()
        p = select.poll()
        p.register(self.host.sock, select.POLLIN | select.POLLERR |
                   select.POLLHUP | select.POLLNVAL)
        while self.host.sock and self.host.connected:
            pollret = p.poll(100)
            if (len(pollret)) == 1:
                (fd, ev) = pollret[0]
                if ev != select.POLLIN:
                    self.host.disconnect()
                else:
                    event = self.host.sock.recv(200)
                    if len(event) == 0:
                        event = self.host.sock.recv(200)
                        if len(event) == 0:
                            self.host.disconnect()
                            return
                    for eventline in event.split('\n'):
                        args = eventline.rstrip('\n').split(' ')

                        if len(args) > 0 and args[0] == 'brick-started':
                            for br in iter(self.factory.bricks):
                                if br.name == args[1]:
                                    br.proc = True
                                    br.factory.emit("brick-started", br.name)
                                    br.run_condition = True
                                    br.post_poweron()

                        if len(args) > 0 and args[0] == 'brick-stopped':
                            for br in iter(self.factory.bricks):
                                if br.name == args[1]:
                                    br.proc = None
                                    br.factory.emit("brick-stopped", br.name)
                                    br.run_condition = False
                                    br.post_poweroff()

                        if len(args) > 0 and args[0] == 'udp':
                            for br in iter(self.factory.bricks):
                                if (br.name == args[1] and
                                        br.get_type() == 'Wire'
                                        and args[2] == 'remoteport'):
                                    br.set_remoteport(args[3])


class RemoteHost:

    sock = None
    connected = False
    connection = None
    password = ""
    autoconnect = False
    baseimages = "/root/VM"
    vdepath = "/usr/bin"
    qemupath = "/usr/bin"
    bricksdirectory = "/root"

    def __init__(self, factory, address):
        self.factory = factory
        self.addr = (address, 1050)
        self.lock = threading.Lock()

    def num_bricks(self):
        r = 0
        for b in iter(self.factory.bricks):
            if b.homehost and b.homehost.addr[0] == self.addr[0]:
                r += 1
        return r

    def connect(self):
        try:
            self._connect()
        except socket.error:
            log.exception(_("Error on socket"))
            return False, "Error connecting to host"
        except _Error as e:
            return False, str(e)

    def _connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect(self.addr)
        rec = self.sock.recv(5)
        self.sock.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
        if not rec.startswith('HELO'):
            raise _Error("Invalid server response")
        rec = self.sock.recv(256)
        sha = hashlib.sha256()
        sha.update(self.password)
        sha.update(rec)
        hashed = sha.digest()
        self.sock.sendall(hashed)
        p = select.poll()
        p.register(self.sock, select.POLLIN)
        pollret = p.poll(2000)
        if pollret is not None and len(pollret) != 0:
            rec = self.sock.recv(4)
            if rec.startswith("OK"):
                self.connected = True
                self.connection = RemoteHostConnectionInstance(self,
                                                               self.factory)
                self.connection.start()
                return True, "Success"
        raise _Error("Authentication Failed.")

    def disconnect(self):
        if self.connected:
            self.connected = False
            for b in iter(self.factory.bricks):
                if b.homehost and b.homehost.addr[0] == self.addr[0]:
                    b.poweroff()
            self.send("reset all")
            self.sock.close()
            self.sock = None

    def expect_OK(self):
        rec = self.recv()
        if rec is not None and rec.endswith("OK"):
            return True
        elif rec is not None and rec.endswith("FAIL"):
            return "FAIL\n"
            return False
        else:
            return "ERROR"
            return False

    def upload(self, b):
        self.lock.acquire()
        self.send_nolock("new " + b.get_type() + " " + b.name)
        self.putconfig(b)
        self.send_nolock("ACK")
        self.lock.release()

    def putconfig(self, b):
        for k, v in ((n, b.config.get(n)) for n in b.config):
            if k != 'homehost':
                # ONLY SEND TO SERVER STRING PARAMETERS,
                # OBJECT WON'T BE SENT TO SERVER AS A STRING!
                if isinstance(v, basestring) is True:
                    self.send_nolock(b.name + ' config ' + "%s=%s" % (k, v))
        for pl in b.plugs:
            if b.get_type() == 'Qemu':
                if pl.mode == 'vde':
                    self.send_nolock(b.name + " connect " + pl.sock.nickname)
                else:
                    log.info("Qemu but not VDE plug")
            elif (pl.sock is not None):
                log.info("Not a Qemu Plug")

    def post_connect_init(self):
        self.send('reset all')

        basepath = self.send_and_recv("i base show")
        if basepath and len(basepath) == 1:
            self.basepath = basepath[0]

        for img in self.factory.disk_images:
            if img.host is not None and img.host.addr[0] == self.addr[0]:
                name = img.path.split("/")
                name = name[len(name) - 1]
                self.send("i add %s %s/%s" % (img.name, self.baseimagesname))

        for b in iter(self.factory.bricks):
            if b.homehost and b.homehost.addr == self.addr:
                    self.upload(b)

        # XXX: this is a bug, for sure
        # self.send("cfg set projects " + self.factory.settings.get("projects"))

    def get_files_list(self):
        return self.send_and_recv("i files")

    def send_and_recv(self, cmd):
        self.lock.acquire()
        self.send_nolock(cmd, norecv=True)
        rec = self.recv()
        buff = ""
        while rec is not None and rec != "OK":
            buff = buff + rec
            rec = self.recv()
        self.lock.release()
        return buff

    def recv(self, size=1):
        if not self.connected:
            return ""

        if size == 1:
            p = select.poll()
            p.register(self.sock, select.POLLIN)
            buff = ""
            rec = ""
            while p.poll(100):
                buff = self.sock.recv(1)
                rec += buff
                if buff == "\n":
                    rec = rec.rstrip("\n")
                    return rec
        #old version
        else:
            ret = ""
            ret = self.sock.recv(size)
            return ret

    def empty_socket(self):
        """remove the data present on the socket"""

        while 1:
            inputready, o, e = select.select([self.sock], [], [], 0.0)
            if not inputready:
                break
            for s in inputready:
                s.recv(1)

    def send(self, cmd, norecv=False):
        self.lock.acquire()
        ret = False
        if self.connected:
            self.sock.sendall(cmd + '\n')
            if not norecv:
                if cmd != "ACK":
                    self.expect_OK()
                else:
                    self.recv()
        self.lock.release()
        return ret

    def send_nolock(self, cmd, norecv=False):
        ret = False
        if self.connected:
            self.sock.sendall(cmd + "\n")
            if not norecv:
                if cmd != "ACK":
                    self.expect_OK()
                else:
                    self.recv()
        return ret


class SocketTransportAdapter:
    implements(interfaces.ITransport)

    def __init__(self, socket):
        self.socket = socket

    def write(self, data):
        self.socket.send(data)

    def writeSequence(self, sequence):
        self.write("".join(sequence))

    loseConnection = getPeer = getHost = lambda s: None

components.registerAdapter(SocketTransportAdapter, socket.socket,
                           interfaces.ITransport)


class FileTransportAdapter:
    implements(interfaces.ITransport)

    def __init__(self, original):
        self.original = original

    def write(self, data):
        self.original.write(data)

    def writeSequence(self, sequence):
        self.original.write("".join(sequence))

    loseConnection = getPeer = getHost = lambda s: None

components.registerAdapter(FileTransportAdapter, StringIO.StringIO,
                           interfaces.ITransport)


class NullTransportAdapter:
    implements(interfaces.ITransport)

    __init__ = write = writeSequence = lambda s, d: None
    loseConnection = getPeer = getHost = lambda s: None

components.registerAdapter(NullTransportAdapter, None, interfaces.ITransport)


def parse(factory, command, console=None):
    transport = interfaces.ITransport(console)
    protocol = VBProtocol(factory)
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
            else:
                self.default(line)

    def default(self, parts):
        pass

    def connectionMade(self):
        for protocol in self.sub_protocols.itervalues():
            protocol.makeConnection(self.transport)

    def connectionLost(self, reason):
        for protocol in self.sub_protocols.itervalues():
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
        "Copyright (C) 2013 Virtualbricks team\n"
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
        intro = self.intro.format(version=virtualbricks.version.short())
        self.transport.write(intro)
        self.transport.write(self.prompt)

    def lineReceived(self, line):
        Protocol.lineReceived(self, line)
        if line != "python":  # :-(
            self.transport.write(self.prompt)

    def brick_action(self, obj, cmd):
        """brick action dispatcher"""
        # XXX: cyclic imports
        from virtualbricks import bricks

        if cmd[0] == "on":
            obj.poweron()
        elif cmd[0] == "off":
            obj.poweroff()
        elif cmd[0] == "remove":
            if obj.get_type() == "Event":
                self.delevent(obj)
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
                log.info("Connection ok")
            else:
                log.info("Connection failed")
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
        log.info("Quitting command loop")
        self.factory.quit()

    def do_help(self):
        self.sendLine(textwrap.dedent(self.__doc__))

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
            except (errors.InvalidTypeError, errors.InvalidNameError), e:
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
