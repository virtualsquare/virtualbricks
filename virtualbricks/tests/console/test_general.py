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

"""The commands without a noun."""

import os

from virtualbricks.bricks import event as event_module
from virtualbricks.console.command import Arg, command
from virtualbricks.console.dispatch import run
from virtualbricks.bricks.eventaction import (
    StopAction,
)
from virtualbricks.console.general import help_
from virtualbricks.tests.console import ConsoleTestCase, own_commands


class FakeProcess:
    def __init__(self, pid):
        self.pid = pid


class TestHelp(ConsoleTestCase):

    def setUp(self):
        super().setUp()
        own_commands(self)
        # help itself, and two commands of a noun
        command(
            None,
            "help",
            Arg("TOPIC", many=True, optional=True),
            help="The commands, a noun's verbs, or one command",
        )(help_)
        command(
            "brick",
            "start",
            Arg("NAME", many=True),
            help="Start bricks",
            example="brick start sw1",
        )(lambda context, name: None)
        command("brick", "list", help="The bricks")(lambda context: None)

    def test_overview(self):
        self.assertEqual(
            self.run_line("help"),
            [
                "A command is a noun, a verb, then its arguments: brick start"
                " sw1.",
                "help NOUN lists the verbs of a noun, and help NOUN VERB tells"
                " about one command.",
                "",
                "brick  Make, change, start, stop and delete bricks",
                "help   The commands, a noun's verbs, or one command",
            ],
        )

    def test_a_noun(self):
        self.assertEqual(
            self.run_line("help brick"),
            [
                "Make, change, start, stop and delete bricks",
                "",
                "brick start NAME…  Start bricks",
                "brick list         The bricks",
            ],
        )

    def test_a_command(self):
        self.assertEqual(
            self.run_line("help brick start"),
            ["brick start NAME…", "Start bricks", "Example: brick start sw1"],
        )
        self.assertEqual(
            self.run_line("help brick list"), ["brick list", "The bricks"]
        )
        self.assertEqual(self.run_line("help help")[0], "help [TOPIC…]")

    def test_nothing_of_the_kind(self):
        for line in ("help nope", "help brick stop", "help brick start sw1"):
            self.assertEqual(
                self.fails(line),
                f"No command {line[5:]}; type help for the commands",
            )


class TestStatusAndQuit(ConsoleTestCase):

    def setUp(self):
        super().setUp()
        self.patch(event_module, "reactor", self.clock())
        self.factory.runtime_dir = "/run/vb"

    def running(self, kind, name, pid):
        brick = self.factory.new_brick(kind, name)
        brick.proc = FakeProcess(pid)
        return brick

    def test_status(self):
        self.assertEqual(self.run_line("status"), ["Nothing runs"])
        self.running("switch", "sw1", 41822)
        self.factory.new_brick("tap", "tap1")
        event = self.factory.new_event("boot")
        event.update_config({"delay": 10, "actions": [StopAction("sw1")]})
        event.start()
        self.clock().advance(3)
        self.assertEqual(
            self.run_line("status"),
            [
                "BRICK  KIND    PROCESS",
                "sw1    Switch  41822",
                "",
                "EVENT  RUNS IN",
                "boot   7 s",
            ],
        )
        event.poweroff()

    def test_quit(self):
        self.running("switch", "sw1", 41822)
        self.assertEqual(self.fails("quit"), "sw1 is running: stop it first")
        self.assertFalse(self.factory.quit_d.called)
        self.factory.get_brick("sw1").proc = None
        self.assertEqual(self.run_line("quit"), [])
        self.assertTrue(self.factory.quit_d.called)


class TestSource(ConsoleTestCase):

    def setUp(self):
        super().setUp()
        self.factory.runtime_dir = "/run/vb"

    def script(self, text):
        path = os.path.abspath(self.mktemp())
        with open(path, "w") as fp:
            fp.write(text)
        return path

    def test_source(self):
        path = self.script(
            "# the lab\nbrick new switch\n\nbrick new tap  # a tap\n"
        )
        self.assertEqual(self.run_line(f"source {path}"), ["sw1", "tap1"])

    def test_up_to_the_first_error(self):
        path = self.script("brick new switch\nbrick new nope\nbrick new tap\n")
        failure = self.failureResultOf(
            run(self.factory, f"source {path}", self.clock())
        )
        self.assertEqual(
            failure.getErrorMessage(),
            f"{path}:2: No kind nope: brick types lists them",
        )
        self.assertEqual(failure.value.lines, ["sw1"])
        self.assertEqual([b.name for b in self.factory.bricks], ["sw1"])

    def test_from_the_folder_of_the_command(self):
        # sent by --command: the file and the paths inside it are read from
        # the folder that it runs in
        folder = os.path.abspath(self.mktemp())
        os.makedirs(folder)
        open(os.path.join(folder, "deb.qcow2"), "w").close()
        with open(os.path.join(folder, "lab.vb"), "w") as fp:
            fp.write("image add deb deb.qcow2\n")
        answer = run(self.factory, "source lab.vb", self.clock(), cwd=folder)
        self.assertEqual(self.successResultOf(answer), ["deb"])
        image = self.factory.get_image("deb")
        self.assertEqual(image.path, os.path.join(folder, "deb.qcow2"))

    def test_a_file_that_cant_be_read(self):
        self.assertEqual(
            self.fails("source /nope.vb"),
            "/nope.vb can't be read: No such file or directory",
        )
