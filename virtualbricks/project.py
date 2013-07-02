# -*- test-case-name: virtualbricks.tests.test_project -*-
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
import errno

from twisted.internet import utils
from twisted.python import filepath

from virtualbricks import tools, _settings, settings, configfile, _compat


log = _compat.getLogger(__name__)
__metaclass__ = type


class InvalidNameError(Exception):
    pass


class ProjectManager:

    def __iter__(self):
        path = filepath.FilePath(settings.get("workspace"))
        return (p.basename() for p in path.children() if
                p.child(".project").isfile())

    def _set_project_default(self, prj, factory):
        self.close()
        global current
        current = prj
        prj.restore(factory)
        settings.set("current_project", prj.name)
        settings.VIRTUALBRICKS_HOME = prj.path

    def open(self, name, factory, create=False):
        workspace = filepath.FilePath(settings.get("workspace"))
        try:
            path = workspace.child(name)
        except filepath.InsecurePath:
            raise InvalidNameError(name)
        if not path.isdir():
            if create:
                return self.create(name, factory)
            else:
                raise InvalidNameError(name)
        path.child(".project").touch()
        prj = Project(path)
        self._set_project_default(prj, factory)
        return prj

    def create(self, name, factory):
        if isinstance(name, basestring):
            workspace = filepath.FilePath(settings.get("workspace"))
            try:
                path = workspace.child(name)
            except filepath.InsecurePath:
                raise InvalidNameError(name)
        else:  # type(name) == filepath.FilePath
            path = name
        try:
            path.makedirs()
        except OSError as e:
            if e.errno == errno.EEXIST:
                raise InvalidNameError(name)
            else:
                raise
        path.child(".project").touch()
        prj = Project(path)
        self._set_project_default(prj, factory)
        return prj

    def close(self):
        global current
        if current:
            current = None
            settings.VIRTUALBRICKS_HOME = _settings.VIRTUALBRICKS_HOME


manager = ProjectManager()
current = None


class Project:

    def __init__(self, path):
        self.filepath = path

    @property
    def path(self):
        return self.filepath.path

    @property
    def name(self):
        return self.filepath.basename()

    def restore(self, factory):
        configfile.restore(factory, self.filepath.child(".project").path)

    def save(self, factory):
        configfile.save(factory, self.filepath.child(".project").path)

    def files(self):
        return (fp for fp in self.filepath.walk() if fp.isfile())

    def export(self, output, files, include_backing_file=False):
        if include_backing_file:
            files.extend(tools.backing_files_for(files))
        return self.archive.create(output, files)


class Tar:

    def create(self, path, files):
        d = utils.getProcessValue(self.executable, ["cfz", path] + files,
                                  os.environ)
        return d


class BSDTgz(Tar):

    executable = "bsdtar"


class GNUTgz(Tar):

    executable = "tar"


def is_in_path(executable):
    return any(os.access(os.path.join(p, executable), os.X_OK) for p in
               os.environ.get("PATH", "").split(":"))


def install_archive_manager():
    if is_in_path("bsdtar"):
        Project.archive = BSDTgz()
    else:
        Project.archive = GNUTgz()
def restore_last_project(factory):
    """Restore the last project if found or create a new one."""

    try:
        os.mkdir(_settings.VIRTUALBRICKS_HOME)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    return manager.open(settings.get("current_project"), factory, create=True)
