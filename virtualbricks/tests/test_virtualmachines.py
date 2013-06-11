import os.path
import errno
import struct
import StringIO

from twisted.trial import unittest
from twisted.internet import defer

from virtualbricks import link, virtualmachines as vm, errors, tests
from virtualbricks.tests import stubs, test_link, Skip


def disks(vm):
    names = ("hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock")
    return (vm.cfg.__getitem__(d) for d in names)


ARGS = ["/usr/bin/i386", "-nographic", "-name", "vm", "-net", "none", "-mon",
        "chardev=mon", "-chardev", "socket,id=mon_cons,path=/home/marco/."
        "virtualbricks/vm.mgmt,server,nowait", "-mon", "chardev=mon_cons",
        "-chardev", "socket,id=mon,path=/home/marco/.virtualbricks/"
        "vm_cons.mgmt,server,nowait"]


class TestVirtualMachine(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.vm = vm.VirtualMachine(self.factory, "vm")

    @Skip("test outdated")
    def test_basic_args(self):
        # XXX: this will fail in another system
        self.assertEquals(self.vm.args(), ARGS)

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
        self.assertEqual(self.factory.socks, [sock._sock])

    def test_associate_disk_on_new_vm(self):
        for hd in "hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock":
            disk = self.vm.cfg[hd]
            self.assertTrue(hasattr(disk, "image"))
            self.assertIs(disk.image, None)
        basehda = self.mktemp()
        open(basehda, "w").close()
        self.vm.cfg["basehda"] = basehda
        self.vm._associate_disk()
        self.assertIsNot(self.vm.cfg["hda"], None)
        for hd in "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock":
            disk = self.vm.cfg[hd]
            self.assertTrue(hasattr(disk, "image"))
            self.assertIs(disk.image, None)


class TestVMPlug(test_link.TestPlug):

    @staticmethod
    def sock_factory(brick):
        return vm.VMSock(link.Sock(brick))

    @staticmethod
    def plug_factory(brick):
        return vm.VMPlug(link.Plug(brick))

    def get_real_plug(self):
        return self.plug._plug

    def test_model_driver(self):
        self.assertEqual(self.plug.get_model_driver(), self.plug.model)
        self.plug.model = "virtio"
        self.assertEqual(self.plug.get_model_driver(), "virtio-net-pci")

    def test_hotadd(self):
        # sock is not set
        self.assertRaises(AttributeError, self.plug.hotadd)
        # clean the communication
        del self.brick.sended[:]
        self.plug.connect(self.sock_factory(self.brick))
        self.brick.active = True
        self.plug.hotadd()
        comm = ["device_add rtl8139,mac=%s,vlan=0,id=eth0\n" % self.plug.mac,
                "host_net_add vde sock=%s,vlan=0\n" %
                self.plug.sock.path.rstrip('[]')]
        self.assertEqual(self.brick.sended, comm)

    def test_hostdel(self):
        self.plug.hotdel()
        comm = ["host_net_remove 0 vde.0\n", "device_del eth0\n"]
        self.assertEqual(self.brick.sended, comm)


class TestVMSock(test_link.TestSock):

    @staticmethod
    def plug_factory(brick):
        return vm.VMPlug(link.Plug(brick))

    @staticmethod
    def sock_factory(brick):
        return vm.VMSock(link.Sock(brick))

    def test_has_valid_path2(self):
        """Because a VMSock has already a valid path."""
        self.assertTrue(self.sock.has_valid_path())


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

    def _sync(self, ret):
        pass

    _basefolder = None

    def get_basefolder(self):
        if self._basefolder is not None:
            return self._basefolder
        return self.VM.get_basefolder()

    def set_basefolder(self, value):
        self._basefolder = value

    basefolder = property(get_basefolder, set_basefolder)


class TestDisk(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.vm = stubs.VirtualMachineStub(self.factory, "test_vm")
        self.disk = DiskStub(self.vm, "hda")
        self.disk.sync = "false"

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
        self.factory.settings.set("qemupath", "/supercali")
        result = []
        self.disk._create_cow("name").addErrback(result.append)
        self.assertEqual(len(result), 1)
        result[0].trap(errors.BadConfigError)
        qemupath = os.path.abspath(os.path.dirname(tests.__file__))
        self.factory.settings.set("qemupath", qemupath)
        self.disk.image = ImageStub()

        def cb(ret):
            self.fail("cow created, callback called with %s" % ret)

        def eb(failure):
            self.assertEqual(failure.type, RuntimeError)
        return self.disk._create_cow("1").addCallbacks(cb, eb)

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
