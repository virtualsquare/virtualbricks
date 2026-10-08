# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2026 Virtualbricks team

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

"""A switch wrapper: it runs while a switch listens in its folder."""

import os
import socket

from virtualbricks import errors
from virtualbricks.bricks import must_stop, switchwrapper
from virtualbricks.bricks.eventaction import StartAction
from virtualbricks.bricks.switchwrapper import (
    ExternalSwitch,
    is_switchwrapper,
    listens,
    look_all,
    switch_pid,
)
from virtualbricks.config.projectfile import project_document, restore_project
from virtualbricks.config.report import Report
from virtualbricks.config.settings import ProjectSettings
from virtualbricks.tests import (
    BrickTestCase,
    FakeLogger,
    make_factory,
    short_folder,
)


class Switch:
    """The control folder of a switch, as vde_switch makes it: its ctl."""

    def __init__(self, test, folder=None):
        self.folder = short_folder(test) if folder is None else folder
        self.ctl = os.path.join(self.folder, "ctl")
        self.socket = None
        test.addCleanup(self.quit)

    def listen(self):
        os.makedirs(self.folder, exist_ok=True)
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.bind(self.ctl)
        self.socket.listen()
        return self

    def quit(self):
        if self.socket is not None:
            self.socket.close()
            self.socket = None
            os.unlink(self.ctl)


class TestListens(BrickTestCase):

    def test_a_switch(self):
        self.assertTrue(listens(Switch(self).listen().folder))

    def test_no_folder(self):
        self.assertFalse(listens(""))
        self.assertFalse(listens(os.path.join(short_folder(self), "none")))

    def test_a_folder_without_a_switch(self):
        switch = Switch(self)
        self.assertFalse(listens(switch.folder))
        with open(switch.ctl, "w"):
            pass
        self.assertFalse(listens(switch.folder))


class TestSwitchPid(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.proc = os.path.abspath(self.mktemp())
        os.makedirs(os.path.join(self.proc, "net"))
        self.folder = os.path.abspath(self.mktemp())

    def unix(self, *lines):
        header = "Num       RefCount Protocol Flags    Type St Inode Path\n"
        with open(os.path.join(self.proc, "net", "unix"), "w") as table:
            table.write(header + "".join(line + "\n" for line in lines))

    def files(self, pid, *links):
        fds = os.path.join(self.proc, pid, "fd")
        os.makedirs(fds)
        for fd, link in enumerate(links):
            os.symlink(link, os.path.join(fds, str(fd)))

    def socket(self, inode, path):
        return f"0000000000000000: 00000002 00000000 00010000 0001 01 {inode} {path}"

    def test_the_process_with_the_socket(self):
        self.unix(
            self.socket(70, "/run/other/ctl"),
            "0000000000000000: 00000003 00000000 00000000 0001 03 71",
            self.socket(72, os.path.join(self.folder, "ctl")),
        )
        self.files("12", "/dev/null", "socket:[70]")
        self.files("34", "/dev/null", "pipe:[72]", "socket:[72]")
        os.makedirs(os.path.join(self.proc, "self"))
        self.assertEqual(switch_pid(self.folder, self.proc), 34)

    def test_none(self):
        # Linux tells no socket there, or the process is another user's
        self.assertIsNone(switch_pid(self.folder, self.proc))
        self.unix(self.socket(70, "/run/other/ctl"))
        self.files("12", "socket:[70]")
        self.assertIsNone(switch_pid(self.folder, self.proc))
        self.unix(self.socket(72, os.path.join(self.folder, "ctl")))
        self.assertIsNone(switch_pid(self.folder, self.proc))

    def test_this_process(self):
        switch = Switch(self).listen()
        self.assertEqual(switch_pid(switch.folder), os.getpid())


class SwitchWrapperTestCase(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.switch = Switch(self)
        self.wrapper = self.factory.new_brick("switchwrapper", "wr")
        self.changed = []
        self.wrapper.changed.connect(self.changed.append)

    def wrap(self):
        self.wrapper.update_config({"socket_path": self.switch.folder})
        del self.changed[:]


class TestTheState(SwitchWrapperTestCase):

    def test_is_switchwrapper(self):
        self.assertTrue(is_switchwrapper(self.wrapper))
        self.assertFalse(
            is_switchwrapper(self.factory.new_brick("switch", "sw"))
        )
        self.assertFalse(is_switchwrapper(self.factory.new_event("boot")))

    def test_configured_by_its_folder(self):
        self.assertFalse(self.wrapper.configured())
        self.assertEqual(self.wrapper.socks[0].path, "")
        self.wrap()
        self.assertTrue(self.wrapper.configured())
        self.assertEqual(self.wrapper.socks[0].path, self.switch.folder)
        # whatever the folder: a switch may make it later
        self.wrapper.update_config({"socket_path": "/nonexistent/lab.ctl"})
        self.assertTrue(self.wrapper.configured())

    def test_runs_while_a_switch_listens(self):
        self.switch.listen()
        self.wrap()
        self.assertTrue(self.wrapper.is_running())
        self.assertIsInstance(self.wrapper.proc, ExternalSwitch)
        self.assertEqual(self.wrapper.pid, os.getpid())
        self.wrapper.look()
        self.assertEqual(self.changed, [])
        self.switch.quit()
        self.wrapper.look()
        self.assertFalse(self.wrapper.is_running())
        self.assertEqual(self.changed, [self.wrapper])
        self.switch.listen()
        self.wrapper.look()
        self.assertTrue(self.wrapper.is_running())
        self.assertEqual(self.changed, [self.wrapper, self.wrapper])

    def test_another_folder(self):
        self.switch.listen()
        self.wrap()
        other = Switch(self).listen()
        self.wrapper.update_config({"socket_path": other.folder})
        self.assertEqual(self.wrapper.proc.folder, other.folder)
        self.wrapper.update_config({"socket_path": short_folder(self)})
        self.assertFalse(self.wrapper.is_running())
        self.wrap()
        self.assertTrue(self.wrapper.is_running())
        self.wrapper.update_config({"socket_path": ""})
        self.assertFalse(self.wrapper.configured())
        self.assertFalse(self.wrapper.is_running())

    def test_events_of_the_changes(self):
        started = []
        for name in ("up", "down"):
            event = self.factory.new_event(name)
            event.update_config({"actions": [StartAction("wr")]})
            event.start = lambda name=name: started.append(name)
        self.wrapper.update_config({"on_start": "up", "on_stop": "down"})
        # the switch found at the first look starts nothing
        self.switch.listen()
        self.wrap()
        self.assertEqual(started, [])
        self.switch.quit()
        self.wrapper.look()
        self.assertEqual(started, ["down"])
        self.switch.listen()
        self.wrapper.look()
        self.assertEqual(started, ["down", "up"])
        self.wrapper.update_config({"socket_path": short_folder(self)})
        self.assertEqual(started, ["down", "up"])

    def test_loaded(self):
        self.switch.listen()
        self.wrap()
        data = project_document(self.factory, ProjectSettings())
        factory = make_factory(self)
        restore_project(factory, data, Report(), "/")
        wrapper = factory.get_brick("wr")
        self.assertEqual(wrapper.socks[0].path, self.switch.folder)
        self.assertTrue(wrapper.is_running())


class TestStartAndStop(SwitchWrapperTestCase):

    def test_not_configured(self):
        failure = self.failureResultOf(self.wrapper.start())
        failure.trap(errors.BadConfigError)
        self.assertEqual(
            failure.getErrorMessage(), "Cannot start 'wr': not configured"
        )

    def test_no_switch(self):
        self.wrap()
        failure = self.failureResultOf(self.wrapper.start())
        failure.trap(errors.BadConfigError)
        self.assertEqual(
            failure.getErrorMessage(),
            f"No switch listens in {self.switch.folder}",
        )

    def test_start_looks(self):
        started = []
        event = self.factory.new_event("up")
        event.update_config({"actions": [StartAction("wr")]})
        event.start = lambda: started.append("up")
        self.wrapper.update_config({"on_start": "up"})
        self.wrap()
        self.switch.listen()
        self.assertIs(self.successResultOf(self.wrapper.start()), self.wrapper)
        self.assertTrue(self.wrapper.is_running())
        self.assertEqual(self.changed, [self.wrapper])
        self.assertEqual(started, ["up"])
        self.assertIs(self.successResultOf(self.wrapper.start()), self.wrapper)
        self.assertEqual(started, ["up"])

    def test_stop_refused(self):
        self.wrap()
        self.assertEqual(
            self.successResultOf(self.wrapper.stop()), (self.wrapper, None)
        )
        self.switch.listen()
        self.wrapper.look()
        failure = self.failureResultOf(self.wrapper.stop(kill=True))
        failure.trap(errors.OtherProgramError)
        self.assertEqual(
            failure.getErrorMessage(), "Another program runs the switch of wr"
        )
        self.assertTrue(self.wrapper.is_running())

    def test_no_signals_no_input(self):
        self.switch.listen()
        self.wrap()
        self.assertRaises(
            errors.OtherProgramError, self.wrapper.send_signal, "STOP"
        )
        self.assertRaises(errors.OtherProgramError, self.wrapper.send, b"x")


class TestFactory(SwitchWrapperTestCase):

    def test_it_never_has_to_stop(self):
        self.switch.listen()
        self.wrap()
        self.assertTrue(self.wrapper.is_running())
        self.assertFalse(must_stop(self.wrapper))
        switch = self.factory.new_brick("switch", "sw")
        self.assertFalse(must_stop(switch))
        switch.proc = ExternalSwitch(self.wrapper, "")
        self.assertTrue(must_stop(switch))

    def test_deleted_running(self):
        self.switch.listen()
        self.wrap()
        self.factory.remove_brick(self.wrapper)
        self.assertIsNone(self.factory.get_brick("wr"))

    def test_quit_running(self):
        self.switch.listen()
        self.wrap()
        self.factory.reset()
        self.assertEqual(list(self.factory.bricks), [])
        self.factory.quit()
        self.assertTrue(self.factory.quit_d.called)


class TestLookAll(SwitchWrapperTestCase):

    def test_the_wrappers(self):
        self.wrap()
        other = self.factory.new_brick("switchwrapper", "wr2")
        second = Switch(self).listen()
        other.update_config({"socket_path": second.folder})
        self.factory.new_brick("switch", "sw")
        self.switch.listen()
        second.quit()
        look_all(self.factory)
        self.assertTrue(self.wrapper.is_running())
        self.assertFalse(other.is_running())

    def test_a_failure_is_logged(self):
        logger = FakeLogger()
        self.patch(switchwrapper, "logger", logger)
        broken = self.factory.new_brick("switchwrapper", "broken")
        broken.look = lambda: 1 / 0
        self.wrap()
        self.switch.listen()
        look_all(self.factory)
        self.assertTrue(self.wrapper.is_running())
        self.assertEqual(
            logger.events,
            [
                (
                    "failure",
                    "Cannot look at the control folder of {name}",
                    {"name": "broken"},
                )
            ],
        )
