# -*- test-case-name: virtualbricks.tests.test_sudo -*-
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
Running a program as root, when Virtualbricks doesn't run as root.

A tap runs vde_plug2tap and a capture vde_pcapplug, which open network
interfaces, and turning KSM on or off writes to /sys: they need root. Unless
Virtualbricks runs as root, it runs them with sudo.

sudo asks for the password on the terminal, and the programs that
Virtualbricks runs have none. So it's one of:

- ``sudo -A``, when an askpass helper is configured: sudo runs the helper to
  ask for the password, in a window. The helper is the program of the
  SUDO_ASKPASS variable, or of a ``Path askpass`` line of /etc/sudo.conf, as
  OpenSSH's ssh-askpass or KDE's ksshaskpass. The helpers are graphical: they
  need a display.
- ``sudo -n`` otherwise: sudo never asks, and fails at once when it would
  have to, rather than waiting for an answer that can't come. It works when a
  rule of sudoers lets the user run the program without a password
  (NOPASSWD), as a machine without a display needs.

The signals that stop a brick go to sudo, which passes them to the program.
"""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Mapping

SUDO_CONF = "/etc/sudo.conf"
# "Path askpass /usr/bin/ssh-askpass"; a comment starts with "#".
ASKPASS_LINE = re.compile(r"\s*path\s+askpass\s+\S", re.IGNORECASE)


def askpass_configured(
    environ: Mapping[str, str] | None = None, sudo_conf: str = SUDO_CONF
) -> bool:
    """Whether sudo has a helper to ask for the password in a window."""

    if environ is None:
        environ = os.environ
    if environ.get("SUDO_ASKPASS"):
        return True
    try:
        with open(sudo_conf, encoding="utf-8", errors="replace") as fp:
            return any(ASKPASS_LINE.match(line) for line in fp)
    except OSError:
        return False


def sudo_command(
    environ: Mapping[str, str] | None = None, sudo_conf: str = SUDO_CONF
) -> list[str]:
    """
    The start of a command that runs a program as root.

    ``[sudo, "-A", "--"]`` with an askpass helper, else ``[sudo, "-n",
    "--"]``: the program and its arguments follow.
    """

    option = "-A" if askpass_configured(environ, sudo_conf) else "-n"
    return [shutil.which("sudo") or "sudo", option, "--"]
