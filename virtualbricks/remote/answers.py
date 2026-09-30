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
``Apply``, the OK of a panel, and ``Connect``, a drop.

The AMP connections of the control sockets take them on, beside Follow.
Like the typed commands, they run in the order they came, their line goes to
the log, and the pushes that wait go before their answer. NotFound and
BadArgument say that nothing was done.
"""

import json

from twisted.logger import Logger
from twisted.protocols import amp

from virtualbricks.bricks import brickinfo
from virtualbricks.console import ampcommands, ampwire
from virtualbricks.remote import commands
from virtualbricks.remote.drafts import apply_changes

logger = Logger()
failed = "{command} of {name} failed"


class Answers(amp.CommandLocator):
    """
    The answers to Apply and Connect; the connection has brickfactory,
    requests, pushes_first(), _log_line() and _log_failed().
    """

    def _answer_in_order(self, line, name, call):
        def run():
            self._log_line(line)
            try:
                return call()
            except LookupError as exc:
                # a KeyError's str() has quotes
                message = str(exc.args[0]) if exc.args else str(exc)
                self._log_failed(message)
                raise ampcommands.NotFound(message) from None
            except ValueError as exc:
                self._log_failed(str(exc))
                raise ampcommands.BadArgument(str(exc)) from None
            except Exception as exc:
                logger.failure(failed, command=line.split()[0], name=name)
                raise ampwire.CommandFailed(str(exc) or type(exc).__name__)

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
