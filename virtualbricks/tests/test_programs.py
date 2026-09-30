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

"""What the installed programs of the bricks can do."""

import json
import locale
import os
import re
from typing import NamedTuple

from twisted.internet import defer
from twisted.trial import unittest

from virtualbricks import programs as programs_module
from virtualbricks.programs import (
    PACKAGES,
    QEMU_QUESTIONS,
    REQUIRED,
    VDE_QUESTIONS,
    Answer,
    Device,
    Entry,
    Missing,
    ProgramError,
    Programs,
    QemuInfo,
    Version,
    decode_output,
    find_program,
    machine_question,
    missing_programs,
    parse_cpus,
    parse_devices,
    parse_machine_properties,
    parse_machines,
    parse_names,
    parse_options,
    parse_vde_options,
    parse_version,
    qemu_info,
    qemu_programs,
    run,
    vde_info,
)

RECORDINGS = os.path.join(os.path.dirname(__file__), "data", "programs")


class Target(NamedTuple):
    """What differs between the QEMU of the targets."""

    vde: bool
    stream: bool
    audio_listed: bool
    # which of the options that newer QEMUs dropped it still has
    old_options: frozenset[str]


OLD_OPTIONS = frozenset(("-no-acpi", "-portrait", "-sdl", "-soundhw"))
TARGETS = {
    "ubuntu-22.04": Target(False, False, False, OLD_OPTIONS),
    "debian-12": Target(
        True, True, True, frozenset(("-no-acpi", "-portrait"))
    ),
    "ubuntu-24.04": Target(
        False, True, True, frozenset(("-no-acpi", "-portrait"))
    ),
    "ubuntu-25.04": Target(False, True, True, frozenset()),
    "debian-13": Target(True, True, True, frozenset()),
    "ubuntu-26.04": Target(False, True, True, frozenset()),
    "debian-testing": Target(True, True, True, frozenset()),
}
# What Netemu passes to its program.
NETEMU_OPTIONS = ("-v", "-b", "-d", "-c", "-l", "--nofifo", "-M")


def load(target):
    with open(os.path.join(RECORDINGS, f"{target}.json")) as fp:
        return json.load(fp)


def answers(table):
    return {name: Answer(**answer) for name, answer in table.items()}


def recorded_info(target):
    data = load(target)
    return qemu_info(data["qemu"]["program"], answers(data["qemu"]["answers"]))


def upstream(package_version):
    """ "1:6.2+dfsg-2ubuntu6.31" is 6.2, "1:10.0.13+ds-0+deb13u1" 10.0.13."""

    return re.match(r"(?:\d+:)?([\d.]+)", package_version).group(1)


class TestRecordings(unittest.SynchronousTestCase):
    """What the programs of each target said, as recorded by record.py."""

    def test_every_target(self):
        recorded = sorted(
            name[: -len(".json")]
            for name in os.listdir(RECORDINGS)
            if name.endswith(".json")
        )
        self.assertEqual(recorded, sorted(TARGETS))

    def test_version(self):
        for target in TARGETS:
            package = load(target)["packages"]["qemu-system-x86"]
            version = str(recorded_info(target).version)
            self.assertTrue(
                version.startswith(upstream(package)), (target, version)
            )
            self.assertGreaterEqual(
                recorded_info(target).version, Version(6, 2), target
            )

    def test_differences(self):
        for target, expected in TARGETS.items():
            info = recorded_info(target)
            self.assertEqual("vde" in info.netdevs, expected.vde, target)
            self.assertEqual(
                {"stream", "dgram"} <= info.netdevs, expected.stream, target
            )
            self.assertEqual(
                info.audio_drivers is not None, expected.audio_listed, target
            )
            self.assertEqual(
                info.options & OLD_OPTIONS, expected.old_options, target
            )

    def test_what_every_target_has(self):
        for target in TARGETS:
            info = recorded_info(target)
            self.assertTrue(info.has_machine("pc"), target)
            self.assertTrue(info.has_machine("q35"), target)
            self.assertTrue(info.has_machine(info.default_machine), target)
            self.assertTrue(
                info.default_machine.startswith("pc-i440fx-"), target
            )
            self.assertTrue(info.has_cpu("qemu64"), target)
            self.assertTrue(info.has_cpu("host"), target)
            for card in ("rtl8139", "e1000", "virtio-net-pci", "usb-host"):
                self.assertIsNotNone(info.device(card), (target, card))
            self.assertEqual(info.device("ac97").name, "AC97", target)
            self.assertEqual(info.device("es1370").name, "ES1370", target)
            self.assertEqual(
                info.device("rtl8139").category, "Network devices", target
            )
            self.assertIn("sdl", info.displays, target)
            self.assertLessEqual({"user", "socket"}, info.netdevs, target)
            self.assertLessEqual({"kvm", "tcg"}, info.accelerators, target)
            self.assertLessEqual(
                {"-accel", "-audiodev", "-device", "-netdev", "-machine"},
                info.options,
                target,
            )
            if info.audio_drivers is not None:
                self.assertIn("alsa", info.audio_drivers, target)

    def test_machine_properties(self):
        for target in TARGETS:
            for machine, answer in load(target)["qemu"]["machines"].items():
                properties = parse_machine_properties(answer["out"])
                self.assertIn("acpi", properties, (target, machine))

    def test_vde(self):
        for target in TARGETS:
            data = load(target)
            found = {
                name: path
                for name, path in data["vde"]["programs"].items()
                if path
            }
            info = vde_info("/usr/bin", found, answers(data["vde"]["answers"]))
            self.assertLessEqual(set(REQUIRED), set(info.programs), target)
            self.assertNotIn("vde_router", info.programs, target)
            for option in NETEMU_OPTIONS:
                self.assertIn(option, info.options["wirefilter"], target)


class TestParse(unittest.SynchronousTestCase):

    def test_version(self):
        text = "QEMU emulator version 6.2.0 (Debian 1:6.2+dfsg-2ubuntu6)\n"
        self.assertEqual(parse_version(text), Version(6, 2, 0))

    def test_version_without_micro(self):
        text = "qemu-system-x86_64 version 2.11, Copyright\n"
        self.assertEqual(parse_version(text), Version(2, 11, 0))
        self.assertEqual(str(parse_version(text)), "2.11.0")

    def test_no_version(self):
        with self.assertRaises(ProgramError) as caught:
            parse_version("Usage: something else\n")
        self.assertIn("Usage: something else", str(caught.exception))
        self.assertRaises(ProgramError, parse_version, "")

    def test_options(self):
        text = (
            "usage: qemu-system-x86_64 [options] [disk_image]\n"
            "-h or -help     display this help and exit\n"
            "-machine [type=]name[,prop[=value][,...]]\n"
            "                selects emulated machine ('-machine help')\n"
            "-no-acpi        disable ACPI\n"
        )
        self.assertEqual(
            parse_options(text), {"-h", "-help", "-machine", "-no-acpi"}
        )

    def test_names(self):
        text = (
            "Available display backend types:\n"
            "none\n"
            "qemu: module ui-ui-gtk not found, do you want to install it?\n"
            "gtk\n"
            "\n"
            "Some display backends support suboptions:\n"
            "   -display backend,option=value\n"
        )
        self.assertEqual(parse_names(text), {"none", "gtk"})

    def test_names_without_heading(self):
        self.assertEqual(parse_names("Help is not available\n"), frozenset())

    def test_machines(self):
        text = (
            "Supported machines are:\n"
            "pc                   Standard PC (alias of pc-i440fx-7.2)\n"
            "pc-i440fx-7.2        Standard PC (i440FX + PIIX, 1996) (default)\n"
            "none                 empty machine\n"
        )
        machines, default = parse_machines(text)
        self.assertEqual(default, "pc-i440fx-7.2")
        self.assertEqual(
            machines,
            (
                Entry("pc", "Standard PC (alias of pc-i440fx-7.2)"),
                Entry("pc-i440fx-7.2", "Standard PC (i440FX + PIIX, 1996)"),
                Entry("none", "empty machine"),
            ),
        )

    def test_machines_without_default(self):
        self.assertEqual(
            parse_machines("Supported machines are:\nnone   empty\n")[1], ""
        )

    def test_cpus_with_architecture(self):
        text = (
            "Available CPUs:\n"
            "x86 486                   (alias configured by machine type)\n"
            "x86 486-v1                \n"
            "\n"
            "Recognized CPUID flags:\n"
            "  3dnow 3dnowext\n"
        )
        self.assertEqual(
            parse_cpus(text),
            (
                Entry("486", "(alias configured by machine type)"),
                Entry("486-v1", ""),
            ),
        )

    def test_cpus_indented(self):
        text = (
            "Available CPUs:\n"
            "  486                   (alias configured by machine type)\n"
            "  host                  processor with all host features\n"
        )
        self.assertEqual(
            [entry.name for entry in parse_cpus(text)], ["486", "host"]
        )

    def test_devices(self):
        text = (
            "Controller/Bridge/Hub devices:\n"
            'name "usb-host", bus usb-bus\n'
            "Network devices:\n"
            'name "e1000", bus PCI, alias "e1000-82540em", desc "Intel, GbE"\n'
            'name "rtl8139", bus PCI\n'
            "USB devices:\n"
            'name "usb-host", bus usb-bus\n'
            "Misc devices:\n"
            'name "vmcoreinfo"\n'
        )
        self.assertEqual(
            parse_devices(text),
            (
                Device("usb-host", "Controller/Bridge/Hub devices", "usb-bus"),
                Device(
                    "e1000",
                    "Network devices",
                    "PCI",
                    "e1000-82540em",
                    "Intel, GbE",
                ),
                Device("rtl8139", "Network devices", "PCI"),
                Device("vmcoreinfo", "Misc devices"),
            ),
        )

    def test_machine_properties(self):
        text = (
            "pc-i440fx-7.2-machine options:\n"
            "  acpi=<OnOffAuto>       - Enable ACPI\n"
            "  x-oem-id=<string>      - Override the OEMID\n"
            "  boot=<BootConfiguration> - Boot configuration\n"
        )
        self.assertEqual(
            parse_machine_properties(text), {"acpi", "x-oem-id", "boot"}
        )

    def test_vde_options(self):
        text = (
            "Usage: wirefilter OPTIONS\n"
            "\t--help|-h\n"
            "\t--band|-b bandwidth(bytes/s)\n"
            "\t--vde-plug plug1:plug2 | -v plug1:plug2\n"
            "\t--RED |-r min,max,probability,limit\n"
            "\t--TCPADV| -A\n"
        )
        self.assertEqual(
            parse_vde_options(text),
            {"--help", "-h", "--band", "-b", "--vde-plug", "-v"}
            | {"--RED", "-r", "--TCPADV", "-A"},
        )

    def test_audio_drivers_not_listed(self):
        info = recorded_info("ubuntu-22.04")
        self.assertIsNone(info.audio_drivers)

    def test_device_unknown(self):
        self.assertIsNone(recorded_info("debian-13").device("no-such-card"))

    def test_missing(self):
        self.assertEqual(
            str(Missing("vde_cryptcab", "vde2-cryptcab")),
            "vde_cryptcab (vde2-cryptcab)",
        )
        self.assertEqual(str(Missing("vde_router", None)), "vde_router")


def executable(directory, name, mode=0o755):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name)
    with open(path, "w") as fp:
        fp.write("#!/bin/sh\n")
    os.chmod(path, mode)
    return path


class ProgramsTestCase(unittest.SynchronousTestCase):

    def setUp(self):
        self.root = os.path.abspath(self.mktemp())
        self.bin = os.path.join(self.root, "bin")
        self.path = os.path.join(self.root, "path")
        os.makedirs(self.path)
        self.patch(os, "environ", dict(os.environ, PATH=self.path))


class TestFind(ProgramsTestCase):

    def test_in_folder(self):
        path = executable(self.bin, "vde_switch")
        executable(self.path, "vde_switch")
        self.assertEqual(find_program("vde_switch", self.bin), path)

    def test_in_path(self):
        path = executable(self.path, "vde_switch")
        self.assertEqual(find_program("vde_switch", self.bin), path)

    def test_not_executable(self):
        executable(self.bin, "vde_switch", mode=0o644)
        os.makedirs(os.path.join(self.path, "vde_switch"))
        self.assertIsNone(find_program("vde_switch", self.bin))

    def test_qemu_programs(self):
        executable(self.bin, "qemu-system-x86_64")
        executable(self.path, "qemu-system-x86_64")
        executable(self.path, "qemu-system-arm")
        executable(self.path, "qemu-system-ppc", mode=0o644)
        executable(self.path, "qemu-img")
        self.patch(
            os,
            "environ",
            dict(os.environ, PATH=f"{self.path}:{self.root}/missing"),
        )
        self.assertEqual(
            qemu_programs(self.bin), ["qemu-system-arm", "qemu-system-x86_64"]
        )

    def test_missing_programs(self):
        for name in REQUIRED:
            if name != "vde_cryptcab":
                executable(self.bin, name)
        self.assertEqual(
            missing_programs(self.bin, self.bin),
            [
                Missing("vde_cryptcab", "vde2-cryptcab"),
                Missing("qemu-img", "qemu-utils"),
                Missing("qemu-system-x86_64", "qemu-system-x86"),
            ],
        )

    def test_nothing_missing(self):
        for name in REQUIRED + ("qemu-img", "qemu-system-i386"):
            executable(self.bin, name)
        self.assertEqual(missing_programs(self.bin, self.bin), [])

    def test_packages(self):
        for name in REQUIRED:
            self.assertIsNotNone(PACKAGES[name], name)


class FakeRun:
    """Answers the questions from a recording, and counts them."""

    def __init__(self, target="debian-13", wait=False):
        data = load(target)
        self.answers = {
            QEMU_QUESTIONS[name]: Answer(**answer)
            for name, answer in data["qemu"]["answers"].items()
        }
        for machine, answer in data["qemu"]["machines"].items():
            self.answers[machine_question(machine)] = Answer(**answer)
        # the default machine is one of the pc machines
        default = qemu_info("", answers(data["qemu"]["answers"]))
        self.answers.setdefault(
            machine_question(default.default_machine),
            self.answers[machine_question("pc")],
        )
        for name, answer in data["vde"]["answers"].items():
            self.answers[(name,) + VDE_QUESTIONS[name]] = Answer(**answer)
        # no target ships vde-netemu, a fork of wirefilter with its help
        wirefilter = ("wirefilter",) + VDE_QUESTIONS["wirefilter"]
        netemu = ("vde-netemu",) + VDE_QUESTIONS["vde-netemu"]
        self.answers.setdefault(netemu, self.answers[wirefilter])
        self.calls = []
        self.wait = wait
        self.pending = []
        self.fail = None

    def __call__(self, path, args):
        args = tuple(args)
        self.calls.append((path, args))
        if self.fail is not None:
            return defer.fail(self.fail)
        key = args
        if os.path.basename(path) in VDE_QUESTIONS:
            key = (os.path.basename(path),) + args
        if self.wait:
            deferred = defer.Deferred()
            self.pending.append((deferred, self.answers[key]))
            return deferred
        return defer.succeed(self.answers[key])

    def fire(self):
        pending, self.pending = self.pending, []
        for deferred, answer in pending:
            deferred.callback(answer)


class TestQemu(ProgramsTestCase):

    def setUp(self):
        super().setUp()
        self.qemu = executable(self.bin, "qemu-system-x86_64")
        self.run = FakeRun()
        self.programs = Programs(self.run)

    def test_asks_every_question(self):
        info = self.successResultOf(self.programs.qemu(self.qemu))
        self.assertIsInstance(info, QemuInfo)
        self.assertEqual(info.path, self.qemu)
        self.assertEqual(
            sorted(args for _, args in self.run.calls),
            sorted(QEMU_QUESTIONS.values()),
        )

    def test_asks_once(self):
        first = self.successResultOf(self.programs.qemu(self.qemu))
        second = self.successResultOf(self.programs.qemu(self.qemu))
        self.assertIs(first, second)
        self.assertEqual(len(self.run.calls), len(QEMU_QUESTIONS))

    def test_the_answers_once(self):
        answers = self.successResultOf(self.programs.qemu_answers(self.qemu))
        self.assertEqual(set(answers), set(QEMU_QUESTIONS))
        self.assertEqual(
            answers["version"], self.run.answers[QEMU_QUESTIONS["version"]]
        )
        # what the info is read from
        self.successResultOf(self.programs.qemu(self.qemu))
        self.successResultOf(self.programs.qemu_answers(self.qemu))
        self.assertEqual(len(self.run.calls), len(QEMU_QUESTIONS))

    def test_asks_once_while_waiting(self):
        self.run.wait = True
        first = self.programs.qemu(self.qemu)
        second = self.programs.qemu(self.qemu)
        self.assertNoResult(first)
        self.run.fire()
        self.assertIs(
            self.successResultOf(first), self.successResultOf(second)
        )
        self.assertEqual(len(self.run.calls), len(QEMU_QUESTIONS))

    def test_asks_again_after_an_update(self):
        self.successResultOf(self.programs.qemu(self.qemu))
        with open(self.qemu, "a") as fp:
            fp.write("# a new version\n")
        self.successResultOf(self.programs.qemu(self.qemu))
        self.assertEqual(len(self.run.calls), 2 * len(QEMU_QUESTIONS))

    def test_failure_not_kept(self):
        self.run.fail = ProgramError("killed by signal 9")
        failure = self.failureResultOf(self.programs.qemu(self.qemu))
        self.assertIsInstance(failure.value, ProgramError)
        self.run.fail = None
        self.successResultOf(self.programs.qemu(self.qemu))

    def test_failure_while_waiting(self):
        self.run.wait = True
        first = self.programs.qemu(self.qemu)
        second = self.programs.qemu(self.qemu)
        pending, self.run.pending = self.run.pending, []
        pending[0][0].errback(ProgramError("killed by signal 9"))
        for deferred, answer in pending[1:]:
            deferred.callback(answer)
        for result in (first, second):
            failure = self.failureResultOf(result)
            self.assertIsInstance(failure.value, ProgramError)
        self.run.wait = False
        self.successResultOf(self.programs.qemu(self.qemu))

    def test_not_qemu(self):
        self.run.answers[QEMU_QUESTIONS["version"]] = Answer("Usage: x\n")
        failure = self.failureResultOf(self.programs.qemu(self.qemu))
        self.assertIsInstance(failure.value, ProgramError)

    def test_missing(self):
        missing = os.path.join(self.bin, "qemu-system-arm")
        failure = self.failureResultOf(self.programs.qemu(missing))
        self.assertIsInstance(failure.value, ProgramError)
        self.assertIn(missing, str(failure.value))
        self.assertEqual(self.run.calls, [])

    def test_machine_properties(self):
        info = self.successResultOf(self.programs.qemu(self.qemu))
        # the recording asked pc and q35, not the default machine by name
        self.run.answers[machine_question(info.default_machine)] = (
            self.run.answers[machine_question("pc")]
        )
        properties = self.successResultOf(
            self.programs.machine_properties(info)
        )
        self.assertIn("acpi", properties)
        self.successResultOf(self.programs.machine_properties(info, "q35"))
        self.successResultOf(self.programs.machine_properties(info, "q35"))
        asked = [args for _, args in self.run.calls[len(QEMU_QUESTIONS) :]]
        self.assertEqual(
            asked,
            [
                machine_question(info.default_machine),
                machine_question("q35"),
            ],
        )

    def test_machine_properties_missing(self):
        info = self.successResultOf(self.programs.qemu(self.qemu))
        os.remove(self.qemu)
        failure = self.failureResultOf(
            self.programs.machine_properties(info, "pc")
        )
        self.assertIsInstance(failure.value, ProgramError)


class TestVde(ProgramsTestCase):

    def setUp(self):
        super().setUp()
        self.run = FakeRun()
        self.programs = Programs(self.run)

    def test_found(self):
        switch = executable(self.bin, "vde_switch")
        wirefilter = executable(self.path, "wirefilter")
        info = self.successResultOf(self.programs.vde(self.bin))
        self.assertEqual(info.folder, self.bin)
        self.assertEqual(
            info.programs, {"vde_switch": switch, "wirefilter": wirefilter}
        )
        self.assertEqual(list(info.options), ["wirefilter"])
        self.assertIn("--nofifo", info.options["wirefilter"])
        self.assertEqual(self.run.calls, [(wirefilter, ("--help",))])

    def test_asks_once(self):
        executable(self.bin, "wirefilter")
        first = self.successResultOf(self.programs.vde(self.bin))
        self.assertIs(first, self.successResultOf(self.programs.vde(self.bin)))
        self.assertEqual(len(self.run.calls), 1)

    def test_asks_again_after_an_install(self):
        executable(self.bin, "wirefilter")
        self.successResultOf(self.programs.vde(self.bin))
        executable(self.bin, "vde_switch")
        info = self.successResultOf(self.programs.vde(self.bin))
        self.assertIn("vde_switch", info.programs)
        self.assertEqual(len(self.run.calls), 2)

    def test_failure(self):
        executable(self.bin, "wirefilter")
        self.run.fail = ProgramError("killed by signal 9")
        failure = self.failureResultOf(self.programs.vde(self.bin))
        self.assertIsInstance(failure.value, ProgramError)

    def test_removed_meanwhile(self):
        executable(self.bin, "wirefilter")

        def gone(name, folder):
            return os.path.join(folder, "gone")

        self.patch(programs_module, "find_program", gone)
        failure = self.failureResultOf(self.programs.vde(self.bin))
        self.assertIsInstance(failure.value, ProgramError)


class TestRun(unittest.TestCase):
    """Running real programs."""

    @defer.inlineCallbacks
    def test_answer(self):
        answer = yield run(
            "/bin/sh", ["-c", "echo out; echo $LC_ALL >&2; exit 3"]
        )
        self.assertEqual(answer, Answer("out\n", "C\n", 3))

    @defer.inlineCallbacks
    def test_killed(self):
        with self.assertRaises(ProgramError) as caught:
            yield run("/bin/sh", ["-c", "kill -9 $$"])
        self.assertIn("killed by signal 9", str(caught.exception))

    def test_failed(self):
        def fail(path, args, env):
            return defer.fail(RuntimeError("no more processes"))

        self.patch(programs_module, "getProcessOutputAndValue", fail)
        failure = self.failureResultOf(run("/usr/bin/qemu-img", ["info"]))
        self.assertIsInstance(failure.value, ProgramError)
        self.assertEqual(
            str(failure.value), "/usr/bin/qemu-img info: no more processes"
        )

    def test_decode_output(self):
        self.patch(locale, "getpreferredencoding", lambda: "latin-1")
        self.assertEqual(decode_output(b"d\xe9b\n"), "d\xe9b\n")
        self.patch(locale, "getpreferredencoding", lambda: "utf-8")
        self.assertEqual(decode_output(b"d\xc3\xa9b\n"), "d\xe9b\n")
        self.assertRaises(UnicodeDecodeError, decode_output, b"d\xe9b\n")

    def test_missing(self):
        failure = self.failureResultOf(run("/nonexistent/qemu", ["-help"]))
        self.assertIsInstance(failure.value, ProgramError)
        self.assertIn("/nonexistent/qemu -help", str(failure.value))

    @defer.inlineCallbacks
    def test_installed_qemu(self):
        path = find_program("qemu-system-x86_64", "/usr/bin")
        if path is None:
            raise unittest.SkipTest("QEMU isn't installed")
        info = yield Programs().qemu(path)
        self.assertGreaterEqual(info.version, Version(6, 2))
        self.assertTrue(info.has_machine(info.default_machine))
        self.assertIsNotNone(info.device("rtl8139"))
