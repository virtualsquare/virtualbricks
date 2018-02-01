# -*- test-case-name: virtualbricks.tests.test_virtualmachines -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2018 Virtualbricks team

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
import re
import datetime
import shutil
import itertools

from twisted.internet import utils, defer

from virtualbricks import (errors, tools, settings, bricks, log, project,
                           observable)
from virtualbricks._spawn import getQemuOutputAndValue, abspath_qemu


if False:
    _ = str

__metaclass__ = type
logger = log.Logger()
new_cow = log.Event("Creating a new private COW from {base} image.")
invalid_base = log.Event("{cowname} private cow found with a different base "
                         "image ({base}): moving it in {path}")
powerdown = log.Event("Sending powerdown to {vm}")
update_usb = log.Event("update_usbdevlist: old {old} - new {new}")
own_err = log.Event("plug {plug} does not belong to {brick}")
acquire_lock = log.Event("Aquiring disk locks")
release_lock = log.Event("Releasing disk locks")


class UsbDevice:

    def __init__(self, ID, desc=""):
        self.ID = ID
        self.desc = desc

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.ID == other.ID

    def __ne__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.ID)

    def __str__(self):
        return str(self.ID)

    def __repr__(self):
        return str(self.ID)

    def __format__(self, format_string):
        if format_string == "id":
            return str(self.ID)
        elif format_string == "d":
            return str(self.desc)
        elif format_string == "":
            return str(self)
        raise ValueError("invalid format string" + repr(format_string))


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


class Image:

    readonly = False
    master = None
    _description = None
    _name = ""

    def __init__(self, name, path, description=""):
        self.observable = observable.Observable("changed")
        self._name = name
        self.path = os.path.abspath(path)
        if description:
            self.set_description(description)

    def _description_file(self):
        return self.path + ".vbdescr"

    def set_description(self, descr):
        if descr != self._description:
            self._description = descr
            try:
                with open(self._description_file(), "w") as fp:
                    fp.write(descr)
            except IOError:
                pass
            self.observable.notify("changed", self)

    def get_description(self):
        if self._description is None:
            try:
                with open(self._description_file()) as fp:
                    return fp.read()
            except IOError:
                return ""
        else:
            return self._description

    description = property(get_description, set_description)

    def set_name(self, value):
        self._name = value
        self.observable.notify("changed", self)

    def get_name(self):
        return self._name

    name = property(get_name, set_name)

    def basename(self):
        return os.path.basename(self.path)

    def get_size(self):
        if not self.exists():
            return "0"
        size = os.path.getsize(self.path)
        if size > 1000000:
            return str(size / 1000000)
        else:
            return str(size / 1000000.0)

    def exists(self):
        return os.path.exists(self.path)

    def acquire(self, disk):
        if self.master in (None, disk):
            self.master = disk
        else:
            raise errors.LockedImageError(self, self.master)

    def release(self, disk):
        if self.master is disk:
            self.master = None
        else:
            raise errors.LockedImageError(self, self.master)

    def save_to(self, fileobj):
        fileobj.write("[Image:{0.name}]\npath={0.path}\n\n".format(self))

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


def move(src, dst):
    try:
        os.rename(src, dst)
    except OSError as e:
        if e.errno == errno.EXDEV:
            shutil.move(src, dst)
        else:
            raise


class Disk:

    sync_cmd = "sync"
    image = None

    @property
    def cow(self):
        return self.VM.config["private" + self.device]

    @property
    def basefolder(self):
        return project.manager.current.path

    @property
    def vm_name(self):
        return self.VM.name

    def __init__(self, VM, dev):
        self.VM = VM
        self.device = dev

    def _virtio_args_cb(self, disk_name):
        return ["-drive", "file={0},if=virtio".format(disk_name)]

    def _args_cb(self, disk_name):
        return ["-" + self.device, disk_name]

    def args(self):
        if self.image:
            d = self.get_real_disk_name()
            if self.VM.get("use_virtio"):
                d.addCallback(self._virtio_args_cb)
            else:
                d.addCallback(self._args_cb)
            return d
        else:
            return defer.succeed([])

    def set_image(self, image):
        self.image = image

    def acquire(self):
        if self.image and not self.cow and not self.readonly():
            self.image.acquire(self)

    def release(self):
        if self.image and not self.cow and not self.readonly():
            self.image.release(self)

    def _get_base(self):
        return self.image.path

    def _sync(self, ret):

        def complain_on_error(ret):
            out, err, code = ret
            if code != 0:
                raise RuntimeError("sync failed\n%s" % err)

        out, err, code = ret
        if code != 0:
            raise RuntimeError("Cannot create private COW\n%s" % err)

        exit = utils.getProcessOutputAndValue(self.sync_cmd, env=os.environ)
        exit.addCallback(complain_on_error)
        return exit

    def _create_cow(self, cowname):
        if abspath_qemu('qemu-img', return_relative=False) is None:
            msg = _("qemu-img not found! I can't create a new image.")
            return defer.fail(errors.BadConfigError(msg))

        logger.info(new_cow, base=self._get_base())
        args = ["create", "-b", self._get_base(), "-f",
                settings.get("cowfmt"), cowname]
        exit = getQemuOutputAndValue("qemu-img", args, os.environ)
        exit.addCallback(self._sync)
        exit.addCallback(lambda _: cowname)
        return exit

    def _check_base(self, cowname):
        with open(cowname) as fp:
            backing_file = tools.get_backing_file(fp)
        if backing_file == self._get_base():
            return defer.succeed(cowname)
        else:
            dt = datetime.datetime.now()
            cowback = cowname + ".back-" + dt.strftime("%Y-%m-%d_%H-%M-%S")
            logger.debug(invalid_base, cowname=cowname, base=backing_file,
                         path=cowback)
            move(cowname, cowback)
            return self._create_cow(cowname).addCallback(lambda _: cowname)

    def _get_cow_name(self):
        try:
            os.makedirs(self.basefolder)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
        cowname = self.get_cow_path()
        try:
            return self._check_base(cowname)
        except IOError, e:
            if e.errno == errno.ENOENT:
                return self._create_cow(cowname)
            else:
                raise

    def get_cow_path(self):
        return os.path.join(self.basefolder, "%s_%s.cow" % (self.vm_name,
                                                            self.device))

    def get_real_disk_name(self):
        if self.image is None:
            # XXX: this should be really an error
            return defer.succeed("")
        elif self.cow:
            try:
                return self._get_cow_name()
            except (OSError, IOError) as e:
                return defer.fail(e)
        else:
            return defer.succeed(self.image.path)

    def readonly(self):
        return self.VM.config["snapshot"]

    def __deepcopy__(self, memo):
        new = type(self)(self.VM, self.device)
        new.sync_cmd = self.sync_cmd
        if self.image is not None:
            new.set_image(self.image)
        return new

    def __repr__(self):
        return "<Disk {self.device}({self.vm_name}) image={self.image:p} " \
                "readonly={readonly} cow={self.cow}>".format(
                    self=self, readonly=self.readonly())


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
        self.image_changed = observable.Event(self._observable,
                                              "image-changed")
        self.config["name"] = name
        for dev in "hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock":
            self.config[dev] = Disk(self, dev)

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
            self.send("system_powerdown\n")
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
        self.logger.debug(update_usb, old=self.config["usbdevlist"], new=dev)
        for device in set(dev) - set(self.config["usbdevlist"]):
            self.send("usb_add host:{0}\n".format(device))
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
            for dev in self.config["usbdevlist"]:
                res.extend(["-usbdevice", "host:%s" % dev])

        res.extend(["-name", self.name])
        if not self.plugs and not self.socks:
            res.extend(["-net", "none"])
        else:
            for i, link in enumerate(itertools.chain(self.plugs, self.socks)):
                res.append("-device")
                res.append("{1.model},vlan={0},mac={1.mac},id=eth{0}".format(
                    i, link))
                if link.sock and link.sock.mode == "hostonly":
                    res.extend(("-net", "user,vlan={0}".format(i)))
                elif link.mode == "vde":
                    res.append("-net")
                    res.append("vde,vlan={0},sock={1}".format(
                        i, link.sock.path.rstrip('[]')))
                elif link.mode == "sock":
                    res.append("-net")
                    res.append("vde,vlan={0},sock={1}".format(
                        i, link.path))
                else:
                    res.extend(["-net", "user"])

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
        disk.VM = self

    cbset_hda = cbset_hdb = cbset_hdc = cbset_hdd = cbset_fda = cbset_fdb = \
            cbset_mtblock = set_vm


def is_virtualmachine(brick):
    return brick.get_type() == "Qemu"
