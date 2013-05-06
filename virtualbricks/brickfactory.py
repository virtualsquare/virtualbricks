# -*- test-case-name: virtualbricks.tests.test_factory -*-
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

from __future__ import print_function

import os
import sys
import errno
import re
import copy
import getpass
import logging
import threading

import gobject

import virtualbricks
from virtualbricks import (app, tools, logger, wires, virtualmachines, errors,
                           console, settings, events, switches, tuntaps,
                           tunnels, router, bricks)
from virtualbricks.models import BricksModel, EventsModel
from virtualbricks.errors import UnmanagedType
from virtualbricks.configfile import ConfigFile


log = logging.getLogger(__name__)

if False:  # pyflakes
    _ = str

# synchronized is a decorator that serializes methods invocation. Don't use
# outside the BrickFactory if not needed. The lock is a reentrant one because
# one synchronized method could call another synchronized method and we allow
# this (in the same thread). The quit method is on example.
synchronized = tools.synchronize_with(threading.RLock())


def install_brick_types(registry=None, vde_support=False):
    if registry is None:
        registry = {}

    registry.update({
        'switch': switches.Switch,
        'tap': tuntaps.Tap,
        'capture': tuntaps.Capture,
        'vm': virtualmachines.VM,
        'qemu': virtualmachines.VM,
        'wirefilter': wires.Wirefilter,
        'tunnelc': tunnels.TunnelConnect,
        'tunnel client': tunnels.TunnelConnect,
        'tunnelconnect': tunnels.TunnelConnect,
        'tunnell': tunnels.TunnelListen,
        'tunnel server': tunnels.TunnelListen,
        'tunnellisten': tunnels.TunnelListen,
        'event': events.Event,
        'switchwrapper': switches.SwitchWrapper,
        'router': router.Router,
    })
    if vde_support:
        registry['wire'] = wires.PyWire
    else:
        registry['wire'] = wires.Wire
    return registry


class BrickFactory(logger.ChildLogger(__name__), gobject.GObject):
    """This is the main class for the core engine.

    All the bricks are created and stored in the factory.
    It also contains a thread to manage the command console.
    """

    __gsignals__ = {
        'engine-closed': (gobject.SIGNAL_RUN_LAST, None, ()),
        'brick-started': (gobject.SIGNAL_RUN_LAST, None, (str,)),
        'brick-stopped': (gobject.SIGNAL_RUN_LAST, None, (str,)),
        'brick-changed': (gobject.SIGNAL_RUN_LAST, None, (str,)),
        'event-started': (gobject.SIGNAL_RUN_LAST, None, (str,)),
        'event-stopped': (gobject.SIGNAL_RUN_LAST, None, (str,)),
        'event-changed': (gobject.SIGNAL_RUN_LAST, None, (str,)),
        'event-accomplished': (gobject.SIGNAL_RUN_LAST, None, (str,)),
        "image_added": (gobject.SIGNAL_RUN_LAST, None, (object,)),
        "image_removed": (gobject.SIGNAL_RUN_LAST, None, (object,))
    }

    TCP = None
    quitting = False

    def __init__(self):
        gobject.GObject.__init__(self)
        # DEFINE PROJECT PARMS
        self.remote_hosts = []
        self.bricks = []
        self.events = []
        self.socks = []
        self.disk_images = []
        self.bricksmodel = BricksModel()
        self.eventsmodel = EventsModel()
        self.remotehosts_changed = False
        self.running_condition = True
        self.settings = settings.Settings(settings.CONFIGFILE)
        self.configfile = ConfigFile(self)
        self.BRICKTYPES = install_brick_types(
            None, wires.VDESUPPORT and self.settings.python)

    def save_configfile(self):
        # This method is not synchronized because configfile take care of
        # synchonize itself
        try:
            self.configfile.save(self.settings.get('current_project'))
        # except Exception:
        except (IOError, OSError):
            log.exception("ERROR WRITING CONFIGURATION!\n"
                          "Probably file doesn't exist or you can't write "
                          "it.\n")

    @synchronized
    def quit(self):
        if not self.quitting:
            # because factory quit can be called twice from the console:
            # vb> quit
            # factory.quit() send "engine-closed"
            # the gui termine and the application calls factory.quit() again
            self.quitting = True
            for e in self.events:
                e.poweroff()
            for b in self.bricks:
                if b.proc is not None:
                    b.poweroff()
            for h in self.remote_hosts:
                h.disconnect()

            self.info(_('Engine: Bye!'))
            self.save_configfile()
            self.running_condition = False
            self.emit("engine-closed")

    @synchronized
    def reset(self):
        # hard reset
        self.bricksmodel.clear()
        self.eventsmodel.clear()
        for b in self.bricks:
            self.delbrick(b)
        del self.bricks[:]

        for e in self.events:
            self.delevent(e)
        del self.events[:]

        self.socks = []

    def err(self, _, *args, **kwds):
        self.error(*args, **kwds)

    def get_basefolder(self):
        baseimages = self.settings.get("baseimages")
        project_file = self.settings.get("current_project")
        project_name = os.path.splitext(os.path.basename(project_file))[0]
        return os.path.join(baseimages, project_name)

    @synchronized
    def reset_config(self):
        """ Power off and kickout all bricks and events """
        # XXX: what about socks?
        for b in self.bricks:
            b.poweroff()
            self.delbrick(b)
        for e in self.events:
            self.delevent(e)
        self.bricks[:] = []
        self.events[:] = []

    # [[[[[[[[[]]]]]]]]]
    # [   Disk Images  ]
    # [[[[[[[[[]]]]]]]]]

    def get_image_by_name(self, name):
        """Get disk image object from the image library by its name."""

        for img in self.disk_images:
            if img.name == name:
                return img

    def get_image_by_path(self, path):
        """Get disk image object from the image library by its path."""

        for img in self.disk_images:
            if img.path == path:
                return img

    @synchronized
    def new_disk_image(self, name, path, description="", host=None):
        """Add one disk image to the library."""

        img = virtualmachines.DiskImage(name, path, description, host)
        self.disk_images.append(img)
        self.emit("image_added", img)
        return img

    @synchronized
    def remove_disk_image(self, image):
        self.disk_images.remove(image)
        self.emit("image_removed", image)

    '''[[[[[[[[[]]]]]]]]]'''
    '''[ Bricks, Events ]'''
    '''[[[[[[[[[]]]]]]]]]'''

    def get_brick_by_name(self, name):
        for b in self.bricks:
            if b.name == name:
                return b
    getbrickbyname = get_brick_by_name

    def get_event_by_name(self, name):
        for e in self.events:
            if e.name == name:
                return e
    geteventbyname = get_event_by_name

    def get_host_by_name(self, host):
        for h in self.remote_hosts:
            if h.addr[0] == host:
                return h
        return None

    '''naming'''
    @synchronized
    def renamebrick(self, b, newname):
        newname = tools.ValidName(newname)
        if newname is None:
            raise errors.InvalidNameError("No name given!")
            return

        if not tools.NameNotInUse(self, newname):
            raise errors.InvalidNameError()
            return

        b.name = newname
        #some bricks need to do some extra operations
        b.post_rename(newname)
        b.gui_changed = True

    @synchronized
    def renameevent(self, e, newname):
        newname = tools.ValidName(newname)
        if newname is None:
            raise errors.InvalidNameError()
            return

        if not tools.NameNotInUse(self, newname):
            raise errors.InvalidNameError()
            return

        e.name = newname
        if e.get_type() == "Event":
            #It's a little comlicated here, if we are renaming
            #an event we have to rename it in all command of other
            #events...
            pass
        #e.gui_changed = True

    def nextValidName(self, name, toappend="_new"):
        """Generate a potential next valid name by appending _new"""

        newname = tools.ValidName(name)
        if not newname:
            return None
        while(not tools.NameNotInUse(self, newname)):
            newname += toappend
        return newname

    ''' construction functions '''

    def normalize(self, name):
        """Return the normalized name or raise an InvalidNameError."""
        if not isinstance(name, str):
            raise errors.InvalidNameError("Name must be a string")
        nname = name.strip()
        if not re.search("\A[a-zA-Z]", nname):
            raise errors.InvalidNameError("Name does not start with a letter, "
                                          "%s" % name)
        nname = re.sub(' ', '_', nname)
        if not re.search("\A[a-zA-Z0-9_\.-]+\Z", nname):
            raise errors.InvalidNameError("Name must contains only letters, "
                    "numbers, underscores, hyphens and points, %s" % name)
        return name

    def is_in_use(self, name):
        """used to determine whether the chosen name can be used or
        it has already a duplicate among bricks or events."""

        for b in self.bricks:
            if b.name == name:
                return True
        for e in self.events:
            if e.name == name:
                return True
        for i in self.disk_images:
            if i.name == name:
                return True
        return False

    def newbrick(self, type, name, host="", remote=False):
        """Old interface, use new_brick instead.

        Two possible method invocations:

        arg1 == "remote"  |  arg1 = ntype
        arg2 == type      |  arg2 = name
        arg3 = name       |  arg3 = host
        arg4 = host       |  arg4 = remote (boolean)
        """

        if name == "remote":
            return self.new_brick(type=name, name=host, host=remote,
                                   remote=True)
        else:
            return self.new_brick(type, name, host, remote)

    @synchronized
    def new_brick(self, type, name, host="", remote=False):
        """Return a new brick.

        @param type: The type of new brick. Must be known.
        @type type: C{str}
        @param name: The name for the new brick. Must contains only letters,
            numbers, underscores, hyphens and points. Must not be already in
            use.
        @type name: C{str}
        @param host: The host for the brick. Default: "".
        @type type: C{str}
        @param remote: If this brick is a remote brick. Default = False.
        @type remote: C{bool}

        @return: the new brick.

        @raises: InvalidNameError, InvalidTypeError
        """

        nname = self.normalize(name)  # raises InvalidNameError
        if self.is_in_use(nname):
            raise errors.InvalidNameError("Normalized name %s already in use" %
                                     nname)
        ltype = type.lower()
        if ltype not in self.BRICKTYPES:
            raise errors.InvalidTypeError("Invalid type %s" % type)
        brick = self.BRICKTYPES[ltype](self, name)
        if remote:
            brick.set_host(host)
            if brick.homehost.connected:
                brick.homehost.send("new " + brick.get_type() + " " +
                                    brick.name)
        return brick

    # def __new_brick(self, type, name, host="", remote=False):
    #     brick = self.new_brick(type, name, host, remote)
    #     self.bricks.append(brick)
    #     self.bricksmodel.append(brick)

    def newevent(self, ntype="", name=""):
        """Old interface, use new_event instead."""
        if ntype not in ("event", "Event"):
            log.error("Invalid event command '%s %s'", ntype, name)
            return False
        self.new_event(name)
        return True

    @synchronized
    def new_event(self, name):
        """Create a new event.

        @arg name: The event name.
        @type name: C{str}

        @return: The new created event.

        @raises: InvalidNameError, InvalidTypeError
        """

        nname = self.normalize(name)  # raises InvalidNameError
        if self.is_in_use(nname):
            raise errors.InvalidNameError("Normalized name %s already in use" %
                                          nname)
        event = events.Event(self, name)
        log.debug("New event %s OK", event.name)
        return event

    @synchronized
    def new_plug(self, brick):
        return link.Plug(brick)

    # @synchronized
    # def new_sock(self, brick, name=""):
    #     sock = link.Sock(brick, name)
    #     self.socks.append(sock)
    #     return sock

    ''' brick action dispatcher '''
    def brickAction(self, obj, cmd):
        if (cmd[0] == 'on'):
            obj.poweron()
        if (cmd[0] == 'off'):
            obj.poweroff()
        if (cmd[0] == 'remove'):
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
                log.info("Connection ok")
            else:
                log.info("Connection failed")
        if (cmd[0] == 'disconnect'):
            obj.disconnect()

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
    @synchronized
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

    @synchronized
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

    @synchronized
    def delevent(self, eventtodel):
        # XXX check me
        for e in self.events:
            if e == eventtodel:
                e.poweroff()
                self.events.remove(e)
        self.eventsmodel.del_event(eventtodel)


def readline(filename):
    with open(filename) as fp:
        return fp.readline()


def write(filename, data):
    with open(filename, "w") as fp:
        fp.write(data)


def writesafe(filename, data):
    write(filename, data)
    try:
        os.chmod(filename, 0600)
    except Exception, err:
        try:
            os.unlink(filename)
        except OSError:
            pass
        raise IOError(*err.args)


class PermissionError(Exception):
    pass


class BrickFactoryServer(BrickFactory):

    password_file = "/etc/virtualbricks-passwd"

    def get_password(self):
        try:
            return readline(self.password_file)
        except IOError:
            while True:
                pwd = getpass.getpass("Insert password:")
                pwd2 = getpass.getpass("Confirm:")
                if pwd == pwd2:
                    try:
                        write(self.password_file, pwd)
                    except IOError:
                        print("Could not save password.")
                    else:
                        print("Password saved.")
                    return pwd
                else:
                    print("Passwords don't match. Retry.")

    def save_configfile(self):
        log.warning("BrickFactory does not support save_configfile when in "
                    "server mode. This should be considerated a code bug.\n"
                    + "Stack trace:\n" + tools.stack_trace())


class Console(object):

    prompt = "virtualbricks> "
    intro = ("Virtualbricks, version {version}\n"
        "Copyright (C) 2013 Virtualbricks team\n"
        "This is free software; see the source code for copying conditions.\n"
        "There is ABSOLUTELY NO WARRANTY; not even for MERCHANTABILITY or\n"
        "FITNESS FOR A PARTICULAR PURPOSE.  For details, type `warranty'.\n\n")

    def __init__(self, factory, stdout=sys.__stdout__, stdin=sys.__stdin__):
        self.factory = factory
        self.stdout = stdout
        self.stdin = stdin

    def _check_changed(self):
        if self.factory.remotehosts_changed:
            for rh in self.factory.remote_hosts:
                if rh.connection and rh.connection.isAlive():
                    rh.connection.join(0.001)
                    if not rh.connection.isAlive():
                        rh.connected = False
                        rh.connection = None

    def _poll(self):
        command = ""    # because if stdin.readline raise an exception,
                        # command is not defined
        try:
            command = self.stdin.readline()
            console.parse(self.factory, command)
        except Exception as e:
            log.exception("An exception is occurred while processing "
                          "command %s", command)
            msg = ""
            errno = ""
            if len(e.args) == 2:
                msg, errno = e.args
            elif len(e.args) == 1:
                msg = e.args[0]
            print(_("Exception:\n\tType: %s\n\tErrno: %s\n\t"
                    "Message: %s\n" % (type(e), errno, msg)),
                  file=self.stdout)

    def run(self):
        intro = self.intro.format(version=virtualbricks.version.short())
        print(intro, end="", file=self.stdout)
        while self.factory.running_condition:
            print(self.prompt, end="", file=self.stdout)
            self.stdout.flush()
            self._poll()
            self._check_changed()
        self.stdout.flush()


def AutosaveTimer(factory, timeout=180):
    t = tools.LoopingCall(timeout, factory.save_configfile)
    t.set_name("AutosaveTimer_%d" % timeout)
    t.start()
    return t


class Application:

    factory = None
    autosave_timer = None

    def __init__(self, config):
        self.config = config

    def get_logging_handler(self):
        pass

    def install_locale(self):
        import locale
        locale.setlocale(locale.LC_ALL, '')
        import gettext

        gettext.install('virtualbricks', codeset='utf8', names=["gettext"])

    def install_sys_hooks(self):
        # displayhook is necessary because otherwise the python console sets
        # __builtin__._ to the result of the last command and this breaks
        # gettext. excepthook is useful to not show traceback on the console
        # but to log it.
        sys.displayhook = print
        sys.excepthook = self.excepthook

    def excepthook(self, exc_type, exc_value, traceback):
        if exc_type in (SystemExit, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, traceback)
        else:
            log.error("Uncaught exception", exc_info=(exc_type, exc_value,
                                                      traceback))

    def restore_last_project(self):
        try:
            os.mkdir(settings.MYPATH)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
        try:
            self.factory.configfile.restore(self.factory.settings.get(
                "current_project"))
        except IOError as e:
            if e.errno != errno.ENOENT:
                raise
        # except (IOError, OSError, errors.Error):
        #     # NOTE: I don't think OSError is really necessary
        #     # XXX: what kind of errors could be raised on factory restoring?
        #     log.exception("Error while restoring the last project")
        #     # XXX: what to do? Should I reset the factory?
        #     self.factory.reset()

    def start(self):
        self.factory = BrickFactory()
        self.restore_last_project()
        self.autosave_timer = AutosaveTimer(self.factory)
        console = Console(self.factory)
        console.run()

    def quit(self):
        if self.factory:
            self.factory.quit()
        if self.autosave_timer:
            self.autosave_timer.stop()
            self.autosave_timer = None


class ApplicationServer(Application):

    def start(self):
        if os.getuid() != 0:
            raise app.QuitError("server requires to be run by root.", 5)
        self.factory = factory = BrickFactoryServer()
        from virtualbricks import tcpserver
        server_t = tcpserver.TcpServer(factory, factory.get_password())
        factory.TCP = server_t
        server_t.start()
        Console(factory).run()
