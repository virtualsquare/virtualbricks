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

"""The engine of the windows on this machine: what LocalEngine calls."""

import os
import signal

from twisted.trial import unittest
from twisted.internet import defer, error, task

from virtualbricks import errors, ksm
from virtualbricks.bricks import FakeProcess
from virtualbricks.bricks.brickinfo import NEW_KINDS
from virtualbricks.bricks.eventaction import ShellAction
from virtualbricks.bricks.virtualmachine import UsbDevice
from virtualbricks.config import images, settings
from virtualbricks.config.images import RunningError
from virtualbricks.config.settings import get_setting
from virtualbricks.config.tomlfile import load_toml
from virtualbricks.config.workspace import Workspace
from virtualbricks.engine import LocalEngine, folder_entries
from virtualbricks.tests import (
    BrickTestCase,
    FakeTrash,
    isolate,
    short_folder,
    use_workspace,
)
from virtualbricks.tests.config.test_images import (
    INFO,
    FakeQemuImg,
    FakeWorkspace,
    ImagesTestCase,
)


class FakeBrick:
    """A brick that says what it was asked."""

    name = "sw1"

    def __init__(self, exited=False):
        self.calls = []
        self.exited = exited

    def poweron(self):
        self.calls.append(("poweron",))
        return defer.succeed(self)

    def poweroff(self, kill=False, term=False):
        self.calls.append(("poweroff", kill, term))
        return defer.succeed(self)

    def send_signal(self, number):
        self.calls.append(("signal", number))
        if self.exited:
            raise error.ProcessExitedAlready()

    def send(self, data):
        self.calls.append(("send", data))

    def open_console(self):
        self.calls.append(("console",))


class FakePrograms:
    """What QEMU answers, as Programs gives it."""

    def __init__(self):
        self.asked = []

    def qemu(self, path):
        self.asked.append(("qemu", path))
        return defer.succeed(f"info of {path}")

    def machine_properties(self, info, machine):
        self.asked.append(("properties", info, machine))
        return defer.succeed(frozenset({"accel"}))


class EngineTestCase(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.clock = task.Clock()
        self.engine = LocalEngine(self.factory, clock=self.clock)


class TestBricks(EngineTestCase):

    def test_what_the_windows_read(self):
        self.assertIs(self.engine.factory, self.factory)

    def test_start(self):
        brick = FakeBrick()
        self.assertIs(self.successResultOf(self.engine.start(brick)), brick)
        self.assertEqual(brick.calls, [("poweron",)])

    def test_a_refusal_is_a_failure(self):
        # a brick that isn't configured can't start
        tap = self.factory.new_brick("tap", "tap1")
        failure = self.failureResultOf(self.engine.start(tap))
        self.assertTrue(failure.check(errors.BadConfigError))

    def test_stop_terminate_kill(self):
        brick = FakeBrick()
        self.engine.stop(brick)
        self.engine.terminate(brick)
        self.engine.kill(brick)
        self.assertEqual(
            brick.calls,
            [
                ("poweroff", False, False),
                ("poweroff", False, True),
                ("poweroff", True, False),
            ],
        )

    def test_restart(self):
        brick = FakeBrick()
        self.successResultOf(self.engine.restart(brick))
        self.assertEqual(
            brick.calls, [("poweroff", False, False), ("poweron",)]
        )
        # stopped in time: nothing kills it later
        self.assertEqual(self.clock.getDelayedCalls(), [])

    def test_pause_and_continue(self):
        brick = FakeBrick()
        self.successResultOf(self.engine.pause(brick))
        self.successResultOf(self.engine.continue_(brick))
        self.assertEqual(
            brick.calls,
            [("signal", signal.SIGSTOP), ("signal", signal.SIGCONT)],
        )

    def test_a_signal_to_a_process_gone(self):
        brick = FakeBrick(exited=True)
        self.successResultOf(self.engine.pause(brick))

    def test_reset(self):
        vm = FakeBrick()
        self.successResultOf(self.engine.reset(vm))
        self.assertEqual(vm.calls, [("send", b"system_reset\n")])

    def test_suspend_without_a_disk(self):
        vm = self.factory.new_brick("qemu", "vm1")
        vm.proc = FakeProcess(vm)
        self.failureResultOf(self.engine.suspend(vm))

    def test_open_console(self):
        brick = FakeBrick()
        self.successResultOf(self.engine.open_console(brick))
        self.assertEqual(brick.calls, [("console",)])

    def test_new_brick(self):
        brick = self.successResultOf(self.engine.new_brick("switch", "sw1"))
        self.assertIs(self.factory.get_brick("sw1"), brick)
        failure = self.failureResultOf(self.engine.new_brick("switch", "1sw"))
        self.assertTrue(failure.check(errors.InvalidNameError))

    def test_connect(self):
        switch = self.factory.new_brick("switch", "sw1")
        tap = self.factory.new_brick("tap", "tap1")
        self.assertTrue(self.successResultOf(self.engine.connect(tap, switch)))
        self.assertIs(tap.plugs[0].sock, switch.socks[0])
        other = self.factory.new_brick("tap", "tap2")
        self.assertFalse(self.successResultOf(self.engine.connect(tap, other)))

    def test_update_config(self):
        switch = self.factory.new_brick("switch", "sw1")
        self.successResultOf(
            self.engine.update_config(switch, {"hub_mode": True})
        )
        self.assertTrue(switch.config.hub_mode)
        failure = self.failureResultOf(
            self.engine.update_config(switch, {"ports": "many"})
        )
        self.assertTrue(failure.check(ValueError))

    def test_apply(self):
        switch = self.factory.new_brick("switch", "sw1")
        draft = switch.draft_factory(switch)
        draft.set("ports", 64)
        self.successResultOf(self.engine.apply(draft))
        self.assertEqual(switch.config.ports, 64)

    def test_apply_with_errors(self):
        switch = self.factory.new_brick("switch", "sw1")
        draft = switch.draft_factory(switch)
        draft.set("ports", "many")
        self.failureResultOf(self.engine.apply(draft), ValueError)
        self.assertEqual(switch.config.ports, 32)


class TestItems(EngineTestCase):

    def test_rename(self):
        switch = self.factory.new_brick("switch", "sw1")
        event = self.factory.new_event("boot")
        image = self.factory.new_image("frr", "/lab/frr.qcow2")
        for item, name in ((switch, "sw2"), (event, "up"), (image, "debian")):
            self.successResultOf(self.engine.rename(item, name))
            self.assertEqual(item.name, name)
        failure = self.failureResultOf(self.engine.rename(switch, "up"))
        self.assertTrue(failure.check(errors.NameAlreadyInUseError))

    def test_duplicate(self):
        switch = self.factory.new_brick("switch", "sw1")
        event = self.factory.new_event("boot")
        copy = self.successResultOf(self.engine.duplicate(switch))
        self.assertEqual(copy.name, "sw2")
        self.assertEqual(copy.get_type(), "Switch")
        copy = self.successResultOf(self.engine.duplicate(event))
        self.assertIs(self.factory.get_event("boot2"), copy)

    def test_remove(self):
        switch = self.factory.new_brick("switch", "sw1")
        event = self.factory.new_event("boot")
        image = self.factory.new_image("frr", "/lab/frr.qcow2")
        for item in (switch, event, image):
            self.successResultOf(self.engine.remove(item))
        self.assertEqual(list(self.factory.bricks), [])
        self.assertEqual(list(self.factory.events), [])
        self.assertEqual(list(self.factory.images), [])

    def test_remove_a_running_brick(self):
        switch = self.factory.new_brick("switch", "sw1")
        switch.proc = FakeProcess(switch)
        failure = self.failureResultOf(self.engine.remove(switch))
        self.assertTrue(failure.check(errors.BrickRunningError))


class TestEvents(EngineTestCase):

    def test_new_event(self):
        event = self.successResultOf(self.engine.new_event("boot", 5))
        self.assertIs(self.factory.get_event("boot"), event)
        self.assertEqual(event.config.delay, 5)

    def test_start_an_event_without_actions(self):
        event = self.factory.new_event("boot")
        failure = self.failureResultOf(self.engine.start_event(event))
        self.assertTrue(failure.check(errors.BadConfigError))

    def test_start_and_stop(self):
        event = self.factory.new_event("boot")
        event.update_config({"delay": 5, "actions": [ShellAction("true")]})
        self.engine.start_event(event)
        self.assertIsNotNone(event.scheduled)
        self.successResultOf(self.engine.stop_event(event))
        self.assertIsNone(event.scheduled)

    def test_run_event(self):
        event = self.factory.new_event("boot")
        ran = []
        event.run_actions = lambda: ran.append(event)
        self.successResultOf(self.engine.run_event(event))
        self.assertEqual(ran, [event])


class TestImages(ImagesTestCase):

    def setUp(self):
        super().setUp()
        self.trash = self.projects.trasher = FakeTrash()
        self.engine = LocalEngine(self.factory, qemu_img=self.qemu_img)

    def test_new_image(self):
        image = self.successResultOf(
            self.engine.new_image("debian", "/lab/debian.qcow2", "Bookworm")
        )
        self.assertIs(self.factory.get_image("debian"), image)
        self.assertEqual(image.description, "Bookworm")
        failure = self.failureResultOf(
            self.engine.new_image("other", "/lab/debian.qcow2")
        )
        self.assertTrue(failure.check(errors.ImageAlreadyInUseError))

    def test_make_image(self):
        self.successResultOf(
            self.engine.make_image("/lab/disk.qcow2", "qcow2", 1024)
        )
        self.assertEqual(
            self.qemu_img.calls,
            [["create", "-q", "-f", "qcow2", "/lab/disk.qcow2", "1024"]],
        )

    def test_image_info(self):
        self.qemu_img.infos["/lab/frr.qcow2"] = INFO
        info = self.successResultOf(self.engine.image_info("/lab/frr.qcow2"))
        self.assertEqual(info.virtual_size, INFO["virtual-size"])

    def test_relink(self):
        self.successResultOf(self.engine.relink(self.image, "/new/frr.qcow2"))
        self.assertEqual(self.image.path, "/new/frr.qcow2")

    def test_discard_file(self):
        vm = self.vm("r1")
        path = self.copy(vm)
        self.assertTrue(self.successResultOf(self.engine.discard_file(path)))
        self.assertEqual(self.trash.trashed, [path])
        self.projects.trasher = None
        path = self.copy(vm)
        self.assertFalse(self.successResultOf(self.engine.discard_file(path)))
        self.assertFalse(os.path.exists(path))

    def test_start_over(self):
        vm = self.vm("r1")
        path = self.copy(vm)
        self.assertTrue(
            self.successResultOf(self.engine.start_over(vm, "hda"))
        )
        self.assertEqual(self.trash.trashed, [path])
        vm = self.running(self.vm("r2"))
        failure = self.failureResultOf(self.engine.start_over(vm, "hda"))
        self.assertTrue(failure.check(RunningError))


class TestProjects(BrickTestCase):

    def setUp(self):
        super().setUp()
        settings.use_project(None)
        # the sockets of the bricks fit in the runtime folder
        os.environ["XDG_RUNTIME_DIR"] = short_folder(self)
        self.workspace = Workspace(short_folder(self))
        self.engine = LocalEngine(self.factory, workspace=self.workspace)

    def open(self, name):
        self.successResultOf(self.engine.new_project(name))
        return self.workspace.current

    def test_new_project(self):
        current = self.open("lab1")
        self.assertEqual(current.name, "lab1")
        failure = self.failureResultOf(self.engine.new_project("lab1"))
        self.assertTrue(failure.check(errors.InvalidNameError))

    def test_open_and_save(self):
        self.open("lab1")
        self.factory.new_brick("switch", "sw1")
        self.open("lab2")
        report = self.successResultOf(self.engine.open_project("lab1"))
        self.assertEqual(report.messages, [])
        self.assertEqual([b.name for b in self.factory.bricks], ["sw1"])
        self.factory.new_brick("switch", "sw2")
        self.successResultOf(self.engine.save_project())
        data = load_toml(self.workspace.current.project_file)
        self.assertIn("sw2", data["bricks"])

    def test_open_what_isnt_there(self):
        failure = self.failureResultOf(self.engine.open_project("nowhere"))
        self.assertTrue(failure.check(errors.InvalidNameError))

    def test_summaries(self):
        self.open("lab1")
        self.open("lab2")
        summaries = self.successResultOf(self.engine.project_summaries())
        self.assertEqual({s.name for s in summaries}, {"lab1", "lab2"})

    @defer.inlineCallbacks
    def test_disk_usage(self):
        self.open("lab1")
        usage = yield self.engine.disk_usage("lab1")
        self.assertEqual(usage.private_disks, 0)
        self.assertGreater(usage.other_files, 0)

    def test_rename_the_open_project(self):
        self.open("lab1")
        self.factory.new_brick("switch", "sw1")
        self.successResultOf(self.engine.rename_project("lab1", "ospf"))
        self.assertEqual(self.workspace.current.name, "ospf")

    def test_rename_leaves_room_for_the_sockets(self):
        self.open("lab1")
        self.factory.new_brick("switch", "s" * 60)
        failure = self.failureResultOf(
            self.engine.rename_project("lab1", "o" * 40)
        )
        self.assertTrue(failure.check(errors.InvalidNameError))

    def test_duplicate_and_remove(self):
        self.open("lab1")
        self.successResultOf(self.engine.duplicate_project("lab1", "lab2"))
        self.assertTrue(self.workspace.exists("lab2"))
        self.successResultOf(self.engine.remove_project("lab2", trash=False))
        self.assertFalse(self.workspace.exists("lab2"))
        failure = self.failureResultOf(
            self.engine.remove_project("lab1", trash=False)
        )
        self.assertTrue(failure.check(errors.ProjectOpenError))

    def test_remove_to_the_trash(self):
        self.open("lab1")
        self.open("lab2")
        trash = self.workspace.trasher = FakeTrash()
        self.successResultOf(self.engine.remove_project("lab1", trash=True))
        self.assertEqual(trash.trashed, [self.workspace.project_path("lab1")])

    def test_restore_last(self):
        self.open("lab1")
        self.open("lab2")
        self.workspace.close(self.factory)
        self.successResultOf(self.engine.restore_last())
        self.assertEqual(self.workspace.current.name, "lab2")

    def test_readme(self):
        self.open("lab1")
        self.successResultOf(self.engine.set_readme("# OSPF\n"))
        self.assertEqual(
            self.successResultOf(self.engine.readme()), "# OSPF\n"
        )

    def test_a_picture_of_the_readme(self):
        self.open("lab1")
        path = os.path.join(self.workspace.project_path("lab1"), "map.png")
        with open(path, "wb") as fp:
            fp.write(b"\x89PNG")
        self.assertEqual(
            self.successResultOf(self.engine.picture("lab1", "map.png")),
            b"\x89PNG",
        )
        failure = self.failureResultOf(self.engine.picture("lab1", "../x"))
        self.assertTrue(failure.check(ValueError))


class TestSettings(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.path = os.path.abspath(self.mktemp())
        self.patch(settings, "_settings_path", self.path)
        self.workspace = use_workspace(self, os.path.abspath(self.mktemp()))
        self.engine = LocalEngine(self.factory, workspace=self.workspace)

    def test_set_settings(self):
        self.successResultOf(self.engine.set_settings({"audio_driver": "pa"}))
        self.assertEqual(get_setting("audio_driver"), "pa")
        self.assertEqual(load_toml(self.path)["audio_driver"], "pa")

    def test_project_settings(self):
        settings.use_project(None)
        os.makedirs(self.workspace.path)
        self.successResultOf(self.engine.new_project("lab1"))
        self.successResultOf(
            self.engine.set_settings({"vde_path": "/opt/vde"})
        )
        data = load_toml(self.workspace.current.project_file)
        self.assertEqual(data["settings"]["vde_path"], "/opt/vde")
        # nothing of Virtualbricks changed
        self.assertFalse(os.path.exists(self.path))

    def test_a_value_refused(self):
        failure = self.failureResultOf(
            self.engine.set_settings({"tray_icon": "sometimes"})
        )
        self.assertTrue(failure.check(ValueError))

    def test_set_ksm(self):
        asked = []

        def set_ksm(enable):
            asked.append(enable)
            return defer.succeed(enable)

        self.patch(ksm, "set_ksm", set_ksm)
        self.assertTrue(self.successResultOf(self.engine.set_ksm(True)))
        self.assertEqual(asked, [True])


class TestMachine(EngineTestCase):

    def test_lacks(self):
        folder = os.path.abspath(self.mktemp())
        os.makedirs(folder)
        settings.set_setting("vde_path", folder)
        # not the programs of this computer: those of the setting only
        os.environ["PATH"] = ""
        switch = next(k for k in NEW_KINDS if k.type == "Switch")
        issue = self.successResultOf(self.engine.lacks(switch))
        self.assertIn("vde_switch", issue.line + issue.text)
        path = os.path.join(folder, "vde_switch")
        with open(path, "w"):
            pass
        os.chmod(path, 0o755)
        self.assertIsNone(self.successResultOf(self.engine.lacks(switch)))

    def which(self, name):
        if name == "qemu-system-aarch64":
            raise FileNotFoundError(name)
        return f"/usr/bin/{name}"

    def test_qemu(self):
        programs = FakePrograms()
        engine = LocalEngine(self.factory, programs=programs, which=self.which)
        info = self.successResultOf(engine.qemu("qemu-system-x86_64"))
        properties = self.successResultOf(
            engine.machine_properties(info, "pc")
        )
        self.assertEqual(properties, frozenset({"accel"}))
        self.assertEqual(
            programs.asked,
            [
                ("qemu", "/usr/bin/qemu-system-x86_64"),
                ("properties", "info of /usr/bin/qemu-system-x86_64", "pc"),
            ],
        )

    def test_no_such_qemu(self):
        programs = FakePrograms()
        engine = LocalEngine(self.factory, programs=programs, which=self.which)
        failure = self.failureResultOf(engine.qemu("qemu-system-aarch64"))
        self.assertTrue(failure.check(FileNotFoundError))
        self.assertEqual(programs.asked, [])

    def test_usb(self):
        found = [UsbDevice("1d6b:0002", "hub")]
        engine = LocalEngine(
            self.factory, usb_devices=lambda: defer.succeed(found)
        )
        self.assertEqual(self.successResultOf(engine.usb()), found)

    def test_what_the_windows_read(self):
        folder = os.path.abspath(self.mktemp())
        os.makedirs(folder)
        settings.set_setting("qemu_path", folder)
        os.environ["PATH"] = ""
        path = os.path.join(folder, "qemu-system-riscv64")
        with open(path, "w"):
            pass
        os.chmod(path, 0o755)
        machine = self.engine.machine
        self.assertEqual(machine.setting("qemu_path"), folder)
        self.assertEqual(machine.qemu_programs(), ["qemu-system-riscv64"])

    def test_its_files(self):
        path = os.path.abspath(self.mktemp())
        with open(path, "wb") as fp:
            fp.write(b"x" * 5000)
        stat = os.stat(path)
        machine = self.engine.machine
        self.assertTrue(machine.exists(path))
        self.assertEqual(machine.taken(path), stat.st_blocks * 512)
        self.assertEqual(machine.changed(path), stat.st_mtime)
        for gone in (machine.taken, machine.changed):
            self.assertIsNone(gone("/nowhere/frr.qcow2"))
        self.assertFalse(machine.exists("/nowhere/frr.qcow2"))

    def test_what_qemu_img_says(self):
        qemu_img = FakeQemuImg()
        qemu_img.infos["/lab/frr.qcow2"] = INFO
        engine = LocalEngine(self.factory, qemu_img=qemu_img)
        # once, while the file doesn't change
        self.assertIsInstance(engine.machine.infos, images.InfoCache)
        self.assertIs(engine.machine.infos.run, qemu_img)

    def test_the_other_projects(self):
        workspace = FakeWorkspace("lab", ospf=[("debian", "/ws/frr.qcow2")])
        engine = LocalEngine(self.factory, workspace=workspace)
        self.assertEqual(
            engine.machine.other_projects("/ws/frr.qcow2"),
            [("ospf", "debian")],
        )

    def test_the_trash(self):
        workspace = FakeWorkspace(None)
        workspace.path = "/ws"
        workspace.trasher = None
        machine = LocalEngine(self.factory, workspace=workspace).machine
        self.assertFalse(machine.can_trash("/ws/vimages/frr.qcow2"))
        workspace.trasher = FakeTrash()
        self.assertTrue(machine.can_trash("/ws/vimages/frr.qcow2"))
        # another file system, as a USB disk
        workspace.trasher = FakeTrash(can_trash=False)
        self.assertFalse(machine.can_trash("/ws/vimages/frr.qcow2"))
        self.assertEqual(machine.image_folder(), "/ws/vimages")

    def test_quit(self):
        switch = self.factory.new_brick("switch", "sw1")
        switch.proc = FakeProcess(switch)
        failure = self.failureResultOf(self.engine.quit())
        self.assertTrue(failure.check(errors.BrickRunningError))
        switch.proc = None
        self.successResultOf(self.engine.quit())
        self.assertTrue(self.factory.quit_d.called)


class TestFolder(unittest.TestCase):
    """What completes a path typed in the windows."""

    def setUp(self):
        self.root = isolate(self)
        self.folder = os.path.join(self.root, "lab")
        os.makedirs(os.path.join(self.folder, "images"))
        for name in ("frr.qcow2", "pc.qcow2", ".hidden"):
            with open(os.path.join(self.folder, name), "w"):
                pass

    def test_a_folder(self):
        entries, more = folder_entries(self.folder + "/")
        self.assertEqual(
            entries,
            [
                self.folder + "/frr.qcow2",
                self.folder + "/images/",
                self.folder + "/pc.qcow2",
            ],
        )
        self.assertFalse(more)

    def test_the_start_of_a_name(self):
        self.assertEqual(
            folder_entries(self.folder + "/f"),
            ([self.folder + "/frr.qcow2"], False),
        )
        # the hidden ones, once a dot is typed
        self.assertEqual(
            folder_entries(self.folder + "/.h")[0], [self.folder + "/.hidden"]
        )

    def test_more(self):
        entries, more = folder_entries(self.folder + "/", limit=2)
        self.assertEqual(len(entries), 2)
        self.assertTrue(more)

    def test_home(self):
        # isolate() made the root the home folder
        self.assertEqual(folder_entries("~/l"), (["~/lab/"], False))

    def test_no_such_folder(self):
        self.assertEqual(folder_entries("/nowhere/x"), ([], False))

    def test_the_engine(self):
        engine = LocalEngine(None)
        self.assertEqual(
            self.successResultOf(engine.folder(self.folder + "/p")),
            ([self.folder + "/pc.qcow2"], False),
        )
