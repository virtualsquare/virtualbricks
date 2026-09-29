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

"""The commands of the AMP socket, for the programs that import them."""

import subprocess
import sys

from twisted.trial import unittest


class TestTheImport(unittest.TestCase):

    def test_what_it_loads(self):
        # a program imports the commands: no reactor, no GTK, and nothing of
        # Virtualbricks but its packages
        code = (
            "import sys\n"
            "from virtualbricks.console import ampwire\n"
            "print('twisted.internet.reactor' in sys.modules,"
            " 'gi' in sys.modules)\n"
            "print(sorted(name for name in sys.modules"
            " if name.startswith('virtualbricks')))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual(
            result.stdout.splitlines(),
            [
                "False False",
                "['virtualbricks', 'virtualbricks.console',"
                " 'virtualbricks.console.ampwire']",
            ],
        )
