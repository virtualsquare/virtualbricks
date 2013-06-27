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

import os
import errno
import sys
import termios
import tty
import re
import copy
import itertools

from twisted.application import app
from twisted.internet import defer, task, stdio, error
from twisted.protocols import basic
from twisted.python import failure, log as _log
from twisted.conch.insults import insults
from twisted.conch import manhole

from virtualbricks import errors, settings, configfile, console, _compat
from virtualbricks import (events, link, router, switches, tunnels,
                           tuntaps, virtualmachines, wires)


log = _compat.getLogger(__name__)

if False:  # pyflakes
    _ = str


def install_brick_types(registry=None):
    if registry is None:
        registry = {}

    log.debug("Registering basic types")
    registry.update({
        "switch": switches.Switch,
        "tap": tuntaps.Tap,
        "capture": tuntaps.Capture,
        "vm": virtualmachines.VirtualMachine,
        "qemu": virtualmachines.VirtualMachine,
        "wirefilter": wires.Wirefilter,
        "wire": wires.Wire,
        "tunnelc": tunnels.TunnelConnect,
        "tunnel client": tunnels.TunnelConnect,
        "tunnelconnect": tunnels.TunnelConnect,
        "tunnell": tunnels.TunnelListen,
        "tunnel server": tunnels.TunnelListen,
        "tunnellisten": tunnels.TunnelListen,
        "event": events.Event,
        "switchwrapper": switches.SwitchWrapper,
        "router": router.Router,
    })
    return registry


class BrickFactory(object):
    """This is the main class for the core engine.

    All the bricks are created and stored in the factory.
    It also contains a thread to manage the command console.
    """

    def __init__(self, quit):
        self.quit_d = quit
        self.remote_hosts = []
        self.bricks = []
        self.events = []
        self.socks = []
        self.disk_images = []
        self.__factories = install_brick_types()

    def lock(self):
        return self._lock

    def stop(self):
        log.info(_('Engine: Bye!'))
        for e in self.events:
            e.poweroff()
        # for h in self.remote_hosts:
        #     h.disconnect()

        configfile.safe_save(self)
        l = [brick.poweroff() for brick in self.bricks]
        return defer.DeferredList(l, consumeErrors=True)

    def quit(self):
        if not self.quit_d.called:
            self.quit_d.callback(None)

    def reset(self):
        # hard reset
        # XXX: what about remote hosts?
        # XXX: what about disk images?
        for b in self.bricks:
            self.del_brick(b)
        del self.bricks[:]

        for e in self.events:
            self.del_event(e)
        del self.events[:]

        del self.socks[:]

    def get_basefolder(self):
        baseimages = settings.get("baseimages")
        project_file = settings.get("current_project")
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

    def new_disk_image(self, name, path, description="", host=None):
        """Add one disk image to the library."""

        # XXX: assert that name and path are unique
        log.msg("Creating new disk image with name '%s'" % name)
        nname = self.normalize(name)
        log.msg("Name normalized to '%s'" % nname)
        if self.is_in_use(nname):
            raise errors.NameAlreadyInUseError(nname)
        img = virtualmachines.Image(nname, path, description, host)
        self.disk_images.append(img)
        return img

    def remove_disk_image(self, image):
        self.disk_images.remove(image)

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
        return brick

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
                                      brick.config["homehost"])
        else:
            new_brick = self.newbrick(ty, name)
        # Copy only strings, and not objects, into new vm config
        new_brick.config = copy.deepcopy(brick.config)

        for p in brick.plugs:
            if p.sock is not None:
                new_brick.connect(p.sock)

        new_brick.on_config_changed()
        return new_brick

    def do_del_brick(self, result):
        brick, status = result
        socks = set(brick.socks)
        log.msg("Removing socks: " + ", ".join(s.nickname for s in socks))
        for _brick in self.bricks:
            for plug in _brick.plugs:
                if plug.connected() and plug.sock in socks:
                    log.msg("Disconnecting plug to %s" % plug.sock.nickname)
                    plug.disconnect()
        for sock in [s for s in self.socks if s.brick is brick]:
            self.socks.remove(sock)
        self.bricks.remove(brick)

    def del_brick(self, brick):
        return brick.poweroff().addCallback(self.do_del_brick)

    def get_brick_by_name(self, name):
        for b in self.bricks:
            if b.name == name:
                return b

    def rename_brick(self, brick, name):
        nname = self.normalize(name)
        if self.is_in_use(nname):
            raise errors.NameAlreadyInUseError(nname)
        brick.name = nname

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
        return event

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
        event = events.Event(self, nname)
        log.debug("New event %s OK", event.name)
        return event

    def dup_event(self, event):
        name = self.normalize(self.next_name("copy_of_" + event.name))
        new = self.new_event(name)
        new.config = copy.deepcopy(event.config)
        return new

    def del_event(self, event):
        event.poweroff()
        self.events.remove(event)

    def get_event_by_name(self, name):
        for e in self.events:
            if e.name == name:
                return e

    def rename_event(self, event, name):
        name = self.normalize(name)
        if self.is_in_use(name):
            raise errors.NameAlreadyInUseError(name)
        event.name = name

    ############################################

    def __get_host_by_name(self, hostname):
        for h in self.remote_hosts:
            if h.addr[0] == hostname:
                return h

    def get_host_by_name(self, hostname):
        host = self.__get_host_by_name(hostname)
        if host is None:
            host = console.RemoteHost(self, hostname)
            # self.remote_hosts.append(host)
            # log.debug("Created new host %s", hostname)
        return host

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

    def new_plug(self, brick):
        return link.Plug(brick)

    def new_sock(self, brick, name=""):
        sock = link.Sock(brick, name)
        self.socks.append(sock)
        return sock

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

    # def delremote(self, hostname):
    #     if isinstance(hostname, console.RemoteHost):
    #         self.__del_remote(hostname)
    #     else:
    #         host = self.__get_host_by_name(hostname)
    #         if host is not None:
    #             self.__del_remote(host)

    # def __del_remote(self, host):
    #     bricks = [b for b in self.bricks if b.homehost and
    #               b.homehost.addr[0] == host.addr[0]]
    #     for brick in bricks:
    #         self.del_brick(brick)
    #     self.remote_hosts.remove(host)

    # ###################

    delbrick = del_brick
    dupbrick = dup_brick
    renamebrick = rename_brick
    delevent = del_event
    dupevent = dup_event
    renameevent = rename_event


class Manhole(manhole.Manhole):

    def connectionMade(self):
        fd = sys.__stdin__.fileno()
        self.oldSettings = termios.tcgetattr(fd)
        tty.setraw(fd)
        manhole.Manhole.connectionMade(self)

    def connectionLost(self, reason):
        termios.tcsetattr(sys.__stdin__.fileno(), termios.TCSANOW,
                          self.oldSettings)
        manhole.Manhole.connectionLost(self, reason)


class Console(basic.LineOnlyReceiver):

    inner_protocol = None
    protocol = None
    delimiter = "\n"

    def __init__(self, factory, namespace={}):
        self.factory = factory
        self.namespace = namespace

    def _inject_python(self, protocol):

        def do_python():
            """Open a python interpreter. Use ^D (^Z on windows) to exit."""
            protocol = insults.ServerProtocol(Manhole, self.namespace)
            self._switchTo(protocol)
        protocol.do_python = do_python

    def _switchTo(self, new_proto):
        self.inner_protocol = new_proto
        new_proto.makeConnection(self.transport)

    def connectionMade(self):
        if self.protocol is None:
            self.protocol = console.VBProtocol(self.factory)
            self._inject_python(self.protocol)
        self.protocol.makeConnection(self.transport)

    def dataReceived(self, data):
        if self.inner_protocol is not None:
            self.inner_protocol.dataReceived(data)
        else:
            basic.LineOnlyReceiver.dataReceived(self, data)

    def lineReceived(self, line):
        self.protocol.lineReceived(line)

    def connectionLost(self, reason):
        # This method is called for a multitude of reasons, I'm trying to
        # enumerate them here.
        if reason.check(error.ConnectionDone):
            if self.inner_protocol:
                # 1. Manhole is terminated and the transport close its
                # connection. Here I want to restart the virtualbricks
                # protocol.
                self.inner_protocol.connectionLost(reason)
                self.inner_protocol = None
                stdio.StandardIO(self)
            else:
                # 2. ^D, twisted.internet.fdesc.readFromFD reads an empty
                # string and returns ConnectionDone.
                self.factory.quit()
        if reason.check(error.ConnectionLost):
            # 3. The quit deferred is activated, the reactor disconnects all
            # selectables with ConnectionLost. This method is called twice
            # after a ^D with a ConnectionDone followed by a ConnectionLost.
            if self.inner_protocol:
                # 1. Manhole is terminated and the transport close its
                # connection. Here I want to restart the virtualbricks
                # protocol.
                self.inner_protocol.connectionLost(reason)
                self.inner_protocol = None
        else:
            # 4. An exception is raised inside the protocol, this in an error
            # in the code, don't quit and reopen the terminal.
            stdio.StandardIO(self)


def AutosaveTimer(factory, interval=180):
    l = task.LoopingCall(configfile.safe_save, factory)
    l.start(interval, now=False)
    return l


class AppLogger(app.AppLogger):

    def start(self, application):
        s_observer = None
        if self._observerFactory is not None:
            self._observer = self._observerFactory()
            if self._logfilename:
                s_observer = self._getLogObserver()
        elif self._logfilename:
            self._observer = self._getLogObserver()
        else:
            self._observer = _log.FileLogObserver(_log.NullFile()).emit
        _log.startLoggingWithObserver(self._observer, False)
        if s_observer:
            _log.addObserver(s_observer)
        self._initialLog()


class Application:

    logger_factory = AppLogger
    factory_factory = BrickFactory

    def __init__(self, config):
        self.config = config
        self.logger = self.logger_factory(config)

    def getComponent(self, interface, default):
        return default

    def install_locale(self):
        import locale
        locale.setlocale(locale.LC_ALL, '')
        import gettext

        gettext.install('virtualbricks', codeset='utf8', names=["gettext"])

    def install_settings(self):
        settings.load()

    def _get_log_level(self, verbosity):
        if verbosity >= 2:
            return _compat.DEBUG
        elif verbosity == 1:
            return _compat.INFO
        elif verbosity == -1:
            return _compat.ERROR
        elif verbosity <= -2:
            return _compat.CRITICAL

    def install_stdlog_handler(self):
        root = _compat.getLogger()
        root.addHandler(_compat.LoggingToTwistedLogHandler())
        if self.config["verbosity"]:
            root.setLevel(self._get_log_level(self.config["verbosity"]))

    def install_sys_hooks(self):
        import threading

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
            log.err(failure.Failure(exc_value, exc_type, traceback))

    def install_home(self):
        try:
            os.mkdir(settings.VIRTUALBRICKS_HOME)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

    def get_namespace(self):
        return {}

    def run(self, reactor):
        self.install_locale()
        self.install_settings()
        self.install_stdlog_handler()
        self.logger.start(self)
        self.install_home()
        quit = defer.Deferred()
        factory = self.factory_factory(quit)
        self._run(factory, quit)
        if self.config["verbosity"] >= 2 and not self.config["daemon"]:
            import signal
            import pdb
            signal.signal(signal.SIGUSR2, lambda *args: pdb.set_trace())
            signal.signal(signal.SIGINT, lambda *args: pdb.set_trace())
            app.fixPdb()
        reactor.addSystemEventTrigger("before", "shutdown", factory.stop)
        reactor.addSystemEventTrigger("before", "shutdown", self.logger.stop)
        configfile.restore_last_project(factory)
        AutosaveTimer(factory)
        if not self.config["noterm"] and not self.config["daemon"]:
            namespace = self.get_namespace()
            namespace["factory"] = factory
            stdio.StandardIO(Console(factory, namespace))
        # delay as much as possible the installation of hooks because the
        # exception hook can hide errors in the code requiring to start the
        # application again with logging redirected
        self.install_sys_hooks()
        return quit

    def _run(self, factory, quit):
        pass
