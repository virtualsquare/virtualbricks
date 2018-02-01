import errno
import json
import os.path
import pkgutil
import re
import sys


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
    syswide = os.path.join(sys.prefix, 'share', 'virtualbricks', filename)
    # Try system wide specs files
    try:
        with open(syswide) as fp:
            return fp.read()
    except IOError as exc:
        if exc.errno != errno.ENOENT:
            raise
    # Try package data files
    try:
        data = pkgutil.get_data('virtualbricks', filename)
    except IOError as exc:
        if exc.errno == errno.ENOENT:
            raise SpecsNotFound(ENOSPECS.format(version=version))
        raise
    if data is None:
        raise SpecsNotFound(ENOSPECS.format(version=version))
    return data


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
    r'^(QEMU emulator|qemu-[\w-]+)'
    r' version '
    r'(?P<version>\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)'
)


def parse_qemu_version(command_output, pattern=QEMU_VERSION_RE):
    match = pattern.match(command_output)
    if match is None:
        raise ValueError("invalid version string " + repr(command_output))
    return match.group('version')
