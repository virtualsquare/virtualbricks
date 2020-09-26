# -*- test-case-name: virtualbricks.tests.test_virtualmachines -*-
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

import datetime
import errno
import itertools
import os
import pathlib
import re
import shutil
import warnings

from twisted.internet import defer
from twisted.internet.utils import getProcessOutput

from virtualbricks import errors, tools, settings, bricks, log, project
from virtualbricks.spawn import abspath_qemu, encode_proc_output, qemu_img
from virtualbricks.observable import Event, Observable
from virtualbricks.tools import NotCowFileError, discard_first_arg, sync


if False:
    _ = str

__metaclass__ = type
logger = log.Logger()
new_cow = log.Event(
    'Creating a new private COW from a base image. backing_file={backing_file}'
)
use_backing_file = log.Event(
    'Using  backing file for private cow. backing_file={backing_file}'
    ' image_file={imagefile}'
)
invalid_base = log.Event(
    'Private cow found with a different backing image. Backup the private cow'
    ' and use a new one. private_cow={private_cow}'
    ' expected_backing_file={expected_backing_file}'
    ' found_backing_file={found_backing_file} backup_file={backup_file}'
)
powerdown = log.Event("Sending powerdown to {vm}")
update_usb = log.Event("update_usbdevlist: old {old} - new {new}")
own_err = log.Event("plug {plug} does not belong to {brick}")
acquire_lock = log.Event("Aquiring disk locks")
release_lock = log.Event("Releasing disk locks")
search_usb = log.Event('Searching USB devices')


class UsbDevice:

    @classmethod
    def parse_line(cls, line):
        """
        :type line: str
        :rtype: Optional[UsbDevice]
        """

        matchobj = LSUSB_REGEX.search(line)
        if matchobj:
            dev_id = matchobj.group('id')
            description = matchobj.group('description').strip()
            return cls(dev_id, description)

    @property
    def ID(self):
        return self.id

    @property
    def desc(self):
        return self.description

    def __init__(self, id, description):
        self.id = id
        self.description = description


    def __str__(self):
        return self.id

    def __repr__(self):
        return self.id

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.id == other.id

    def __ne__(self, other):
        equal = self.__eq__(other)
        if equal is NotImplemented:
            return NotImplemented
        return not equal

    def __format__(self, format_string):
        if format_string == 'id' or format_string == '':
            return self.id
        elif format_string == 'd':
            return self.description
        raise ValueError('invalid format string {format_string!r}')


LSUSB_REGEX = re.compile(
    r'(?P<id>\w{4}:\w{4})'
    r'(?:\s(?P<description>.+))?$'
)


def _parse_lsusb_output(stdout):
    """
    :type output: str
    :rtype: List[UsbDevice]
    """

    devices = map(UsbDevice.parse_line, stdout.splitlines())
    return list(filter(None, devices))


def get_usb_devices():
    """
    :rtype: twisted.internet.defer.Deferred[List[UsbDevice]]
    """

    logger.info(search_usb)
    deferred = getProcessOutput('lsusb', env=os.environ)
    deferred.addCallback(encode_proc_output)
    deferred.addCallback(_parse_lsusb_output)
    return deferred


class Wrapper:

    def __init__(self, original):
        self.__dict__["original"] = original

    def __getattr__(self, name):
        try:
            return getattr(self.original, name)
        except AttributeError:
            raise AttributeError("{0.__class__.__name__}.{1}".format(
                self, name))

    def __setattr__(self, name, value):
        if name in self.__dict__:
            self.__dict__[name] = value
        else:
            for klass in self.__class__.__mro__:
                if name in klass.__dict__:
                    self.__dict__[name] = value
                    break
            else:
                setattr(self.original, name, value)


class VMPlug(Wrapper):

    def __init__(self, plug):
        Wrapper.__init__(self, plug)
        self.model = "rtl8139"
        self.mac = tools.random_mac()


class VMSock(Wrapper):

    def __init__(self, sock):
        Wrapper.__init__(self, sock)
        self.model = "rtl8139"
        self.mac = tools.random_mac()

    def connect(self, endpoint):
        return


class _FakeBrick:

    name = "hostonly"

    def poweron(self):
        return defer.succeed(self)


class _HostonlySock:
    """
    This is dummy implementation of a VMSock used with VirtualMachines that
    want a plug that is not connected to nothing. The instance is a singleton,
    but not enforced anyhow, maybe a better solution is to have a different
    hostonly socket for each plug and let the brick choose which socket should
    be saved and which not.
    """

    nickname = "_hostonly"
    path = "?"
    model = "?"
    mac = "?"
    mode = "hostonly"
    brick = _FakeBrick()
    plugs = []


hostonly_sock = _HostonlySock()


def sizeof_fmt(num, suffix='B'):
    """
    :type num: Union[float, int, str]
    :type suffix: str
    :rtype: str
    """

    num = float(num)
    for unit in '', 'Ki', 'Mi':
        if abs(num) < 1024.0:
            return '{num:.1f}{unit}{suffix}'.format(num=num, unit=unit, suffix=suffix)
        num /= 1024.0
    return '{num:.1f}Gi{suffix}'.format(num=num, suffix=suffix)


class Image:

    readonly = False
    master = None

    def __init__(self, name, path, description=''):
        """
        :type name: str
        :type path: str
        :type description: str
        """

        self._name = name
        self._path = os.path.abspath(path)
        self._description = description
        self.changed = Event(Observable(), 'changed')

    def get_name(self):
        """
        :rtype: str
        """

        return self._name

    def set_name(self, value):
        """
        :type value: str
        """

        self._name = value
        self.changed.notify(self)

    def _get_name_prop(self):
        warnings.warn('Image.name', DeprecationWarning)
        return self.get_name()

    def _set_name_prop(self, value):
        warnings.warn('Image.name', DeprecationWarning)
        return self.set_name(value)

    name = property(_get_name_prop, _set_name_prop)

    def get_path(self):
        """
        :rtype: str
        """

        return self._path

    def set_path(self, value):
        """
        :type value: str
        """

        self._path = value
        self.changed.notify(self)

    def _get_path_prop(self):
        warnings.warn('Image.path', DeprecationWarning)
        return self.get_path()

    def _set_path_prop(self, value):
        warnings.warn('Image.path', DeprecationWarning)
        return self.set_path(value)

    path = property(_get_path_prop, _set_path_prop)

    def get_description(self):
        """
        :rtype: str
        """

        return self._description

    def set_description(self, description):
        """
        :type value: str
        """

        if self._description != description:
            self._description = description
            self.changed.notify(self)

    def _get_description_prop(self):
        warnings.warn('Image.description', DeprecationWarning)
        return self.get_description()

    def _set_description_prop(self, value):
        warnings.warn('Image.description', DeprecationWarning)
        return self.set_description(value)

    description = property(_get_description_prop, _set_description_prop)

    def basename(self):
        return os.path.basename(self.path)

    def get_size(self):
        """
        :rtype: str
        """

        if not self.exists():
            return '0B'
        return sizeof_fmt(os.path.getsize(self.path))

    def exists(self):
        return os.path.exists(self.path)

    def acquire(self, disk):
        """
        :type disk: virtualbricks.virtualmachines.Disk
        :rtype: None
        """

        if self.master is None:
            self.master = disk
        elif self.master is disk:
            # TODO: check this case
            pass
        else:
            raise errors.LockedImageError(self, self.master)

    def release(self, disk):
        """
        :type disk: virtualbricks.virtualmachines.Disk
        :rtype: None
        """

        # TODO: remove parameter
        if self.master is disk:
            self.master = None
        else:
            raise errors.LockedImageError(self, self.master)

    def save_to(self, fileobj):
        """
        Save the configuration of this disk image to fileobj.

        :type fileobj: io.TextIOBase
        """

        # TODO: horrible but I need a quit solution for flattening the
        # description to one line until _configparser will be replaced by the
        # stdlib configparser.
        description = '<nl>'.join(self.get_description().splitlines())
        fileobj.write((
            '[Image:{self.name}]\n'
            'path={self.path}\n'
            'description={description}\n\n'
        ).format(self=self, description=description))

    def __format__(self, format_string):
        if format_string in ("n", ""):
            return str(self.name)
        elif format_string == "p":
            return str(self.path)
        elif format_string == "d":
            return str(self.get_description())
        elif format_string == "m":
            if self.master is None:
                return ""
            return repr(self.master)
        elif format_string == "s":
            return self.get_size()
        raise ValueError("invalid format string " + repr(format_string))


def is_disk_image(brick):
    return isinstance(brick, Image)


def move(src, dst):
    try:
        os.rename(src, dst)
    except OSError as e:
        if e.errno == errno.EXDEV:
            shutil.move(src, dst)
        else:
            raise


class Disk:

    @property
    def cow(self):
        return self.is_cow()

    def __init__(self, vm, dev, image=None):
        """
        :param VirtualMachines vm:
        :param str dev:
        :param Optional[Image] image:
        """

        self.vm = vm
        self.device = dev
        self.image = image

    def is_cow(self):
        return self.vm.config['private' + self.device]

    def _basefolder(self):
        return project.manager.current.path

    def args(self):

        def cb(disk_name):
            if self.vm.get('use_virtio'):
                return ['-drive', 'file={0},if=virtio'.format(disk_name)]
            else:
                return ['-' + self.device, disk_name]

        if self.image:
            d = self.get_real_disk_name()
            d.addCallback(cb)
            return d
        else:
            # TODO: check!! Maybe return a failure?
            return defer.succeed([])

    def set_image(self, image):
        self.image = image

    def acquire(self):
        self.lock_image()

    def lock_image(self):
        """
        Acquire a lock on the image. The image can be locked multiple times by
        the same disk but the first call to unlock_image will release all the
        locks.

        If the image is a private COW or in readonly mode, the image won't be
        locked.
        """

        if self.image is not None and not self.is_cow() and not self.readonly():
            self.image.acquire(self)

    def release(self):
        self.unlock_image()

    def unlock_image(self):
        """
        Release the lock on the image.
        """

        if self.image is not None and not self.is_cow() and not self.readonly():
            self.image.release(self)

    def _new_disk_image_differential(self, filename):
        """
        Create a new disk image for Qemu with the given name. The new disk
        image is a differential of this disk image (self.image.path).

        :param str filename: the name of the new disk image.
        :return: A Deferred that fires when the image has been created.
        :rtype: twisted.internet.defer.Deferred[None]
        """

        assert self.image is not None

        logger.info(new_cow, backup_file=self.image.path)
        args = [
            'create', '-b', self.image.path, '-f', settings.get('cowfmt'),
            filename
        ]
        deferred = qemu_img(args)
        deferred.addCallback(discard_first_arg(sync))
        # Always return None, independently of the return from sync
        deferred.addCallback(lambda _: None)
        return deferred

    def _ensure_private_image_cow(self, image_file):
        """
        Ensure that the private disk image exists and its backing file is this
        disk image (self.image.path).

        If the file does not exist, it is created.

        If the file ``image_file`` exists, check that its backing file is this
        disk image. If the backing file is correct, do nothing. If the file
        exists but the backing file is the wrong one or it is an unknown file
        type, backup the file and create a new private image file

        :param str image_file: the private cow image file for which we search
            the backing file.
        :rtype: twisted.internet.defer.Deferred[None]
        """

        assert self.image is not None

        try:
            os.makedirs(self._basefolder())
        except FileExistsError:
            pass
        except Exception:
            return defer.fail()
        try:
            backing_file = tools.get_backing_file(image_file)
        except FileNotFoundError:
            # TODO
            # logger.debug(new_private_image_file, image_file=image_file)
            return self._new_disk_image_differential(image_file)
        except NotCowFileError:
            # TODO
            # logger.debug(invalid_image_file, image_file=image_file)
            return self._new_disk_image_differential(image_file)
        except Exception:
            # Any IOError
            return defer.fail()
        expected_backing_file = self.image.path
        if backing_file == expected_backing_file:
            logger.debug(use_backing_file, imagefile=image_file,
                         backing_file=backing_file)
            return defer.succeed(None)
        else:
            now = datetime.datetime.now()
            backup_file = '{image_file}.bak-{now:%Y%m%d-%H%M%S}'.format(image_file=image_file, now=now)
            logger.warn(
                invalid_base,
                private_cow=image_file,
                expected_backing_file=expected_backing_file,
                found_backing_file=backing_file,
                backup_file=backup_file
            )
            move(image_file, backup_file)
            return self._new_disk_image_differential(image_file)

    def get_cow_path(self):
        """
        Return the fullpath of the (private) image file that will be used for
        this disk devide.

        :rtype: str
        """

        filename = '{self.vm.name}_{self.device}.cow'.format(self=self)
        return os.path.join(self._basefolder(), filename)

    def get_real_disk_name(self):
        return self.disk_image_path()

    def disk_image_path(self):
        """
        Return the path of the image used with this disk.

        If the image is differential, ensure that it exists and the backing
        file is the correct one.

        :rtype: twisted.internet.defer.Deferred[str]
        """

        # TODO: what if the image file does not exist?
        # assert self.image is not None
        if self.image is None:
            # XXX: this should be really an error
            return defer.succeed('No image file set for this disk')
        if self.is_cow():
            private_image_path = self.get_cow_path()
            deferred = self._ensure_private_image_cow(private_image_path)
            deferred.addCallback(lambda _: private_image_path)
            return deferred
        else:
            return defer.succeed(self.image.path)

    def readonly(self):
        return self.vm.config['snapshot']

    def __deepcopy__(self, memo):
        new = self.__class__(self.vm, self.device, self.image)
        return new

    def __repr__(self):
        return (
            '<Disk {self.device}({self.vm.name}) image={self.image:p} '
            'readonly={readonly} cow={is_cow}>'
        ).format(self=self, readonly=self.readonly(), is_cow=self.is_cow())


VM_COMMAND_BUILDER = {
        "#argv0": "argv0",
        "#M": "machine",
        "#cpu": "cpu",
        "-smp": "smp",
        "-m": "ram",
        "-boot": "boot",
        # numa not supported
        "#privatehda": "privatehda",
        "#privatehdb": "privatehdb",
        "#privatehdc": "privatehdc",
        "#privatehdd": "privatehdd",
        "#privatefda": "privatefda",
        "#privatefdb": "privatefdb",
        "#privatemtdblock": "privatemtdblock",
        "#cdrom": "cdrom",
        "#device": "device",
        "#cdromen": "cdromen",
        "#deviceen": "deviceen",
        "#keyboard": "keyboard",
        "#usbdevlist": "usbdevlist",
        "-soundhw": "soundhw",
        "-usb": "usbmode",
        # "-uuid": "uuid",
        # "-curses": "curses", ## not implemented
        # "-no-frame": "noframe", ## not implemented
        # "-no-quit": "noquit", ## not implemented.
        "-snapshot": "snapshot",
        "#vga": "vga",
        "#vncN": "vncN",
        "#vnc": "vnc",
        # "-full-screen": "full-screen", ## TODO 0.3
        "-sdl": "sdl",
        "-portrait": "portrait",
        "-win2k-hack": "win2k",  # not implemented
        "-no-acpi": "noacpi",
        # "-no-hpet": "nohpet", ## ???
        # "-baloon": "baloon", ## ???
        # #acpitable not supported
        # #smbios not supported
        "#kernel": "kernel",
        "#kernelenbl": "kernelenbl",
        "#append": "kopt",
        "#initrd": "initrd",
        "#initrdenbl": "initrdenbl",
        # "-serial": "serial",
        # "-parallel": "parallel",
        # "-monitor": "monitor",
        # "-qmp": "qmp",
        # "-mon": "",
        # "-pidfile": "", ## not needed
        # "-singlestep": "",
        # "-S": "",
        "#gdb_e": "gdb",
        "#gdb_port": "gdbport",
        # "-s": "",
        # "-d": "",
        # "-hdachs": "",
        # "-L": "",
        # "-bios": "",
        "#kvm": "kvm",
        # "-no-reboot": "", ## not supported
        # "-no-shutdown": "", ## not supported
        "-loadvm": "loadvm",
        # "-daemonize": "", ## not supported
        # "-option-rom": "",
        # "-clock": "",
        "#rtc": "rtc",
        # "-icount": "",
        # "-watchdog": "",
        # "-watchdog-action": "",
        # "-echr": "",
        # "-virtioconsole": "", ## future
        # "-show-cursor": "",
        # "-tb-size": "",
        # "-incoming": "",
        # "-nodefaults": "",
        # "-chroot": "",
        # "-runas": "",
        # "-readconfig": "",
        # "-writeconfig": "",
        # "-no-kvm": "", ## already implemented otherwise
        # "-no-kvm-irqchip": "",
        # "-no-kvm-pit": "",
        # "-no-kvm-pit-reinjection": "",
        # "-pcidevice": "",
        # "-enable-nesting": "",
        # "-nvram": "",
        "#kvmsm": "kvmsm",
        "#kvmsmem": "kvmsmem",
        # "-mem-path": "",
        # "-mem-prealloc": "",
        "#icon": "icon",
        "#serial": "serial",
        "#stdout": ""}


class DefaultDevice:

    def __ne__(self, other):
        if isinstance(other, Disk):
            return other.image is not None
        return NotImplemented

    def __eq__(self, other):
        return not self != other


default_device = DefaultDevice()


class Device(bricks.Parameter):

    def __init__(self, name):
        self.name = name
        bricks.Parameter.__init__(self, default_device)

    def from_string_brick(self, in_string, brick):
        disk = brick.config[self.name]
        disk.set_image(brick.factory.get_image_by_name(in_string))
        return disk

    def to_string(self, disk):
        if disk.image is not None:
            return disk.image.name
        return ""


class UsbDeviceParameter(bricks.String):

    def from_string(self, in_string):
        return UsbDevice(in_string)

    def to_string(self, in_object):
        return str(in_object)


class VirtualMachineConfig(bricks.Config):

    parameters = {"name": bricks.String(""),

                  # boot options
                  "boot": bricks.String(""),
                  "snapshot": bricks.Boolean(False),

                  # cdrom device
                  "deviceen": bricks.Boolean(False),
                  "device": bricks.String(""),
                  "cdromen": bricks.Boolean(False),
                  "cdrom": bricks.String(""),

                  # additional media
                  "use_virtio": bricks.Boolean(False),

                  "hda": Device("hda"),
                  "privatehda": bricks.Boolean(False),

                  "hdb": Device("hdb"),
                  "privatehdb": bricks.Boolean(False),

                  "hdc": Device("hdc"),
                  "privatehdc": bricks.Boolean(False),

                  "hdd": Device("hdd"),
                  "privatehdd": bricks.Boolean(False),

                  "fda": Device("fda"),
                  "privatefda": bricks.Boolean(False),

                  "fdb": Device("fdb"),
                  "privatefdb": bricks.Boolean(False),

                  "mtdblock": Device("mtdblock"),
                  "privatemtdblock": bricks.Boolean(False),

                  # system and machine
                  "argv0": bricks.String("qemu-system-i386"),
                  "cpu": bricks.String(""),
                  "machine": bricks.String(""),
                  "kvm": bricks.Boolean(False),
                  "smp": bricks.SpinInt(1, 1, 64),

                  # audio device soundcard
                  "soundhw": bricks.String(""),

                  # memory device settings
                  "ram": bricks.SpinInt(64, 1, 99999),
                  "kvmsm": bricks.Boolean(False),
                  "kvmsmem": bricks.SpinInt(1, 0, 99999),

                  # display options
                  "novga": bricks.Boolean(False),
                  "vga": bricks.Boolean(False),
                  "vnc": bricks.Boolean(False),
                  "vncN": bricks.SpinInt(1, 0, 500),
                  "sdl": bricks.Boolean(False),
                  "portrait": bricks.Boolean(False),

                  # usb settings
                  "usbmode": bricks.Boolean(False),
                  "usbdevlist": bricks.ListOf(UsbDeviceParameter("")),

                  # extra settings
                  "rtc": bricks.Boolean(False),
                  "tdf": bricks.Boolean(False),
                  "keyboard": bricks.String(""),
                  "serial": bricks.Boolean(False),

                  # booting linux
                  "kernelenbl": bricks.Boolean(False),
                  "kernel": bricks.String(""),
                  "initrdenbl": bricks.Boolean(False),
                  "initrd": bricks.String(""),
                  "kopt": bricks.String(""),
                  "gdb": bricks.Boolean(False),
                  "gdbport": bricks.SpinInt(1234, 1, 65535),

                  # virtual machine icon
                  "icon": bricks.String(""),

                  # others
                  "noacpi": bricks.String(""),
                  "stdout": bricks.String(""),
                  "loadvm": bricks.String("")}


def _get_nick(link):
    if hasattr(link, "sock"):
        return str(getattr(link.sock, "nickname", "None"))
    return "None"


class VirtualMachine(bricks.Brick):

    type = "Qemu"
    term_command = "unixterm"
    command_builder = VM_COMMAND_BUILDER
    config_factory = VirtualMachineConfig
    process_protocol = bricks.Process
    default_arg0 = 'qemu-system-x86_64'

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self._observable.add_event("image-changed")
        self.image_changed = Event(self._observable, 'image-changed')
        self.config["name"] = name
        for dev in "hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock":
            self.config[dev] = Disk(self, dev)

    def rename(self, new_name):
        """
        Override Brick.rename() to rename also the disks.

        :type new_name: str
        :rtype: None
        """

        # TODO: logs
        # TODO: rewind in case of error
        prev_name = super().rename(new_name)
        project_path = pathlib.Path(project.manager.current.path)
        disk_regex = re.compile((
            '{prev_name}_'                                # vm name
            '(?P<disk>[a-z0-9]+)'                         # disk
            '.cow'                                        # extension
            r'(?P<bak_suffix>\.(?:bak|back)-[0-9\-_]+)?'  # backup suffix
            '$'                                           # end
        ).format(prev_name=prev_name))
        new_name_repl = r'{new_name}_\g<disk>.cow\g<bak_suffix>'.format(new_name=new_name)
        for path in project_path.iterdir():
            if path.is_file() and disk_regex.match(path.name):
                new_disk_name = disk_regex.sub(new_name_repl, path.name)
                path.rename(project_path.joinpath(new_disk_name))
        return prev_name

    def poweron(self, snapshot=""):
        def acquire(passthru):
            self.acquire()
            return passthru

        def release(passthru):
            self.release()
            return passthru

        def clear_snapshot(passthru):
            self.config["loadvm"] = ""
            return passthru

        self.config["loadvm"] = snapshot
        d = bricks.Brick.poweron(self)
        d.addCallback(acquire).addBoth(clear_snapshot)
        self._exited_d.addBoth(release)
        return d

    def poweroff(self, kill=False, term=False):
        if self.proc is None:
            return defer.succeed((self, self._last_status))
        elif not any((kill, term)):
            self.logger.info(powerdown, vm=self)
            self.send(b"system_powerdown\n")
            return self._exited_d
        if term:
            return bricks.Brick.poweroff(self)
        else:
            return bricks.Brick.poweroff(self, kill)

    def get_parameters(self):
        ram = self.config["ram"]
        txt = [_("command:") + " %s, ram: %s" % (self.prog(), ram)]
        for i, link in enumerate(itertools.chain(self.plugs, self.socks)):
            txt.append("eth%d: %s" % (i, _get_nick(link)))
        return ", ".join(txt)

    def update_usbdevlist(self, dev):
        self.logger.debug(update_usb, old=self.config['usbdevlist'], new=dev)
        for usb_dev in set(dev) - set(self.config['usbdevlist']):
            self.send('usb_add host:{usb_dev.id}\n'.format(usb_dev=usb_dev))
        # FIXME: Don't know how to remove old devices, due to the ugly syntax
        # of usb_del command.

    def configured(self):
        # return all([p.configured() for p in self.plugs])
        for p in self.plugs:
            if p.sock is None and p.mode == 'vde':
                return False
        return True

    def prog(self):
        if self.config["argv0"]:
            arg0 = self.config['argv0']
        else:
            arg0 = self.default_arg0
        return abspath_qemu(arg0)

    def args(self):
        d = defer.gatherResults([disk.args() for disk in self.disks()])
        d.addCallback(self.__args)
        return d

    def __args(self, results):
        res = [self.prog()]
        if (self.config['kvm'] or self.config['machine'] or
                self.config['kvmsm']):
            props = []
            if self.config["machine"]:
                props.append('type={}'.format(self.config["machine"]))
            if self.config['kvm']:
                props.append('accel=kvm:tcg')
            if self.config["kvmsm"]:
                props.append(
                    'kvm_shadow_mem={}'.format(self.config["kvmsmem"])
                )
            res.extend(['-machine', ','.join(props)])

        if self.config["cpu"]:
            res.extend(["-cpu", self.config["cpu"]])
        res.extend(list(self.build_cmd_line()))
        if self.config["novga"]:
            res.extend(["-display", "none"])
        for disk_args in results:
            res.extend(disk_args)
        if self.config["kernelenbl"] and self.config["kernel"]:
            res.extend(["-kernel", self.config["kernel"]])
        if self.config["initrdenbl"] and self.config["initrd"]:
            res.extend(["-initrd", self.config["initrd"]])
        if (self.config["kopt"] and self.config["kernelenbl"] and
                self.config["kernel"]):
            res.extend([
                "-append",
                "'{0}'".format(re.sub("\"", "", self.config["kopt"]))
            ])
        if self.config["gdb"]:
            res.extend(["-gdb", "tcp::%d" % self.config["gdbport"]])
        if self.config["vnc"]:
            res.extend(["-vnc", ":%d" % self.config["vncN"]])
        if self.config["vga"]:
            res.extend(["-vga", "std"])

        if self.config["usbmode"]:
            for usb_dev in self.config["usbdevlist"]:
                res.extend(['-usbdevice',
                            'host:{usb_dev.id}'.format(usb_dev=usb_dev)])

        res.extend(["-name", self.name])
        if not self.plugs and not self.socks:
            res.extend(["-net", "none"])
        else:
            for i, link in enumerate(itertools.chain(self.plugs, self.socks)):
                res.append("-device")
                res.append("{1.model},mac={1.mac},id=vx{0},netdev=vx{0}".format(
                    i, link))
                if link.sock and link.sock.mode == "hostonly":
                    res.extend(("-netdev", "user,id=vx{0}".format(i)))
                elif link.mode == "vde":
                    res.append("-netdev")
                    res.append("vde,id=vx{0},sock={1}".format(
                        i, link.sock.path.rstrip('[]')))
                elif link.mode == "sock":
                    res.append("-netdev")
                    res.append("vde,id=vx{0},sock={1}".format(
                        i, link.path))
                else:
                    res.extend(["-netdev", "user"])

        if self.config["cdromen"] and self.config["cdrom"]:
                res.extend(["-cdrom", self.config["cdrom"]])
        elif self.config["deviceen"] and self.config["device"]:
                res.extend(["-cdrom", self.config["device"]])
        if (self.config["rtc"] or self.config["tdf"]):
            rtcarg = []
            if self.config['rtc']:
                rtcarg.append('base=localtime')
            if self.config['tdf']:
                rtcarg.append('driftfix=slew')
            res.extend(['-rtc', ','.join(rtcarg)])
        if len(self.config["keyboard"]) == 2:
            res.extend(["-k", self.config["keyboard"]])
        if self.config["serial"]:
            res.extend(["-serial", "unix:%s/%s_serial,server,nowait" %
                        (settings.VIRTUALBRICKS_HOME, self.name)])
        res.extend(["-mon", "chardev=mon", "-chardev",
                    "socket,id=mon,path=%s,server,nowait" %
                    self.console(),
                    "-mon", "chardev=mon_cons", "-chardev",
                    "stdio,id=mon_cons,signal=off"])
        return res

    def add_sock(self, mac=None, model=None):
        s = self.factory.new_sock(self)
        sock = VMSock(s)
        vlan = len(self.plugs) + len(self.socks)
        sock.path = "{0}/{1.brick.name}_sock_eth{2}[]".format(
            settings.VIRTUALBRICKS_HOME, sock, vlan)
        sock.nickname = "{0.brick.name}_sock_eth{1}".format(sock, vlan)
        self.socks.append(sock)
        if mac:
            sock.mac = mac
        if model:
            sock.model = model
        return sock

    def add_plug(self, sock, mac=None, model=None):
        plug = VMPlug(self.factory.new_plug(self))
        self.plugs.append(plug)
        if sock:
            plug.connect(sock)
        if mac:
            plug.mac = mac
        if model:
            plug.model = model
        return plug

    def connect(self, sock, *args):
        self.add_plug(sock, *args)

    def remove_plug(self, plug):
        try:
            if plug.mode == "sock":
                self.socks.remove(plug)
            else:
                self.plugs.remove(plug)
        except ValueError:
            self.logger.error(own_err, plug=plug, brick=self)

    def commit_disks(self, args):
        # XXX: fixme
        self.send("commit all\n")

    def acquire(self):
        """Acquire locks on images if needed."""
        self.logger.debug(acquire_lock)
        acquired = []
        for disk in self.disks():
            try:
                disk.acquire()
            except errors.LockedImageError:
                for _disk in acquired:
                    _disk.release()
                raise
            else:
                acquired.append(disk)

    def release(self):
        self.logger.debug(release_lock)
        for disk in self.disks():
            disk.release()

    def disks(self):
        for hd in "hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock":
            yield self.config[hd]

    def set_image(self, disk, image):
        self.config[disk].image = image
        if not self._restore:
            self._observable.notify("image-changed", (self, image))

    def set_vm(self, disk):
        disk.vm = self

    cbset_hda = cbset_hdb = cbset_hdc = cbset_hdd = cbset_fda = cbset_fdb = \
            cbset_mtblock = set_vm


def is_virtualmachine(brick):
    return brick.get_type() == "Qemu"
