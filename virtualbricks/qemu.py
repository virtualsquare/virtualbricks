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

from virtualbricks import _qemu


_version = None


def _get_version():
    return _version


def install(version):
    global _version
    _version = version


def parse_and_install(string):
    version = _qemu.parse_qemu_version(string)
    supported_version = _qemu.last_supported_version(version)
    install(supported_version)


def get_executables(version=None):
    if version is None:
        version = _get_version()
    if version is None:
        raise TypeError("Invalid qemu version")
    return _qemu.load_spec(version)['binaries']


def get_cpus(architecture, version=None):
    if version is None:
        version = _get_version()
    if version is None:
        raise TypeError("Invalid qemu version")
    cpus = _qemu.load_spec(version)['cpus']
    return cpus[architecture]


def get_machines(architecture, version=None):
    if version is None:
        version = _get_version()
    if version is None:
        raise TypeError("Invalid qemu version")
    machines = _qemu.load_spec(version)['machines']
    return machines[architecture]
