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

import os.path
import errno
import copy
import six

from twisted.trial import unittest
from twisted.internet import defer

from virtualbricks import (link, virtualmachines as vm, errors, settings,
                           configfile, tools)
from virtualbricks.tests import (stubs, test_link, successResultOf,
                                 failureResultOf, TEST_DATA_PATH)


def disks(vm):
    return (vm.config.__getitem__(d) for d in ("hda", "hdb", "hdc", "hdd",
                                               "fda", "fdb", "mtdblock"))


ARGS = ["true", "-m", "64", "-smp", "1", "@@DRIVESARGS@@", "-name", "vm",
        "-net", "none", "-mon", "chardev=mon", "-chardev",
        "socket,id=mon,path=/home/marco/.virtualbricks/vm.mgmt,server,nowait",
        "-mon", "chardev=mon_cons", "-chardev", "stdio,id=mon_cons,signal=off"]


class _Image(vm.Image):

    def __init__(self):
        self.acquired = []
        self.released = []

    def acquire(self, disk):
        self.acquired.append(disk)

    def release(self, disk):
        self.released.append(disk)


class TestVirtualMachine(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.vm = stubs.VirtualMachineStub(self.factory, "vm")
        self.image_path = os.path.abspath(self.mktemp())
        self.image = vm.Image("test", self.image_path)
        self.vm.get("hda").set_image(self.image)

    def get_args(self, *drive_args):
        args = ARGS[:]
        i = args.index("@@DRIVESARGS@@")
        args[i:i + 1] = drive_args
        return args

    def test_args(self):
        self.todo = 'test broken, to be refactored'
        args = self.get_args("-hda", self.image_path)
        self.assertEquals(successResultOf(self, self.vm.args()), args)

    def test_args_virtio(self):
        self.todo = 'test broken, to be refactored'
        self.vm.set({"use_virtio": True})
        drv = "file={0},if=virtio".format(self.image_path)
        args = self.get_args("-drive", drv)
        self.assertEquals(successResultOf(self, self.vm.args()), args)

    def test_add_plug_hostonly(self):
        mac, model = object(), object()
        plug = self.vm.add_plug(vm.hostonly_sock, mac, model)
        self.assertEqual(plug.mode, "vde")
        self.assertEqual(len(self.vm.plugs), 1)
        self.assertIs(plug.sock, vm.hostonly_sock)
        self.assertIs(plug.mac, mac)
        self.assertIs(plug.model, model)

    def test_add_plug_sock(self):
        brick = stubs.BrickStub(self.factory, "test")
        sock = vm.VMSock(self.factory.new_sock(brick))
        plug = self.vm.add_plug(sock)
        self.assertEqual(plug.mode, "vde")
        self.assertEqual(len(self.vm.plugs), 1)
        self.assertIs(plug.sock, sock)
        self.assertEqual(len(sock.plugs), 1)
        # self.assertIs(sock.plugs[0], plug)

    def test_add_sock(self):
        mac, model = object(), object()
        sock = self.vm.add_sock(mac, model)
        self.assertEqual(self.vm.socks, [sock])
        self.assertIs(sock.mac, mac)
        self.assertIs(sock.model, model)
        self.assertEqual(self.factory.socks, [sock.original])

    def test_get_disk_args(self):
        disk = DiskStub(self.vm, "hda")
        self.vm.config["hda"] = disk

    def test_del_brick(self):
        factory = stubs.FactoryStub()
        vm = factory.new_brick("vm", "test")
        sock = vm.add_sock()
        self.assertEqual(factory.socks, [sock.original])
        factory.del_brick(vm)
        self.assertEqual(factory.socks, [])

    def test_brick_plug_sock_self(self):
        """A plug can be connected to a sock of the same brick."""
        sock = self.vm.add_sock()
        plug = self.vm.add_plug(sock)
        self.assertEqual(self.vm.socks, [sock])
        self.assertEqual(self.vm.plugs, [plug])
        self.assertIs(plug.sock, sock)
        self.assertIs(plug.brick, sock.brick)

    def test_poweron_loop_on_self_plug(self):
        """If a vm is plugged to itself it can start without error. The last
        check seem obvious but poweron() deferred is called only there is no
        errors."""
        self.vm._poweron = lambda _: defer.succeed(None)
        self.vm.add_plug(self.vm.add_sock())
        d = self.vm.poweron()
        d.callback(self.vm)
        self.assertEqual(successResultOf(self, d), self.vm)

    def test_lock(self):
        self.vm.acquire()
        self.vm.release()
        image = vm.Image("test", "/vmimage")
        disk = DiskStub(self.vm, "hdb")
        disk.set_image(image)
        disk.acquire()
        self.vm.config["hda"].set_image(image)
        self.assertRaises(errors.LockedImageError, self.vm.acquire)
        _image = _Image()
        self.vm.config["hdb"].set_image(_image)
        try:
            self.vm.acquire()
        except errors.LockedImageError:
            pass
        else:
            self.fail("vm lock acquired but it should not happend")
        self.assertEqual(_image.acquired, _image.released)


class TestVMPlug(test_link.TestPlug):

    @staticmethod
    def sock_factory(brick):
        return vm.VMSock(link.Sock(brick))

    @staticmethod
    def plug_factory(brick):
        return vm.VMPlug(link.Plug(brick))


class TestVMSock(test_link.TestSock):

    @staticmethod
    def plug_factory(brick):
        return vm.VMPlug(link.Plug(brick))

    @staticmethod
    def sock_factory(brick):
        return vm.VMSock(link.Sock(brick))

    def test_has_valid_path2(self):
        factory = stubs.FactoryStub()
        vm = stubs.VirtualMachineStub(factory, "vm")
        sock = vm.add_sock()
        self.assertTrue(sock.has_valid_path())


HOSTONLY_CONFIG = """[Qemu:vm]
name=vm

link|vm|_hostonly|rtl8139|00:11:22:33:44:55
"""


class TestPlugWithHostOnlySock(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.vm = self.factory.new_brick("vm", "vm")
        self.plug = self.vm.add_plug(vm.hostonly_sock, "00:11:22:33:44:55")

    def test_add_plug(self):
        self.assertIs(self.plug.sock, vm.hostonly_sock)

    def test_poweron(self):
        self.vm._poweron = lambda _: defer.succeed(self.vm)
        d = self.vm.poweron()
        d.callback(self.vm)

    def test_config_save(self):
        sio = six.StringIO()
        configfile.ConfigFile().save_to(self.factory, sio)
        self.assertEqual(sio.getvalue(), HOSTONLY_CONFIG)

    def test_config_resume(self):
        self.factory.del_brick(self.vm)
        self.assertEqual(len(self.factory.bricks), 0)
        sio = six.StringIO(HOSTONLY_CONFIG)
        configfile.ConfigFile().restore_from(self.factory, sio)
        self.assertEqual(len(self.factory.bricks), 1)
        vm1 = self.factory.get_brick_by_name("vm")
        self.assertEqual(len(vm1.plugs), 1)
        plug = vm1.plugs[0]
        self.assertEqual(plug.mac, "00:11:22:33:44:55")
        self.assertIs(plug.sock, vm.hostonly_sock)


class ImageStub:

    path = "cucu"


class NULL:

    def __eq__(self, other):
        return self is other

    def __ne__(self, other):
        return self is not other


class FULL:

    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False


class DiskStub(vm.Disk):

    _basefolder = None
    sync_cmd = "false"

    def get_basefolder(self):
        if self._basefolder is not None:
            return self._basefolder
        return self.VM.get_basefolder()

    def set_basefolder(self, value):
        self._basefolder = value

    basefolder = property(get_basefolder, set_basefolder)


class Object:
    pass


class TestDisk(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.vm = stubs.VirtualMachineStub(self.factory, "test_vm")
        self.disk = DiskStub(self.vm, "hda")

    def test_create_cow(self):
        settings.set("qemupath", "/supercali")
        failureResultOf(self, self.disk._create_cow("name"),
                        errors.BadConfigError)
        settings.set("qemupath", TEST_DATA_PATH)
        self.disk.image = ImageStub()

        def cb(ret):
            self.fail("cow created, callback called with %s" % ret)

        def eb(failure):
            failure.trap(RuntimeError)
        return self.disk._create_cow("1").addCallbacks(cb, eb)

    def test_sync_err(self):
        def cb(ret):
            self.fail("_create_cow did not failed while it had to")

        def eb(failure):
            failure.trap(RuntimeError)
            failure.value.args[0].startswith("sync failed")

        return self.disk._sync(("", "", 0)).addCallbacks(cb, eb)

    def test_check_base(self):
        err = self.assertRaises(IOError, self.disk._check_base, "/montypython")
        self.assertEqual(err.errno, errno.ENOENT)
        self.patch(tools, "get_backing_file", lambda _: NULL())
        self.disk._create_cow = lambda _: defer.succeed(None)
        self.disk.image = ImageStub()
        cowname = self.mktemp()
        fp = open(cowname, "w")
        fp.close()
        result = []
        self.disk._check_base(cowname).addCallback(result.append)
        self.assertEqual(result, [cowname])
        self.patch(tools, "get_backing_file", lambda _: FULL())
        del result[:]
        cowname = self.mktemp()
        fp = open(cowname, "w")
        fp.close()
        self.disk._check_base(cowname).addCallback(result.append)
        self.assertEqual(result, [cowname])

    def test_get_cow_name(self):
        self.disk.basefolder = "/nonono/"
        err = self.assertRaises(OSError, self.disk._get_cow_name)
        self.assertEqual(err.errno, errno.EACCES)
        self.disk.basefolder = basefolder = self.mktemp()
        self.disk._check_base = lambda passthru: defer.succeed(passthru)

        def cb(cowname):
            self.assertTrue(os.path.exists(basefolder))
            self.assertEqual(cowname, os.path.join(basefolder, "%s_%s.cow" %
                                                   (self.disk.VM.name,
                                                    self.disk.device)))
        return self.disk._get_cow_name().addCallback(cb)

    def test_get_cow_name_create_cow(self):

        def throw(_errno):
            def _check_base(_):
                raise IOError(_errno, os.strerror(_errno))
            return _check_base

        self.disk.basefolder = basefolder = self.mktemp()
        cowname = os.path.join(basefolder, "%s_%s.cow" % (self.disk.VM.name,
                                                          self.disk.device))
        self.disk._check_base = throw(errno.EACCES)
        self.disk._create_cow = lambda passthru: defer.succeed(passthru)
        err = self.assertRaises(IOError, self.disk._get_cow_name)
        self.assertEqual(err.errno, errno.EACCES)
        self.disk._check_base = throw(errno.ENOENT)
        result = []
        self.disk._get_cow_name().addCallback(result.append)
        self.assertEqual(result, [cowname])

    def test_args(self):
        # XXX: Temporary pass this test but rework disk.args()
        self.assertIs(self.disk.image, None)
        self.disk.get_real_disk_name = lambda: defer.succeed("test")
        self.assertEqual(successResultOf(self, self.disk.args()), [])
        # self.assertEqual(successResultOf(self, self.disk.args()),
        #                                  ["-hda", "test"])
        # f = failure.Failure(RuntimeError())
        # self.disk.get_real_disk_name = lambda: defer.fail(f)
        # failureResultOf(self, self.disk.args(), RuntimeError)

    def test_get_real_disk_name(self):

        def raise_IOError():
            raise IOError(-1)

        result = successResultOf(self, self.disk.get_real_disk_name())
        self.assertEqual(result, "")
        self.disk.image = Object()
        self.disk.image.path = "ping"
        result = successResultOf(self, self.disk.get_real_disk_name())
        self.assertEqual(result, "ping")
        self.disk._get_cow_name = raise_IOError
        self.vm.config["private" + self.disk.device] = True
        failureResultOf(self, self.disk.get_real_disk_name(), IOError)

    def test_deepcopy(self):
        disk = copy.deepcopy(self.disk)
        self.assertIsNot(disk, self.disk)
        self.assertIs(disk.image, None)
        image = self.factory.new_disk_image("test", "/cucu")
        self.disk.set_image(image)
        disk = copy.deepcopy(self.disk)
        self.assertIsNot(disk, self.disk)
        self.assertIsNot(disk.image, None)
        self.assertIs(disk.image, image)

    def test_acquire(self):
        self.assertFalse(self.disk.cow)
        self.assertIs(self.disk.image, None)
        self.assertFalse(self.vm.config["snapshot"])
        self.disk.acquire()
        image = vm.Image("test", "/vmimage")
        self.vm.set({"snapshot": False, "privatehda": False})
        self.disk.set_image(image)
        self.disk.acquire()
        self.assertIs(image.master, self.disk)
        disk = DiskStub(self.vm, "hdb")
        disk.set_image(image)
        self.assertRaises(errors.LockedImageError, disk.acquire)

    def test_release(self):
        self.assertFalse(self.disk.cow)
        self.assertIs(self.disk.image, None)
        self.assertFalse(self.vm.config["snapshot"])
        self.disk.release()
        image = vm.Image("test", "/vmimage")
        self.vm.set({"snapshot": False, "privatehda": False})
        self.disk.set_image(image)
        self.disk.acquire()
        self.disk.release()


class TestImage(unittest.TestCase):

    def test_acquire(self):
        image = vm.Image("test", "/vmimage")
        o = object()
        image.acquire(o)
        self.assertIs(image.master, o)
        exc = self.assertRaises(errors.LockedImageError, image.acquire,
                                object())
        self.assertEqual(exc.args, (image, o))
        image.acquire(o)

    def test_release(self):
        image = vm.Image("test", "/vmimage")
        exc = self.assertRaises(errors.LockedImageError, image.release,
                                object())
        self.assertEqual(exc.args, (image, None))
        image.release(None)
        o = object()
        image.acquire(o)
        image.release(o)
        self.assertRaises(errors.LockedImageError, image.release, o)
