# -*- test-case-name: virtualbricks.tests.test_factory -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2019 Virtualbricks team

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

from twisted.application import app
from twisted.internet import defer, task, stdio, error
from twisted.protocols import basic
from twisted.python import failure, log as legacyLog
from twisted.conch.insults import insults
from twisted.conch import manhole

from virtualbricks import errors, settings, configfile, console, project, log
from virtualbricks import link, router, switches, tunnels, tuntaps
from virtualbricks import virtualmachines, wires
from virtualbricks.errors import NameAlreadyInUseError
from virtualbricks.events import Event, is_event
from virtualbricks.observable import Event as Signal, Observable
from virtualbricks.tools import is_running
from virtualbricks.virtualmachines import is_disk_image


if False:  # pyflakes
    _ = str

logger = log.Logger()
reg_basic_types = log.Event("Registering basic types")
engine_bye = log.Event("Engine: Bye!")
reg_new_type = log.Event("Registering new brick type {type}")
type_present = log.Event("Type {type} already present, overriding it")
create_image = log.Event("Creating new disk image at '{path}'")
remove_socks = log.Event("Removing socks: {socks}")
disconnect_plug = log.Event("Disconnecting plug to {sock}")
remove_brick = log.Event("Removing brick {brick}")
endpoint_not_found = log.Event("Endpoint {nick} not found.")
shut_down = log.Event("Server Shut Down.")
new_event_ok = log.Event("New event {name} OK")
uncaught_exception = log.Event("Uncaught exception: {error()}")
brick_stop = log.Event("Error on brick poweroff")


def install_brick_types(registry=None):
    if registry is None:
        registry = {}

    logger.debug(reg_basic_types)
    registry.update({
        "switch": switches.Switch,
        "tap": tuntaps.Tap,
        "capture": tuntaps.Capture,
        "vm": virtualmachines.VirtualMachine,
        "qemu": virtualmachines.VirtualMachine,
        "wirefilter": wires.Netemu,
        "netemu": wires.Netemu,
        "wire": wires.Wire,
        "tunnelc": tunnels.TunnelConnect,
        "tunnel client": tunnels.TunnelConnect,
        "tunnelclient": tunnels.TunnelConnect,
        "tunnelconnect": tunnels.TunnelConnect,
        "tunnell": tunnels.TunnelListen,
        "tunnel server": tunnels.TunnelListen,
        "tunnelserver": tunnels.TunnelListen,
        "tunnellisten": tunnels.TunnelListen,
        "event": Event,
        "switchwrapper": switches.SwitchWrapper,
        "router": router.Router,
    })
    return registry


def normalize_brick_name(name):
    """
    Return the new normalized name or raise InvalidNameError.

    Leading and trailing spaces are trimmed and spaces are replaced with
    underscores.

    :param str name: the chosen name for the brick.
    :raise InvalidNameError: if the name is invalid (malformatted of
        contains invalid characters).
    """

    if not isinstance(name, str):
        raise errors.InvalidNameError(_('Name must be a string'))
    if name == '':
        raise errors.InvalidNameError(_('Name is empty'))
    normalized_name = re.sub(r'\s+', '_', name.strip())
    if not re.search(r'\A[a-zA-Z]', normalized_name):
        msg = _('Name must start with a letter')
        raise errors.InvalidNameError(msg.format(brick_name=name))
    if not re.search(r'\A[a-zA-Z0-9_\.-]+\Z', normalized_name):
        msg = _('Name must contains only letters, numbers, underscores, '
                'hyphens and points').format(brick_name=name)
        raise errors.InvalidNameError(msg)
    return normalized_name


class BrickFactory(object):
    """This is the main class for the core engine.

    All the bricks are created and stored in the factory.
    It also contains a thread to manage the command console.
    """

    @property
    def bricks(self):
        return self._bricks

    def __init__(self, quit):
        self.quit_d = quit
        self._bricks = []
        self._events = {}
        self.socks = []
        self._disk_images = {}
        self.__factories = install_brick_types()
        self.__observable = observable = Observable('quit')
        self.changed = Signal(observable, 'brick-changed')
        self.quit_signal = Signal(observable, 'quit')
        self.brick_added = Signal(observable, 'brick-added')
        self.brick_removed = Signal(observable, 'brick-removed')
        self.brick_changed = Signal(observable, 'brick-changed')
        self.event_added = Signal(observable, 'event-added')
        self.event_removed = Signal(observable, 'event-removed')
        self.event_changed = Signal(observable, 'event-changed')
        self.image_added = Signal(observable, 'image-added')
        self.image_removed = Signal(observable, 'image-removed')
        self.image_changed = Signal(observable, 'image-changed')

    def quit(self):
        if any(is_running(brick) for brick in self._bricks):
            msg = _("Cannot close virtualbricks: there are running bricks")
            raise errors.BrickRunningError(msg)
        logger.info(engine_bye)
        for e in self._events.values():
            e.poweroff()
        self.quit_signal.notify(self)
        if not self.quit_d.called:
            self.quit_d.callback(None)

    def reset(self):
        if any(is_running(brick) for brick in self._bricks):
            msg = _("Project cannot be closed: there are running bricks")
            raise errors.BrickRunningError(msg)
        # Don't change the list while iterating over it
        for brick in list(self._bricks):
            self.del_brick(brick)

        # Don't change the list while iterating over it
        for e in list(self._events.values()):
            self.del_event(e)

        del self.socks[:]
        for image in list(self._disk_images.values()):
            self.remove_disk_image(image)

    def register_brick_type(self, factory, *types):
        """Register a new brick type.

        Factory argument is a contructor (or factory but factory is overused as
        term)"""

        for type in types:
            logger.debug(reg_new_type, type=type)
            if type in self.__factories:
                logger.debug(type_present, type=type)
            self.__factories[type] = factory

    def connect(self, name, callback, *args, **kwds):
        self.__observable.add_observer(name, callback, args, kwds)

    def disconnect(self, name, callback, *args, **kwds):
        self.__observable.remove_observer(name, callback, args, kwds)

    def set_restore(self, restore):
        pass

    # Disk Images

    def new_disk_image(self, name, path, description=''):
        """Add one disk image to the library."""

        logger.info(create_image, path=path)
        new_name = normalize_brick_name(name)
        path = os.path.abspath(path)
        if self.get_image_by_name(new_name) is not None:
            raise NameAlreadyInUseError(new_name)
        if self.get_image_by_path(path) is not None:
            raise errors.ImageAlreadyInUseError(path)
        disk_image = virtualmachines.Image(new_name, path, description)
        self._disk_images[new_name] = disk_image
        disk_image.changed.connect(self.image_changed.notify)
        self.image_added.notify(disk_image)
        return disk_image

    def remove_disk_image(self, disk_image):
        disk_image.changed.disconnect(self.image_changed.notify)
        del self._disk_images[disk_image.get_name()]
        self.image_removed.notify(disk_image)

    def get_image_by_name(self, name):
        """
        Return a disk image given its name.

        :type name: str
        :rtype: Optional[virtualbricks.virtualmachines.Image]
        """

        return self._disk_images.get(name)

    def get_image_by_path(self, path):
        """
        Get disk image object from the image library by its path.

        :type path: str
        :rtype: Optional[virtualbricks.virtualmachines.Image]
        """

        for disk_image in self._disk_images.values():
            if disk_image.get_path() == path:
                return disk_image

    def iter_disk_images(self):
        """
        :rtype: Iterable[virtualbricks.virtualmachines.Image]
        """

        return iter(self._disk_images.values())

    # Bricks

    def new_brick(self, type, name, host='', remote=False):
        """Return a new brick.

        @param type: The type of new brick.
        @type type: C{str}
        @param name: The name for the new brick. Must contains only letters,
            numbers, underscores, hyphens and points. Must not be already in
            use.
        @type name: C{str}
        @return: the new brick.
        @raises: InvalidNameError, InvalidTypeError
        """

        try:
            BrickClass = self.__factories[type.lower()]
        except KeyError:
            raise errors.InvalidTypeError(_('Invalid brick type %s') % type)
        name = normalize_brick_name(name)
        if self.get_brick_by_name(name) is not None:
            raise NameAlreadyInUseError(name)
        brick = BrickClass(self, name)
        self._bricks.append(brick)
        brick.changed.connect(self.brick_changed.notify)
        self.brick_added.notify(brick)
        return brick

    def dup_brick(self, brick):
        name = self.next_name("copy_of_" + brick.name)
        new_brick = self.new_brick(brick.get_type(), name)
        # Copy only strings, and not objects, into new vm config
        new_brick.set(copy.deepcopy(brick.config))

        for p in brick.plugs:
            if p.sock is not None:
                new_brick.connect(p.sock)

        return new_brick

    def del_brick(self, brick):
        if is_running(brick):
            msg = "Cannot delete brick {0:n}: brick is running".format(brick)
            raise errors.BrickRunningError(msg)
        logger.info(remove_brick, brick=brick.name)
        socks = set(brick.socks)
        if socks:
            logger.info(remove_socks,
                        socks=", ".join(s.nickname for s in socks))
            for _brick in self._bricks:
                for plug in _brick.plugs:
                    if plug.configured() and plug.sock in socks:
                        logger.info(disconnect_plug, sock=plug.sock.nickname)
                        plug.disconnect()
            for sock in [s for s in self.socks if s.brick is brick]:
                self.socks.remove(sock)
        for plug in brick.plugs:
            if plug.configured():
                plug.disconnect()
        brick.changed.disconnect(self.brick_changed.notify)
        self._bricks.remove(brick)
        self.brick_removed.notify(brick)

    def _get_element_by_name(self, name, sequence):
        for item in sequence:
            if item.get_name() == name:
                return item

    def get_brick_by_name(self, name):
        """
        Return a brick given its name.

        :type name: str
        :rtype: Optional[virtualbricks.bricks.Brick]
        """

        return self._get_element_by_name(name, self.iter_bricks())

    def iter_bricks(self):
        return iter(self._bricks)

    # Events

    def new_event(self, name):
        """Create a new event.

        @arg name: The event name.
        @type name: C{str}
        @return: The new created event.
        @raises: InvalidNameError, InvalidTypeError
        """

        norm_name = normalize_brick_name(name)
        if self.get_event_by_name(norm_name) is not None:
            raise NameAlreadyInUseError(norm_name)
        event = Event(self, norm_name)
        logger.debug(new_event_ok, name=norm_name)
        self._events[norm_name] = event
        event.changed.connect(self.event_changed.notify)
        self.event_added.notify(event)
        return event

    def dup_event(self, event):
        name = self.next_name("copy_of_" + event.name)
        new = self.new_event(name)
        new.config = copy.deepcopy(event.config)
        return new

    def del_event(self, event):
        event.poweroff()
        event.changed.disconnect(self.event_changed.notify)
        del self._events[event.get_name()]
        self.event_removed.notify(event)

    def get_event_by_name(self, name):
        """
        Return an event given its name.

        :type name: str
        :rtype: Optional[virtualbricks.events.Event]
        """

        return self._disk_images.get(name)

    def iter_events(self):
        return iter(self._events.values())

    def next_name(self, name):
        c = 1
        orig_name = name
        while self.is_in_use(name):
            name = f'{orig_name}.{c}'
        return name

    def is_in_use(self, name):
        """used to determine whether the chosen name can be used or
        it has already a duplicate among bricks or events."""

        if self._get_brick_event_disk(name) is not None:
            return True
        else:
            return False

    def _get_brick_event_disk(self, name):
        brick = self.get_brick_by_name(name)
        if brick is not None:
            return brick
        event = self.get_event_by_name(name)
        if event is not None:
            return event
        disk_image = self.get_image_by_name(name)
        if disk_image is not None:
            return disk_image
        return None

    def rename(self, brick, name):
        prev_name = brick.get_name()
        new_name = self.normalize_name(name)
        # Update indexes
        if is_event(brick):
            self._events[new_name] = brick
            del self._events[prev_name]
        elif is_disk_image(brick):
            self._disk_images[new_name] = brick
            del self._disk_images[prev_name]
        brick.set_name(new_name)
        return prev_name

    def normalize_name(self, name):
        """
        Return the new normalized name or raise InvalidNameError.

        :param str name: the chosen name for the brick.
        :raise InvalidNameError: if the name is invalid (malformatted of
            contains invalid characters).
        :raise NameAlreadyInUseError: if the name is already in use.
        """

        normalized_name = normalize_brick_name(name)
        if self.is_in_use(normalized_name):
            raise errors.NameAlreadyInUseError(normalized_name)
        return normalized_name

    def new_plug(self, brick):
        return link.Plug(brick)

    def new_sock(self, brick, name=""):
        sock = link.Sock(brick, name)
        self.socks.append(sock)
        return sock

    def get_sock_by_name(self, name):
        if name == "_hostonly":
            return virtualmachines.hostonly_sock
        for sock in self.socks:
            if sock.nickname == name:
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
            logger.debug(endpoint_not_found, nick=nick)
            return None


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
    delimiter = b"\n"

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

    observer = None

    def __init__(self, options):
        self.observerFactory = options.get("logger")

    def start(self, application):
        if self.observerFactory is not None:
            self.observer = self.observerFactory()

        if self.observer is not None:
            logger.publisher.addObserver(self.observer, False)
        legacyLog.defaultObserver.stop()
        legacyLog.defaultObserver = None
        legacyLog.addObserver(log.LegacyAdapter())
        self._initialLog()

    def stop(self):
        logger.info(shut_down)
        if self.observer is not None:
            logger.publisher.removeObserver(self.observer)
            self.observer = None


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

        gettext.install('virtualbricks', names=["gettext"])

    def install_settings(self):
        settings.load()

    def install_stdlog_handler(self):
        import logging

        def get_log_level(verbosity):
            if verbosity >= 2:
                return logging.DEBUG
            elif verbosity == 1:
                return logging.INFO
            elif verbosity == -1:
                return logging.ERROR
            elif verbosity <= -2:
                return logging.CRITICAL

        root = logging.getLogger()
        root.addHandler(log.StdLoggingAdapter())
        if self.config["verbosity"]:
            root.setLevel(get_log_level(self.config["verbosity"]))

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
            fail = failure.Failure(exc_value, exc_type, traceback)
            logger.error(uncaught_exception, log_failure=fail,
                         error=lambda: fail.getErrorMessage())

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
        self._run(factory)
        if self.config["verbosity"] >= 2 and not self.config["daemon"]:
            import signal
            import pdb
            signal.signal(signal.SIGUSR2, lambda *args: pdb.set_trace())
            signal.signal(signal.SIGINT, lambda *args: pdb.set_trace())
            app.fixPdb()
        reactor.addSystemEventTrigger("before", "shutdown", settings.store)
        project.manager.restore_last(factory)
        reactor.addSystemEventTrigger("before", "shutdown",
                                      project.manager.save_current, factory)
        reactor.addSystemEventTrigger("before", "shutdown", self.logger.stop)
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

    def _run(self, factory):
        pass
