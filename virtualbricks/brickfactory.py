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
import re
import copy
import getpass
import logging
import threading
import itertools
import warnings

import gtk
import gobject

import virtualbricks
from virtualbricks import app, tools, errors, settings, configfile, console
from virtualbricks import (events, link, router, switches, tunnels,
                           tuntaps, virtualmachines, wires)


log = logging.getLogger(__name__)

if False:  # pyflakes
    _ = str


def install_brick_types(registry=None, vde_support=False):
    if registry is None:
        registry = {}

    log.debug("Registering basic types")
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
        log.debug("Register wire with vde_support")
        registry['wire'] = wires.PyWire
    else:
        registry['wire'] = wires.Wire
    return registry


class BrickFactory(gobject.GObject):
    """This is the main class for the core engine.

    All the bricks are created and stored in the factory.
    It also contains a thread to manage the command console.
    """

    # synchronized is a decorator that serializes methods invocation. Don't use
    # outside the BrickFactory if not needed. The lock is a reentrant one
    # because one synchronized method could call another synchronized method
    # and we allow this (in the same thread). The quit method is on example.
    # NOTE: this is a class variable but should not be a problem because
    # BrickFactory is a singleton
    _lock = threading.RLock()
    synchronized = tools.synchronize_with(_lock)

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
    remotehosts_changed = False
    running_condition = True

    def __init__(self):
        gobject.GObject.__init__(self)
        self.remote_hosts = []
        self.bricks = []
        self.events = []
        self.socks = []
        self.disk_images = []
        self.bricksmodel = gtk.ListStore(object)
        self.__brick_signals = {}
        self.eventsmodel = gtk.ListStore(object)
        self.__event_signals = {}
        self.settings = settings.Settings(settings.CONFIGFILE)
        self.__factories = install_brick_types(
            None, wires.VDESUPPORT and self.settings.python)

    def lock(self):
        return self._lock

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

            log.info(_('Engine: Bye!'))
            configfile.safe_save(self)
            self.running_condition = False
            self.emit("engine-closed")

    @synchronized
    def reset(self):
        # hard reset
        # XXX: what about remote hosts?
        # XXX: what about disk images?
        self.bricksmodel.clear()
        self.eventsmodel.clear()
        for b in self.bricks:
            self.delbrick(b)
        del self.bricks[:]

        for e in self.events:
            self.delevent(e)
        del self.events[:]

        del self.socks[:]

    def get_basefolder(self):
        baseimages = self.settings.get("baseimages")
        project_file = self.settings.get("current_project")
        project_name = os.path.splitext(os.path.basename(project_file))[0]
        return os.path.join(baseimages, project_name)

    def register_brick_type(self, factory, *types):
        """Register a new brick type.

        Factory argument is a contructor (or factory but factory is overused as
        term)"""

        for type in types:
            log.debug("Registering new brick type %s", type)
            if type in self.__factories:
                log.debug("Type %s already present, overriding it", type)
            self.__factories[type] = factory
            # self.__factories.setdefault(type, []).append(factory)

    # [[[[[[[[[]]]]]]]]]
    # [   Disk Images  ]
    # [[[[[[[[[]]]]]]]]]

    @synchronized
    def new_disk_image(self, name, path, description="", host=None):
        """Add one disk image to the library."""

        # XXX: assert that name and path are unique
        nname = self.normalize(name)
        if self.is_in_use(nname):
            raise errors.NameAlreadyInUseError(nname)
        img = virtualmachines.DiskImage(name, path, description, host)
        self.disk_images.append(img)
        self.emit("image_added", img)
        return img

    @synchronized
    def remove_disk_image(self, image):
        self.disk_images.remove(image)
        self.emit("image_removed", image)

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

    # [[[[[[[[[]]]]]]]]]
    # [     Bricks     ]
    # [[[[[[[[[]]]]]]]]]

    def newbrick(self, type, name, host="", remote=False):
        """Old interface, use brickfactory.new_brick() instead.

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

    def new_brick(self, type, name, host="", remote=False):
        brick = self._new_brick(type, name, host, remote)
        self.bricks.append(brick)
        self.bricksmodel.append((brick,))
        self.__brick_signals[brick.name] = brick.signal_connect(
            "changed", self.__brick_changed)
        return brick

    def __do_action_for_brick(self, action, brick):
        i = self.bricksmodel.get_iter_first()
        while i:
            if self.bricksmodel.get_value(i, 0) == brick:
                action(brick, i)
                break
            i = self.bricksmodel.iter_next(i)

    def __emit_brick_row_changed(self, brick, i):
        self.bricksmodel.row_changed(self.bricksmodel.get_path(i), i)

    def __brick_changed(self, brick):
        self.__do_action_for_brick(self.__emit_brick_row_changed, brick)
        self.emit("brick-changed", brick.name)

    @synchronized
    def _new_brick(self, type, name, host, remote):
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
            raise errors.NameAlreadyInUseError(nname)
        ltype = type.lower()
        if ltype not in self.__factories:
            raise errors.InvalidTypeError(_("Invalid brick type %s") % type)
        brick = self.__factories[ltype](self, nname)
        if remote:
            brick.set_host(host)
            if brick.homehost.connected:
                brick.homehost.send("new " + brick.get_type() + " " +
                                    brick.name)
        return brick

    def dup_brick(self, brick):
        name = self.normalize(self.next_name("copy_of_" + brick.name))
        ty = brick.get_type()
        if (brick.homehost):
            new_brick = self.newbrick("remote", ty, name,
                                      brick.cfg.homehost)
        else:
            new_brick = self.newbrick(ty, name)
        # Copy only strings, and not objects, into new vm config
        # XXX: there is a problem here, new configs will have all kind of types
        # XXX: maybe use deepcopy
        for c in brick.cfg:
            val = brick.cfg.get(c)
            if isinstance(val, str):
                new_brick.cfg.set(c + '=' + val)

        for p in brick.plugs:
            if p.sock is not None:
                new_brick.connect(p.sock)

        new_brick.on_config_changed()
        return new_brick
    dupbrick = dup_brick

    def __remove_brick(self, brick, i):
        self.bricksmodel.remove(i)

    @synchronized
    def delbrick(self, brick):
        # XXX check me
        if brick.proc is not None:
            brick.poweroff()
        for b in self.bricks:
            if b == brick:
                for so in b.socks:
                    self.socks.remove(so)
            else:  # connections to brick must be deleted too
                for pl in reversed(b.plugs):
                    if pl.sock:
                        if pl.sock.nickname.startswith(brick.name):
                            log.debug("Deleting plug to %s", pl.sock.nickname)
                            b.plugs.remove(pl)
                            b.clear_self_socks(pl.sock.path)
                            # recreate Plug(self) of some objects
                            b.restore_self_plugs()
        self.bricks.remove(brick)
        self.__do_action_for_brick(self.__remove_brick, brick)
        brick.signal_disconnect(self.__brick_signals[brick.name])
        del self.__brick_signals[brick.name]

    def get_brick_by_name(self, name):
        for b in self.bricks:
            if b.name == name:
                return b

    @synchronized
    def rename_brick(self, brick, name):
        # XXX: this should emit "changed" signal
        nname = self.normalize(name)
        if self.is_in_use(nname):
            raise errors.NameAlreadyInUseError(nname)
        brick.name = nname
        # b.gui_changed = True

    renamebrick = rename_brick

    # [[[[[[[[[]]]]]]]]]
    # [     Events     ]
    # [[[[[[[[[]]]]]]]]]

    def newevent(self, ntype="", name=""):
        """Old interface, use brickfactory.new_event() instead."""
        if ntype not in ("event", "Event"):
            log.error("Invalid event command '%s %s'", ntype, name)
            return False
        self.new_event(name)
        return True

    def new_event(self, name):
        event = self._new_event(name)
        self.events.append(event)
        self.eventsmodel.append((event,))
        self.__event_signals[event.name] = event.signal_connect(
            "changed", self.__event_changed)
        return event

    def __do_action_for_event(self, action, event):
        i = self.eventsmodel.get_iter_first()
        while i:
            if self.eventsmodel.get_value(i, 0) == event:
                action(event, i)
                break
            i = self.eventsmodel.iter_next(i)

    def __emit_event_row_changed(self, event, i):
        self.eventsmodel.row_changed(self.eventsmodel.get_path(i), i)

    def __event_changed(self, event):
        self.__do_action_for_event(self.__emit_event_row_changed, event)
        self.emit("event-changed", event.name)

    @synchronized
    def _new_event(self, name):
        """Create a new event.

        @arg name: The event name.
        @type name: C{str}

        @return: The new created event.

        @raises: InvalidNameError, InvalidTypeError
        """

        nname = self.normalize(name)  # raises InvalidNameError
        if self.is_in_use(nname):
            raise errors.NameAlreadyInUseError(nname)
        event = events.Event(self, name)
        log.debug("New event %s OK", event.name)
        return event

    def dupevent(self, event):
        name = self.normalize(self.next_name("copy_of_" + event.name))
        self.new_event(name)
        new_event = self.get_event_by_name(name)
        new_event.cfg = copy.deepcopy(event.cfg)
        new_event.active = False
        new_event.on_config_changed()
        return new_event

    def __remove_event(self, event, i):
        self.eventsmodel.remove(i)

    @synchronized
    def del_event(self, event):
        for e in self.events:
            if e == event:
                e.poweroff()
        self.events.remove(event)
        self.__do_action_for_event(self.__remove_event, event)
        event.signal_disconnect(self.__event_signals[event.name])
        del self.__event_signals[event.name]

    delevent = del_event

    def get_event_by_name(self, name):
        for e in self.events:
            if e.name == name:
                return e

    @synchronized
    def rename_event(self, event, name):
        name = self.normalize(name)
        if self.is_in_use(name):
            raise errors.NameAlreadyInUseError(name)
        event.name = name

    renameevent = rename_event

    ############################################

    def get_host_by_name(self, host):
        for h in self.remote_hosts:
            if h.addr[0] == host:
                return h
        return None

    def next_name(self, name, suffix="_new"):
        while self.is_in_use(name):
            name += suffix
        return name

    def normalize(self, name):
        """Return the normalized name or raise an InvalidNameError."""

        if not isinstance(name, str):
            raise errors.InvalidNameError(_("Name must be a string"))
        nname = name.strip()
        if not re.search("\A[a-zA-Z]", nname):
            raise errors.InvalidNameError(_("Name %s does not start with a "
                                            "letter") % name)
        nname = re.sub(' ', '_', nname)
        if not re.search("\A[a-zA-Z0-9_\.-]+\Z", nname):
            raise errors.InvalidNameError(_("Name must contains only letters, "
                    "numbers, underscores, hyphens and points, %s") % name)
        return nname

    def is_in_use(self, name):
        """used to determine whether the chosen name can be used or
        it has already a duplicate among bricks or events."""

        for o in itertools.chain(self.bricks, self.events, self.disk_images):
            if o.name == name:
                return True
        return False

    @synchronized
    def new_plug(self, brick):
        return link.Plug(brick)

    # @synchronized
    # def new_sock(self, brick, name=""):
    #     sock = link.Sock(brick, name)
    #     self.socks.append(sock)
    #     return sock

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
            log.debug("Endpoint %s not found.", nick)
            return None

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
    except Exception, e:
        try:
            os.unlink(filename)
        except OSError:
            pass
        raise IOError(*e.args)


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
                        writesafe(self.password_file, pwd)
                    except IOError:
                        print("Could not save password.")
                    else:
                        print("Password saved.")
                    return pwd
                else:
                    print("Passwords don't match. Retry.")


class Console(object):

    prompt = "virtualbricks> "
    intro = ("Virtualbricks, version {version}\n"
        "Copyright (C) 2013 Virtualbricks team\n"
        "This is free software; see the source code for copying conditions.\n"
        "There is ABSOLUTELY NO WARRANTY; not even for MERCHANTABILITY or\n"
        "FITNESS FOR A PARTICULAR PURPOSE.  For details, type `warranty'.\n\n")

    def __init__(self, factory, stdout=sys.__stdout__, stdin=sys.__stdin__,
                 **local):
        self.factory = factory
        self.stdout = stdout
        self.stdin = stdin
        self.local = local

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
            console.parse(self.factory, command, **self.local)
        except EnvironmentError, e:
            log.exception("An exception is occurred while processing "
                          "command %s", command)
            print(_("Exception:\n\tType: %s\n\tErrno: %s\n\t"
                    "Message: %s\n" % (type(e), e.errno, e.strerror)),
                  file=self.stdout)
        except Exception as e:
            log.exception("An exception is occurred while processing "
                          "command %s", command)
            print(_("Exception:\n\tType: %s\n\tErrno: %s\n\t"
                    "Message: %s\n" % (type(e), "", str(e))),
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
    t = tools.LoopingCall(timeout, configfile.safe_save, (factory,))
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

        # Workaround for sys.excepthook thread bug
        # See: http://bugs.python.org/issue1230540#msg91244
        old_init = threading.Thread.__init__

        def init(self, *args, **kwargs):
            old_init(self, *args, **kwargs)
            run_old = self.run

            def run_with_except_hook(*args, **kw):
                try:
                    run_old(*args, **kw)
                except (KeyboardInterrupt, SystemExit):
                    raise
                except:
                    sys.excepthook(*sys.exc_info())
            self.run = run_with_except_hook
        threading.Thread.__init__ = init

    def excepthook(self, exc_type, exc_value, traceback):
        if exc_type in (SystemExit, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, traceback)
        else:
            log.error(str(exc_value), exc_info=(exc_type, exc_value,
                                                traceback))

    def start(self):
        self.factory = BrickFactory()
        configfile.restore_last_project(self.factory)
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
        logging.captureWarnings(True)
        warnings.filterwarnings("default", category=DeprecationWarning)
        if os.getuid() != 0:
            raise app.QuitError("server requires to be run by root.", 5)
        self.factory = factory = BrickFactoryServer()
        from virtualbricks import tcpserver
        server_t = tcpserver.TcpServer(factory, factory.get_password())
        factory.TCP = server_t
        server_t.start()
        Console(factory).run()
