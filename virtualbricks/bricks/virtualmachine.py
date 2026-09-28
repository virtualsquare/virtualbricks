# -*- test-case-name: virtualbricks.tests.bricks.test_virtualmachine -*-
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

from dataclasses import dataclass
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
from twisted.logger import Logger

from virtualbricks import bricks, errors, tools
from virtualbricks.bricks.command import Command, Prepared, joined, socket_path
from virtualbricks.config.projectfile import DEFAULT_MODEL
from virtualbricks.config.schema import (
    Bool,
    Choice,
    Int,
    Kind,
    ListOf,
    Path,
    Ref,
    Str,
    define,
    field,
)
from virtualbricks.config.settings import get_setting
from virtualbricks.config.workspace import projects
from virtualbricks.i18n import _
from virtualbricks.nic import random_mac
from virtualbricks.programs import PACKAGES, Missing, ProgramError, programs
from virtualbricks.spawn import abspath_qemu, encode_proc_output, qemu_img
from virtualbricks.observable import Event, Observable
from virtualbricks.tools import NotCowFileError, discard_first_arg, sync

logger = Logger()
new_cow = (
    "Creating a new private COW from a base image. backing_file={backing_file}"
)
use_backing_file = (
    "Using  backing file for private cow. backing_file={backing_file}"
    " image_file={imagefile}"
)
invalid_base = (
    "Private cow found with a different backing image. Backup the private cow"
    " and use a new one. private_cow={private_cow}"
    " expected_backing_file={expected_backing_file}"
    " found_backing_file={found_backing_file} backup_file={backup_file}"
)
powerdown = "Sending powerdown to {vm}"
update_usb = "update_usb_devices: old {old} - new {new}"
own_err = "plug {plug} does not belong to {brick}"
acquire_lock = "Aquiring disk locks"
release_lock = "Releasing disk locks"
search_usb = "Searching USB devices"


@dataclass(frozen=True)
class UsbDevice:

    id: str
    description: str

    @classmethod
    def parse_line(cls, line):
        """
        :type line: str
        :rtype: Optional[UsbDevice]
        """

        matchobj = LSUSB_REGEX.search(line)
        if matchobj:
            dev_id = matchobj.group("id")
            description = matchobj.group("description").strip()
            return cls(dev_id, description)

    @property
    def ID(self):
        return self.id

    @property
    def desc(self):
        return self.description

    def __str__(self):
        return self.id

    # def __repr__(self):
    #     return self.id

    def __format__(self, format_string):
        if format_string == "id" or format_string == "":
            return self.id
        elif format_string == "d":
            return self.description
        raise ValueError("invalid format string {format_string!r}")


LSUSB_REGEX = re.compile(r"(?P<id>\w{4}:\w{4})" r"(?:\s(?P<description>.+))?$")
USB_ID = re.compile(r"\w{4}:\w{4}")


class UsbDeviceKind(Kind):
    """A USB device, stored as ``{ id, description }``."""

    def check(self, value):
        if not isinstance(value, UsbDevice):
            raise ValueError(f"{value!r} is not a USB device")

    def to_data(self, value):
        return {"id": value.id, "description": value.description}

    def from_data(self, data, report, where):
        if not isinstance(data, dict):
            raise ValueError(f"{data!r} is not a table")
        dev_id = data.get("id")
        description = data.get("description", "")
        if not isinstance(dev_id, str) or not USB_ID.fullmatch(dev_id):
            raise ValueError(f"{dev_id!r} is not a USB id")
        if not isinstance(description, str):
            raise ValueError(f"{description!r} is not a description")
        for key in data.keys() - {"id", "description"}:
            report.warning("unknown field, dropped", f"{where}.{key}")
        return UsbDevice(dev_id, description)

    def format(self, value):
        return value.id


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
    deferred = getProcessOutput("lsusb", env=os.environ)
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
            raise AttributeError(
                "{0.__class__.__name__}.{1}".format(self, name)
            )

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
        self.mac = random_mac()


class VMSock(Wrapper):

    def __init__(self, sock):
        Wrapper.__init__(self, sock)
        self.model = "rtl8139"
        self.mac = random_mac()

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


class Image:

    readonly = False
    master = None

    def __init__(self, name, path, description=""):
        """
        :type name: str
        :type path: str
        :type description: str
        """

        self._name = name
        self._path = os.path.abspath(path)
        self._description = description
        self.changed = Event(Observable(), "changed")

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
        warnings.warn("Image.name", DeprecationWarning)
        return self.get_name()

    def _set_name_prop(self, value):
        warnings.warn("Image.name", DeprecationWarning)
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
        warnings.warn("Image.path", DeprecationWarning)
        return self.get_path()

    def _set_path_prop(self, value):
        warnings.warn("Image.path", DeprecationWarning)
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
        warnings.warn("Image.description", DeprecationWarning)
        return self.get_description()

    def _set_description_prop(self, value):
        warnings.warn("Image.description", DeprecationWarning)
        return self.set_description(value)

    description = property(_get_description_prop, _set_description_prop)

    def basename(self):
        return os.path.basename(self.path)

    def exists(self):
        return os.path.exists(self.path)

    def acquire(self, disk):
        """
        :type disk: virtualbricks.bricks.virtualmachine.Disk
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
        :type disk: virtualbricks.bricks.virtualmachine.Disk
        :rtype: None
        """

        # TODO: remove parameter
        if self.master is disk:
            self.master = None
        else:
            raise errors.LockedImageError(self, self.master)

    def __format__(self, format_string):
        if format_string in ("n", ""):
            return str(self.name)
        elif format_string == "p":
            return str(self.path)
        elif format_string == "d":
            return str(self.get_description())
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

    def __init__(self, vm, dev):
        """
        :param VirtualMachines vm:
        :param str dev:
        """

        self.vm = vm
        self.device = dev

    @property
    def image(self):
        """The image named in the configuration, if it's in the library."""

        name = getattr(self.vm.config, f"{self.device}_image")
        if not name:
            return None
        return self.vm.factory.get_image_by_name(name)

    def set_image(self, image):
        name = "" if image is None else image.get_name()
        setattr(self.vm.config, f"{self.device}_image", name)

    def is_cow(self):
        return getattr(self.vm.config, f"{self.device}_private")

    def _basefolder(self):
        return projects.current.path

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

        if (
            self.image is not None
            and not self.is_cow()
            and not self.readonly()
        ):
            self.image.acquire(self)

    def release(self):
        self.unlock_image()

    def unlock_image(self):
        """
        Release the lock on the image.
        """

        if (
            self.image is not None
            and not self.is_cow()
            and not self.readonly()
        ):
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

        logger.info(new_cow, backing_file=self.image.path)
        args = [
            "create",
            "-f",
            get_setting("cow_format"),
            "-b",
            self.image.path,
            "-F",
            get_setting("cow_format"),
            filename,
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
            logger.debug(
                use_backing_file,
                imagefile=image_file,
                backing_file=backing_file,
            )
            return defer.succeed(None)
        else:
            now = datetime.datetime.now()
            backup_file = f"{image_file}.bak-{now:%Y%m%d-%H%M%S}"
            logger.warn(
                invalid_base,
                private_cow=image_file,
                expected_backing_file=expected_backing_file,
                found_backing_file=backing_file,
                backup_file=backup_file,
            )
            move(image_file, backup_file)
            return self._new_disk_image_differential(image_file)

    def get_cow_path(self):
        """
        Return the fullpath of the (private) image file that will be used for
        this disk devide.

        :rtype: str
        """

        filename = f"{self.vm.name}_{self.device}.cow"
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
            return defer.succeed("No image file set for this disk")
        if self.is_cow():
            private_image_path = self.get_cow_path()
            deferred = self._ensure_private_image_cow(private_image_path)
            deferred.addCallback(lambda _: private_image_path)
            return deferred
        else:
            return defer.succeed(self.image.path)

    def readonly(self):
        return self.vm.config.forget_disk_changes

    def __repr__(self):
        return (
            f"<Disk {self.device}({self.vm.name}) image={self.image:p} "
            f"readonly={self.readonly()} cow={self.is_cow()}>"
        )


DISK_DEVICES = ("hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock")


def _image(dev):
    """
    The field of the image of a disk device, such as ``hda``.

    It holds the name of an image of the project, or "" for none, and the
    project file writes it as the ``image`` key of the ``[disks.<dev>]``
    table of the brick, not as a key named after the device.

    Without this function each disk field would repeat the kind, the default
    and the path. Leaving the path out changes the format of the project file:
    the field would then be written as a top-level ``hda_image = "..."`` key
    of the brick, which the project files don't have.
    """

    return field(Ref("image"), default="", path=("disks", dev, "image"))


def _private(dev):
    """
    The field that makes a disk device, such as ``hda``, private.

    When it's true the virtual machine writes to its own copy-on-write file,
    ``<vm>_<dev>.cow`` in the project directory, and the image stays as it is.
    The project file writes it as the ``private`` key of the ``[disks.<dev>]``
    table of the brick.

    As for :func:`_image`, without this function each field would repeat the
    kind, the default and the path, and leaving the path out would write a
    top-level ``hda_private = ...`` key instead, a different file format.
    """

    return field(Bool(), default=False, path=("disks", dev, "private"))


@define
class VirtualMachineConfig(bricks.BrickConfig):
    """
    The configuration of a virtual machine.

    The order of the fields is the order of the keys in the project file.
    """

    # the program and the machine
    qemu_program = field(Str(required=True), default="qemu-system-i386")
    machine_type = field(Str(), default="")
    cpu_model = field(Str(), default="")
    use_kvm = field(Bool(), default=False)
    cpus = field(Int(1, 64), default=1)
    # in MiB
    memory = field(Int(1, 99999), default=64)
    use_kvm_shadow_memory = field(Bool(), default=False)
    kvm_shadow_memory = field(Int(0, 99999), default=1)
    # the boot and the disks
    boot_order = field(Str(), default="")
    forget_disk_changes = field(Bool(), default=False)
    virtio_disks = field(Bool(), default=False)
    # the CD-ROM: none, an image file, or a drive of the host
    cdrom = field(Choice("none", "image", "device"), default="none")
    cdrom_image = field(Path(), default="")
    cdrom_device = field(Str(), default="")
    # the display
    headless = field(Bool(), default=False)
    standard_vga = field(Bool(), default=False)
    use_vnc = field(Bool(), default=False)
    vnc_display = field(Int(0, 500), default=1)
    sdl_window = field(Bool(), default=False)
    # sound and USB
    sound_card = field(Str(), default="")
    use_usb = field(Bool(), default=False)
    usb_devices = field(ListOf(UsbDeviceKind()), factory=list)
    # the keyboard, the clock and the serial port
    keyboard_layout = field(Str(), default="")
    clock_local_time = field(Bool(), default=False)
    clock_drift_fix = field(Bool(), default=False)
    serial_socket = field(Bool(), default=False)
    # booting a kernel directly, and debugging it
    use_kernel = field(Bool(), default=False)
    kernel = field(Path(), default="")
    use_initrd = field(Bool(), default=False)
    initrd = field(Path(), default="")
    kernel_command_line = field(Str(), default="")
    use_gdb = field(Bool(), default=False)
    gdb_port = field(Int(1, 65535), default=1234)
    acpi = field(Bool(), default=True)
    # the disks, one per device of DISK_DEVICES, in the same order
    hda_image = _image("hda")
    hda_private = _private("hda")
    hdb_image = _image("hdb")
    hdb_private = _private("hdb")
    hdc_image = _image("hdc")
    hdc_private = _private("hdc")
    hdd_image = _image("hdd")
    hdd_private = _private("hdd")
    fda_image = _image("fda")
    fda_private = _private("fda")
    fdb_image = _image("fdb")
    fdb_private = _private("fdb")
    mtdblock_image = _image("mtdblock")
    mtdblock_private = _private("mtdblock")


def _get_nick(link):
    if hasattr(link, "sock"):
        return str(getattr(link.sock, "nickname", "None"))
    return "None"


class VirtualMachine(bricks.Brick):

    type = "Qemu"
    term_command = "unixterm"
    config_factory = VirtualMachineConfig
    process_protocol = bricks.Process
    connections = "nics"

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self._observable.add_event("image-changed")
        self.image_changed = Event(self._observable, "image-changed")
        self._disks = {dev: Disk(self, dev) for dev in DISK_DEVICES}

    def set_name(self, name):
        prefix = f"{self.name}_"
        bricks.Brick.set_name(self, name)
        for sock in self.socks:
            if sock.nickname.startswith(prefix):
                suffix = sock.nickname[len(prefix) :]
                sock.nickname = f"{name}_{suffix}"
                sock.path = self.runtime_path(f"{name}_{suffix}[]")

    name = property(bricks.Brick.get_name, set_name)

    def rename(self, new_name):
        """
        Override Brick.rename() to rename also the disks.

        :type new_name: str
        :rtype: None
        """

        # TODO: logs
        # TODO: rewind in case of error
        prev_name = super().rename(new_name)
        project_path = pathlib.Path(projects.current.path)
        disk_regex = re.compile(
            f"{prev_name}_"  # vm name
            "(?P<disk>[a-z0-9]+)"  # disk
            ".cow"  # extension
            r"(?P<bak_suffix>\.(?:bak|back)-[0-9\-_]+)?"  # backup suffix
            "$"  # end
        )
        new_name_repl = rf"{new_name}_\g<disk>.cow\g<bak_suffix>"
        for path in project_path.iterdir():
            if path.is_file() and disk_regex.match(path.name):
                new_disk_name = disk_regex.sub(new_name_repl, path.name)
                path.rename(project_path.joinpath(new_disk_name))
        return prev_name

    def poweron(self, resume=""):
        """
        Start the machine, from the saved state resume if given.

        The images of its disks are locked while it runs.
        """

        if self.proc is not None:
            return defer.succeed(self)

        def acquire(passthru):
            self.acquire()
            return passthru

        def release(passthru):
            self.release()
            return passthru

        d = bricks.Brick.poweron(self, resume)
        # a machine refused, as one not configured, has nothing to release
        if self._exited_d is not None:
            d.addCallback(acquire)
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
        try:
            command = self.program()
        except FileNotFoundError:
            command = self.config.qemu_program

        ram = self.config.memory
        txt = [_("command:") + " %s, ram: %s" % (command, ram)]
        for i, link in enumerate(itertools.chain(self.plugs, self.socks)):
            txt.append("eth%d: %s" % (i, _get_nick(link)))
        return ", ".join(txt)

    def update_usb_devices(self, dev):
        self.logger.debug(update_usb, old=self.config.usb_devices, new=dev)
        for usb_dev in set(dev) - set(self.config.usb_devices):
            self.send(f"usb_add host:{usb_dev.id}\n".encode())
        # FIXME: Don't know how to remove old devices, due to the ugly syntax
        # of usb_del command.

    def configured(self):
        # return all([p.configured() for p in self.plugs])
        for p in self.plugs:
            if p.sock is None and p.mode == "vde":
                return False
        return True

    def program(self):
        """The path of the QEMU program; FileNotFoundError if missing."""

        return abspath_qemu(self.config.qemu_program)

    def prepare(self, resume=""):
        """
        Ask the QEMU program what it has, and make sure of the disks.

        The machine type is asked for its properties, as ACPI; a machine type
        that the program doesn't have is left out, so its default is asked.
        """

        name = self.config.qemu_program
        try:
            path = self.program()
        except FileNotFoundError:
            missing = Missing(name, PACKAGES.get(name))
            return defer.fail(ProgramError(f"{missing} isn't installed"))
        disks = [disk for disk in self.disks() if disk.image]

        def ask_machine(qemu):
            machine = self.config.machine_type
            if not qemu.has_machine(machine):
                machine = ""
            deferred = programs.machine_properties(qemu, machine)
            return deferred.addCallback(lambda properties: (qemu, properties))

        def prepared(results):
            (qemu, properties), paths = results
            return Prepared(
                qemu=qemu,
                machine_properties=properties,
                disks=tuple((disk.device, p) for disk, p in zip(disks, paths)),
                audio_driver=get_setting("audio_driver"),
                resume=resume,
            )

        deferred = defer.gatherResults(
            [
                programs.qemu(path).addCallback(ask_machine),
                defer.gatherResults(
                    [disk.get_real_disk_name() for disk in disks],
                    consumeErrors=True,
                ),
            ],
            consumeErrors=True,
        )
        return deferred.addCallback(prepared)

    def command(self, prepared):
        """The command line, with what the QEMU program has."""

        config = self.config
        qemu = prepared.qemu
        version = f"{self.name}: QEMU {qemu.version}"
        cmd = Command(qemu.path)
        machine = config.machine_type
        if machine and not qemu.has_machine(machine):
            cmd.warn(
                f"{version} has no machine type {machine} (machine_type): the"
                " machine starts with the default one"
            )
            machine = ""
        acpi_off = not config.acpi
        machine_acpi = acpi_off and "acpi" in prepared.machine_properties
        sound, speaker = self._sound(cmd, prepared)
        cmd.option(
            "-machine",
            joined(
                f"type={machine}" if machine else "",
                "acpi=off" if machine_acpi else "",
                "pcspk-audiodev=snd0" if speaker else "",
            ),
        )
        if acpi_off and not machine_acpi:
            if "-no-acpi" in qemu.options:
                cmd.arg("-no-acpi")
            else:
                cmd.warn(f"{version} can't turn ACPI off here (acpi)")
        if config.use_kvm:
            if "kvm" in qemu.accelerators:
                # with the emulator in its place where KVM can't run; QEMU
                # takes the shadow memory in bytes
                shadow = (
                    f"kvm-shadow-mem={config.kvm_shadow_memory * 1024 * 1024}"
                )
                cmd.option(
                    "-accel",
                    joined(
                        "kvm", shadow if config.use_kvm_shadow_memory else ""
                    ),
                )
                cmd.option("-accel", "tcg")
            else:
                cmd.warn(
                    f"{version} has no KVM (use_kvm): the machine is emulated"
                )
        cpu = config.cpu_model
        if cpu and not qemu.has_cpu(cpu):
            cmd.warn(
                f"{version} has no CPU model {cpu} (cpu_model): the machine starts"
                " with the default one"
            )
            cpu = ""
        cmd.option("-cpu", cpu)
        cmd.option("-smp", config.cpus)
        cmd.option("-m", config.memory)
        cmd.option("-boot", config.boot_order)
        cmd.arg(*sound)
        cmd.flag("-usb", config.use_usb)
        cmd.flag("-snapshot", config.forget_disk_changes)
        if config.sdl_window:
            if "sdl" in qemu.displays:
                cmd.option("-display", "sdl")
            else:
                cmd.warn(
                    f"{version} has no SDL window (sdl_window): install the"
                    " qemu-system-gui package"
                )
        cmd.option("-loadvm", prepared.resume)
        if config.headless:
            cmd.option("-display", "none")
        for device, path in prepared.disks:
            if config.virtio_disks:
                cmd.option("-drive", f"file={path},if=virtio")
            else:
                cmd.option(f"-{device}", path)
        if config.use_kernel:
            cmd.option("-kernel", config.kernel)
        if config.use_initrd:
            cmd.option("-initrd", config.initrd)
        if config.use_kernel and config.kernel:
            # as it is: no shell reads it
            cmd.option("-append", config.kernel_command_line)
        if config.use_gdb:
            cmd.option("-gdb", f"tcp::{config.gdb_port}")
        if config.use_vnc:
            cmd.option("-vnc", f":{config.vnc_display}")
        if config.standard_vga:
            cmd.option("-vga", "std")
        if config.use_usb:
            for device in config.usb_devices:
                vendor, product = device.id.split(":")
                cmd.option(
                    "-device",
                    f"usb-host,vendorid=0x{vendor},productid=0x{product}",
                )
        cmd.option("-name", self.name)
        self._cards(cmd, qemu)
        if config.cdrom == "image":
            cmd.option("-cdrom", config.cdrom_image)
        elif config.cdrom == "device":
            cmd.option("-cdrom", config.cdrom_device)
        cmd.option(
            "-rtc",
            joined(
                "base=localtime" if config.clock_local_time else "",
                "driftfix=slew" if config.clock_drift_fix else "",
            ),
        )
        if len(config.keyboard_layout) == 2:
            cmd.option("-k", config.keyboard_layout)
        if config.serial_socket:
            serial = self.runtime_path(f"{self.name}_serial")
            cmd.option("-serial", f"unix:{serial},server=on,wait=off")
        console = f"socket,id=mon,path={self.console()},server=on,wait=off"
        cmd.arg("-mon", "chardev=mon", "-chardev", console)
        cmd.arg("-mon", "chardev=mon_cons")
        cmd.arg("-chardev", "stdio,id=mon_cons,signal=off")
        return cmd

    def _sound(self, cmd, prepared):
        """
        The arguments of the sound card, and whether it's the PC speaker.

        A card or a driver that the program doesn't have is left out, with a
        warning in cmd.
        """

        card = self.config.sound_card
        if not card:
            return [], False
        qemu = prepared.qemu
        version = f"{self.name}: QEMU {qemu.version}"
        driver = prepared.audio_driver
        # QEMU 6.2 doesn't list its drivers: the driver is taken on trust
        drivers = qemu.audio_drivers
        if drivers is not None and driver not in drivers:
            cmd.warn(
                f"{version} has no audio driver {driver} (audio_driver of the"
                " settings): the machine has no sound card"
            )
            return [], False
        audiodev = ["-audiodev", f"{driver},id=snd0"]
        # the PC speaker is part of the machine, not a device of its own
        if card == "pcspk":
            return audiodev, True
        device = qemu.device(card)
        if device is None:
            cmd.warn(
                f"{version} has no sound card {card} (sound_card): the machine"
                " has none"
            )
            return [], False
        return audiodev + ["-device", f"{device.name},audiodev=snd0"], False

    def _cards(self, cmd, qemu):
        """The network cards, each with its backend when QEMU has it."""

        links = list(itertools.chain(self.plugs, self.socks))
        if not links:
            cmd.option("-net", "none")
            return
        version = f"{self.name}: QEMU {qemu.version}"
        vde = "vde" in qemu.netdevs
        unplugged = []
        for index, link in enumerate(links):
            model = link.model
            if qemu.device(model) is None:
                cmd.warn(
                    f"{version} has no network card {model}: card {index} is"
                    f" a {DEFAULT_MODEL}"
                )
                model = DEFAULT_MODEL
            netdev = _netdev(link, index, vde)
            device = f"{model},mac={link.mac},id=vx{index}"
            if netdev is None:
                unplugged.append(str(index))
                cmd.option("-device", device)
            else:
                cmd.option("-device", f"{device},netdev=vx{index}")
                cmd.option("-netdev", netdev)
        if unplugged:
            cmd.warn(
                f"{version} can't join a VDE switch: card"
                f" {', '.join(unplugged)} unplugged; install a QEMU built with"
                " VDE"
            )

    def add_sock(self, mac=None, model=None, name=None):
        """
        Add a network card with a VDE socket other bricks can plug into.

        ``name`` is the socket's name within this VM, ``sock_ethN`` by default.
        """

        s = self.factory.new_sock(self)
        sock = VMSock(s)
        if name is None:
            name = f"sock_eth{len(self.plugs) + len(self.socks)}"
        sock.path = self.runtime_path(f"{self.name}_{name}[]")
        sock.nickname = f"{self.name}_{name}"
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
        for dev in DISK_DEVICES:
            yield self._disks[dev]

    def disk(self, dev):
        return self._disks[dev]

    def set_image(self, dev, image):
        self._disks[dev].set_image(image)
        if not self._restore:
            self._observable.notify("image-changed", (self, image))


def _netdev(link, index, vde):
    """The backend of a card, or None when it needs VDE and QEMU has none."""

    if link.mode == "sock":
        # a socket card: other bricks plug into it
        return f"vde,id=vx{index},sock={link.path}" if vde else None
    if link.sock is not None and link.sock.mode == "hostonly":
        return f"user,id=vx{index}"
    if link.mode == "vde":
        return f"vde,id=vx{index},sock={socket_path(link)}" if vde else None
    # a card on QEMU's own user network
    return f"user,id=vx{index}"


def is_virtualmachine(brick):
    return brick.get_type() == "Qemu"
