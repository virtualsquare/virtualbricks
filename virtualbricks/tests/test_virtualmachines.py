from virtualbricks import link, virtualmachines
from virtualbricks.tests import unittest, stubs, test_link


def disks(vm):
    names = ("hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock")
    return (vm.cfg.__getitem__(d) for d in names)


ARGS = ["/usr/bin/i386", "-nographic", "-name", "vm", "-net", "none", "-mon",
        "chardev=mon", "-chardev",
        "socket,id=mon_cons,path=/home/marco/.virtualbricks/vm.mgmt,server,nowait",
        "-mon", "chardev=mon_cons", "-chardev",
        "socket,id=mon,path=/home/marco/.virtualbricks/vm_cons.mgmt,server,nowait"]


class TestVirtualMachine(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.vm = virtualmachines.VM(self.factory, "vm")

    def test_basic_args(self):
        # XXX: this will fail in another system
        self.assertEquals(self.vm.args(), ARGS)

    def test_disk_on_rename(self):
        olds = list(disks(self.vm))
        self.vm.name = "vmng"
        for old, new in zip(olds, disks(self.vm)):
            self.assertIsNot(old, new)


class TestVMPlug(test_link.TestPlug):

    plug_factory = virtualmachines.VMPlug
    sock_factory = virtualmachines.VMSock

    def test_model_driver(self):
        self.assertEqual(self.plug.get_model_driver(), self.plug.model)
        self.plug.model = "virtio"
        self.assertEqual(self.plug.get_model_driver(), "virtio-net-pci")

    def test_hotadd(self):
        # sock is not set
        self.assertRaises(AttributeError, self.plug.hotadd)
        self.assertIs(self.brick.internal_console, None)
        self.plug.connect(self.sock_factory(self.brick))
        cnsl = self.brick.internal_console = self.brick.open_internal_console()
        self.brick.active = True
        self.plug.hotadd()
        self.assertEqual(cnsl, ["device_add rtl8139,mac=%s,vlan=0,id=eth0\n" %
                                self.plug.mac,
                                "host_net_add vde sock=%s,vlan=0\n" %
                                self.plug.sock.path.rstrip('[]')])

    def test_hostdel(self):
        # sock is not set
        self.assertRaises(AttributeError, self.plug.hotadd)
        self.assertIs(self.brick.internal_console, None)
        self.plug.connect(self.sock_factory(self.brick))
        cnsl = self.brick.internal_console = self.brick.open_internal_console()
        self.brick.active = True
        self.plug.hotdel()
        self.assertEqual(cnsl, ["host_net_remove 0 vde.0\n",
                                "device_del eth0\n"])


class Test_VMPlug(TestVMPlug):

    @staticmethod
    def plug_factory(brick):
        return virtualmachines._VMPlug(link.Plug(brick))


class TestVMSock(test_link.TestSock):

    plug_factory = virtualmachines.VMPlug
    sock_factory = virtualmachines.VMSock

    def test_has_valid_path2(self):
        """Because a VMSock has already a valid path."""
        self.assertTrue(self.sock.has_valid_path())


class Test_VMSock(TestVMSock):

    @staticmethod
    def sock_factory(brick):
        return virtualmachines._VMSock(link.Sock(brick))
