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
import sys
import select
import socket
import hashlib
import threading
import logging

from virtualbricks import errors


log = logging.getLogger(__name__)


class VbShellCommand(str):
    pass


class ShellCommand(str):
    pass


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
                            for br in self.factory.bricks:
                                if br.name == args[1]:
                                    br.proc = True
                                    br.factory.emit("brick-started", br.name)
                                    #print "Started %s" % br.name
                                    br.run_condition = True
                                    br.post_poweron()

                        if len(args) > 0 and args[0] == 'brick-stopped':
                            for br in self.factory.bricks:
                                if br.name == args[1]:
                                    br.proc = None
                                    br.factory.emit("brick-stopped", br.name)
                                    #print "Stopped %s" % br.name
                                    br.run_condition = False
                                    br.post_poweroff()

                        if len(args) > 0 and args[0] == 'udp':
                            for br in self.factory.bricks:
                                if (br.name == args[1] and
                                        br.get_type() == 'Wire'
                                        and args[2] == 'remoteport'):
                                    br.set_remoteport(args[3])
                        self.remotehosts_changed = True


class RemoteHost:

    def __init__(self, factory, address):
        self.sock = None
        self.factory = factory
        self.addr = (address, 1050)
        self.connected = False
        self.connection = None
        self.password = ""
        self.factory.remotehosts_changed = True
        self.autoconnect = False
        self.baseimages = "/root/VM"
        self.vdepath = "/usr/bin"
        self.qemupath = "/usr/bin"
        self.bricksdirectory = "/root"
        self.lock = threading.Lock()

    def num_bricks(self):
        r = 0
        for b in self.factory.bricks:
            if b.homehost and b.homehost.addr[0] == self.addr[0]:
                r += 1
        return r

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.connect(self.addr)
        except:  # XXX don't catch all errors
            return False, "Error connecting to host"
        else:
            try:
                rec = self.sock.recv(5)
            except:  # XXX: don't catch all errors
                return False, "Error reading from socket"

        self.sock.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
        if not rec.startswith('HELO'):
            return False, "Invalid server response"
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
                self.factory.remotehosts_changed = True
                self.connection = RemoteHostConnectionInstance(self,
                                                               self.factory)
                self.connection.start()
                return True, "Success"
        self.factory.remotehosts_changed = True
        return False, "Authentication Failed."

    def disconnect(self):
        if self.connected:
            self.connected = False
            for b in self.factory.bricks:
                if b.homehost and b.homehost.addr[0] == self.addr[0]:
                    b.poweroff()
            self.send("reset all")
            self.sock.close()
            self.sock = None
        self.factory.remotehosts_changed = True

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
        self.factory.remotehosts_changed = True
        self.lock.release()

    def putconfig(self, b):
        for (k, v) in b.cfg.iteritems():
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
                    print "Qemu but not VDE plug"
            elif (pl.sock is not None):
                print "Not a Qemu Plug"
        self.factory.remotehosts_changed = True

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

        for b in self.factory.bricks:
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


class SocketWrapper:

    def __init__(self, socket):
        self.socket = socket

    def write(self, data):
        self.socket.send(data)


def parse(factory, command, console=sys.stdout):
    if isinstance(console, socket.socket):
        console = SocketWrapper(console)

    protocol = VBProtocol(factory, console)
    protocol.sub_protocols["images"] = ImagesProtocol(factory, console)
    protocol.sub_protocols["config"] = ConfigurationProtocol(factory, console)
    return protocol.lineReceived(command)

Parse = parse


class Protocol:

    def __init__(self, factory, sender):
        self.factory = factory
        self.sender = sender
        self.sub_protocols = {}

    def lineReceived(self, line):
        if not line:
            line = "EOF"
        parts = line.split()
        if parts:
            handler = getattr(self, "do_" + parts[0], None)
            if handler is not None:
                try:
                    handler(parts[1:])
                except TypeError, e:
                    if "argument" in str(e):  # XXX: a better check?
                        self.sendLine("invalid command %s" % line)
                except IndexError:  # args[0] where no args are given
                        self.sendLine("invalid command %s" % line)
                return True
            self.default(line)
            return False

    def sendLine(self, line):
        self.sender.write(line + "\n")

    def default(self, parts):
        pass


class VBProtocol(Protocol):

    def default(self, line):
        if not line:
            self.sendLine("Invalid console command '%s'" % line)
            return False
        line = line.strip()
        args = line.split()
        obj = self.factory.get_brick_by_name(args[0])
        if obj is None:
            obj = self.factory.get_event_by_name(args[0])
            if obj is None:
                self.sendLine("Invalid console command '%s'" % line)
                return False
        self.factory.brickAction(obj, args[1:])
        return True

    def do_quit(self, args):
        log.info("Quitting command loop")
        self.factory.quit()
        return True
    do_q = do_EOF = do_quit

    def do_help(self, args):
        self.sendLine("Base command " + "-" * 40)
        self.sendLine("ps               List of active process")
        self.sendLine("n[ew] TYPE NAME  Create a new TYPE brick with NAME")
        self.sendLine("list             List of bricks already created")
        self.sendLine("socks            List of connections available for bricks")
        self.sendLine("conn[ections]    List of connections for each bricks")
        self.sendLine("")
        self.sendLine("Brick configuration command " + "-" * 25)
        self.sendLine("BRICK_NAME show      List parameters of BRICK_NAME brick")
        self.sendLine("BRICK_NAME on        Starts BRICK_NAME")
        self.sendLine("BRICK_NAME off       Stops BRICK_NAME")
        self.sendLine("BRICK_NAME remove    Delete BRICK_NAME")
        self.sendLine("BRICK_NAME config PARM=VALUE     Configure a parameter of BRICK_NAME.")
        self.sendLine("BRICK_NAME connect NICK  Connect BRICK_NAME to a Sock")
        self.sendLine("BRICK_NAME disconnect    Disconnect BRICK_NAME to a sock")
        self.sendLine("BRICK_NAME help      Help about parameters of BRICK_NAME")
    do_h = do_help

    def do_ps(self, args):
        """List of active processes"""

        procs = len([b for b in self.factory.bricks if b.proc is not None])
        if not procs:
            self.sendLine("No process running")
            return

        self.sendLine("PID\tType\tName")
        self.sendLine("-" * 24)
        for b in self.factory.bricks:
            if b.proc is not None:
                self.sendLine("%d\t%s\t%s" % (b.pid, b.get_type(), b.name))

    def do_reset(self, args):
        if args and args[0] == "all":  # backward compatibility
            self.factory.reset_config()

    def do_new(self, args):
        """Create a new brick or event"""

        if args[0] == "event":
            self.factory.new_event(args[1])
        else:
            try:
                self.factory.newbrick(*args)
            except (errors.InvalidTypeError, errors.InvalidNameError), e:
                self.sendLine(str(e))
    do_n = do_new

    def do_list(self, args):
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

    def do_config(self, args):
        self.sub_protocols["config"].lineReceived(" ".join(args))
    do_cfg = do_config

    def do_images(self, args):
        self.sub_protocols["images"].lineReceived(" ".join(args))
    do_i = do_images

    def do_socks(self, args):
        """List of connections available for bricks"""
        for s in self.factory.socks:
            if s.brick is not None:
                self.sendLine("%s - port on %s %s - %d available" % (
                    s.nickname, s.brick.get_type(), s.brick.name,
                    s.get_free_ports()))
            else:
                self.sendLine("%s, not configured." % s.nickname)

    def do_connections(self, args):
        """List of connections for each brick"""
        for b in self.factory.bricks:
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
    do_conn = do_connections

    def do_control(self, args):
        if len(args) == 2:
            host, password = args
            remote = None
            for h in self.factory.remote_hosts:
                if h.addr == host:
                    remote = h
                    break
            else:
                remote = RemoteHost(self.factory, host)
            remote.password = password
            self.factory.remotehosts_changed = True

            if remote.connect():
                self.sendLine("Connection OK")
            else:
                self.sendLine("Connection Failed.")

    def do_udp(self, args):
        self.sendLine("udp command does not work at the moment")
        return
        # if self.factory.TCP:
        #     if len(args) != 4:
        #         self.sendLine("FAIL udp arguments")
        #     for b in self.factory.bricks:
        #         if b.name == args[2]:
        #             w = PyWire(self.factory, args[1])
        #             w.set_remoteport(args[3])
        #             w.connect(b.socks[0])
        #             w.poweron()
        #             break
        #         self.sendLine("FAIL Brick not found: %s" % args[2])

    # easter eggs
    def do_python(self, args):
        """Open a python interpreter. Use ^D (^Z on windows) to exit."""
        import code

        local = {"__name__": "__console__", "__doc__": None,
                 "factory": self.factory}
        code.interact(local=local)

    def do_threads(self, args):
        self.sendLine("Threads:")
        for i, thread in enumerate(threading.enumerate()):
            self.sendLine("  %d: %s" % (i, repr(thread)))

    def do_warranty(self):
        self.sendLine("NotImplementedError")


class ImagesProtocol(Protocol):

    def do_list(self, parts):
        host = None
        if parts:
            host = self.factory.get_host_by_name(parts[0])
        for img in self.factory.disk_images:
            if len(parts) == 1 and img.host is None:
                self.sendLine("%s,%s" % (img.name, img.path))
            if (host is not None and img.host is not None
                and img.host.addr[0] == host.addr[0]):
                self.sendLine("%s,%s" % (img.name, img.path))

    def do_files(self, parts):
        if parts:
            host = self.factory.get_host_by_name(parts[0])
            if host is not None and host.connected:
                self.sendLine("files not works for remote hosts.")
                return
                # XXX
                # files = host.get_files_list()
                # log.debug(files)
                # if files is None:
                #     self.sendLine("No files found.")
                # else:
                #     for f in files:
                #         self.sendLine(f)
            else:
                self.sendLine("Not connected to %s" % parts[0])
            return
        dirname = self.factory.settings.get("baseimages")
        for image_file in os.listdir(dirname):
            if os.path.isfile(dirname + "/" + image_file):
                self.sendLine(image_file)

    def do_add(self, parts):
        if parts:
            basepath = self.factory.settings.get("baseimages")
            host = None
            name = parts[0].replace(".", "_")
            name = name.replace("/", "_")
            if len(parts) == 2:
                host = self.factory.get_host_by_name(parts[1])
                if host is not None:
                    basepath = host.baseimages
            if len(parts) == 2 and parts[1].find("/") > -1:
                img = self.factory.new_disk_image(name, parts[1])
            else:
                img = self.factory.new_disk_image(name, basepath + "/" + parts[0])
            if host is not None:
                img.host = host
                if host.connected is True:
                    host.send("i add " + parts[1])
                    host.expect_OK()

    def do_del(self, parts):
        if parts:
            image = self.factory.get_image_by_name(parts[0])
            if image is not None:
                if len(parts) == 2:
                    host = self.factory.get_host_by_name(parts[1])
                    if host.connected is False:
                        host = None
                    if host is None:
                        return
                    if host is not None and image.host != host:
                        return
                    self.factory.remove_disk_image(image)
                    # self.disk_images.remove(image)
                    if host.connected is True:
                        host.send("i del " + parts[0])
                        host.expect_OK()
                if image.host is not None:
                    return
                self.factory.remove_disk_image(image)
                # self.disk_images.remove(image)

    def do_base(self, parts):
        if not parts or parts[0] == "show":
            self.sendLine("%s" % self.factory.settings.get("baseimages"))
        elif parts[0] == "set" and len(parts) > 1:
            if len(parts) == 3:
                host = None
                host = self.factory.get_host_by_name(parts[2])
                if host is None:
                    return
                host.baseimages = str(parts[1])
            else:
                self.factory.settings.set("baseimages", parts[1])


class ConfigurationProtocol(Protocol):

    def do_get(self, args):
        if len(args) == 1:
            if self.factory.settings.has_option(args[0]):
                self.sendLine("%s = %s" % (args[0],
                                           self.factory.settings.get(args[0])))
            else:
                self.sendLine("No such option %s" % args[0])
        # elif len(args) == 0:
        #     pass  # TODO: show all settings

    def do_set(self, args):
        if len(args) > 1:
            if self.factory.settings.has_option(args[0]):
                host = None
                if len(args) == 3:
                    host = self.factory.get_host_by_name(args[2])
                    if host is not None and host.connected is True:
                        host.send("cfg " + args[0] + " " + args[1])
                else:
                    self.factory.settings.set(args[0], args[1])
