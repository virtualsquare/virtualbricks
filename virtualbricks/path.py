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

from os.path import basename, dirname, join as joinpath, exists as pathexists
import pkgutil
import sys
import virtualbricks


def _resource_paths(package, resource):
    # Search the resource in the system, in well known locations.
    filename = basename(resource)
    for prefix in sys.prefix, "/usr", "/usr/local":
        syswide = joinpath(prefix, "share", "virtualbricks", filename)
        yield syswide
    # Then search it in the package itself.
    loader = pkgutil.get_loader(package)
    mod = sys.modules.get(package) or loader.load_module(package)
    if mod is None or not hasattr(mod, "__file__"):
        return
    pkgdir = dirname(mod.__file__)
    yield joinpath(pkgdir, "data/" + resource)
    # Last chance. Sometime, if the package is installed via the setup.py
    # script, the data files are installed in very strange
    # locations. For example, this was a real case, the data files were in
    # /usr/local/lib/python2.7/dist-packages/... (continue)
    #       .../virtualbricks-1.0.12-py2.7.egg/share/virtualbricks
    for vpath in virtualbricks.__path__:
        yield joinpath(dirname(vpath), "share", "virtualbricks", filename)
    # I did my best, I give up.


def get_resource_filename(package, resource):
    for path in _resource_paths(package, resource):
        if pathexists(path):
            return path
