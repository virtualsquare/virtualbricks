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

import os
import os.path
import sys
import re
import tempfile
import shutil
import glob

from distutils.command import install_data
from distutils.core import setup

from virtualbricks import version


class InstallData(install_data.install_data):

    GLADEFILE_TEMPLATE = "share/virtualbricks.template.glade"
    GLADEFILE = "share/virtualbricks.glade"

    def initialize_options(self):
        install_data.install_data.initialize_options(self)
        self.tmpdirs = []

    def write_glade(self):
        with open(self.GLADEFILE_TEMPLATE) as fp:
            data = fp.read()
            out = re.sub("__IMAGES_PATH__",
                           os.path.join(sys.prefix, "share"), data)
            with open(self.GLADEFILE, "w") as fp:
                fp.write(out)
        self.data_files.append(("share/virtualbricks", [self.GLADEFILE]))

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
        self.execute(self.write_glade, ())
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
      packages=["virtualbricks", "virtualbricks.gui", "virtualbricks.scripts",
               "virtualbricks.tests"],
      package_data={"virtualbricks.gui": ["virtualbricks.glade"]},
      data_files=[("share/applications", ["share/virtualbricks.desktop"]),
                  ("share/virtualbricks", ["share/about.ui",
                                           "share/disklibrary.ui"]),
                  ("share/pixmaps", ["share/virtualbricks.png",
                                     "images/Connect.png",
                                     "images/Disconnect.png",
                                     "images/Event.png", "images/Qemu.png",
                                     "images/Switch.png", "images/Tap.png",
                                     "images/Capture.png",
                                     "images/TunnelConnect.png",
                                     "images/TunnelListen.png",
                                     "images/Wirefilter.png",
                                     "images/Wire.png", "images/Router.png",
                                     "images/SwitchWrapper.png"])],
      scripts=["bin/virtualbricks", "bin/vbgui", "bin/vbd"],
      cmdclass={"install_data": InstallData}
     )
