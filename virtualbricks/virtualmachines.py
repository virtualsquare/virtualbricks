# -*- test-case-name: virtualbricks.tests.test_virtualmachines -*-
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
import re
import datetime
import shutil
import itertools

from twisted.internet import utils, defer
from twisted.python import failure

from virtualbricks import errors, tools, settings, bricks, _compat


if False:
    _ = str

__metaclass__ = type
log = _compat.getLogger(__name__)


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

    model = "rtl8139"
    mode = "vde"

    def __init__(self, plug):
        Wrapper.__init__(self, plug)
        self.__dict__["mac"] = tools.random_mac()


class VMSock(Wrapper):

    model = "rtl8139"
    # mac = ""

    def __init__(self, sock):
        Wrapper.__init__(self, sock)
        self.__dict__["mac"] = tools.random_mac()

    def connect(self, endpoint):
        return


class _FakeBrick:

    name = "hostonly"

    def poweron(self):
        return defer.succeed(self)


class _HostonlySock:
    """This is dummy implementation of a VMSock used with VirtualMachines that
    want a plug that is not connected to nothing. The instance is a singleton,
    but not enforced anyhow, maybe a better solution is to have a different
    hostonly socket for each plug and let the brick choose which socket should
    be saved and which not."""

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

    def __init__(self, path, description=""):
        self.path = os.path.abspath(path)
        if description:
            self.set_description(description)

    def _description_file(self):
        return self.path + ".vbdescr"

    def set_description(self, descr):
        try:
            with open(self._description_file(), "w") as fp:
                fp.write(descr)
        except IOError:
            pass

    def get_description(self):
        try:
            with open(self._description_file()) as fp:
                return fp.read()
        except IOError:
            return ""

    description = property(get_description, set_description)

    @property
    def name(self):
        return os.path.basename(self.path)

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

    def repr_master(self):
        if self.master is None:
            return ""
        return repr(self.master)


def move(src, dst):
    try:
        os.rename(src, dst)
    except OSError as e:
        if e.errno == errno.EXDEV:
            shutil.move(src, dst)
        else:
            raise


def is_missing(path, file):
    return not os.access(os.path.join(path, file), os.X_OK)


class Disk:

    sync_cmd = "sync"
    image = None

    @property
    def cow(self):
        return self.vm.config["private" + self.device]

    @property
    def basefolder(self):
        return self.VM.get_basefolder()

    def __init__(self, VM, dev):
        self.VM = self.vm = VM
        self.device = dev

    def args(self):
        d = self.get_real_disk_name()
        d.addCallback(lambda dn: ["-" + self.device, dn])
        return d

    def set_image(self, image):
        self.image = image

    def acquire(self):
        if self.image and not self.cow and not self.VM.config["snapshot"]:
            self.image.acquire(self)

    def release(self):
        if self.image and not self.cow and not self.VM.config["snapshot"]:
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
        if is_missing(settings.get("qemupath"), "qemu-img"):
            msg = _("qemu-img not found! I can't create a new image.")
            return defer.fail(failure.Failure(errors.BadConfigError(msg)))

        log.msg("Creating a new private COW from %s base image." %
                self._get_base())
        args = ["create", "-b", self._get_base(), "-f",
                settings.get("cowfmt"), cowname]
        exe = os.path.join(settings.get("qemupath"), "qemu-img")
        exit = utils.getProcessOutputAndValue(exe, args, os.environ)
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
            log.debug("%s private cow found with a different base "
                      "image (%s): moving it in %s", cowname, backing_file,
                      cowback)
            move(cowname, cowback)
            return self._create_cow(cowname).addCallback(lambda _: cowname)

    def _get_cow_name(self):
        try:
            os.makedirs(self.basefolder)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
        cowname = os.path.join(self.basefolder,
                               "%s_%s.cow" % (self.VM.name, self.device))
        try:
            return self._check_base(cowname)
        except IOError, e:
            if e.errno == errno.ENOENT:
                return self._create_cow(cowname)
            else:
                raise

    def get_real_disk_name(self):
        if self.image is None:
            # XXX: this should be really an error
            return defer.succeed("")
        elif self.cow:
            try:
                return self._get_cow_name()
            except (OSError, IOError) as e:
                return defer.fail(failure.Failure(e))
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
        return "<Disk {self.device}({self.VM.name}) image={self.image} " \
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
        "-tdf": "tdf",
        "#kvmsm": "kvmsm",
        "#kvmsmem": "kvmsmem",
        # "-mem-path": "",
        # "-mem-prealloc": "",
        "#icon": "icon",
        "#serial": "serial",
        "#stdout": ""}


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

                  "hda": bricks.String(""),
                  "privatehda": bricks.Boolean(False),

                  "hdb": bricks.String(""),
                  "privatehdb": bricks.Boolean(False),

                  "hdc": bricks.String(""),
                  "privatehdc": bricks.Boolean(False),

                  "hdd": bricks.String(""),
                  "privatehdd": bricks.Boolean(False),

                  "fda": bricks.String(""),
                  "privatefda": bricks.Boolean(False),

                  "fdb": bricks.String(""),
                  "privatefdb": bricks.Boolean(False),

                  "mtdblock": bricks.String(""),
                  "privatemtdblock": bricks.Boolean(False),

                  # system and machine
                  "argv0": bricks.String("i386"),
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
                  "usbdevlist": bricks.ListOf(bricks.String("")),

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


class VirtualMachine(bricks.Brick):

    type = "Qemu"
    term_command = "unixterm"
    # sudo_factory = QemuSudo
    command_builder = VM_COMMAND_BUILDER
    config_factory = VirtualMachineConfig

    for hd in "hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock":
        s = """def cbset_{0}(self, value):
            image = self.factory.get_image_by_path(value)
            self.disks["{0}"].set_image(image)""".format(hd)
        exec s
    del hd

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.config["name"] = name
        self.disks = {}
        for hd in "hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock":
            disk = Disk(self, hd)
            self.disks[hd] = disk
            if self.config[hd]:
                image = factory.get_image_by_path(self.config[hd])
                disk.set_image(image)

    def poweron(self, snapshot=""):
        def acquire(passthru):
            self.acquire()
            return passthru

        def release(passthru):
            self.release()
            return passthru

        self.config["loadvm"] = snapshot
        d = bricks.Brick.poweron(self)
        d.addCallback(acquire)
        self._exited_d.addBoth(release)
        return d

    def poweroff(self, kill=False, term=False):
        if self.proc is None:
            return defer.succeed((self, self._last_status))
        elif not any((kill, term)):
            log.msg("Sending powerdown to %r" % self)
            self.send("system_powerdown\n")
            return self._exited_d
        if term:
            return bricks.Brick.poweroff(self)
        else:
            return bricks.Brick.poweroff(self, kill)

    def get_basefolder(self):
        return self.factory.get_basefolder()

    def get_parameters(self):
        txt = [_("command:") + " %s, ram: %s" % (self.prog(),
                                                 self.config["ram"])]

        for i, link in enumerate(itertools.chain(self.plugs, self.socks)):
            txt.append("eth%d: %s" % (i, link.sock.nickname))
        return ", ".join(txt)

    def update_usbdevlist(self, dev):
        log.debug("update_usbdevlist: old %s - new %s",
                  self.config["usbdevlist"], dev)
        for d in set(dev) - set(self.config["usbdevlist"]):
            self.send("usb_add host:" + d + "\n")
        # FIXME: Don't know how to remove old devices, due to the ugly syntax
        # of usb_del command.

    def configured(self):
        # return all([p.configured() for p in self.plugs])
        for p in self.plugs:
            if p.sock is None and p.mode == 'vde':
                return False
        return True

    def prog(self):
        #IF IS IN A SERVER, CHECK IF KVM WORKS
        # XXX: I disabled this, how can be renabled?
        # if self.factory.server:
        #     try:
        #         self.settings.check_kvm()
        #     except IOError:
        #         raise errors.BadConfigError(_("KVM not found! Please change VM configuration."))
        #         return
        #     except NotImplementedError:
        #         raise errors.BadConfigError(_("KVM not found! Please change VM configuration."))
        #         return

        if self.config["argv0"] and not self.config["kvm"]:
            cmd = settings.get("qemupath") + "/" + self.config["argv0"]
        else:
            cmd = settings.get("qemupath") + "/qemu"
        if self.config["kvm"]:
            cmd = settings.get("qemupath") + "/kvm"
        return cmd

    def args(self):
        d = defer.gatherResults(self._get_devices())
        d.addCallback(self.__args)
        return d

    def _get_devices(self,):
        devs = ("hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock")
        return [self._get_disk_args(i, self.disks[dev]) for i, dev in
                enumerate(devs) if self.config[dev]]

    def _get_disk_args(self, idx, disk):
        if self.config["use_virtio"]:
            def cb(disk_name):
                return ["-drive", "file=%s,if=virtio,index=%s" %
                        (disk_name, str(idx))]
            return disk.get_real_disk_name().addCallback(cb)
        else:
            return disk.args()

    def __args(self, results):
        res = [self.prog()]
        if not self.config["kvm"]:
            if self.config["machine"] != "":
                res.extend(["-M", self.config["machine"]])
            if self.config["cpu"]:
                res.extend(["-cpu", self.config["cpu"]])
        res.extend(list(self.build_cmd_line()))
        if not self.has_graphic() or self.config["novga"]:
            res.extend(["-display", "none"])
        for disk_args in results:
            res.extend(disk_args)
        if self.config["kernelenbl"] and self.config["kernel"]:
            res.extend(["-kernel", self.config["kernel"]])
        if self.config["initrdenbl"] and self.config["initrd"]:
            res.extend(["-initrd", self.config["initrd"]])
        if (self.config["kopt"] and self.config["kernelenbl"] and
                self.config["kernel"]):
            res.extend(["-append", re.sub("\"", "", self.config["kopt"])])
        if self.config["gdb"]:
            res.extend(["-gdb", "tcp::%d" % self.config["gdbport"]])
        if self.config["vnc"]:
            res.extend(["-vnc", ":%d" % self.config["vncN"]])
        if self.config["vga"]:
            res.extend(["-vga", "std"])

        if self.config["usbmode"]:
            for dev in self.config["usbdevlist"]:
                res.extend(["-usbdevice", "host:%s" % dev])
            # The world is not ready for this, do chown /dev/bus/usb instead.
            # self._needsudo = True
        # else:
        #     self._needsudo = False

        res.extend(["-name", self.name])
        if not self.plugs and not self.socks:
            res.extend(["-net", "none"])
        else:
            for i, link in enumerate(itertools.chain(self.plugs, self.socks)):
                res.append("-device")
                res.append("{1.model},vlan={0},mac={1.mac},id=eth{0}".format(
                    i, link))
                if link.mode == "vde":
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
        if self.config["rtc"]:
            res.extend(["-rtc", "base=localtime"])
        if len(self.config.keyboard) == 2:
            res.extend(["-k", self.config["keyboard"]])
        if self.config["kvmsm"]:
            res.extend(["-kvm-shadow-memory", self.config["kvmsmem"]])
        if self.config["serial"]:
            res.extend(["-serial", "unix:%s/%s_serial,server,nowait" %
                        (settings.VIRTUALBRICKS_HOME, self.name)])
        res.extend(["-mon", "chardev=mon", "-chardev",
                    "socket,id=mon,path=%s,server,nowait" %
                    self.console(),
                    "-mon", "chardev=mon_cons", "-chardev",
                    "stdio,id=mon_cons,signal=off"])
        return res

    def has_graphic(self):
        return False

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

    def connect(self, socket):
        plug = self.add_plug()
        plug.connect(socket)

    def remove_plug(self, plug):
        try:
            if plug.mode == "sock":
                self.socks.remove(plug)
            else:
                self.plugs.remove(plug)
        except ValueError:
            log.error("plug %r does not belong to %r" % (plug, self))

    def commit_disks(self, args):
        # XXX: fixme
        self.send("commit all\n")

    def acquire(self):
        """Acquire locks on images if needed."""
        log.debug("Aquiring disk locks")
        devices = ["hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock"]
        acquired = []
        while devices:
            dev = devices.pop()
            try:
                self.disks[dev].acquire()
            except errors.LockedImageError:
                for _dev in acquired:
                    self.disks[_dev].release()
                raise
            else:
                acquired.append(dev)

    def release(self):
        log.debug("Releasing disk locks")
        for hd in "hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock":
            self.disks[hd].release()
