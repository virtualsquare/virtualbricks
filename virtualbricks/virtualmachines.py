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

import copy
import os
import re
import subprocess
from datetime import datetime
from shutil import move

from virtualbricks import errors, tools, settings, bricks, _compat
from virtualbricks.deprecated import deprecated
from virtualbricks.versions import Version
from virtualbricks.settings import MYPATH


if False:
    _ = str

log = _compat.getLogger(__name__)
__metaclass__ = type


class VMPlug:

    model = "rtl8139"
    mode = "vde"

    def __init__(self, plug):
        self._plug = plug
        self.mac = tools.random_mac()
        self.vlan = len(plug.brick.plugs) + len(plug.brick.socks)

    def __getattr__(self, name):
        try:
            return getattr(self._plug, name)
        except AttributeError:
            raise AttributeError("_VMPlug." + name)

    def get_model_driver(self):
        if self.model == "virtio":
            return "virtio-net-pci"
        return self.model

    def hotadd(self):
        driver = self.get_model_driver()
        self._plug.brick.send("device_add %s,mac=%s,vlan=%s,id=eth%s\n" %
                              (driver, self.mac, self.vlan, self.vlan))
        self._plug.brick.send("host_net_add vde sock=%s,vlan=%s\n" %
                              (self._plug.sock.path.rstrip("[]"), self.vlan))

    def hotdel(self):
        self._plug.brick.send("host_net_remove %s vde.%s\n" %
                              (self.vlan, self.vlan))
        self._plug.brick.send("device_del eth%s\n" % self.vlan)


class VMSock:

    model = "rtl8139"

    def __init__(self, sock):
        self.__dict__["_sock"] = sock
        self.__dict__["mac"] = tools.random_mac()
        # import pdb; pdb.set_trace()
        self.__dict__["vlan"] = len(sock.brick.plugs) + len(sock.brick.socks)
        sock.path = "{MYPATH}/{sock.brick.name}_sock_eth{self.vlan}[]".format(
            self=self, MYPATH=MYPATH, sock=sock)
        sock.nickname = "{sock.brick.name}_sock_eth{self.vlan}".format(
            self=self, sock=sock)

    def __getattr__(self, name):
        try:
            return getattr(self._sock, name)
        except AttributeError:
            raise AttributeError("_VMSock." + name)

    def __setattr__(self, name, value):
        if name in self.__dict__:
            self.__dict__[name] = value
        else:
            for klass in self.__class__.__mro__:
                if name in klass.__dict__:
                    self.__dict__[name] = value
                    break
            else:
                setattr(self._sock, name, value)

    def connect(self, endpoint):
        return

    def get_model_driver(self):
        if self.model == "virtio":
            return "virtio-net-pci"
        return self.model


class VMPlugHostonly(VMPlug):

    mode = "hostonly"

    def connect(self, endpoint):
        pass

    def configured(self):
        return True

    def connected(self):
        return True


class Image:
    """
    locked if already in use as read/write non-cow.
    Disk must associate to this, and must check the locked flag
    before use.
    """

    master = None
    readonly = False

    def __init__(self, name, path, description=None, host=None):
        self.name = name
        self.path = path
        if description is not None:
            self.set_description(description)
        self.vmdisks = []
        self.host = host

    def set_readonly(self, value):
        self.readonly = value

    def is_readonly(self):
        return self.readonly

    def rename(self, newname):
        self.name = newname
        for vmd in self.vmdisks:
            vmd.VM.cfg["base" + vmd.device] = self.name

    def set_master(self, vmdisk):
       # XXX: Change name to something more useful
        if self.master is None:
            self.master = vmdisk
        if self.master == vmdisk:
            return True
        else:
            return False

    def get_master_name(self):
        if self.master is not None:
            return self.master.VM.name
        return ""

    def add_vmdisk(self, vmdisk):
        # XXX: O(n) complexity, a dict could fit?
        if vmdisk not in self.vmdisks:
            self.vmdisks.append(vmdisk)
        # for vmd in self.vmdisks:
        #     if vmd == vmdisk:
        #         return
        # self.vmdisks.append(vmdisk)

    def del_vmdisk(self, vmdisk):
        self.vmdisks.remove(vmdisk)
        if len(self.vmdisks) == 0 or self.master == vmdisk:
            self.master = None

    def description_file(self):
        return self.path + ".vbdescr"

    def set_description(self, descr):
        try:
            with open(self.description_file(), "w") as fp:
                fp.write(descr)
        except IOError:
            return False
        return True

    def get_description(self):
        try:
            with open(self.description_file()) as fp:
                return fp.read()
        except IOError:
            return ""

    def get_cows(self):
        return len([vmd for vmd in self.vmdisks if vmd.cow])

    def get_users(self):
        return len(self.vmdisks)

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

    def get_path(self):
        return self.path


DiskImage = Image


class Disk:

    @property
    def basefolder(self):
        return self.VM.get_basefolder()

    def __init__(self, VM, dev):
        self.VM = VM
        self.cow = False
        self.device = dev
        self.image = None

    def args(self, k):
        ret = []
        diskname = self.get_real_disk_name()
        if k:
            ret.append("-" + self.device)
        ret.append(diskname)
        return ret

    def set_image(self, image):
        ''' Old virtualbricks (0.4) will pass a full path here, new behavior
            is to pass the image nickname '''
        if len(image) == 0:
            img = None
            if self.image:
                self.image.vmdisks.remove(self)
                self.image = None
            return

        ''' Try to look for image by nickname '''
        img = self.VM.factory.get_image_by_name(image)
        if img:
            self.image = img
            img.add_vmdisk(self)
            self.VM.cfg["base" + self.device] = img.name
            if not self.cow and not self.VM.cfg["snapshot"] and self.image.set_master(self):
                log.debug("Machine %s acquired master lock on image %s",
                          self.VM.name, self.image.name)
            return True

        ''' If that fails: rollback to old behavior, and search for an already
            registered image under that path. '''
        if img is None:
            img = self.VM.factory.get_image_by_path(image)

        ''' If that fails: check for path existence and create a new image based
            there. It may be that we are using new method for the first time. '''
        if img is None:
            if os.access(image, os.R_OK):
                img = self.VM.factory.new_disk_image(os.path.basename(image), image)
        if img is None:
            return False

        self.image = img
        img.add_vmdisk(self)
        self.VM.cfg["base" + self.device] = img.name
        if not self.cow and not self.VM.cfg["snapshot"]:
            if self.image.set_master(self):
                log.debug("Machine %s acquired master lock on image %s",
                          self.VM.name, self.image.name)
            else:
                log.warning("ERROR SETTING MASTER!!")
        return True

    def get_base(self):
        return self.image.path

    def get_real_disk_name(self):
        if self.image is None:
            return ""
        if self.cow:
            if not os.path.exists(self.basefolder):
                os.makedirs(self.basefolder)
            cowname = self.basefolder + "/" + self.VM.name + "_" + self.device + ".cow"
            if os.access(cowname, os.R_OK):
                f = open(cowname)
                buff = f.read(1)
                while buff != '/':
                    buff = f.read(1)
                base = ""
                while buff != '\x00':
                    base += buff
                    buff = f.read(1)
                f.close()
                if base != self.get_base():
                    dt = datetime.now()
                    cowback = cowname + ".back-" + dt.strftime("%Y-%m-%d_%H-%M-%S")
                    log.debug("%s private cow found with a different base "
                              "image (%s): moving it in %s", cowname, base,
                              cowback)
                    move(cowname, cowback)
            if not os.access(cowname, os.R_OK):
                qmissing, qfound = tools.check_missing_qemu(
                    self.VM.settings.get("qemupath"))
                if "qemu-img" in qmissing:
                    raise errors.BadConfigError(_("qemu-img not found! I can't"
                                                  "create a new image."))
                else:
                    log.debug("Creating a new private COW from %s base image.",
                              self.get_base())
                    command = [self.VM.settings.get("qemupath") + "/qemu-img", "create", "-b", self.get_base(), "-f", self.VM.settings.get('cowfmt'), cowname]
                    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    proc.wait()
                    proc = subprocess.Popen(["/bin/sync"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    proc.wait()
            return cowname
        else:
            return self.image.path

    def readonly(self):
        return self.VM.cfg["snapshot"]

    def __repr__(self):
        return "<Disk %s(%s) image=%s readonly=%s>" % (self.device,
                                                       self.VM.name,
                                                       self.image,
                                                       self.readonly())


VMDisk = Disk


class VirtualMachine(bricks.Brick):

    type = "Qemu"
    term_command = "unixterm"
    # sudo_factory = QemuSudo
    command_builder = {
        "#argv0": "argv0",
        "#M": "machine",
        "#cpu": "cpu",
        "-smp": "smp",
        "-m": "ram",
        "-boot": "boot",
        # numa not supported
        "#basefda": "basefda",
        "#basefdb": "basefdb",
        "#basehda": "basehda",
        "#basehdb": "basehdb",
        "#basehdc": "basehdc",
        "#basehdd": "basehdd",
        "#basemtdblock": "basemtdblock",
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

    def set_name(self, name):
        self._name = name
        self.newbrick_changes()  # XXX: why?

    name = property(bricks.Brick.get_name, set_name)

    class config_factory(bricks.Config):

        parameters = {"name": bricks.String(""),

                      # boot options
                      "boot": bricks.String(""),
                      "snapshot": bricks.Boolean(False),

                      # cdrom device
                      "deviceen": bricks.String(""),
                      "device": bricks.String(""),
                      "cdromen": bricks.String(""),
                      "cdrom": bricks.String(""),

                      # additional media
                      "use_virtio": bricks.Boolean(False),
                      "basehda": bricks.String(""),
                      "hda": bricks.Object(None),
                      "privatehda": bricks.Boolean(False),
                      "basehdb": bricks.String(""),
                      "hdb": bricks.Object(None),
                      "privatehdb": bricks.Boolean(False),
                      "basehdc": bricks.String(""),
                      "hdc": bricks.Object(None),
                      "privatehdc": bricks.Boolean(False),
                      "basehdd": bricks.String(""),
                      "hdd": bricks.Object(None),
                      "privatehdd": bricks.Boolean(False),
                      "basefda": bricks.String(""),
                      "fda": bricks.Object(None),
                      "privatefda": bricks.Boolean(False),
                      "basefdb": bricks.String(""),
                      "fdb": bricks.Object(None),
                      "privatefdb": bricks.Boolean(False),
                      "basemtdblock": bricks.String(""),
                      "mtdblock": bricks.Object(None),
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
                      "usbdevlist": bricks.String(""),

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

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.terminal = "unixterm"
        self.cfg["name"] = name
        self.newbrick_changes()
        # self.connect("changed", lambda s: s.associate_disk())

    def poweron(self, snapshot=None):
        if snapshot is not None:
            self.original.cfg["loadvm"] = snapshot
        bricks.Brick.poweron(self)

    def get_basefolder(self):
        return self.factory.get_basefolder()

    def get_parameters(self):
        txt = _("command:") + " %s, ram: %s" % (self.prog(), self.cfg["ram"])
        for p in self.plugs:
            if p.mode == 'hostonly':
                txt += ', eth %s: Host' % unicode(p.vlan)
            elif p.sock:
                txt += ', eth %s: %s' % (unicode(p.vlan), p.sock.nickname)
        return txt

    def update_usbdevlist(self, dev, old):
        log.debug("update_usbdevlist: old [%s] - new[%s]", old, dev)
        for d in dev.split(' '):
            if not d in old.split(' '):
                self.send("usb_add host:" + d + "\n")
        # FIXME: Don't know how to remove old devices, due to the ugly syntax
        # of usb_del command.

    def associate_disk(self):
        for hd in ["hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock"]:
            disk = self.cfg[hd]
            if hasattr(disk, "image"):
                if (disk.image is not None and self.cfg["base" + hd] !=
                        disk.image.name):
                    disk.set_image(self.cfg["base" + hd])
                elif disk.image is None and self.cfg["base" + hd]:
                    disk.set_image(self.cfg["base" + hd])
            else:
                return

    def on_config_changed(self):
        self.associate_disk()  # XXX: really useful?
        bricks.Brick.on_config_changed(self)

    def set(self, attrs):
        bricks.Brick.set(self, attrs)
        self.associate_disk()  # XXX: really useful?

    def configured(self):
        cfg_ok = True
        for p in self.plugs:
            if p.sock is None and p.mode == 'vde':
                cfg_ok = False
        return cfg_ok

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

        if self.cfg["argv0"] and not self.cfg["kvm"]:
            cmd = self.settings.get("qemupath") + "/" + self.cfg["argv0"]
        else:
            cmd = self.settings.get("qemupath") + "/qemu"
        if self.cfg["kvm"]:
            cmd = self.settings.get("qemupath") + "/kvm"
        return cmd

    def args(self):
        res = []
        res.append(self.prog())
        if not self.cfg["kvm"]:
            if self.cfg["machine"] != "":
                res.extend(["-M", self.cfg["machine"]])
            if self.cfg["cpu"]:
                res.extend(["-cpu", self.cfg["cpu"]])
        res.extend(list(self.build_cmd_line()))
        if not self.has_graphic() or self.cfg["novga"]:
            res.extend(["-display", "none"])
        self.__clear_machine_vmdisks()
        idx = 0
        for dev in ["hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock"]:
            if self.cfg["base" + dev]:
                # master = False
                disk = self.cfg[dev]
                disk.cow = self.cfg["private" + dev]
                if not disk.cow and not disk.readonly():
                    if not disk.image.readonly:
                        if disk.image.set_master(disk):
                            log.debug(_("Machine %s acquired master lock on "
                                        "image %s"), self.name, disk.image.name)
                            # master = True
                        else:
                            raise errors.DiskLockedError(
                                _("Disk image %s already in use."),
                                disk.image.name)
                    else:
                        raise errors.DiskLockedError(
                            _("Disk image %s is marked as readonly and you are"
                              "not using private cow or snapshot mode."),
                            disk.image.name)
                if self.cfg["use_virtio"]:
                    res.extend(["-drive", "file=%s,if=virtio,index=%s" %
                                (disk.get_real_disk_name(), str(idx))])
                    idx += 1
                else:
                    # res.extend(disk.args(master))
                    res.extend(disk.args(True))
                    # XXX: check this
                    # if master:
                    #     args = disk.args(True)
                    #     res.append(args[0])
                    #     res.append(args[1])
                    # else:
                    #     args = disk.args(True)
                    #     res.append(args[0])
                    #     res.append(args[1])

        if self.cfg["kernelenbl"] and self.cfg["kernel"]:
            res.extend(["-kernel", self.cfg["kernel"]])
        if self.cfg["initrdenbl"] and self.cfg["initrd"]:
            res.extend(["-initrd", self.cfg["initrd"]])
        if self.cfg["kopt"] and self.cfg["kernelenbl"] and self.cfg["kernel"]:
            res.extend(["-append", re.sub("\"", "", self.cfg["kopt"])])
        if self.cfg["gdb"]:
            res.extend(["-gdb", "tcp::%d" % self.cfg["gdbport"]])
        if self.cfg["vnc"]:
            res.extend(["-vnc", ":%d" % self.cfg["vncN"]])
        if self.cfg["vga"]:
            res.extend(["-vga", "std"])

        if self.cfg["usbmode"]:
            for dev in self.cfg["usbdevlist"].split():
                res.extend(["-usbdevice", "host:%s" % dev])
            # The world is not ready for this, do chown /dev/bus/usb instead.
            # self._needsudo = True
        # else:
        #     self._needsudo = False

        res.extend(["-name", self.name])
        if not self.plugs and not self.socks:
            res.extend(["-net", "none"])
        else:
            for pl in sorted(self.plugs + self.socks, key=lambda p: p.vlan):
                res.append("-device")
                res.append("%s,vlan=%d,mac=%s,id=eth%s" % (pl.get_model_driver(), pl.vlan, pl.mac, str(pl.vlan)))
                if pl.mode == "vde":
                    res.append("-net")
                    res.append("vde,vlan=%d,sock=%s" % (pl.vlan, pl.sock.path.rstrip('[]')))
                elif pl.mode == "sock":
                    res.append("-net")
                    res.append("vde,vlan=%d,sock=%s" % (pl.vlan, pl.path))
                else:
                    res.extend(["-net", "user"])
        if self.cfg["cdromen"] and self.cfg["cdrom"]:
                res.extend(["-cdrom", self.cfg["cdrom"]])
        elif self.cfg["deviceen"] and self.cfg["device"]:
                res.extend(["-cdrom", self.cfg["device"]])
        if self.cfg["rtc"]:
            res.extend(["-rtc", "base=localtime"])
        if len(self.cfg.keyboard) == 2:
            res.extend(["-k", self.cfg["keyboard"]])
        if self.cfg["kvmsm"]:
            res.extend(["-kvm-shadow-memory", self.cfg["kvmsmem"]])
        if self.cfg["serial"]:
            res.extend(["-serial", "unix:%s/%s_serial,server,nowait" %
                        (settings.VIRTUALBRICKS_HOME, self.name)])
        res.extend(["-mon", "chardev=mon", "-chardev",
                    "socket,id=mon,path=%s,server,nowait" %
                    self.console(),
                    "-mon", "chardev=mon_cons", "-chardev",
                    "stdio,id=mon_cons,signal=off"])
        return res

    def __clear_machine_vmdisks(self):
        for image in self.factory.disk_images:
            for vmdisk in image.vmdisks:
                if vmdisk.VM is self:
                    image.del_vmdisk(vmdisk)
                    log.debug("VM disk lock released")
                    return

    def has_graphic(self):
        return False

    @deprecated(Version("virtualbricks", 1, 0), "brickfactory.dup_brick()")
    def __deepcopy__(self, memo):
        newname = self.factory.normalize(self.factory.next_name(
            "Copy_of_%s" % self.name))
        new_brick = type(self)(self.factory, newname)
        new_brick.cfg = copy.deepcopy(self.cfg, memo)
        new_brick.newbrick_changes()
        return new_brick

    def newbrick_changes(self):
        self.cfg["hda"] = Disk(self, "hda")
        self.cfg["hdb"] = Disk(self, "hdb")
        self.cfg["hdc"] = Disk(self, "hdc")
        self.cfg["hdd"] = Disk(self, "hdd")
        self.cfg["fda"] = Disk(self, "fda")
        self.cfg["fdb"] = Disk(self, "fdb")
        self.cfg["mtdblock"] = Disk(self, "mtdblock")
        self.associate_disk()

    def add_sock(self, mac=None, model=None):
        s = self.factory.new_sock(self)
        sock = VMSock(s)
        self.socks.append(sock)
        if mac:
            sock.mac = mac
        if model:
            sock.model = model
        self.gui_changed = True
        return sock

    def add_plug(self, sock=None, mac=None, model=None):
        p = self.factory.new_plug(self)
        plug = VMPlugHostonly(p) if sock == "_hostonly" else VMPlug(p)
        self.plugs.append(plug)
        plug.connect(sock)
        if mac:
            plug.mac = mac
        if model:
            plug.model = model
        self.gui_changed = True
        return plug

    def connect(self, endpoint):
        pl = self.add_plug()
        pl.mac = tools.RandMac()
        pl.model = 'rtl8139'
        pl.connect(endpoint)
        self.gui_changed = True

    def remove_plug(self, idx):
        for p in self.plugs:
            if p.vlan == idx:
                self.plugs.remove(p)
                del(p)
        for p in self.socks:
            if p.vlan == idx:
                self.socks.remove(p)
                del(p)
        for p in self.plugs:
            if p.vlan > idx:
                p.vlan -= 1
        for p in self.socks:
            if p.vlan > idx:
                p.vlan -= 1
        self.gui_changed = True

    def commit_disks(self, args):
        self.send("commit all\n")


VM = VirtualMachine
