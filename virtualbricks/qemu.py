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
