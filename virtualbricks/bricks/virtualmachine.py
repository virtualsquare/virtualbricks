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
import re
import shutil

import attr
from twisted.internet import defer
from twisted.internet.utils import getProcessOutput
from twisted.logger import Logger

from virtualbricks import bricks, errors
from virtualbricks.bricks.command import (
    Command,
    Prepared,
    joined,
    socket_path,
    vde_socket,
)
from virtualbricks.bricks.draft import Draft, Problem
from virtualbricks.bricks.plug import Plug
from virtualbricks.config.images import read_info
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
from virtualbricks.i18n import N_, _
from virtualbricks.nic import is_valid_mac, random_mac
from virtualbricks.programs import (
    PACKAGES,
    Missing,
    ProgramError,
    decode_output,
    programs,
)
from virtualbricks.observable import Observable, Signal
from virtualbricks.qemu import imageformat
from virtualbricks.qemu.imageformat import NotCowFileError
from virtualbricks.qemu.run import qemu_img, which

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
not_supported = "Suspend/Resume not supported on this disk."
snapshot_error = "Error on snapshot"
# The snapshot that suspend() saves in the first disk, and resume() loads.
SNAPSHOT = "virtualbricks"


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
    deferred.addCallback(decode_output)
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
        self.changed = Signal(Observable(), "changed")

    @property
    def name(self) -> str:
        """Read-only: the factory's rename_item() changes it, with set_name()."""

        return self._name

    def set_name(self, value):
        """
        :type value: str
        """

        self._name = value
        self.changed.notify(self)

    @property
    def path(self) -> str:
        """Read-only: images.relink() changes it, with set_path()."""

        return self._path

    def set_path(self, value):
        """
        :type value: str
        """

        self._path = value
        self.changed.notify(self)

    @property
    def description(self) -> str:
        """Read-only: set_description() changes it."""

        return self._description

    def set_description(self, description):
        """
        :type value: str
        """

        if self._description != description:
            self._description = description
            self.changed.notify(self)

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


@define
class ImageSettings:
    """What the details of an image change: its name and its description."""

    name: str = field(Str(), default="", help="The name of the image")
    description: str = field(
        Str(), default="", help="A description of the image"
    )


class ImageDraft(Draft):
    """
    The name and the description of an image, until OK. The name is checked
    as the factory checks it, and a new one reaches the disks that use the
    image.
    """

    def __init__(self, image: Image, factory) -> None:
        self.factory = factory
        super().__init__(image)

    def read(self) -> ImageSettings:
        return ImageSettings(self.brick.name, self.brick.description)

    def new_name(self) -> str | None:
        """
        The name the image takes, normalized, or None if it keeps its own;
        InvalidNameError if it can't take it.
        """

        name = self.settings.name
        if name == self.original.name:
            return None
        try:
            return self.factory.check_name(name)
        except errors.NameAlreadyInUseError as exc:
            # its own name, written another way
            if exc.name == self.original.name:
                return None
            raise

    def check(self) -> list[Problem]:
        try:
            self.new_name()
        except errors.NameAlreadyInUseError as exc:
            text = _("The name “{name}” is in use").format(name=exc.name)
            return [Problem("name", text)]
        except errors.InvalidNameError as exc:
            return [Problem("name", str(exc))]
        return []

    def give(self, changes: dict[str, object]) -> None:
        image = self.brick
        name = self.new_name()
        if name is not None:
            # through the factory: the disks follow
            self.factory.rename_item(image, name)
        if "description" in changes:
            image.set_description(self.settings.description)


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
        return self.vm.factory.get_image(name)

    def set_image(self, image):
        name = "" if image is None else image.name
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

        path = self.image.path
        logger.info(new_cow, backing_file=path)

        def create(info):
            # -F is the format of the image, which may be raw
            args = ["create", "-f", get_setting("cow_format")]
            args += ["-b", path, "-F", info.format, filename]
            return qemu_img(args)

        deferred = read_info(path, qemu_img)
        deferred.addCallback(create)
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
            backing_file = imageformat.get_backing_file(image_file)
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
            f"<Disk {self.device}({self.vm.name}) image={self.image.path} "
            f"readonly={self.readonly()} cow={self.is_cow()}>"
        )


DISK_DEVICES = ("hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock")


def _rename_private_disks(folder, old, new):
    """
    Rename the private disks of the machine ``old`` in ``folder``, and their
    backups, after the machine ``new``.
    """

    disk = re.compile(
        rf"{re.escape(old)}_(?P<rest>(?:{'|'.join(DISK_DEVICES)})\.cow"
        r"(?:\.(?:bak|back)-[0-9_-]+)?)\Z"
    )
    for filename in sorted(os.listdir(folder)):
        match = disk.match(filename)
        path = os.path.join(folder, filename)
        if match and os.path.isfile(path):
            os.rename(path, os.path.join(folder, f"{new}_{match['rest']}"))


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

    return field(
        Ref("image"),
        default="",
        help="The image of the disk, by name",
        path=("disks", dev, "image"),
    )


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

    return field(
        Bool(),
        default=False,
        help="Write to a private copy in the project folder, not the image",
        path=("disks", dev, "private"),
    )


@define
class VirtualMachineConfig(bricks.BrickConfig):
    """
    The configuration of a virtual machine.

    The order of the fields is the order of the keys in the project file.
    """

    # the program and the machine
    qemu_program = field(
        Str(required=True),
        default="qemu-system-i386",
        label=N_("Program"),
        help=N_("The QEMU program, in the QEMU folder of the settings"),
    )
    machine_type = field(
        Str(),
        default="",
        label=N_("Machine type"),
        help=N_(
            "The machine type, as -machine type= takes it; empty for the QEMU"
            " default"
        ),
    )
    cpu_model = field(
        Str(),
        default="",
        label=N_("CPU model"),
        help=N_("The CPU model, as -cpu takes it; empty for the QEMU default"),
    )
    use_kvm = field(
        Bool(),
        default=False,
        label=N_("KVM"),
        help=N_("Use KVM when the host has it"),
    )
    cpus = field(
        Int(1, 64),
        default=1,
        label=N_("Virtual CPUs"),
        help=N_("The number of virtual CPUs"),
    )
    # in MiB
    memory = field(
        Int(1, 99999), default=64, label=N_("Memory"), help=N_("Memory in MiB")
    )
    use_kvm_shadow_memory = field(
        Bool(),
        default=False,
        label=N_("KVM shadow memory"),
        help=N_("Set the size of the KVM shadow memory"),
        when=("use_kvm", True),
    )
    kvm_shadow_memory = field(
        Int(0, 99999),
        default=1,
        label=N_("Shadow memory"),
        help=N_("KVM shadow memory in MiB"),
        when=("use_kvm_shadow_memory", True),
    )
    # the boot and the disks
    boot_order = field(
        Str(),
        default="",
        label=N_("Boot from"),
        help=N_(
            "Boot order as -boot takes it: c the first disk, d the CD-ROM, a the floppy; empty for the QEMU default"
        ),
    )
    forget_disk_changes = field(
        Bool(),
        default=False,
        label=N_("Forget the changes"),
        help=N_(
            "Write the changes to the disks in temporary files, forgotten when the machine stops"
        ),
    )
    virtio_disks = field(
        Bool(),
        default=False,
        label=N_("Virtio disks"),
        help=N_("Attach the disks as virtio devices"),
    )
    # the CD-ROM: none, an image file, or a drive of the host
    cdrom = field(
        Choice("none", "image", "device"),
        default="none",
        label=N_("CD-ROM"),
        help=N_(
            "What the CD-ROM holds: nothing, an image file or a drive of the host"
        ),
    )
    cdrom_image = field(
        Path(),
        default="",
        label=N_("Image"),
        help=N_("An image file for the CD-ROM"),
        when=("cdrom", "image"),
    )
    cdrom_device = field(
        Str(),
        default="",
        label=N_("Drive"),
        help=N_("A CD-ROM drive of the host, as /dev/cdrom"),
        when=("cdrom", "device"),
    )
    # the display
    headless = field(
        Bool(),
        default=False,
        label=N_("No display"),
        help=N_("No display at all"),
    )
    standard_vga = field(
        Bool(),
        default=False,
        label=N_("Standard VGA"),
        help=N_("A standard VGA card instead of the machine's"),
    )
    use_vnc = field(
        Bool(),
        default=False,
        label=N_("VNC"),
        help=N_("Show the display over VNC"),
        # no display at all wins over VNC and SDL
        when=("headless", False),
    )
    vnc_display = field(
        Int(0, 500),
        default=1,
        label=N_("VNC display"),
        help=N_("The VNC display number"),
        when=("use_vnc", True),
    )
    sdl_window = field(
        Bool(),
        default=False,
        label=N_("SDL window"),
        help=N_("Show the display in an SDL window"),
        when=("headless", False),
    )
    # sound and USB
    sound_card = field(
        Str(),
        default="",
        label=N_("Sound card"),
        help=N_("The sound card, as ac97; empty for none"),
    )
    use_usb = field(
        Bool(),
        default=False,
        label=N_("USB"),
        help=N_("Give the machine USB, and its USB devices"),
    )
    usb_devices = field(
        ListOf(UsbDeviceKind()),
        factory=list,
        label=N_("USB devices"),
        help=N_("USB devices of the host, by vendor and product id"),
        when=("use_usb", True),
    )
    # the keyboard, the clock and the serial port
    keyboard_layout = field(
        Str(),
        default="",
        label=N_("Keyboard layout"),
        help=N_("The keyboard layout, two letters; empty for the default"),
    )
    clock_local_time = field(
        Bool(),
        default=False,
        label=N_("Local time"),
        help=N_("Start the clock of the machine at local time, not UTC"),
    )
    clock_drift_fix = field(
        Bool(),
        default=False,
        label=N_("Drift fix"),
        help=N_("Correct the drift of the clock of the machine"),
    )
    serial_socket = field(
        Bool(),
        default=False,
        label=N_("Serial socket"),
        help=N_("Connect the serial port to a socket in the runtime folder"),
    )
    # booting a kernel directly, and debugging it
    use_kernel = field(
        Bool(),
        default=False,
        label=N_("Boot a kernel"),
        help=N_("Boot a kernel directly"),
    )
    kernel = field(
        Path(),
        default="",
        label=N_("Kernel"),
        help=N_("A kernel image"),
        when=("use_kernel", True),
    )
    use_initrd = field(
        Bool(),
        default=False,
        label=N_("Initial ramdisk"),
        help=N_("Load an initial ramdisk with the kernel"),
        when=("use_kernel", True),
    )
    initrd = field(
        Path(),
        default="",
        label=N_("Ramdisk"),
        help=N_("An initial ramdisk"),
        when=("use_initrd", True),
    )
    kernel_command_line = field(
        Str(),
        default="",
        label=N_("Command line"),
        help=N_("The command line of the kernel"),
        when=("use_kernel", True),
    )
    use_gdb = field(
        Bool(),
        default=False,
        label=N_("GDB"),
        help=N_("Accept a GDB connection"),
    )
    gdb_port = field(
        Int(1, 65535),
        default=1234,
        label=N_("GDB port"),
        help=N_("The TCP port for GDB"),
        when=("use_gdb", True),
    )
    acpi = field(
        Bool(),
        default=True,
        label=N_("ACPI"),
        help=N_("Give the machine ACPI"),
    )
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


@attr.define
class Card:
    """
    A network card in the draft of a machine: a plug, whose socket is sock,
    None for nothing and hostonly_sock for QEMU's own user network; or a
    socket that other bricks plug into. link is the card of the machine it
    is, None for a new one.
    """

    kind: str
    model: str
    mac: str
    sock: object = None
    link: object = None

    def needs_vde(self) -> bool:
        return self.kind == "socket" or self.sock is not hostonly_sock


# The disks' images, which the draft gives the machine one by one.
DISK_IMAGES = frozenset(f"{device}_image" for device in DISK_DEVICES)
KEYBOARD_LAYOUT = re.compile(r"[a-z]{2}")


class VirtualMachineDraft(Draft):
    """
    The settings of a machine, its network cards, and what its QEMU lacks.

    The panel gives the draft the answers of the QEMU program, ``qemu`` and
    ``machine_properties``, when they come; until then nothing lacks.
    """

    def __init__(self, brick):
        super().__init__(brick)
        # the cards are the draft's own, and not links
        self.links = []
        self.original_links = []
        self.cards = [
            Card("plug", plug.model, plug.mac, plug.sock, plug)
            for plug in brick.plugs
        ] + [
            Card("socket", sock.model, sock.mac, None, sock)
            for sock in brick.socks
        ]
        self.qemu = None
        self.machine_properties = frozenset()

    def note(self, name):
        qemu = self.qemu
        if name == "audio_driver" and qemu and qemu.audio_drivers is None:
            # QEMU 6.2
            return _(
                "QEMU {version} doesn't list its drivers: this one is taken on"
                " trust"
            ).format(version=qemu.version)
        return ""

    # the cards

    def add_card(self) -> int:
        """A new card in nothing, after the other plugs; its index."""

        index = sum(1 for card in self.cards if card.kind == "plug")
        self.cards.insert(
            index, Card("plug", DEFAULT_MODEL, random_mac(), None)
        )
        return index

    def remove_card(self, index: int) -> None:
        del self.cards[index]

    def set_card(self, index: int, **values) -> None:
        """
        Change a card: its model, mac, kind or sock. A plug that becomes a
        socket, or back, moves among the plugs or the sockets.
        """

        card = self.cards[index]
        for name, value in values.items():
            setattr(card, name, value)
        if card.kind == "socket":
            card.sock = None
        self.cards.sort(key=lambda card: card.kind == "socket")

    # what is wrong

    def lacks(self) -> list:
        """What the QEMU program lacks, once it answered."""

        if self.qemu is None:
            return []
        cards = [(card.model, card.needs_vde()) for card in self.cards]
        return lacks(
            self.settings,
            cards,
            self.qemu,
            self.machine_properties,
            get_setting("audio_driver"),
        )

    def check(self):
        settings = self.settings
        problems = []
        for used, name, text in (
            (
                settings.use_kernel and not settings.kernel,
                "kernel",
                _("Choose the kernel, or don't boot one"),
            ),
            (
                settings.use_kernel
                and settings.use_initrd
                and not settings.initrd,
                "initrd",
                _("Choose the ramdisk, or don't load one"),
            ),
            (
                settings.cdrom == "image" and not settings.cdrom_image,
                "cdrom_image",
                _("Choose the image of the CD-ROM"),
            ),
            (
                settings.cdrom == "device" and not settings.cdrom_device,
                "cdrom_device",
                _("Choose the drive of the CD-ROM"),
            ),
            (
                settings.keyboard_layout
                and not KEYBOARD_LAYOUT.fullmatch(settings.keyboard_layout),
                "keyboard_layout",
                _("Two letters, as it or de"),
            ),
        ):
            if used:
                problems.append(Problem(name, text))
        for index, card in enumerate(self.cards):
            if not is_valid_mac(card.mac):
                text = _("{mac} isn't a MAC address").format(mac=card.mac)
                problems.append(Problem(f"card{index}", text))
            elif card.kind == "plug" and card.sock is None:
                text = _("In nothing: {brick} can't start").format(
                    brick=self.brick.name
                )
                problems.append(Problem(f"card{index}", text, error=False))
        problems += [
            Problem(lack.key, lack.words(), error=False)
            for lack in self.lacks()
        ]
        return problems

    # to the machine

    def changes(self):
        return {
            name: value
            for name, value in super().changes().items()
            if name not in DISK_IMAGES
        }

    def apply_extras(self):
        changed = self._apply_images()
        before = list(self.original.usb_devices)
        after = list(self.settings.usb_devices)
        if after != before:
            # a running machine gets the new ones at once
            self.brick.update_usb_devices(after)
        return self._apply_cards() or changed

    def _apply_images(self) -> bool:
        brick = self.brick
        changed = False
        for device in DISK_DEVICES:
            name = getattr(self.settings, f"{device}_image")
            if name == getattr(self.original, f"{device}_image"):
                continue
            image = brick.factory.get_image(name) if name else None
            if name and image is None:
                # an image not in the library keeps its name
                setattr(brick.config, f"{device}_image", name)
            else:
                brick.set_image(device, image)
            changed = True
        return changed

    def _apply_cards(self) -> bool:
        brick = self.brick
        kept = {
            id(card.link)
            for card in self.cards
            if card.link is not None and card.kind == _kind(brick, card.link)
        }
        changed = False
        for link in list(brick.plugs) + list(brick.socks):
            if id(link) not in kept:
                if link in brick.plugs and link.sock is not None:
                    link.disconnect()
                brick.remove_plug(link)
                changed = True
        for card in self.cards:
            link = card.link
            if link is None or id(link) not in kept:
                if card.kind == "socket":
                    brick.add_sock(card.mac, card.model)
                else:
                    brick.add_plug(card.sock, card.mac, card.model)
                changed = True
                continue
            if (link.model, link.mac) != (card.model, card.mac):
                link.model = card.model
                link.mac = card.mac
                changed = True
            if card.kind == "plug" and link.sock is not card.sock:
                if link.sock is not None:
                    link.disconnect()
                if card.sock is not None:
                    link.connect(card.sock)
                changed = True
        return changed


def _kind(brick, link) -> str:
    return "socket" if link in brick.socks else "plug"


class VirtualMachine(bricks.Brick):

    type = "Qemu"
    summary = "A virtual machine, run by QEMU"
    # a new machine's: its settings choose another
    programs = (("qemu-system-i386",),)
    term_command = "unixterm"
    config_factory = VirtualMachineConfig
    draft_factory = VirtualMachineDraft
    process_protocol = bricks.Process
    connections = "nics"

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.image_changed = Signal(self._observable, "image-changed")
        self._disks = {dev: Disk(self, dev) for dev in DISK_DEVICES}

    def set_name(self, name):
        """The sockets and the private disks named after it follow."""

        if projects.current is not None:
            _rename_private_disks(projects.current.path, self.name, name)
        self.rename_sockets(name)
        bricks.Brick.set_name(self, name)

    def rename_sockets(self, name):
        """Name the sockets named after the machine after name."""

        prefix = f"{self.name}_"
        for sock in self.socks:
            if sock.nickname.startswith(prefix):
                suffix = sock.nickname[len(prefix) :]
                sock.nickname = f"{name}_{suffix}"
                sock.path = self.runtime_path(f"{name}_{suffix}[]")

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

        return which(self.config.qemu_program)

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
        """
        The command line, with what the QEMU program has: what it lacks is
        left out, with the warnings of lacks().
        """

        config = self.config
        qemu = prepared.qemu
        cmd = Command(qemu.path)
        links = list(itertools.chain(self.plugs, self.socks))
        found = lacks(
            config,
            [(link.model, needs_vde(link)) for link in links],
            qemu,
            prepared.machine_properties,
            prepared.audio_driver,
        )
        for lack in found:
            cmd.warn(lack.warning(self.name))
        lacked = {lack.key for lack in found}
        machine = "" if "machine_type" in lacked else config.machine_type
        acpi_off = not config.acpi
        machine_acpi = acpi_off and "acpi" in prepared.machine_properties
        sound, speaker = self._sound(prepared, "sound_card" in lacked)
        cmd.option(
            "-machine",
            joined(
                f"type={machine}" if machine else "",
                "acpi=off" if machine_acpi else "",
                "pcspk-audiodev=snd0" if speaker else "",
            ),
        )
        if acpi_off and not machine_acpi and "-no-acpi" in qemu.options:
            cmd.arg("-no-acpi")
        if config.use_kvm and "use_kvm" not in lacked:
            # with the emulator in its place where KVM can't run; QEMU takes
            # the shadow memory in bytes
            shadow = f"kvm-shadow-mem={config.kvm_shadow_memory * 1024 * 1024}"
            cmd.option(
                "-accel",
                joined("kvm", shadow if config.use_kvm_shadow_memory else ""),
            )
            cmd.option("-accel", "tcg")
        cmd.option("-cpu", "" if "cpu_model" in lacked else config.cpu_model)
        cmd.option("-smp", config.cpus)
        cmd.option("-m", config.memory)
        cmd.option("-boot", config.boot_order)
        cmd.arg(*sound)
        cmd.flag("-usb", config.use_usb)
        cmd.flag("-snapshot", config.forget_disk_changes)
        # no display at all leaves out SDL and VNC, as the panel greys them
        if config.sdl_window and not config.headless:
            if "sdl_window" not in lacked:
                cmd.option("-display", "sdl")
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
        if config.use_kernel and config.use_initrd:
            cmd.option("-initrd", config.initrd)
        if config.use_kernel and config.kernel:
            # as it is: no shell reads it
            cmd.option("-append", config.kernel_command_line)
        if config.use_gdb:
            cmd.option("-gdb", f"tcp::{config.gdb_port}")
        if config.use_vnc and not config.headless:
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
        self._cards(cmd, qemu, links, lacked)
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

    def _sound(self, prepared, lacked):
        """
        The arguments of the sound card, and whether it's the PC speaker;
        none when the program lacks the card or the driver.
        """

        card = self.config.sound_card
        if not card or lacked:
            return [], False
        audiodev = ["-audiodev", f"{prepared.audio_driver},id=snd0"]
        # the PC speaker is part of the machine, not a device of its own
        if card == "pcspk":
            return audiodev, True
        device = prepared.qemu.device(card)
        return audiodev + ["-device", f"{device.name},audiodev=snd0"], False

    def _cards(self, cmd, qemu, links, lacked):
        """The network cards, each with its backend when QEMU has it."""

        if not links:
            cmd.option("-net", "none")
            return
        vde = "vde" in qemu.netdevs
        for index, link in enumerate(links):
            model = link.model
            if f"card{index}" in lacked:
                model = DEFAULT_MODEL
            netdev = _netdev(link, index, vde)
            device = f"{model},mac={link.mac},id=vx{index}"
            if netdev is None:
                cmd.option("-device", device)
            else:
                cmd.option("-device", f"{device},netdev=vx{index}")
                cmd.option("-netdev", netdev)

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
        plug = VMPlug(Plug(self))
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
        self.image_changed.notify((self, image))


def _netdev(link, index, vde):
    """The backend of a card, or None when it needs VDE and QEMU has none."""

    if link.mode == "sock":
        # a socket card: other bricks plug into it
        sock = vde_socket(link.path)
        return f"vde,id=vx{index},sock={sock}" if vde else None
    if link.sock is not None and link.sock.mode == "hostonly":
        return f"user,id=vx{index}"
    if link.mode == "vde":
        return f"vde,id=vx{index},sock={socket_path(link)}" if vde else None
    # a card on QEMU's own user network
    return f"user,id=vx{index}"


def needs_vde(link):
    """Whether a card of the machine joins a VDE socket, as _netdev() says."""

    if link.mode == "sock":
        return True
    if link.sock is not None and link.sock.mode == "hostonly":
        return False
    return link.mode == "vde"


@attr.define(frozen=True)
class Lack:
    """
    What the QEMU program lacks of a setting, and what the start does then.

    The panel says ``words()`` under the setting's row; the start writes
    ``warning()``, with the machine's name and the key: ``where`` when it
    isn't the key, none when it's empty.
    """

    key: str
    text: str
    then: str = ""
    where: str | None = None

    def words(self) -> str:
        return f"{self.text}: {self.then}" if self.then else self.text

    def warning(self, name: str) -> str:
        where = self.key if self.where is None else self.where
        line = f"{name}: {self.text}"
        if where:
            line += f" ({where})"
        if self.then:
            line += f": {self.then}"
        return line


def lacks(config, cards, qemu, machine_properties, audio_driver):
    """
    What the QEMU program lacks of the settings of a machine, in the order
    of its command line: a Lack for each.

    cards are the model of each network card, and whether it joins a VDE
    socket. machine_properties are those of the machine type, or of the
    default one when the program lacks it.
    """

    version = f"QEMU {qemu.version}"
    found = []
    machine = config.machine_type
    if machine and not qemu.has_machine(machine):
        found.append(
            Lack(
                "machine_type",
                f"{version} has no machine type {machine}",
                "the machine starts with the default one",
            )
        )
    card = config.sound_card
    # QEMU 6.2 doesn't list its drivers: the driver is taken on trust
    drivers = qemu.audio_drivers
    if card and drivers is not None and audio_driver not in drivers:
        found.append(
            Lack(
                "sound_card",
                f"{version} has no audio driver {audio_driver}",
                "the machine has no sound card",
                "audio_driver of the settings",
            )
        )
    elif card and card != "pcspk" and qemu.device(card) is None:
        found.append(
            Lack(
                "sound_card",
                f"{version} has no sound card {card}",
                "the machine has none",
            )
        )
    if (
        not config.acpi
        and "acpi" not in machine_properties
        and "-no-acpi" not in qemu.options
    ):
        found.append(Lack("acpi", f"{version} can't turn ACPI off here"))
    if config.use_kvm and "kvm" not in qemu.accelerators:
        found.append(
            Lack("use_kvm", f"{version} has no KVM", "the machine is emulated")
        )
    cpu = config.cpu_model
    if cpu and not qemu.has_cpu(cpu):
        found.append(
            Lack(
                "cpu_model",
                f"{version} has no CPU model {cpu}",
                "the machine starts with the default one",
            )
        )
    if (
        config.sdl_window
        and not config.headless
        and "sdl" not in qemu.displays
    ):
        found.append(
            Lack(
                "sdl_window",
                f"{version} has no SDL window",
                "install the qemu-system-gui package",
            )
        )
    for index, (model, _vde) in enumerate(cards):
        if qemu.device(model) is None:
            found.append(
                Lack(
                    f"card{index}",
                    f"{version} has no network card {model}",
                    f"card {index} is a {DEFAULT_MODEL}",
                    "",
                )
            )
    if "vde" not in qemu.netdevs:
        unplugged = [
            str(index) for index, (_model, vde) in enumerate(cards) if vde
        ]
        if unplugged:
            found.append(
                Lack(
                    "cards",
                    f"{version} can't join a VDE switch",
                    f"card {', '.join(unplugged)} unplugged; install a QEMU"
                    " built with VDE",
                    "",
                )
            )
    return found


def is_virtualmachine(brick):
    return brick.get_type() == "Qemu"


# Suspend and resume a machine, as its menu does


def _first_disk(vm) -> str | None:
    disk = vm.disk("hda")
    if disk.is_cow():
        return disk.get_cow_path()
    if disk.image:
        return disk.image.path
    return None


def _not_supported() -> defer.Deferred:
    logger.error(not_supported)
    return defer.fail(
        RuntimeError(_("Suspend/Resume not supported on this disk."))
    )


def suspend(vm) -> defer.Deferred:
    """Save the state of a virtual machine in its first disk, and stop it."""

    path = _first_disk(vm)
    if path is None:
        return _not_supported()
    image_type = imageformat.image_type_from_file(path)
    if image_type not in (
        imageformat.ImageFormat.QCOW2,
        imageformat.ImageFormat.QCOW3,
    ):
        return _not_supported()
    vm.send(f"savevm {SNAPSHOT}\n".encode())
    return vm.poweroff()


def resume(vm) -> defer.Deferred:
    """Start a virtual machine from what Suspend saved in its first disk."""

    def found(output):
        if output.find(SNAPSHOT) == -1:
            raise RuntimeError(_("Cannot find suspend point."))

    def load(_):
        if vm.proc is not None:
            vm.send(f"loadvm {SNAPSHOT}\n".encode())
        else:
            return vm.poweron(resume=SNAPSHOT)

    def failed(failure):
        logger.failure(snapshot_error, failure)
        return failure

    path = _first_disk(vm)
    if path is None:
        return _not_supported()
    output = qemu_img(["snapshot", "-l", path])
    output.addCallback(found)
    output.addCallback(load)
    output.addErrback(failed)
    return output
