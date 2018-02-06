#!/usr/bin/env python
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2018 Virtualbricks team

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
import glob

from distutils.command.install_data import install_data as _install_data
from setuptools import setup

def _get_version():
    filename = os.path.join('virtualbricks', '__init__.py')
    var = '__version__'
    glb = {}
    with open(filename) as fp:
        for line in fp:
            if var in line:
                exec(line, glb)
                return glb[var ]
    raise RuntimeError('cannot find version')


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


DATA_IMAGES = glob.glob("virtualbricks/gui/data/*.png")
DATA_HELPS = glob.glob("virtualbricks/gui/data/help/*")
DATA_GLADE_UI = glob.glob("virtualbricks/gui/data/*.ui")
QEMU_SPEC_FILES = glob.glob('share/qemu_specs_*.*')
DATA_FILES = DATA_IMAGES + DATA_GLADE_UI + DATA_HELPS + QEMU_SPEC_FILES


setup(
    name="virtualbricks",
    version=_get_version(),
    description="Virtualbricks Virtualization Tools",
    long_description=open('README').read(),
    author="Virtualbricks team",
    url='https://github.com/virtualsquare/virtualbricks',
    license="GPLv2",
    platforms=["linux2", "linux"],
    packages=[
        "virtualbricks",
        "virtualbricks.gui",
        "virtualbricks.scripts",
        "virtualbricks.tests"
    ],
    package_data={"virtualbricks.tests": ["data/*"]},
    data_files=[
        ("share/applications", ["share/virtualbricks.desktop"]),
        ("share/pixmaps", ["share/virtualbricks.xpm"]),
        ("share/virtualbricks", DATA_FILES),
    ],
    install_requires=[
        'mock',
        'Pillow',
        'pygraphviz',
        "Twisted>=12.0.0",
        "zope.interface>=3.5"
    ],
    entry_points={
        'console_scripts': [
            'virtualbricks = virtualbricks.scripts.virtualbricks:run'
        ]
    },
    cmdclass={
        "install_data": install_data
    },
    classifiers=[
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 2 :: Only',
        'Environment :: X11 Applications :: GTK',
        'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)',
        'Operating System :: POSIX :: Linux',
    ],
)
