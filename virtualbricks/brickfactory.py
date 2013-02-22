#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
Copyright (C) 2011 Virtualbricks team

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; version 2.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""

import copy
import gobject
import os
import select
import sys
from threading import Thread, Semaphore
import time
import getpass
import __builtin__
_ = __builtin__._

from virtualbricks import tools
from virtualbricks.logger import ChildLogger
from virtualbricks.models import BricksModel, EventsModel
from virtualbricks.settings import CONFIGFILE, Settings
from virtualbricks.errors import InvalidName, UnmanagedType
from virtualbricks.tcpserver import TcpServer
from virtualbricks.switches import Switch, SwitchWrapper
from virtualbricks.virtualmachines import VM, DiskImage
from virtualbricks.tunnels import TunnelListen, TunnelConnect
from virtualbricks.tuntaps import Capture, Tap
from virtualbricks.wires import Wire, Wirefilter, PyWire, VDESUPPORT
from virtualbricks.console import Parse, CommandLineOutput
from virtualbricks.router import Router
from virtualbricks.project import VBProject
from virtualbricks.configfile import ConfigFile


class BrickFactory(ChildLogger, Thread, gobject.GObject):
    """This is the main class for the core engine.

    All the bricks are created and stored in the factory.
    It also contains a thread to manage the command console.
    """

    __gsignals__ = {
        'engine-closed': (gobject.SIGNAL_RUN_LAST, None, ()),
        'brick-error': (gobject.SIGNAL_RUN_LAST, None, (str,)),
        'brick-started': (gobject.SIGNAL_RUN_LAST, None, (str,)),
        'brick-stopped': (gobject.SIGNAL_RUN_LAST, None, (str,)),
        'brick-changed': (gobject.SIGNAL_RUN_LAST, None, (str, bool,)),
        'event-started': (gobject.SIGNAL_RUN_LAST, None, (str,)),
        'event-stopped': (gobject.SIGNAL_RUN_LAST, None, (str,)),
        'event-changed': (gobject.SIGNAL_RUN_LAST, None, (str, bool,)),
        'event-accomplished': (gobject.SIGNAL_RUN_LAST, None, (str,)),
        'backup-restored': (gobject.SIGNAL_RUN_LAST, None, (str,)),
    }

    def __init__(self, logger=None, showconsole=True, nogui=False,
                 server=False):
        gobject.GObject.__init__(self)
        ChildLogger.__init__(self, logger)
        self.nogui = nogui
        self.server = server
        # DEFINE PROJECT PARMS
        self.project_parms = self.clear_project_parms()
        self.remote_hosts = []
        self.bricks = []
        self.events = []
        self.socks = []
        self.disk_images = []
        self.projects = []
        self.bricksmodel = BricksModel()
        self.eventsmodel = EventsModel()
        self.startup = True
        self.showconsole = showconsole
        self.remotehosts_changed = False
        self.TCP = None
        Thread.__init__(self)
        self.running_condition = True
        self.settings = Settings(CONFIGFILE, self)
        self.configfile = ConfigFile(self)
        self.projectsave_sema = Semaphore()
        self.autosave_timer = tools.AutoSaveTimer(self)
        self.autosave_timer.start()
        self.backup_restore = False

        ''' Brick types
        '   dictionary 'name': class
        '   name must be lowercase here!!
        '   multiple names for one class type are allowed
        '''
        from virtualbricks import events  # cyclic imports
        self.BRICKTYPES = {
            'switch': Switch,
            'tap': Tap,
            'capture': Capture,
            'vm': VM,
            'qemu': VM,
            'wirefilter': Wirefilter,
            'tunnelc': TunnelConnect,
            'tunnel client': TunnelConnect,
            'tunnelconnect': TunnelConnect,
            'tunnell': TunnelListen,
            'tunnel server': TunnelListen,
            'tunnellisten': TunnelListen,
            'event': events.Event,
            'switchwrapper': SwitchWrapper,
            'router': Router,
        }
        if VDESUPPORT and self.settings.python:
            self.BRICKTYPES['Wire'] = PyWire
        else:
            self.BRICKTYPES['Wire'] = Wire

        '''
        '    Initialize server, ask access password if necessary
        '''
        if server:
            if os.getuid() != 0:
                print ("ERROR: -server requires to be run by root.")
                sys.exit(5)
            try:
                pwdfile = open("/etc/virtualbricks-passwd", "r")
            except:
                print "Password not set."
                while True:
                    password = getpass.getpass("Insert password:")
                    repeat = getpass.getpass("Confirm:")
                    if password == repeat:
                        try:
                            pwdfile = open('/etc/virtualbricks-passwd', 'w+')
                        except:
                            print "Could not save password."
                        else:
                            pwdfile.write(password)
                            pwdfile.close()
                            print "Password saved."
                        break
                    else:
                        print "Passwords don't match. Retry."
            else:
                password = pwdfile.readline()
                pwdfile.close()

            try:
                os.chmod('/etc/virtualbricks-passwd', 0600)
            except:
                os.unlink('/etc/virtualbricks-passwd')

            self.start_tcp_server(password)

        if not self.TCP:
            self.info("Current project is %s" %
                      self.settings.get('current_project'))
            self.configfile.restore(self.settings.get('current_project'))
        else:
            self.configfile.restore('/tmp/TCP_controlled.vb')

        self.startup = False

    def run(self):
        """Main thread start."""

        print "\nvirtualbricks> ",
        sys.stdout.flush()
        p = select.poll()
        p.register(sys.stdin, select.POLLIN)
        while self.running_condition:
            if (self.showconsole):
                if (len(p.poll(10)) > 0):
                    try:
                        command = sys.stdin.readline()
                        Parse(self, command.rstrip('\n'))
                    except Exception as e:
                        msg = ""
                        errno = ""
                        if len(e.args) == 2:
                            msg, errno = e.args
                        elif len(e.args) == 1:
                            msg = e.args[0]
                        print _("Exception:\n\tType: %s\n\tErrno: %s\n\t"
                                "Message: %s\n" % (type(e), errno, msg))
                    print "\nvirtualbricks> ",
                    sys.stdout.flush()
            else:
                time.sleep(1)
            if self.remotehosts_changed:
                for rh in self.remote_hosts:
                    if rh.connection and rh.connection.isAlive():
                        rh.connection.join(0.001)
                        if not rh.connection.isAlive():
                            rh.connected = False
                            rh.connection = None
        sys.exit(0)

    def start_tcp_server(self, password):
        self.TCP = TcpServer(self, password)
        try:
            self.TCP.start()
        except:
            print "Error starting TCP server."
            self.quit()

    def err(self, caller_obj, *args, **kargv):
        txt = ''
        for a in args:
            txt += a
        self.emit("brick-error", txt)

    """ Explicit quit was invoked. """
    def quit(self):
        for e in self.events:
            e.poweroff()
        for b in self.bricks:
            if b.proc is not None:
                b.poweroff()
        for h in self.remote_hosts:
            h.disconnect()
        if self.TCP:
            #XXX
            pass

        self.info(_('Engine: Bye!'))
        self.configfile.save(self.settings.get('current_project'))
        self.running_condition = False
        self.autosave_timer.join()
        self.emit("engine-closed")
        sys.exit(0)

    """ Clear parameters, and reset project counter """
    def clear_project_parms(self):
        DEFAULT_PARMS = {
            "id": "0",
            "name": "",
            "filename": ""
        }
        parms = {}
        for key, value in DEFAULT_PARMS.items():
            parms[key] = value

        return parms

    """ Power off and kickout all bricks and events """
    def reset_config(self):
        for b in self.bricks:
            b.poweroff()
            self.delbrick(b)
        for e in self.events:
            self.delevent(e)
        self.bricks = []
        self.events = []

    '''PROJECTS'''

    def add_project(self, id, name, filename):
        if get_project_by_filename(filename):
            if get_project_by_name(name) is None:
                proj = VBProject(id, name, filename)
                self.projects.append(proj)
                print self.projects
            else:
                raise Exception("Project name already in VB database.")
        else:
            raise Exception("Project file already in VB database.!")

    def del_project(self, id):
        pj = self.get_project_by_id(id)
        if pj is not None:
            self.projects.remove(pj)

    def get_project_by_id(self, id):
        for proj in self.projects:
            if proj.id == id:
                return proj
        return None

    def get_project_by_name(self, name):
        for proj in self.projects:
            if proj.name == name:
                return proj
        return None

    def get_project_by_file(self, filename):
        for proj in self.projects:
            if proj.filename == filename:
                return proj
        return None

    '''[[[[[[[[[]]]]]]]]]'''
    '''[   Disk Images  ]'''
    '''[[[[[[[[[]]]]]]]]]'''

    def get_image_by_name(self, name):
        """Get disk image object from the image library by its name."""

        for img in self.disk_images:
            if img.name == name:
                return img
        return None

    def get_image_by_path(self, path):
        """Get disk image object from the image library by its path."""

        for img in self.disk_images:
            if img.path == path:
                return img
        return None

    def new_disk_image(self, name, path, description="", host=None):
        """Add one disk image to the library."""

        img = DiskImage(name, path, description, host)
        self.disk_images.append(img)
        return img

    def clear_machine_vmdisks(self, machine):
        """Release lock from disk image."""

        for img in self.disk_images:
            for vmd in img.vmdisks:
                if vmd.VM == machine:
                    img.del_vmdisk(vmd)
                    self.debug("Vmdisk lock released")
                    return

    def set_configuration(self, console, *cmd):
        '''Console function to set VB's configuration parameters
        (local or remote).'''

        if isinstance(cmd, basestring) is False:
            command = cmd[0]
        else:
            command = cmd
            cmd = []
        if command == "set" and len(cmd) > 2:
            if self.settings.has_option(cmd[1]):
                host = None
                if len(cmd) == 4:
                    host = self.get_host_by_name(cmd[3])
                    if host is not None and host.connected is True:
                        host.send("cfg " + cmd[1] + " " + cmd[2])
                else:
                    self.settings.set(cmd[1], cmd[2])
        return

    def images_manager(self, console, *cmd):
        '''Console function to manage disk images.'''

        if isinstance(cmd, basestring) is False:
            command = cmd[0]
        else:
            command = cmd
            cmd = []
        host = None
        # remote = False
        if command == "list":
            if len(cmd) > 1:
                host = self.get_host_by_name(cmd[1])
            for img in self.disk_images:
                if len(cmd) == 1 and img.host is None:
                    CommandLineOutput(console, "%s,%s" % (img.name, img.path))
                if (host is not None and img.host is not None
                    and img.host.addr[0] == host.addr[0]):
                    CommandLineOutput(console, "%s,%s" % (img.name, img.path))
                else:
                    continue
        elif command == "files":
            if len(cmd) > 1:
                host = self.get_host_by_name(cmd[1])
                if host is not None and host.connected is True:
                    CommandLineOutput(console,
                                      "files not works for remote hosts.")
                    return
                    files = host.get_files_list()
                    print files
                    if files is None:
                        CommandLineOutput(console, "No files found.")
                        return
                    for f in files:
                        CommandLineOutput(console, f)
                else:
                    CommandLineOutput(console, "Not connected to %s" % cmd[1])
                return
            for image_file in os.listdir(self.settings.get("baseimages")):
                if os.path.isfile(self.settings.get("baseimages") + "/" +
                                  image_file):
                    CommandLineOutput(console, "%s" % (image_file))
        elif command == "add":
            if len(cmd) > 1 and cmd[1] is not None:
                basepath = self.settings.get("baseimages")
                host = None
                name = cmd[1].replace(".", "_")
                name = name.replace("/", "_")
                if len(cmd) == 3:
                    host = self.get_host_by_name(cmd[2])
                    if host is not None:
                        basepath = host.baseimages
                if len(cmd) == 3 and cmd[2].find("/") > -1:
                    img = self.new_disk_image(name, cmd[2])
                else:
                    img = self.new_disk_image(name, basepath + "/" + cmd[1])
                if host is not None:
                    img.host = host
                    if host.connected is True:
                        host.send("i add " + cmd[1])
                        host.expect_OK()
        elif command == "del":
            if len(cmd) > 1:
                image = self.get_image_by_name(cmd[1])
                if image is not None:
                    if len(cmd) == 3:
                        host = self.get_host_by_name(cmd[2])
                        if host.connected is False:
                            host = None
                        if host is None:
                            return
                        if host is not None and image.host != host:
                            return
                        self.disk_images.remove(image)
                        if host.connected is True:
                            host.send("i del " + cmd[1])
                            host.expect_OK()
                    if image.host is not None:
                        return
                    self.disk_images.remove(image)
        elif command == "base":
            if len(cmd) == 1 or (len(cmd) > 1 and cmd[1] == "show"):
                CommandLineOutput(console, "%s" %
                                  self.settings.get("baseimages"))
            elif cmd[1] == "set" and len(cmd) > 2:
                if len(cmd) == 4:
                    host = None
                    host = self.get_host_by_name(cmd[3])
                    if host is None:
                        return
                    host.baseimages = str(cmd[2])
                else:
                    self.settings.set("baseimages", cmd[2])
        return

    '''[[[[[[[[[]]]]]]]]]'''
    '''[ Bricks, Events ]'''
    '''[[[[[[[[[]]]]]]]]]'''

    ''' Getbyname helpers '''
    def getbrickbyname(self, name):
        for b in self.bricks:
            if b.name == name:
                return b
        return None

    def geteventbyname(self, name):
        for e in self.events:
            if e.name == name:
                return e
        return None

    def proclist(self, console):
        procs = 0
        for b in self.bricks:
            if b.proc is not None:
                procs += 1

        if procs > 0:
            CommandLineOutput(console, "PID\tType\tName")
            for b in self.bricks:
                if b.proc is not None:
                    CommandLineOutput(console, "%d\t%s\t%s" %
                                      (b.pid, b.get_type(), b.name))
        else:
            CommandLineOutput(console, "No process running")

    def get_host_by_name(self, host):
        for h in self.remote_hosts:
            if h.addr[0] == host:
                return h
        return None

    '''naming'''
    def renamebrick(self, b, newname):
        newname = tools.ValidName(newname)
        if newname is None:
            raise InvalidName("No name given!")
            return

        if not tools.NameNotInUse(self, newname):
            raise InvalidName()
            return

        b.name = newname
        #some bricks need to do some extra operations
        b.post_rename(newname)
        b.gui_changed = True

    def renameevent(self, e, newname):
        newname = tools.ValidName(newname)
        if newname is None:
            raise InvalidName()
            return

        if not tools.NameNotInUse(self, newname):
            raise InvalidName()
            return

        e.name = newname
        if e.get_type() == "Event":
            #It's a little comlicated here, if we are renaming
            #an event we have to rename it in all command of other
            #events...
            pass
        #e.gui_changed = True

    '''
     '    used to generate a potential next valid name
    '    by appending _new
    '''
    def nextValidName(self, name, toappend="_new"):
        newname = tools.ValidName(name)
        if not newname:
            return None
        while(not tools.NameNotInUse(self, newname)):
            newname += toappend
        return newname

    ''' construction functions '''
    def newbrick(self, arg1="", arg2="", arg3="", arg4="", arg5=""):
        host = ""
        remote = False
        if arg1 == "remote":
            self.debug("remote brick")
            remote = True
            ntype = arg2
            name = arg3
            host = arg4
        else:
            ntype = arg1
            name = arg2

        name = tools.ValidName(name)
        if not name:
            raise InvalidName("No name given!")

        if not tools.NameNotInUse(self, name):
            raise InvalidName()

        if ntype.lower() in self.BRICKTYPES:
            brick = self.BRICKTYPES[ntype.lower()](self, name)
        else:
            self.err(self, "Invalid console command '%s'", name)
            return None
        if remote:
            brick.set_host(host)
            if brick.homehost.connected:
                brick.homehost.send("new " + brick.get_type() + " " +
                                    brick.name)

        return brick

    def newevent(self, ntype="", name=""):
        name = tools.ValidName(name)
        if not name:
            raise InvalidName()

        if not tools.NameNotInUse(self, name):
            raise InvalidName()

        if ntype == "event" or ntype == "Event":
            from virtualbricks import events  # cyclic imports
            brick = events.Event(self, name)
            self.debug("new event %s OK", brick.name)
        else:
            self.err(self, "Invalid event command '%s'", name)
            return False

        return True

    ''' brick action dispatcher '''
    def brickAction(self, obj, cmd):
        if (cmd[0] == 'on'):
            obj.poweron()
        if (cmd[0] == 'off'):
            obj.poweroff()
        if (cmd[0] == 'remove'):
            from virtualbricks import bricks  # cyclic imports
            if obj.get_type() == 'Event':
                self.delevent(obj)
            elif isinstance(obj, bricks.Brick):
                self.delbrick(obj)
            else:
                raise UnmanagedType()
        if (cmd[0] == 'config'):
            obj.configure(cmd[1:])
        if (cmd[0] == 'show'):
            obj.cfg.dump()
        if (cmd[0] == 'connect' and len(cmd) == 2):
            if(self.connect_to(obj, cmd[1].rstrip('\n')) is not None):
                print ("Connection ok")
            else:
                print ("Connection failed")
        if (cmd[0] == 'disconnect'):
            obj.disconnect()
        if (cmd[0] == 'help'):
            obj.help()

    ''' connect bricks together '''
    def connect_to(self, brick, nick):
        endpoint = None
        if not nick:
            return None
        for n in self.socks:
            if n.nickname == nick:
                endpoint = n
        if endpoint is not None:
            return brick.connect(endpoint)
        else:
            self.debug("Endpoint %s not found." % nick)
            return None

    ''' duplication functions '''
    def dupbrick(self, bricktodup):
        name = self.nextValidName("Copy_of_" + bricktodup.name)
        ty = bricktodup.get_type()
        if (bricktodup.homehost):
            new_brick = self.newbrick("remote", ty, name,
                                      bricktodup.cfg.homehost)
        else:
            new_brick = self.newbrick(ty, name)
        # Copy only strings, and not objects, into new vm config
        for c in bricktodup.cfg:
            val = bricktodup.cfg.get(c)
            if isinstance(val, str):
                new_brick.cfg.set(c + '=' + val)

        for p in bricktodup.plugs:
            if p.sock is not None:
                new_brick.connect(p.sock)

        new_brick.on_config_changed()
        return new_brick

    def dupevent(self, eventtodup):
        newname = self.nextValidName("Copy_of_" + eventtodup.name)
        if newname is None:
            self.debug("Name error duplicating event.")
            return
        self.newevent("Event", newname)
        event = self.geteventbyname(eventtodup.name)
        newevent = self.geteventbyname(newname)
        newevent.cfg = copy.deepcopy(event.cfg)
        newevent.active = False
        newevent.on_config_changed()

    ''' delete functions '''
    def delbrick(self, bricktodel):
        # XXX check me

        if bricktodel.proc is not None:
            bricktodel.poweroff()

        for b in self.bricks:
            if b == bricktodel:
                for so in b.socks:
                    self.socks.remove(so)
                self.bricks.remove(b)
            else:  # connections to bricktodel must be deleted too
                for pl in reversed(b.plugs):
                    if pl.sock:
                        if pl.sock.nickname.startswith(bricktodel.name):
                            self.debug("Deleting plug to " + pl.sock.nickname)
                            b.plugs.remove(pl)
                            b.clear_self_socks(pl.sock.path)
                            # recreate Plug(self) of some objects
                            b.restore_self_plugs()

        self.bricksmodel.del_brick(bricktodel)

    def delremote(self, address):

        # Deferred removal: fill the list first, then call delbrick(b)
        # in sequence.

        mybricks = []
        for r in self.remote_hosts:
            if r.addr[0] == address:
                for br in self.bricks:
                    if br.homehost and br.homehost.addr[0] == address:
                        mybricks.append(br)
                for br in mybricks:
                    self.delbrick(br)
                self.remote_hosts.remove(r)
        self.remotehosts_changed = True

    def delevent(self, eventtodel):
        # XXX check me
        for e in self.events:
            if e == eventtodel:
                e.poweroff()
                self.events.remove(e)
        self.eventsmodel.del_event(eventtodel)


gobject.type_register(BrickFactory)

if __name__ == "__main__":
    """
    run tests with 'python BrickFactory.py -v'
    """
    import doctest
    doctest.testmod()
