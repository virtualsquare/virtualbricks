import os.path
import errno
import struct
import copy
import StringIO

from twisted.trial import unittest
from twisted.internet import defer
from twisted.python import failure

from virtualbricks import link, virtualmachines as vm, errors, tests, settings
from virtualbricks.tests import (stubs, test_link, successResultOf,
                                 failureResultOf)


def disks(vm):
    names = ("hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock")
    return (vm.config.__getitem__(d) for d in names)


ARGS = ["/usr/bin/i386", "-nographic", "-name", "vm", "-net", "none", "-mon",
        "chardev=mon", "-chardev", "socket,id=mon_cons,path=/home/marco/."
        "virtualbricks/vm.mgmt,server,nowait", "-mon", "chardev=mon_cons",
        "-chardev", "socket,id=mon,path=/home/marco/.virtualbricks/"
        "vm_cons.mgmt,server,nowait"]


class TestVirtualMachine(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.vm = stubs.VirtualMachineStub(self.factory, "vm")

    # @Skip("test outdated")
    # def test_basic_args(self):
    #     # XXX: this will fail in another system
    #     self.assertEquals(self.vm.args(), ARGS)

    def test_disk_on_rename(self):
        olds = list(disks(self.vm))
        self.vm.name = "vmng"
        for old, new in zip(olds, disks(self.vm)):
            self.assertIsNot(old, new)

    def test_add_plug_hostonly(self):
        mac, model = object(), object()
        plug = self.vm.add_plug("_hostonly", mac, model)
        self.assertEqual(plug.mode, "hostonly")
        self.assertEqual(len(self.vm.plugs), 1)
        self.assertIs(plug.sock, None)
        self.assertIs(plug.mac, mac)
        self.assertIs(plug.model, model)

    def test_add_plug_empty(self):
        plug = self.vm.add_plug()
        self.assertEqual(plug.mode, "vde")
        self.assertEqual(len(self.vm.plugs), 1)

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

    def test_associate_disk_on_new_vm(self):
        for hd in "hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock":
            disk = self.vm.config[hd]
            self.assertTrue(hasattr(disk, "image"))
            self.assertIs(disk.image, None)
        basehda = self.mktemp()
        open(basehda, "w").close()
        self.vm.config["basehda"] = basehda
        self.vm._associate_disk()
        self.assertIsNot(self.vm.config["hda"], None)
        for hd in "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock":
            disk = self.vm.config[hd]
            self.assertTrue(hasattr(disk, "image"))
            self.assertIs(disk.image, None)

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


class TestVMPlug(test_link.TestPlug):

    @staticmethod
    def sock_factory(brick):
        return vm.VMSock(link.Sock(brick))

    @staticmethod
    def plug_factory(brick):
        return vm.VMPlug(link.Plug(brick))

    def get_real_plug(self):
        return self.plug._plug

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


HELLO = "/hello/backingfile"
COW_HEADER = "OOOM\x00\x00\x00\x02" + HELLO + "\x00" * 1006
QCOW_HEADER = "QFI\xfb\x00\x00\x00\x01" + struct.pack(">Q", 20) + \
        struct.pack(">I", len(HELLO)) + HELLO
QCOW_HEADER0 = "QFI\xfb\x00\x00\x00\x01" + "\x00" * 12
QCOW_HEADER2 = "QFI\xfb\x00\x00\x00\x02" + struct.pack(">Q", 20) + \
        struct.pack(">I", len(HELLO)) + HELLO
UNKNOWN_HEADER = "MOOO\x00\x00\x00\x02"


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

    def test_backing_file_from_cow(self):
        sio = StringIO.StringIO(COW_HEADER[8:])
        backing_file = self.disk._get_backing_file_from_cow(sio)
        self.assertEqual(backing_file, HELLO)

    def test_backing_file_from_qcow0(self):
        sio = StringIO.StringIO(QCOW_HEADER0[8:])
        backing_file = self.disk._get_backing_file_from_qcow(sio)
        self.assertEqual(backing_file, "")

    def test_backing_file_from_qcow(self):
        sio = StringIO.StringIO(QCOW_HEADER)
        sio.seek(8)
        backing_file = self.disk._get_backing_file_from_qcow(sio)
        self.assertEqual(backing_file, HELLO)

    def test_backing_file(self):
        for header in COW_HEADER, QCOW_HEADER, QCOW_HEADER2:
            sio = StringIO.StringIO(header)
            backing_file = self.disk._get_backing_file(sio)
            self.assertEqual(backing_file, "/hello/backingfile")

        sio = StringIO.StringIO(UNKNOWN_HEADER)
        self.assertRaises(RuntimeError, self.disk._get_backing_file, sio)

    def test_create_cow(self):
        settings.set("qemupath", "/supercali")
        failureResultOf(self, self.disk._create_cow("name"),
                        errors.BadConfigError)
        qemupath = os.path.abspath(os.path.dirname(tests.__file__))
        settings.set("qemupath", qemupath)
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
        self.disk._get_backing_file = lambda _: NULL()
        self.disk._create_cow = lambda _: defer.succeed(None)
        self.disk.image = ImageStub()
        cowname = self.mktemp()
        fp = open(cowname, "w")
        fp.close()
        result = []
        self.disk._check_base(cowname).addCallback(result.append)
        self.assertEqual(result, [cowname])
        self.disk._get_backing_file = lambda _: FULL()
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
        self.disk.get_real_disk_name = lambda: defer.succeed("test")
        self.assertEqual(successResultOf(self, self.disk.args()),
                                         ["-hda", "test"])
        f = failure.Failure(RuntimeError())
        self.disk.get_real_disk_name = lambda: defer.fail(f)
        failureResultOf(self, self.disk.args(), RuntimeError)

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
        self.disk.set_image("test")
        disk = copy.deepcopy(self.disk)
        self.assertIsNot(disk, self.disk)
        self.assertIsNot(disk.image, None)
        self.assertIs(disk.image, image)

