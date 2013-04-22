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

import sys
import hashlib
import socket
import select
from threading import Thread

from virtualbricks.logger import ChildLogger
from virtualbricks.tcpproto import VirtualbricksTCPPROTO
from virtualbricks.wires import PyWire
from virtualbricks.console import Parse


class TcpServer(ChildLogger(__name__), Thread):
    def __init__(self, factory, password, port=1050):
        self.port = port
        self.factory = factory
        self.listening = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.proto = VirtualbricksTCPPROTO()
        self.password = password
        Thread.__init__(self)
        self.factory.connect("brick-stopped", self.cb_brick_stopped)
        self.factory.connect("brick-started", self.cb_brick_started)
        self.sock = None

    def cb_brick_started(self, model, name=""):
        if (self.sock):
            self.sock.sendall("brick-started " + name + '\n')

    def cb_brick_stopped(self, model, name=""):
        if (self.sock):
            self.sock.sendall("brick-stopped " + name + '\n')

    def run(self):
        self.info("TCP server started.")
        try:
            self.listening.bind(("0.0.0.0", self.port))
            self.listening.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR,
                                      1)
            self.listening.listen(1)
        except Exception as e:
            print "socket error (1): " + str(e)
            self.factory.quit()
            sys.exit(1)

        finally:
            while(self.factory.running_condition):
                p = select.poll()
                p.register(self.listening, select.POLLIN)
                if len(p.poll(100)) > 0:
                        try:
                            (sock, addr) = self.listening.accept()

                        except Exception as e:
                            print "socket error (2): " + str(e)
                            self.factory.quit()
                            sys.exit(1)
                        self.info("Connection from %s" % str(addr))
                        self.sock = sock
                        self.sock.setsockopt(socket.SOL_TCP,
                                             socket.TCP_NODELAY, 1)
                        randfile = open("/dev/urandom", "r")
                        challenge = randfile.read(256)
                        sha = hashlib.sha256()
                        sha.update(self.password)
                        sha.update(challenge)
                        hashed = sha.digest()
                        sock.sendall(self.proto.HELO())
                        sock.sendall(challenge)
                        p_cha = select.poll()
                        p_cha.register(sock, select.POLLIN)
                        if len(p_cha.poll(100)) > 0:
                            rec = sock.recv(len(hashed))
                            if rec == hashed:
                                self.info("%s: Client authenticated.",
                                          str(addr))
                                sock.sendall("OK\n")
                                self.master_address = addr
                                self.serve_connection(sock)
                            else:
                                self.info("%s: Authentication failed. " %
                                          str(addr))
                                sock.sendall("FAIL\n")
                        else:
                            self.info("%s: Challenge timeout", str(addr))

                        sock.close()
                        self.sock = None
                        self.info("Connection from %s closed.", str(addr))
            self.listening.close()

    def remote_wire_request(self, req):
        if (len(req) == 0):
            return False
        args = req.rstrip('\n').split(' ')
        if len(args) != 4 or args[0] != 'udp':
            print "Len args: %d" % len(args)
            print "Args[0]=%s" % args[0]
            return False
        for b in self.factory.bricks:
            if b.name == args[2]:
                w = PyWire(self.factory, args[1])
                w.set_remoteport(args[3])
                w.connect(b)
                w.poweron()
                return True
        print "Brick not found: " + args[2]
        return False

    def recv(self, sock):
        p = select.poll()
        p.register(sock, select.POLLIN)
        buff = ""
        rec = ""
        while (p.poll(100)):
            if not self.factory.running_condition:
                return
            try:
                sock.setblocking(0)
                buff = sock.recv(1)
                sock.setblocking(1)
            except:
                return
            rec = rec + buff
            if buff == "\n":
                rec = rec.rstrip("\n")
                return rec

    def serve_connection(self, sock):
        while(self.factory.running_condition):
            rec = self.recv(sock)
            if rec is not None and rec.rstrip("\n") == "ACK":
                print "ACK"
                try:
                    sock.sendall("ACKOK\n")
                    continue
                except:
                    print "Send Error"
                    return
            if rec is not None and Parse(self.factory, rec.rstrip('\n'),
                                         console=sock):
                print "RECV: " + rec
                try:
                    sock.sendall("OK\n")
                except:
                    print "Send error"
                    return
            else:
                try:
                    sock.sendall("FAIL\n")
                except:
                    print "Send error"
                    return

        for b in self.factory.bricks:
            if b.proc is not None:
                pz = b.proc.poll()
                if pz is not None:
                    b.poweroff()
