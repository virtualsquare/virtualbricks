from twisted.trial import unittest

from virtualbricks import link, virtualmachines
from virtualbricks.tests import stubs, test_link


def disks(vm):
    names = ("hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock")
    return (vm.cfg.__getitem__(d) for d in names)


ARGS = ["/usr/bin/i386", "-nographic", "-name", "vm", "-net", "none", "-mon",
        "chardev=mon", "-chardev",
        "socket,id=mon,path=/home/marco/.virtualbricks/vm.mgmt,server,nowait",
        "-mon"]


class TestVirtualMachine(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.vm = virtualmachines.VM(self.factory, "vm")

    # @unittest.skip("test outdated")
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
        sock = virtualmachines.VMSock(self.factory.new_sock(brick))
        plug = self.vm.add_plug(sock)
        self.assertEqual(plug.mode, "vde")
        self.assertEqual(len(self.vm.plugs), 1)
        self.assertIs(plug.sock, sock)
        self.assertEqual(len(sock.plugs), 1)
        # self.assertIs(sock.plugs[0], plug)

    def test_add_sock(self):
        # import pdb; pdb.set_trace()
        mac, model = object(), object()
        sock = self.vm.add_sock(mac, model)
        self.assertEqual(self.vm.socks, [sock])
        self.assertIs(sock.mac, mac)
        self.assertIs(sock.model, model)
        self.assertEqual(self.factory.socks, [sock._sock])


class TestVMPlug(test_link.TestPlug):

    @staticmethod
    def sock_factory(brick):
        return virtualmachines.VMSock(link.Sock(brick))

    @staticmethod
    def plug_factory(brick):
        return virtualmachines.VMPlug(link.Plug(brick))

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
        return virtualmachines.VMPlug(link.Plug(brick))

    @staticmethod
    def sock_factory(brick):
        return virtualmachines.VMSock(link.Sock(brick))

    def test_has_valid_path2(self):
        """Because a VMSock has already a valid path."""
        self.assertTrue(self.sock.has_valid_path())
