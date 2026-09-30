# -*- test-case-name: virtualbricks.tests.remote.test_facts -*-
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

"""
The facts of the machine of the bricks that the windows of another machine
ask for (page 19 §7): what its QEMU programs have, the properties of a
machine type, its USB devices, what a file is. The texts of QEMU go as QEMU
printed them; the windows read them with programs.py and config/images.py,
as they read those of their own.

They change nothing, so they don't wait in the queue of the commands of the
connection: each answers when the programs have, the pushes that wait
first. Nothing goes to the log but the failures.
"""

import json

from twisted.internet import defer, threads
from twisted.logger import Logger
from twisted.protocols import amp

from virtualbricks.bricks.virtualmachine import get_usb_devices
from virtualbricks.config import images
from virtualbricks.config.workspace import projects
from virtualbricks.console import ampcommands, ampwire
from virtualbricks.errors import CommandError
from virtualbricks.i18n import _
from virtualbricks.programs import ProgramError, programs
from virtualbricks.qemu import run
from virtualbricks.remote import commands
from virtualbricks.remote.follower import file_facts

logger = Logger()
fact_failed = "{command} for the windows of another machine failed"


def one_value(text: str) -> str:
    """text, if AMP carries it in one value."""

    size = len(text.encode("utf-8"))
    if size > amp.MAX_VALUE_LENGTH:
        raise ampwire.AnswerTooLong(
            _(
                "The answer, {size} bytes, is longer than the {most} that AMP"
                " carries"
            ).format(size=size, most=amp.MAX_VALUE_LENGTH)
        )
    return text


def _which(program: str) -> str:
    try:
        return run.which(program)
    except FileNotFoundError:
        raise ampcommands.NotFound(
            _("No QEMU program {program}").format(program=program)
        ) from None


class Facts(amp.CommandLocator):
    """The answers of the facts; the connection has pushes_first()."""

    def _answer_fact(self, command, ask):
        """The answer of ask(), a Deferred, with the errors of AMP."""

        def failed(failure):
            if failure.check(
                ampcommands.NotFound,
                ampcommands.BadArgument,
                ampwire.AnswerTooLong,
            ):
                return failure
            if failure.check(ProgramError, CommandError):
                raise ampwire.CommandFailed(failure.getErrorMessage())
            if failure.check(FileNotFoundError):
                # the program that would say
                raise ampwire.CommandFailed(
                    _("No program {name}").format(name=failure.value.args[0])
                )
            logger.failure(fact_failed, failure, command=command)
            raise ampwire.CommandFailed(
                failure.getErrorMessage() or failure.type.__name__
            )

        answering = defer.maybeDeferred(ask)
        answering.addErrback(failed)
        return answering.addBoth(self.pushes_first)

    @commands.QemuFacts.responder
    def qemu_facts(self, program):
        def ask():
            path = _which(program)
            asking = programs.qemu_answers(path)

            def answer(answers):
                box = {"path": path}
                for name in commands.QEMU_ANSWERS:
                    box[name] = one_value(
                        json.dumps(list(answers[name]), ensure_ascii=False)
                    )
                return box

            return asking.addCallback(answer)

        return self._answer_fact("QemuFacts", ask)

    @commands.MachineProperties.responder
    def machine_properties(self, program, machine):
        def ask():
            path = _which(program)
            if machine:
                asking = defer.succeed(machine)
            else:
                asking = programs.qemu(path)
                asking.addCallback(lambda info: info.default_machine)
            asking.addCallback(
                lambda chosen: programs.machine_answer(path, chosen)
            )
            return asking.addCallback(
                lambda answer: {"text": one_value(answer.out)}
            )

        return self._answer_fact("MachineProperties", ask)

    @commands.UsbDevices.responder
    def usb_devices(self):
        def ask():
            asking = get_usb_devices()

            def answer(devices):
                found = [
                    {"id": device.id, "description": device.description}
                    for device in devices
                ]
                return {
                    "devices": one_value(json.dumps(found, ensure_ascii=False))
                }

            return asking.addCallback(answer)

        return self._answer_fact("UsbDevices", ask)

    @commands.ImageFacts.responder
    def image_facts(self, path):
        def ask():
            facts = file_facts(path)
            if facts is None:
                raise ampcommands.NotFound(
                    _("No file {path}").format(path=path)
                )
            others = images.other_projects(projects, path)
            # -U: a running machine locks the image it writes to
            reading = run.qemu_img(["info", "--output=json", "-U", path])
            return reading.addCallback(
                lambda info: {
                    "file": json.dumps(facts),
                    "info": one_value(info),
                    "others": one_value(
                        json.dumps(others, ensure_ascii=False)
                    ),
                }
            )

        return self._answer_fact("ImageFacts", ask)

    @commands.DiskUsage.responder
    def disk_usage(self, name):
        def ask():
            if not projects.exists(name):
                raise ampcommands.NotFound(
                    _("No project named {name}").format(name=name)
                )
            # the files of a project may be many: counted in a thread
            counting = threads.deferToThread(projects.disk_usage, name)
            return counting.addCallback(
                lambda usage: {
                    "private_disks": usage.private_disks,
                    "other_files": usage.other_files,
                }
            )

        return self._answer_fact("DiskUsage", ask)
