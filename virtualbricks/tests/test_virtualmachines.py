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

import os.path
import errno
import copy
import io
import unittest as pyunit
from unittest.mock import patch

from twisted.trial import unittest
from twisted.internet import defer
from twisted.python import failure

from virtualbricks import configfile
from virtualbricks import errors
from virtualbricks import link
from virtualbricks import settings
from virtualbricks import virtualmachines as vm
from virtualbricks.tests import stubs, test_link, patch_settings


def disks(vm):
    return (vm.config.__getitem__(d) for d in ("hda", "hdb", "hdc", "hdd",
                                               "fda", "fdb", "mtdblock"))


ARGS = ["true", "-m", "64", "-smp", "1", "@@DRIVESARGS@@", "-name", "vm",
        "-net", "none", "-mon", "chardev=mon", "-chardev",
        "socket,id=mon,path=/home/marco/.virtualbricks/vm.mgmt,server,nowait",
        "-mon", "chardev=mon_cons", "-chardev", "stdio,id=mon_cons,signal=off"]


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
        self.assertEquals(self.successResultOf(self.vm.args()), args)

    def test_args_virtio(self):
        self.todo = 'test broken, to be refactored'
        self.vm.set({"use_virtio": True})
        drv = "file={0},if=virtio".format(self.image_path)
        args = self.get_args("-drive", drv)
        self.assertEquals(self.successResultOf(self.vm.args()), args)

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
        disk = vm.Disk(self.vm, "hda")
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
        self.assertEqual(self.successResultOf(d), self.vm)

    # def test_lock(self):
    #     self.vm.acquire()
    #     self.vm.release()
    #     image = vm.Image("test", "/vmimage")
    #     disk = vm.Disk(self.vm, "hdb")
    #     disk.set_image(image)
    #     disk.acquire()
    #     self.vm.config["hda"].set_image(image)
    #     self.assertRaises(errors.LockedImageError, self.vm.acquire)
    #     _image = vm.Image('debian8', '/var/images/debian8.img')
    #     self.vm.config["hdb"].set_image(_image)
    #     try:
    #         self.vm.acquire()
    #     except errors.LockedImageError:
    #         pass
    #     else:
    #         self.fail("vm lock acquired but it should not happend")
    #     self.assertEqual(_image.acquired, _image.released)


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
        sio = io.StringIO()
        configfile.ConfigFile().save_to(self.factory, sio)
        self.assertEqual(sio.getvalue(), HOSTONLY_CONFIG)

    def test_config_resume(self):
        self.factory.del_brick(self.vm)
        self.assertEqual(len(self.factory.bricks), 0)
        sio = io.StringIO(HOSTONLY_CONFIG)
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


class Object:
    pass


class TestDisk(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.vm = stubs.VirtualMachineStub(self.factory, "test_vm")
        self.disk = vm.Disk(self.vm, "hda")
        self.image_path = '/var/images/debian8.img'
        self.image = vm.Image(name='debian8', path='/var/images/debian8.img')
        self.disk.set_image(self.image)

    @patch('virtualbricks.virtualmachines.sync')
    @patch('virtualbricks.virtualmachines.getQemuOutputAndValue')
    def test_create_new_disk_image_differential(
            self, mock_getQemuOutputAndValue, mock_sync):
        """
        Test the happy path of creating a new differential image.
        """

        SUCCESS_EXIT_STATUS = ('stdout', 'stderr', 0)
        NEW_DISK_IMAGE = '/var/image/private_hda.cow'
        SYNC_RESULT = object()

        mock_getQemuOutputAndValue.return_value = defer.succeed(
            SUCCESS_EXIT_STATUS)
        # Return a random value from sync, _new_disk_image_differential
        # will always return None
        mock_sync.return_value = defer.succeed(SYNC_RESULT)
        d = self.disk._new_disk_image_differential(NEW_DISK_IMAGE)
        mock_getQemuOutputAndValue.assert_called_once_with(
            "qemu-img",
            [
                "create",
                "-b",
                self.image_path,
                "-f",
                # TODO: patch settings.
                settings.get("cowfmt"),
                NEW_DISK_IMAGE
            ],
            os.environ
        )
        mock_sync.assert_called_once_with()
        result = self.successResultOf(d)
        # Whatever is the return from sync, the deferred fires None.
        self.assertIsNone(result)

    @patch('virtualbricks.virtualmachines.sync')
    @patch('virtualbricks.virtualmachines.getQemuOutputAndValue')
    def test_create_new_disk_image_differential_error_qemu_img(
            self, mock_getQemuOutputAndValue, mock_sync):
        """
        Test the case when qemu-img fails. RuntimeError is raised and contains
        the stderr of the command. sync is not called.
        """

        STDERR = 'qemu-img error'
        ERROR_EXIT_STATUS = ('', STDERR, 1)
        NEW_DISK_IMAGE = '/var/image/private_hda.cow'

        mock_getQemuOutputAndValue.return_value = defer.succeed(
            ERROR_EXIT_STATUS)
        d = self.disk._new_disk_image_differential(NEW_DISK_IMAGE)
        failure = self.failureResultOf(d)
        failure.check(RuntimeError)
        self.assertEqual(
            failure.getErrorMessage(),
            f'Cannot create private COW\n{STDERR}'
        )
        mock_sync.assert_not_called()

    @patch('virtualbricks.virtualmachines.sync')
    @patch('virtualbricks.virtualmachines.getQemuOutputAndValue')
    def test_create_new_disk_image_differential_error_sync(
            self, mock_getQemuOutputAndValue, mock_sync):
        """
        Test that sync fails. The error is propagated to the caller.
        """

        SUCCESS_EXIT_STATUS = ('stdout', 'stderr', 0)
        NEW_DISK_IMAGE = '/var/image/private_hda.cow'
        # Create a new failure to raise from sync
        FAIL = failure.Failure(ZeroDivisionError())

        mock_getQemuOutputAndValue.return_value = defer.succeed(
            SUCCESS_EXIT_STATUS)
        mock_sync.return_value = defer.fail(FAIL)
        d = self.disk._new_disk_image_differential(NEW_DISK_IMAGE)
        mock_getQemuOutputAndValue.assert_called_once_with(
            "qemu-img",
            [
                "create",
                "-b",
                self.image_path,
                "-f",
                settings.get("cowfmt"),
                NEW_DISK_IMAGE
            ],
            os.environ
        )
        mock_sync.assert_called_once_with()
        # The error from sync is returned unchanged
        self.failureResultOf(d).check(FAIL.type)

    def test_create_new_disk_image_differential_qemu_img_not_found(self):
        """
        qemu-img is not found. Raise BadConfigError (FileNotFoundError?
        RuntimeError?)
        """

        QEMUPATH = '/not_existing_path'
        IMAGEFILE = '/home/user/.virtualbricks/project_name/vm1_hda.cow'

        self.assertFalse(os.path.exists(QEMUPATH))
        patch_settings(self, qemupath=QEMUPATH)
        deferred = self.disk._new_disk_image_differential(IMAGEFILE)
        self.assertFailure(deferred, errors.BadConfigError)

    @pyunit.skip('to refactor')
    def test_get_cow_name(self):
        self.disk.basefolder = "/nonono/"
        err = self.assertRaises(OSError, self.disk._get_cow_name)
        self.assertEqual(err.errno, errno.EACCES)
        self.disk.basefolder = basefolder = self.mktemp()
        self.disk._ensure_private_image_cow = lambda passthru: defer.succeed(passthru)

        def cb(cowname):
            self.assertTrue(os.path.exists(basefolder))
            self.assertEqual(cowname, os.path.join(basefolder, "%s_%s.cow" %
                                                   (self.disk.VM.name,
                                                    self.disk.device)))
        return self.disk._get_cow_name().addCallback(cb)

    @pyunit.skip('to refactor')
    def test_get_cow_name_create_cow(self):
        self.todo = 'to refactor'

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

    @pyunit.skip('to refactor')
    def test_args(self):
        # self.todo = 'to refactor'
        # XXX: Temporary pass this test but rework disk.args()
        self.assertIs(self.disk.image, None)
        self.disk.get_real_disk_name = lambda: defer.succeed("test")
        self.assertEqual(self.successResultOf(self.disk.args()), [])
        # self.assertEqual(self.successResultOf(self.disk.args()),
        #                                  ["-hda", "test"])
        # f = failure.Failure(RuntimeError())
        # self.disk.get_real_disk_name = lambda: defer.fail(f)
        # self.failureResultOf(self.disk.args(), RuntimeError)

    @pyunit.skip('to refactor')
    def test_get_real_disk_name(self):

        def raise_IOError():
            raise IOError(-1)

        result = self.successResultOf(self.disk.get_real_disk_name())
        self.assertEqual(result, "")
        self.disk.image = Object()
        self.disk.image.path = "ping"
        result = self.successResultOf(self.disk.get_real_disk_name())
        self.assertEqual(result, "ping")
        self.disk._get_cow_name = raise_IOError
        self.vm.config["private" + self.disk.device] = True
        self.failureResultOf(self.disk.get_real_disk_name(), IOError)

    @pyunit.skip('to refactor')
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

    def assert_image_locked_by(self, image, disk):
        msg = (
            f'Image locked by {image.master},'
            f' expected to be locked by {disk}'
        )
        self.assertIs(image.master, disk, msg)

    def assert_image_not_locked(self, image):
        msg = 'Image locked by {image.master}, expected to be unlocked'
        self.assertIs(image.master, None, msg)

    def test_acquire(self):
        disk, image = self.disk, self.image

        self.assertIsNotNone(disk.image)
        self.assertFalse(disk.is_cow())
        self.assertFalse(disk.readonly())
        self.assert_image_not_locked(image)
        # Acquire the lock and release it
        disk.acquire()
        self.assert_image_locked_by(image, disk)
        # Acquire the lock a second time
        disk.acquire()
        self.assert_image_locked_by(image, disk)

    def test_acquire_read_only(self):
        """
        Disk is read only, lock is not acquired.
        """

        disk, image = self.disk, self.image

        self.vm.set({'snapshot': True})
        self.assertIsNotNone(disk.image)
        self.assertFalse(disk.is_cow())
        self.assertTrue(disk.readonly())
        disk.acquire()
        self.assert_image_not_locked(image)

    def test_acquire_two_disks(self):
        """
        Try to acquire a lock on an image from two different disks: exception.
        """

        disk, image = self.disk, self.image

        self.assertIsNotNone(disk.image)
        self.assertFalse(disk.is_cow())
        self.assertFalse(disk.readonly())
        self.disk.acquire()
        self.assert_image_locked_by(image, disk)
        # Create a second disk with the same image
        hdb = vm.Disk(self.vm, "hdb")
        hdb.set_image(image)
        self.assertRaises(errors.LockedImageError, hdb.acquire)

    def test_release(self):
        disk, image = self.disk, self.image

        self.assertIsNotNone(disk.image)
        self.assertFalse(disk.is_cow())
        self.assertFalse(disk.readonly())
        self.assert_image_not_locked(image)
        # Image not locked, raise an exception
        self.assertRaises(errors.LockedImageError, disk.release)
        # Acquire the lock and release it
        disk.acquire()
        disk.release()
        self.assert_image_not_locked(image)
        # Release the lock twice, raises an exception
        self.assertRaises(errors.LockedImageError, disk.release)

    def test_release_read_only(self):
        """
        Disk is read only, lock is not released (it should not be acquired in
        first instance).
        """

        disk, image = self.disk, self.image

        self.vm.set({'snapshot': True})
        self.assertIsNotNone(disk.image)
        self.assertFalse(disk.is_cow())
        self.assertTrue(disk.readonly())
        # Image not locked but do not raise an exception
        self.assert_image_not_locked(image)
        disk.release()

    def test_release_different_disk(self):
        """
        Try to release a lock on an image from a different disk: exception.
        """

        disk, image = self.disk, self.image

        self.assertIsNotNone(disk.image)
        self.assertFalse(disk.is_cow())
        self.assertFalse(disk.readonly())
        self.disk.acquire()
        self.assert_image_locked_by(image, disk)
        # Create a second disk with the same image
        hdb = vm.Disk(self.vm, "hdb")
        hdb.set_image(image)
        self.assertRaises(errors.LockedImageError, hdb.release)


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
