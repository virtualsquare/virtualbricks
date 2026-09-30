# -*- test-case-name: virtualbricks.tests.remote.test_answers -*-
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
The answers of the Virtualbricks of the bricks to the commands of the
windows of another machine that the console has none for (page 19 §7):
``Apply``, the OK of a panel, ``Connect``, a drop, the commands of the
files of the images: ``MakeImage``, ``StartOver``, ``TrashFile`` and
``Relink``, and those of the projects and the README: ``ProjectNames``,
``ProjectSummary``, ``Readme`` and ``SetReadme``. The reads go to the log
only if they fail.

The AMP connections of the control sockets take them on, beside Follow.
Like the typed commands, they run in the order they came, their line goes to
the log, and the pushes that wait go before their answer. NotFound and
BadArgument say that nothing was done.

TrashFile moves only a file of the workspace that no image uses, of this
project or of another: the windows offer no more, and a connection gets no
more than they offer.
"""

import dataclasses
import json
import os

from twisted.internet import defer
from twisted.logger import Logger
from twisted.protocols import amp

from virtualbricks import errors
from virtualbricks.bricks import brickinfo
from virtualbricks.bricks.virtualmachine import DISK_DEVICES, is_virtualmachine
from virtualbricks.config import images
from virtualbricks.config.workspace import projects
from virtualbricks.console import ampcommands, ampwire
from virtualbricks.errors import CommandError
from virtualbricks.i18n import _
from virtualbricks.qemu import run as qemu_run
from virtualbricks.remote import commands
from virtualbricks.remote.drafts import apply_changes
from virtualbricks.remote.facts import one_value

logger = Logger()
failed = "{command} of {name} failed"

# the formats of a new empty disk
FORMATS = ("qcow2", "raw")


class Answers(amp.CommandLocator):
    """
    The answers to Apply, Connect and the commands of the files; the
    connection has brickfactory, requests, pushes_first(), _log_line() and
    _log_failed().
    """

    def _answer_in_order(self, line, name, call, log=True):
        def refused(failure):
            exc = failure.value
            if failure.check(LookupError):
                # a KeyError's str() has quotes
                message = str(exc.args[0]) if exc.args else str(exc)
                self._log_failed(message)
                raise ampcommands.NotFound(message)
            if failure.check(ValueError, errors.Error):
                self._log_failed(str(exc))
                raise ampcommands.BadArgument(str(exc))
            if failure.check(ampwire.AnswerTooLong):
                self._log_failed(str(exc))
                raise exc
            if failure.check(CommandError, OSError):
                # a program or a file said no: nothing to fix here
                self._log_failed(str(exc))
                raise ampwire.CommandFailed(str(exc))
            logger.failure(failed, failure, command=line.split()[0], name=name)
            raise ampwire.CommandFailed(str(exc) or type(exc).__name__)

        def run():
            if log:
                self._log_line(line)
            return defer.maybeDeferred(call).addErrback(refused)

        return self.requests.add(run).addBoth(self.pushes_first)

    @commands.Apply.responder
    def apply(self, kind, name, changes, links, extras):
        data = {
            "changes": json.loads(changes),
            "links": json.loads(links),
            "extras": json.loads(extras),
        }

        def call():
            apply_changes(self.brickfactory, kind, name, data)
            return {}

        return self._answer_in_order(f"apply {kind} {name}", name, call)

    @commands.Connect.responder
    def connect(self, source, target):
        def call():
            bricks = []
            for name in (source, target):
                brick = self.brickfactory.get_brick(name)
                if brick is None:
                    raise LookupError(f"No brick named {name}")
                bricks.append(brick)
            return {"connected": brickinfo.connect(*bricks)}

        return self._answer_in_order(
            f"connect {source} {target}", source, call
        )

    # The files of the images

    def _vm(self, name):
        vm = self.brickfactory.get_brick(name)
        if vm is None or not is_virtualmachine(vm):
            raise LookupError(
                _("No virtual machine named {name}").format(name=name)
            )
        return vm

    @commands.MakeImage.responder
    def make_image(self, path, format, size):
        def call():
            if format not in FORMATS:
                raise ValueError(
                    _("The format is {formats}").format(
                        formats=" or ".join(FORMATS)
                    )
                )
            if os.path.lexists(path):
                raise ValueError(
                    _("{path} is there already").format(path=path)
                )
            if os.path.dirname(path) == os.path.join(
                projects.path, images.IMAGE_FOLDER
            ):
                # the folder of the images, made when first needed
                images.image_folder(projects)
            making = qemu_run.qemu_img(
                ["create", "-q", "-f", format, path, str(size)]
            )
            return making.addCallback(lambda _: {})

        return self._answer_in_order(f"make image {path}", path, call)

    @commands.StartOver.responder
    def start_over(self, vm, device):
        def call():
            machine = self._vm(vm)
            if machine.project_folder() is None:
                raise ValueError(_("No project is open"))
            if device not in DISK_DEVICES:
                raise ValueError(_("No disk {device}").format(device=device))
            trashed = images.start_over(machine, device, projects.trasher)
            # its copy is gone: what the windows show of it
            machine.changed.notify(machine)
            return {"trashed": trashed}

        return self._answer_in_order(f"start over {vm} {device}", vm, call)

    @commands.TrashFile.responder
    def trash_file(self, path):
        def call():
            path_there = os.path.abspath(path)
            if not images.is_inside(path_there, projects.path):
                raise ValueError(
                    _("{path} isn't in the workspace").format(path=path)
                )
            image = self.brickfactory.get_image_by_path(path_there)
            if image is not None:
                raise ValueError(
                    _("The image {name} has the file").format(name=image.name)
                )
            others = images.other_projects(projects, path_there)
            if others:
                raise ValueError(
                    _("The project {name} uses the file").format(
                        name=others[0][0]
                    )
                )
            trashed = images.discard(path_there, projects.trasher)
            return {"trashed": trashed}

        return self._answer_in_order(f"trash {path}", path, call)

    @commands.Relink.responder
    def relink(self, name, path):
        def call():
            image = self.brickfactory.get_image(name)
            if image is None:
                raise LookupError(_("No image named {name}").format(name=name))
            relinking = images.relink(
                self.brickfactory, image, path, qemu_run.qemu_img
            )
            return relinking.addCallback(lambda _: {})

        return self._answer_in_order(f"relink {name} {path}", name, call)

    # The projects and the README

    @commands.ProjectNames.responder
    def project_names(self):
        return self._answer_in_order(
            "project names",
            "the workspace",
            lambda: {"names": projects.names()},
            log=False,
        )

    @commands.ProjectSummary.responder
    def project_summary(self, name):
        def call():
            if not projects.exists(name):
                raise LookupError(
                    _("No project named {name}").format(name=name)
                )
            summary = dataclasses.asdict(projects.summary(name))
            return {
                "summary": one_value(json.dumps(summary, ensure_ascii=False))
            }

        return self._answer_in_order(
            f"project summary {name}", name, call, log=False
        )

    def _open_project(self):
        current = projects.current
        if current is None:
            raise ValueError(_("No project is open"))
        return current

    @commands.Readme.responder
    def readme(self):
        def call():
            text = self._open_project().get_description()
            return {"text": one_value(text)}

        return self._answer_in_order("readme", "the README", call, log=False)

    @commands.SetReadme.responder
    def set_readme(self, text):
        def call():
            self._open_project().set_description(text)
            return {}

        return self._answer_in_order("set readme", "the README", call)
