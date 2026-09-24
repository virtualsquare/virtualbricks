#!/usr/bin/env python
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

# Package metadata lives in pyproject.toml. This file only exists to compile
# the gettext catalogs (.po -> .mo) at install time.

import glob
import os.path

from setuptools import setup
from distutils.command.install_data import install_data as _install_data


class install_data(_install_data):

    def initialize_options(self):
        _install_data.initialize_options(self)
        self.tmpdirs = []

    def compile_mo(self):
        import tempfile
        for filename in glob.iglob("locale/virtualbricks/??.po"):
            lang, _ = os.path.basename(filename).split(".")
            tmpdir = tempfile.mkdtemp()
            self.tmpdirs.append(tmpdir)
            outfile = "{0}/virtualbricks.mo".format(tmpdir)
            self.spawn(["msgfmt", "-o", outfile, filename])
            self.data_files.append(
                ("share/locale/{0}/LC_MESSAGES".format(lang), [outfile])
            )

    def remove_temps(self):
        import shutil
        for tmpdir in self.tmpdirs:
            shutil.rmtree(tmpdir)

    def run(self):
        self.execute(self.compile_mo, ())
        _install_data.run(self)
        self.execute(self.remove_temps, ())


setup(cmdclass={"install_data": install_data})
