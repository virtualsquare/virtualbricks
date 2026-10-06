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


"""The brick factory."""

from virtualbricks import brickfactory, errors
from virtualbricks.bricks.eventaction import (
    ConsoleAction,
    StartAction,
    StopAction,
)
from virtualbricks.tests import BrickTestCase
from virtualbricks.bricks.virtualmachine import UsbDevice


class TestFactory(BrickTestCase):

    def test_get_event_by_name(self):
        event = self.factory.new_event("boot")
        self.factory.new_image("boot2", "/x")
        self.assertIs(self.factory.get_event("boot"), event)
        self.assertIsNone(self.factory.get_event("boot2"))

    def test_unused_name(self):
        self.factory.new_brick("switch", "sw")
        self.factory.new_brick("switch", "sw.1")
        self.assertEqual(self.factory.unused_name("sw"), "sw.2")

    def test_next_name_increases_the_number(self):
        self.factory.new_brick("switch", "SW1")
        self.assertEqual(self.factory.next_name("SW1"), "SW2")
        self.assertEqual(self.factory.next_name("sw9"), "sw10")
        self.assertEqual(self.factory.next_name("sw1.1"), "sw1.2")

    def test_next_name_without_a_number(self):
        self.factory.new_brick("switch", "node")
        self.assertEqual(self.factory.next_name("node"), "node2")

    def test_next_name_keeps_the_zeros(self):
        self.assertEqual(self.factory.next_name("vm01"), "vm02")
        self.assertEqual(self.factory.next_name("vm09"), "vm10")
        self.assertEqual(self.factory.next_name("vm99"), "vm100")

    def test_next_name_is_free_in_the_project(self):
        # bricks, events and images share the names
        self.factory.new_brick("switch", "sw1")
        self.factory.new_brick("switch", "sw2")
        self.factory.new_event("sw3")
        self.factory.new_image("sw4", "/x")
        self.factory.new_brick("switch", "sw6")
        self.assertEqual(self.factory.next_name("sw1"), "sw5")
        # from the number of the name, not from 1
        self.assertEqual(self.factory.next_name("sw6"), "sw7")

    def test_dup_brick(self):
        vm = self.factory.new_brick("qemu", "vm")
        vm.update_config(
            {"memory": 256, "usb_devices": [UsbDevice("1d6b:0002", "hub")]}
        )
        copy = self.factory.duplicate_brick(vm)
        self.assertEqual(copy.config.memory, 256)
        self.assertEqual(copy.config.usb_devices, vm.config.usb_devices)
        self.assertIsNot(copy.config.usb_devices, vm.config.usb_devices)

    def test_rename_event_updates_the_bricks(self):
        event = self.factory.new_event("boot")
        switch = self.factory.new_brick("switch", "sw")
        switch.update_config({"on_start": "boot", "on_stop": "boot"})
        other = self.factory.new_event("other")
        other.update_config({"delay": 1})
        changed = []
        switch.changed.connect(changed.append)
        self.factory.rename_item(event, "start")
        self.assertEqual(switch.config.on_start, "start")
        self.assertEqual(switch.config.on_stop, "start")
        self.assertEqual(changed, [switch])

    def test_check_socket_room(self):
        self.factory.runtime_dir = "/run/user/1000/virtualbricks/" + "x" * 40
        self.factory.check_socket_room("b" * 18)
        with self.assertRaises(errors.InvalidNameError) as cm:
            self.factory.check_socket_room("b" * 19)
        self.assertEqual(
            str(cm.exception),
            "The name is 19 bytes long, and the sockets of this project"
            " leave room for 18",
        )

    def test_check_name(self):
        self.factory.runtime_dir = "/run/vb"
        self.factory.new_brick("switch", "sw")
        self.assertEqual(
            self.factory.check_brick_name("switch", " my switch "), "my_switch"
        )
        self.assertEqual(
            self.factory.check_brick_name("Tap", "t" * 15), "t" * 15
        )
        # in use, too long for the sockets, refused by the kind
        for type, name in (
            ("switch", "sw"),
            ("switch", "s" * 100),
            ("tap", "t" * 16),
        ):
            with self.assertRaises(errors.InvalidNameError, msg=name):
                self.factory.check_brick_name(type, name)
        with self.assertRaises(errors.InvalidTypeError):
            self.factory.check_brick_name("nope", "nope")

    def test_a_project_opens_with_names_no_longer_taken(self):
        # a tap named before the check
        tap = self.factory.new_brick("tap", "t" * 16)
        self.assertEqual(tap.name, "t" * 16)

    def test_a_rename_follows_the_actions(self):
        # the bricks and the events that actions start or stop
        self.factory.runtime_dir = "/run/vb"
        self.factory.new_brick("switch", "sw1")
        later = self.factory.new_event("later")
        boot = self.factory.new_event("boot")
        boot.update_config(
            {
                "actions": [
                    StartAction("sw1"),
                    StopAction("later"),
                    ConsoleAction("brick set sw1 ports=4"),
                ]
            }
        )
        changed = []
        boot.changed.connect(changed.append)
        self.factory.rename_item(self.factory.get_brick("sw1"), "core")
        self.factory.rename_item(later, "after")
        self.assertEqual(
            boot.config.actions,
            [
                StartAction("core"),
                StopAction("after"),
                # a command stays as it is written
                ConsoleAction("brick set sw1 ports=4"),
            ],
        )
        self.assertEqual(changed, [boot, boot])

    def test_rename_brick(self):
        switch = self.factory.new_brick("switch", "sw")
        self.assertEqual(self.factory.rename_item(switch, "sw2"), "sw")
        self.assertEqual(switch.name, "sw2")

    def test_only_rename_changes_the_name(self):
        """The factory's indexes and the references follow a rename only."""

        for item in (
            self.factory.new_brick("switch", "sw"),
            self.factory.new_brick("qemu", "vm"),
            self.factory.new_event("ev"),
            self.factory.new_image("deb", "/lab/deb.qcow2"),
        ):
            name = item.name
            with self.assertRaises(AttributeError):
                item.name = "other"
            self.assertEqual(item.name, name)
            self.factory.rename_item(item, name + "2")
            self.assertEqual(item.name, name + "2")

    def test_a_name_in_use_says_what_has_it(self):
        self.factory.new_brick("switch", "sw")
        self.factory.new_event("boot")
        self.factory.new_image("deb", "/lab/deb.qcow2")
        for name, words in (
            ("sw", "sw is the name of a brick"),
            (" boot ", "boot is the name of an event"),
            ("deb", "deb is the name of an image"),
        ):
            with self.assertRaises(errors.NameAlreadyInUseError) as cm:
                self.factory.check_name(name)
            self.assertEqual(str(cm.exception), words)
        with self.assertRaises(errors.NameAlreadyInUseError) as cm:
            self.factory.new_brick("tap", "sw")
        self.assertEqual(str(cm.exception), "sw is the name of a brick")
        self.assertEqual(str(errors.NameAlreadyInUseError("x")), "x is in use")

    def test_what_is_wrong_with_a_name(self):
        for name, words in (
            ("", "A name can't be empty"),
            ("1sw", "A name starts with a letter"),
            (
                "sw/1",
                "A name has only letters, digits, underscores (_), hyphens"
                " (-) and dots (.)",
            ),
        ):
            with self.assertRaises(errors.InvalidNameError) as cm:
                brickfactory.normalize_name(name)
            self.assertEqual(str(cm.exception), words)


class TestUsers(BrickTestCase):
    """What names a brick or an event, and what a delete does to it."""

    def setUp(self):
        super().setUp()
        self.factory.runtime_dir = "/run/vb"
        self.sw1 = self.factory.new_brick("switch", "sw1")
        self.vm1 = self.factory.new_brick("qemu", "vm1")
        self.vm1.connect(self.sw1.socks[0])
        self.w1 = self.factory.new_brick("wire", "w1")
        self.w1.plugs[0].connect(self.sw1.socks[0])
        self.boot = self.factory.new_event("boot")
        self.boot.update_config(
            {
                "actions": [
                    StartAction("sw1"),
                    StartAction("vm1"),
                    ConsoleAction("brick set sw1 ports=4"),
                    StopAction("boot"),
                ]
            }
        )
        self.halt = self.factory.new_event("halt")
        self.halt.update_config(
            {"actions": [StopAction("sw1"), StopAction("boot")]}
        )
        self.sw1.update_config({"on_start": "boot", "on_stop": "boot"})
        self.vm1.update_config({"on_stop": "boot"})
        self.changed = []
        for item in (self.sw1, self.vm1, self.w1, self.boot, self.halt):
            item.changed.connect(self.changed.append)

    def test_a_brick(self):
        users = self.factory.users(self.sw1)
        self.assertEqual(users.plugs, [self.vm1.plugs[0], self.w1.plugs[0]])
        # a command stays as it is written
        self.assertEqual(
            users.actions,
            [(self.boot, StartAction("sw1")), (self.halt, StopAction("sw1"))],
        )
        self.assertEqual(users.settings, [])
        users = self.factory.users(self.w1)
        self.assertEqual((users.plugs, users.actions), ([], []))

    def test_an_event(self):
        users = self.factory.users(self.boot)
        self.assertEqual(users.plugs, [])
        # not its own actions
        self.assertEqual(users.actions, [(self.halt, StopAction("boot"))])
        self.assertEqual(
            users.settings,
            [
                (self.sw1, "on_start"),
                (self.sw1, "on_stop"),
                (self.vm1, "on_stop"),
            ],
        )

    def test_a_brick_deleted(self):
        self.factory.remove_brick(self.sw1)
        self.assertIsNone(self.factory.get_brick("sw1"))
        self.assertIsNone(self.vm1.plugs[0].sock)
        self.assertIsNone(self.w1.plugs[0].sock)
        self.assertEqual(
            self.boot.config.actions,
            [
                StartAction("vm1"),
                ConsoleAction("brick set sw1 ports=4"),
                StopAction("boot"),
            ],
        )
        self.assertEqual(self.halt.config.actions, [StopAction("boot")])
        # once each
        self.assertEqual(self.changed, [self.boot, self.halt])

    def test_a_socket_removed(self):
        sock = self.sw1.socks[0]
        self.factory.remove_sock(sock)
        self.assertIsNone(self.factory.get_sock(sock.nickname))
        self.assertIsNone(self.vm1.plugs[0].sock)
        self.assertIsNone(self.w1.plugs[0].sock)
        self.assertEqual(sock.plugs, [])

    def test_an_event_deleted(self):
        self.factory.remove_event(self.boot)
        self.assertIsNone(self.factory.get_event("boot"))
        self.assertEqual(self.halt.config.actions, [StopAction("sw1")])
        self.assertEqual(
            (self.sw1.config.on_start, self.sw1.config.on_stop), ("", "")
        )
        self.assertEqual(self.vm1.config.on_stop, "")
        self.assertEqual(self.changed, [self.halt, self.sw1, self.vm1])

    def test_a_running_brick_stays(self):
        self.patch(self.sw1, "is_running", lambda: True)
        with self.assertRaises(errors.BrickRunningError):
            self.factory.remove_brick(self.sw1)
        self.assertEqual(len(self.boot.config.actions), 4)
        self.assertEqual(self.changed, [])

    def test_a_project_closed_changes_nothing(self):
        self.factory.reset()
        self.assertEqual(list(self.factory.bricks), [])
        self.assertEqual(list(self.factory.events), [])
        self.assertEqual(len(self.boot.config.actions), 4)
        self.assertEqual(self.sw1.config.on_start, "boot")
        self.assertEqual(self.changed, [])
