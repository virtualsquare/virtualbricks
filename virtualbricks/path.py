import errno
from os.path import basename, dirname, join as joinpath, exists as pathexists
import pkgutil
import sys
import virtualbricks


def _resource_paths(package, resource):
    # Search the resource in the system, in well known locations.
    filename = basename(resource)
    for prefix in sys.prefix, '/usr', '/usr/local':
        syswide = joinpath(prefix, 'share', 'virtualbricks', filename)
        yield syswide
    # Then search it in the package itself.
    loader = pkgutil.get_loader(package)
    mod = sys.modules.get(package) or loader.load_module(package)
    if mod is None or not hasattr(mod, "__file__"):
        return
    pkgdir = dirname(mod.__file__)
    yield joinpath(pkgdir, 'data/' + resource)
    # Last chance. Sometime, if the package is installed via the setup.py
    # script, the data files are installed in very strange
    # locations. For example, this was a real case, the data files were in
    # /usr/local/lib/python2.7/dist-packages/... (continue)
    #       .../virtualbricks-1.0.12-py2.7.egg/share/virtualbricks
    for vpath in virtualbricks.__path__:
        yield joinpath(dirname(vpath), 'share', 'virtualbricks', filename)
    # I did my best, I give up.


def get_resource_filename(package, resource):
    for path in _resource_paths(package, resource):
        if pathexists(path):
            return path


def _get_data(package, resource, mode):
    for path in _resource_paths(package, resource):
        try:
            with open(path, mode=mode) as fp:
                return fp.read()
        except IOError as exc:
            if exc.errno != errno.ENOENT:
                raise
    # We will never know, maybe pkgutil will have more luck than us
    data = pkgutil.get_data(package, resource)
    if data and 't' in mode:
        return data.decode('strict')
    return data


def read_data(package, resource):
    return _get_data(package, resource, mode='rb')


def read_text(package, resource):
    return _get_data(package, resource, mode='r')
