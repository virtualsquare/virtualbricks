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

import json
import re
from virtualbricks.path import read_data


IN_MEMORY = ':memory:'
SUPPORTED_QEMU_VERSIONS = (
    '2.0.0',
    '1.1.2',
    '1.0',
)
IN_MEMORY_SPECS = {}
ENOSPECS = 'Cannot find specs for Qemu version {version}'


PARSERS = (
    (IN_MEMORY, lambda value: value),
    ('json', json.loads),
    # ('yaml', yaml.safe_load),
)


class SpecsNotFound(Exception):
    pass


def load_data(version, ext):
    if ext == IN_MEMORY:
        if version not in IN_MEMORY_SPECS:
            raise SpecsNotFound(ENOSPECS.format(version=version))
        return IN_MEMORY_SPECS[version]
    name = version.replace('.', '_')
    filename = 'qemu_specs_{0}.{1}'.format(name, ext)
    data = read_data('virtualbricks.gui', filename)
    if data is not None:
        return data
    raise SpecsNotFound(ENOSPECS.format(version=version))


def load_spec(version):
    for ext, parser in PARSERS:
        try:
            data = load_data(version, ext)
            specs = parser(data)
            IN_MEMORY_SPECS[version] = specs
            return specs
        except SpecsNotFound:
            continue
    errmsg = 'Cannot find specs for Qemu version {0}'.format(version)
    raise SpecsNotFound(errmsg)


def last_supported_version(version):
    for supported_version in SUPPORTED_QEMU_VERSIONS:
        if version >= supported_version:
            # TODO: log info about the used version
            return supported_version
    raise ValueError('Unsupported Qemu version, too old' + repr(version))


def get_specs(version):
    return load_spec(last_supported_version(version))


QEMU_VERSION_RE = re.compile(
    r'^(QEMU emulator|qemu-[\w_-]+)'
    r' version '
    r'(?P<version>\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)'
)


def parse_qemu_version(command_output, pattern=QEMU_VERSION_RE):
    match = pattern.match(command_output)
    if match is None:
        raise ValueError("invalid version string " + repr(command_output))
    return match.group('version')
