#!/usr/bin/env python
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2013 Virtualbricks team

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

import os.path
import tempfile
import shutil
import glob

from distutils.command import install_data
from distutils.core import setup

from virtualbricks import version


class InstallData(install_data.install_data):

    def initialize_options(self):
        install_data.install_data.initialize_options(self)
        self.tmpdirs = []

    def compile_mo(self):
        for filename in glob.iglob("locale/virtualbricks/??.po"):
            l, _ = os.path.basename(filename).split(".")
            tmpdir = tempfile.mkdtemp()
            self.tmpdirs.append(tmpdir)
            outfile = "%s/virtualbricks.mo" % tmpdir
            self.spawn(["msgfmt", "-o", outfile, filename])
            self.data_files.append(("share/locale/%s/LC_MESSAGES" % l,
                                    [outfile]))

    def remove_temps(self):
        for tmpdir in self.tmpdirs:
            shutil.rmtree(tmpdir)

    def run(self):
        self.execute(self.compile_mo, ())
        install_data.install_data.run(self)
        self.execute(self.remove_temps, ())


setup(name="virtualbricks",
      version=version.short(),
      description="Virtualbricks Virtualization Tools",
      author="Daniele Lacamera, Rainer Haage, Francesco Apollonio, "
            "Pierre-Louis Bonicoli, Simone Abbati",
      author_email="qemulator-list@createweb.de",
      url="http://www.virtualbricks.eu/",
      license="GPLv2",
      platforms=["linux2", "linux"],
      packages=["virtualbricks",
                "virtualbricks.gui",
                "virtualbricks.scripts",
                "virtualbricks.tests"],
      package_data={"virtualbricks.gui": ["data/help/*.txt", "data/*.png",
                                          "data/*.ui"],
                    "virtualbricks.tests": ["data/*"]},
      data_files=[("share/applications", ["share/virtualbricks.desktop"])],
      scripts=["bin/virtualbricks"],
      requires=["twisted (>=12.0.0)", "zope.interface (>=3.5)"],
      cmdclass={"install_data": InstallData}
     )
