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


"""The virtual machines: disks, network cards, command line."""

import os

from twisted.internet import defer

from virtualbricks import bricks
from virtualbricks.qemu import imageformat
from virtualbricks.bricks import virtualmachine
from virtualbricks.config.workspace import OpenProject
from virtualbricks.config.report import Report
from virtualbricks.tests import (
    use_workspace,
    BrickTestCase,
    CommandTestCase,
    FakeLogger,
)
from virtualbricks.bricks.virtualmachine import (
    Card,
    ImageDraft,
    Lack,
    UsbDevice,
    UsbDeviceKind,
    VirtualMachineDraft,
    hostonly_sock,
    lacks,
    resume,
    suspend,
)
from virtualbricks.bricks.draft import Problem, apply
from virtualbricks.programs import parse_machine_properties
from virtualbricks.tests.test_programs import TARGETS, load, recorded_info


def properties(target, machine="pc"):
    return parse_machine_properties(
        load(target)["qemu"]["machines"][machine]["out"]
    )


class FakeProcess:
    pid = 1

    def __init__(self):
        self.written = []

    def write(self, data):
        self.written.append(data)


class TestVirtualMachine(BrickTestCase):

    def test_disks_refer_to_images_by_name(self):
        vm = self.factory.new_brick("qemu", "vm")
        disk = vm.disk("hda")
        self.assertIsNone(disk.image)
        image = self.factory.new_disk_image("deb", "/i/deb.qcow2")
        changes = []
        vm.image_changed.connect(lambda payload: changes.append(payload))
        vm.set_image("hda", image)
        self.assertEqual(vm.config.hda_image, "deb")
        self.assertIs(disk.image, image)
        self.assertEqual(changes, [(vm, image)])
        vm.update_config({"hda_private": True})
        self.assertTrue(disk.is_cow())
        self.assertFalse(disk.readonly())
        vm.set_image("hda", None)
        self.assertEqual(vm.config.hda_image, "")
        vm.config.hdb_image = "missing"
        self.assertIsNone(vm.disk("hdb").image)
        self.assertEqual([d.device for d in vm.disks()][0], "hda")

    def test_image_rename_updates_the_disks(self):
        vm = self.factory.new_brick("qemu", "vm")
        image = self.factory.new_disk_image("deb", "/i/deb.qcow2")
        vm.set_image("hda", image)
        self.factory.rename(image, "debian")
        self.assertEqual(vm.config.hda_image, "debian")
        self.assertIs(vm.disk("hda").image, image)

    def test_sockets(self):
        vm = self.factory.new_brick("qemu", "vm")
        sw = self.factory.new_brick("switch", "sw")
        vm.add_plug(sw.socks[0], "00:aa:00:00:00:01", "e1000")
        default = vm.add_sock("00:aa:00:00:00:02", "e1000")
        named = vm.add_sock(name="sock_x")
        self.assertEqual(default.nickname, "vm_sock_eth1")
        self.assertEqual(named.nickname, "vm_sock_x")
        self.assertEqual(
            named.path, os.path.join(self.factory.runtime_dir, "vm_sock_x[]")
        )
        projects = use_workspace(self, self.mktemp())
        projects.current = OpenProject(self.mktemp(), None)
        os.makedirs(projects.current.path)
        vm.rename("vm2")
        self.assertEqual(default.nickname, "vm2_sock_eth1")
        self.assertEqual(
            default.path,
            os.path.join(self.factory.runtime_dir, "vm2_sock_eth1[]"),
        )

    def test_rename_keeps_other_sockets(self):
        vm = self.factory.new_brick("qemu", "vm")
        sock = vm.add_sock()
        sock.nickname = "other"
        vm.set_name("vm3")
        self.assertEqual(sock.nickname, "other")

    def test_usb_kind(self):
        kind = UsbDeviceKind()
        report = Report()
        device = UsbDevice("1d6b:0002", "hub")
        kind.check(device)
        self.assertRaises(ValueError, kind.check, "1d6b:0002")
        self.assertEqual(
            kind.to_data(device), {"id": "1d6b:0002", "description": "hub"}
        )
        self.assertEqual(
            kind.from_data({"id": "1d6b:0002", "x": 1}, report, "u"),
            UsbDevice("1d6b:0002", ""),
        )
        self.assertEqual(len(report), 1)
        for bad in (
            "1d6b:0002",
            {"id": "usb"},
            {"id": "1d6b:0002", "description": 1},
        ):
            self.assertRaises(ValueError, kind.from_data, bad, report, "u")
        self.assertEqual(kind.format(device), "1d6b:0002")

    def test_usb_devices_are_hashable(self):
        devices = {
            UsbDevice("1d6b:0002", "hub"),
            UsbDevice("1d6b:0002", "hub"),
        }
        self.assertEqual(len(devices), 1)


class TestRunning(CommandTestCase):

    def test_update_usb_devices(self):
        vm = self.factory.new_brick("qemu", "vm")
        vm.update_config({"usb_devices": [UsbDevice("1d6b:0002", "hub")]})
        sent = []
        vm.send = sent.append
        vm.update_usb_devices(
            [UsbDevice("1d6b:0002", "hub"), UsbDevice("046d:c52b", "mouse")]
        )
        self.assertEqual(sent, [b"usb_add host:046d:c52b\n"])

    def test_power_on_to_resume(self):
        vm = self.factory.new_brick("qemu", "vm")
        started = defer.Deferred()
        seen = []

        def poweron(brick, resume=""):
            seen.append(resume)
            brick._exited_d = defer.Deferred()
            return started

        self.patch(bricks.Brick, "poweron", poweron)
        locks = []
        vm.acquire = lambda: locks.append("acquire")
        vm.release = lambda: locks.append("release")
        d = vm.poweron(resume="snap1")
        self.assertEqual(seen, ["snap1"])
        self.assertFalse(hasattr(vm.config, "loadvm"))
        started.callback(vm)
        self.successResultOf(d)
        vm._exited_d.callback(None)
        self.assertEqual(locks, ["acquire", "release"])


class TestALack(BrickTestCase):

    def test_its_words(self):
        lack = Lack(
            "use_kvm", "QEMU 10.0.13 has no KVM", "the machine is emulated"
        )
        self.assertEqual(
            lack.words(), "QEMU 10.0.13 has no KVM: the machine is emulated"
        )
        self.assertEqual(
            lack.warning("vm1"),
            "vm1: QEMU 10.0.13 has no KVM (use_kvm): the machine is emulated",
        )
        # elsewhere, or nowhere; and nothing done instead
        lack = Lack(
            "sound_card",
            "no driver",
            "no sound",
            "audio_driver of the settings",
        )
        self.assertEqual(
            lack.warning("vm1"),
            "vm1: no driver (audio_driver of the settings): no sound",
        )
        self.assertEqual(
            Lack("cards", "no VDE", "unplugged", "").warning("vm1"),
            "vm1: no VDE: unplugged",
        )
        self.assertEqual(
            Lack("acpi", "no ACPI off").warning("vm1"),
            "vm1: no ACPI off (acpi)",
        )
        self.assertEqual(Lack("acpi", "no ACPI off").words(), "no ACPI off")


class TestLacks(BrickTestCase):
    """What each recorded QEMU lacks."""

    def setUp(self):
        super().setUp()
        self.vm = self.factory.new_brick("qemu", "vm1")

    def lacking(self, target, cards=(), driver="alsa", machine="pc"):
        return {
            lack.key: lack.words()
            for lack in lacks(
                self.vm.config,
                list(cards),
                recorded_info(target),
                properties(target, machine),
                driver,
            )
        }

    def test_nothing(self):
        for target in TARGETS:
            self.assertEqual(self.lacking(target), {}, target)

    def test_a_machine_type_of_ubuntu(self):
        self.vm.update_config({"machine_type": "pc-i440fx-jammy"})
        self.assertEqual(self.lacking("ubuntu-22.04"), {})
        self.assertEqual(
            self.lacking("debian-13"),
            {
                "machine_type": "QEMU 10.0.13 has no machine type"
                " pc-i440fx-jammy: the machine starts with the default one"
            },
        )

    def test_a_sound_card_of_8_2(self):
        self.vm.update_config({"sound_card": "virtio-sound-pci"})
        self.assertEqual(
            self.lacking("ubuntu-22.04"),
            {
                "sound_card": "QEMU 6.2.0 has no sound card virtio-sound-pci:"
                " the machine has none"
            },
        )
        for target in ("ubuntu-24.04", "debian-13", "debian-testing"):
            self.assertEqual(self.lacking(target), {}, target)
        # the PC speaker is the machine's
        self.vm.update_config({"sound_card": "pcspk"})
        self.assertEqual(self.lacking("ubuntu-22.04"), {})
        # a driver of the settings, taken on trust by 6.2
        self.assertEqual(self.lacking("ubuntu-22.04", driver="nope"), {})
        self.assertEqual(
            self.lacking("debian-12", driver="nope"),
            {
                "sound_card": "QEMU 7.2.22 has no audio driver nope: the"
                " machine has no sound card"
            },
        )

    def test_the_cards_on_ubuntu(self):
        cards = [("e1000", True), ("igb", False), ("rtl8139", True)]
        for target, vde in (
            ("ubuntu-22.04", False),
            ("debian-12", True),
            ("ubuntu-24.04", False),
            ("debian-13", True),
            ("ubuntu-26.04", False),
            ("debian-testing", True),
        ):
            found = self.lacking(target, cards)
            if vde:
                self.assertNotIn("cards", found, target)
            else:
                self.assertTrue(
                    found["cards"].endswith(
                        "can't join a VDE switch: card 0, 2 unplugged; install"
                        " a QEMU built with VDE"
                    ),
                    target,
                )
            # igb came with QEMU 8.2
            self.assertEqual(
                "card1" in found,
                target in ("ubuntu-22.04", "debian-12"),
                target,
            )

    def test_acpi_off(self):
        # every target turns it off, on the pc machine
        self.vm.update_config({"acpi": False})
        for target in TARGETS:
            self.assertEqual(self.lacking(target), {}, target)
        found = lacks(
            self.vm.config, [], recorded_info("debian-13"), frozenset(), "alsa"
        )
        self.assertEqual([lack.key for lack in found], ["acpi"])
        found = lacks(
            self.vm.config,
            [],
            recorded_info("ubuntu-22.04"),
            frozenset(),
            "alsa",
        )
        self.assertEqual(found, [])

    def test_the_command_says_the_same(self):
        self.vm.update_config(
            {
                "machine_type": "pc-i440fx-jammy",
                "cpu_model": "Zen9",
                "sound_card": "virtio-sound-pci",
                "acpi": False,
                "use_kvm": True,
                "sdl_window": True,
            }
        )
        switch = self.factory.new_brick("switch", "sw1")
        self.vm.add_plug(switch.socks[0], "52:54:00:00:00:01", "igb")
        self.vm.add_plug(hostonly_sock, "52:54:00:00:00:02", "e1000")
        from virtualbricks.tests.bricks.test_command import prepared_qemu

        for target in TARGETS:
            prepared = prepared_qemu(target)
            cmd = self.vm.command(prepared)
            found = lacks(
                self.vm.config,
                [("igb", True), ("e1000", False)],
                prepared.qemu,
                prepared.machine_properties,
                prepared.audio_driver,
            )
            self.assertEqual(
                cmd.warnings, [lack.warning("vm1") for lack in found], target
            )


class DraftTestCase(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.vm = self.factory.new_brick("qemu", "vm1")
        self.sw1 = self.factory.new_brick("switch", "sw1")
        self.sw2 = self.factory.new_brick("switch", "sw2")
        self.changed = []
        self.vm.changed.connect(self.changed.append)


class TestTheDraft(DraftTestCase):

    def test_a_machine_has_one(self):
        self.assertIsInstance(
            self.vm.draft_factory(self.vm), VirtualMachineDraft
        )

    def test_its_lists_are_its_own(self):
        device = UsbDevice("046d:c52b", "Logitech")
        self.vm.update_config({"usb_devices": [device]})
        draft = VirtualMachineDraft(self.vm)
        draft.settings.usb_devices.append(UsbDevice("0bda:8153", ""))
        self.assertEqual(self.vm.config.usb_devices, [device])

    def test_what_goes_with_what(self):
        draft = VirtualMachineDraft(self.vm)
        self.assertFalse(draft.uses("initrd"))
        draft.set("use_initrd", True)
        self.assertFalse(draft.uses("initrd"))
        draft.set("use_kernel", True)
        self.assertTrue(draft.uses("initrd"))
        # no display, or VNC
        self.assertTrue(draft.uses("headless"))
        self.assertTrue(draft.uses("use_vnc"))
        draft.set("use_vnc", True)
        # no display wins, and can always be chosen
        self.assertTrue(draft.uses("headless"))
        self.assertTrue(draft.uses("vnc_display"))
        draft.set("use_vnc", False)
        draft.set("headless", True)
        self.assertFalse(draft.uses("use_vnc"))
        self.assertFalse(draft.uses("vnc_display"))
        self.assertFalse(draft.uses("sdl_window"))
        self.assertFalse(draft.uses("kvm_shadow_memory"))

    def test_what_is_wrong(self):
        draft = VirtualMachineDraft(self.vm)
        self.assertEqual(draft.problems(), [])
        for name, value in (
            ("use_kernel", True),
            ("use_initrd", True),
            ("cdrom", "image"),
            ("keyboard_layout", "ita"),
        ):
            draft.set(name, value)
        self.assertEqual(
            draft.errors(),
            [
                Problem("kernel", "Choose the kernel, or don't boot one"),
                Problem("initrd", "Choose the ramdisk, or don't load one"),
                Problem("cdrom_image", "Choose the image of the CD-ROM"),
                Problem("keyboard_layout", "Two letters, as it or de"),
            ],
        )
        draft.set("cdrom", "device")
        draft.set("use_kernel", False)
        draft.set("keyboard_layout", "it")
        self.assertEqual(
            draft.errors(),
            [Problem("cdrom_device", "Choose the drive of the CD-ROM")],
        )

    def test_what_its_qemu_lacks(self):
        draft = VirtualMachineDraft(self.vm)
        draft.set("machine_type", "pc-i440fx-jammy")
        # not asked yet
        self.assertEqual(draft.problems(), [])
        draft.qemu = recorded_info("debian-13")
        draft.machine_properties = properties("debian-13")
        self.assertEqual(
            draft.problems(),
            [
                Problem(
                    "machine_type",
                    "QEMU 10.0.13 has no machine type pc-i440fx-jammy: the"
                    " machine starts with the default one",
                    error=False,
                )
            ],
        )
        self.assertEqual(draft.errors(), [])


class TestTheCards(DraftTestCase):

    def setUp(self):
        super().setUp()
        self.eth0 = self.vm.add_plug(
            self.sw1.socks[0], "52:54:00:00:00:01", "e1000"
        )
        self.sock = self.vm.add_sock("52:54:00:00:00:02", "rtl8139")
        self.eth1 = self.vm.add_plug(
            hostonly_sock, "52:54:00:00:00:03", "e1000"
        )

    def test_the_cards(self):
        draft = VirtualMachineDraft(self.vm)
        self.assertEqual(
            draft.cards,
            [
                Card(
                    "plug",
                    "e1000",
                    "52:54:00:00:00:01",
                    self.sw1.socks[0],
                    self.eth0,
                ),
                Card(
                    "plug",
                    "e1000",
                    "52:54:00:00:00:03",
                    hostonly_sock,
                    self.eth1,
                ),
                Card(
                    "socket", "rtl8139", "52:54:00:00:00:02", None, self.sock
                ),
            ],
        )
        self.assertEqual(draft.links, [])
        self.assertTrue(draft.cards[0].needs_vde())
        self.assertFalse(draft.cards[1].needs_vde())
        self.assertTrue(draft.cards[2].needs_vde())

    def test_add_and_remove(self):
        draft = VirtualMachineDraft(self.vm)
        self.assertEqual(draft.add_card(), 2)
        card = draft.cards[2]
        self.assertEqual(
            (card.kind, card.model, card.sock, card.link),
            ("plug", "rtl8139", None, None),
        )
        self.assertRegex(card.mac, "^[0-9a-f:]{17}$")
        self.assertEqual(
            draft.problems(),
            [Problem("card2", "In nothing: vm1 can't start", error=False)],
        )
        draft.remove_card(0)
        self.assertEqual(
            [c.link for c in draft.cards], [self.eth1, None, self.sock]
        )
        # the machine waits for OK
        self.assertEqual(len(self.vm.plugs), 2)

    def test_a_socket_becomes_a_plug(self):
        draft = VirtualMachineDraft(self.vm)
        draft.set_card(2, kind="plug", sock=self.sw2.socks[0])
        self.assertEqual([c.kind for c in draft.cards], ["plug"] * 3)
        draft.set_card(0, kind="socket")
        self.assertEqual(
            [c.kind for c in draft.cards], ["plug", "plug", "socket"]
        )
        self.assertIsNone(draft.cards[2].sock)
        self.assertIs(draft.cards[2].link, self.eth0)

    def test_a_wrong_mac(self):
        draft = VirtualMachineDraft(self.vm)
        draft.set_card(1, mac="52:54:00")
        self.assertEqual(
            draft.errors(), [Problem("card1", "52:54:00 isn't a MAC address")]
        )

    def test_apply(self):
        draft = VirtualMachineDraft(self.vm)
        draft.set_card(0, model="virtio-net-pci", sock=self.sw2.socks[0])
        draft.remove_card(1)
        index = draft.add_card()
        draft.set_card(index, sock=self.sw1.socks[0], mac="52:54:00:00:00:04")
        apply(draft)
        self.assertEqual(
            [(p.model, p.mac, p.sock) for p in self.vm.plugs],
            [
                ("virtio-net-pci", "52:54:00:00:00:01", self.sw2.socks[0]),
                ("rtl8139", "52:54:00:00:00:04", self.sw1.socks[0]),
            ],
        )
        self.assertIs(self.vm.plugs[0], self.eth0)
        self.assertEqual(self.vm.socks, [self.sock])
        # moved out of sw1, the new one in it
        self.assertEqual(
            [plug.brick for plug in self.sw1.socks[0].plugs], [self.vm]
        )
        self.assertEqual(self.changed, [self.vm])

    def test_a_card_becomes_a_socket(self):
        draft = VirtualMachineDraft(self.vm)
        draft.set_card(0, kind="socket")
        apply(draft)
        self.assertEqual(self.vm.plugs, [self.eth1])
        self.assertEqual(len(self.vm.socks), 2)
        self.assertEqual(self.vm.socks[1].mac, "52:54:00:00:00:01")
        self.assertEqual(self.sw1.socks[0].plugs, [])

    def test_nothing_changed(self):
        apply(VirtualMachineDraft(self.vm))
        self.assertEqual(self.changed, [])
        self.assertEqual(self.vm.plugs, [self.eth0, self.eth1])


class TestApply(DraftTestCase):

    def test_the_images(self):
        image = self.factory.new_disk_image("deb", "/i/deb.qcow2")
        self.vm.update_config({"hdb_image": "gone"})
        images = []
        self.vm.image_changed.connect(images.append)
        draft = VirtualMachineDraft(self.vm)
        draft.set("hda_image", "deb")
        draft.set("hda_private", True)
        draft.set("hdc_image", "missing")
        draft.set("hdb_image", "")
        self.assertEqual(draft.changes(), {"hda_private": True})
        del self.changed[:]
        apply(draft)
        self.assertEqual(self.vm.config.hda_image, "deb")
        self.assertTrue(self.vm.config.hda_private)
        self.assertEqual(self.vm.config.hdb_image, "")
        # a name not in the library stays
        self.assertEqual(self.vm.config.hdc_image, "missing")
        self.assertEqual(images, [(self.vm, image), (self.vm, None)])
        self.assertEqual(self.changed, [self.vm])

    def test_usb_devices(self):
        self.vm.proc = FakeProcess()
        draft = VirtualMachineDraft(self.vm)
        device = UsbDevice("046d:c52b", "Logitech")
        draft.set("use_usb", True)
        draft.set("usb_devices", [device])
        apply(draft)
        self.assertEqual(self.vm.proc.written, [b"usb_add host:046d:c52b\n"])
        self.assertEqual(self.vm.config.usb_devices, [device])


class TestTheDraftOfAnImage(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.image = self.factory.new_disk_image("frr", "/i/frr.qcow2")
        self.image.set_description("FRR")
        self.draft = ImageDraft(self.image, self.factory)

    def test_a_copy(self):
        draft = self.draft
        self.assertEqual(draft.get("name"), "frr")
        self.assertEqual(draft.get("description"), "FRR")
        draft.set("name", "frr-debian")
        self.assertEqual(draft.changes(), {"name": "frr-debian"})
        self.assertEqual(draft.problems(), [])
        self.assertEqual(self.image.name, "frr")

    def test_apply(self):
        vm = self.factory.new_brick("qemu", "vm")
        vm.update_config({"hda_image": "frr"})
        self.draft.set("name", "frr debian")
        self.draft.set("description", "FRR on Debian.")
        apply(self.draft)
        # the name as the factory writes it
        self.assertIs(self.factory.get_image_by_name("frr_debian"), self.image)
        self.assertEqual(self.image.get_description(), "FRR on Debian.")
        # the disks follow
        self.assertEqual(vm.config.hda_image, "frr_debian")

    def test_the_description_alone(self):
        renamed = []
        self.patch(self.factory, "rename", lambda *args: renamed.append(args))
        self.draft.set("description", "FRR on Debian.")
        apply(self.draft)
        self.assertEqual(renamed, [])
        self.assertEqual(self.image.get_description(), "FRR on Debian.")

    def test_a_name_in_use(self):
        self.factory.new_brick("switch", "sw1")
        self.draft.set("name", "sw1")
        self.assertEqual(
            self.draft.problems(),
            [Problem("name", "The name “sw1” is in use")],
        )
        self.assertRaises(ValueError, apply, self.draft)
        self.assertEqual(self.image.name, "frr")

    def test_a_name_that_cant_be(self):
        for name, problem in (
            ("1frr", "Name must start with a letter"),
            ("", "Name is empty"),
        ):
            self.draft.set("name", name)
            self.assertEqual(self.draft.problems(), [Problem("name", problem)])

    def test_its_own_name_written_another_way(self):
        renamed = []
        self.patch(self.factory, "rename", lambda *args: renamed.append(args))
        self.draft.set("name", " frr ")
        self.assertEqual(self.draft.problems(), [])
        apply(self.draft)
        self.assertEqual(renamed, [])
        self.assertEqual(self.image.name, "frr")


class FakeImage:
    def __init__(self, path):
        self.path = path


class FakeDisk:
    def __init__(self, cow=False, image=None):
        self.cow = cow
        self.image = image

    def is_cow(self):
        return self.cow

    def get_cow_path(self):
        return "/lab/vm_hda.cow"


class TestSuspendAndResume(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.logger = FakeLogger()
        self.patch(virtualmachine, "logger", self.logger)
        self.vm = self.factory.new_brick("qemu", "vm")
        self.done = []
        self.vm.send = lambda data: self.done.append(data)
        self.vm.poweroff = lambda: defer.succeed(self.done.append("off"))
        self.vm.poweron = lambda resume="": defer.succeed(
            self.done.append(("on", resume))
        )
        self.disk = FakeDisk(image=FakeImage("/lab/vm.qcow2"))
        self.vm.disk = lambda name: self.disk if name == "hda" else None
        self.formats = []

        def image_type(path):
            self.formats.append(path)
            return imageformat.ImageFormat.QCOW2

        self.patch(imageformat, "image_type_from_file", image_type)

    def not_supported(self, deferred):
        self.failureResultOf(deferred, RuntimeError)
        self.assertEqual(
            self.logger.formatted(),
            ["Suspend/Resume not supported on this disk."],
        )

    def test_suspend(self):
        self.successResultOf(suspend(self.vm))
        self.assertEqual(self.done, [b"savevm virtualbricks\n", "off"])
        self.assertEqual(self.formats, ["/lab/vm.qcow2"])

    def test_suspend_a_private_disk(self):
        self.disk.cow = True
        self.successResultOf(suspend(self.vm))
        self.assertEqual(self.formats, ["/lab/vm_hda.cow"])

    def test_suspend_needs_qcow2(self):
        self.patch(
            imageformat,
            "image_type_from_file",
            lambda path: imageformat.ImageFormat.RAW,
        )
        self.not_supported(suspend(self.vm))
        self.assertEqual(self.done, [])

    def test_no_disk(self):
        self.disk.image = None
        self.not_supported(suspend(self.vm))
        self.logger = FakeLogger()
        self.patch(virtualmachine, "logger", self.logger)
        self.not_supported(resume(self.vm))

    def snapshots(self, output):
        listed = []

        def qemu_img(args):
            listed.append(args)
            return defer.succeed(output)

        self.patch(virtualmachine, "qemu_img", qemu_img)
        return listed

    def test_resume_a_stopped_machine(self):
        listed = self.snapshots("1  virtualbricks  1.2 GiB")
        self.successResultOf(resume(self.vm))
        self.assertEqual(listed, [["snapshot", "-l", "/lab/vm.qcow2"]])
        self.assertEqual(self.done, [("on", "virtualbricks")])

    def test_resume_a_running_machine(self):
        self.snapshots("1  virtualbricks  1.2 GiB")
        self.vm.proc = FakeProcess()
        self.successResultOf(resume(self.vm))
        self.assertEqual(self.done, [b"loadvm virtualbricks\n"])

    def test_nothing_to_resume(self):
        self.snapshots("")
        self.failureResultOf(resume(self.vm), RuntimeError)
        self.assertEqual(self.done, [])
        self.assertEqual(self.logger.formatted(), ["Error on snapshot"])
