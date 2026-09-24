# -*- test-case-name: virtualbricks.tests.test_project -*-
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

"""
Projects: directories of the workspace with a ``project.toml``.

One project is open at a time. While it's open its settings win over the app
settings, and the sockets of its bricks are in its runtime directory.
"""

import os
import errno
import itertools
import re

from twisted.internet import utils, error, defer
from twisted.python import filepath
from twisted.logger import Logger

from virtualbricks import errors, locations
from virtualbricks.config import (
    ProjectFormatError,
    Report,
    projectfile,
    settings,
    tomlfile,
)
from virtualbricks import tools

logger = Logger()

create_archive = "Create archive in {path}"
extract_archive = "Extract archive in {path}"
open_project = "Restoring project {name}"
create_project = "Create project {name}"
cannot_find_project = (
    'Cannot find project "{name}". A new project will be created.'
)
cannot_open_project = (
    'Cannot open project "{name}": {error}. A new project will be created.'
)
include_images = "Including the following images to the project: {images}."
autosave_error = "Error while saving the project"
DEFAULT_PROJECT_RE = re.compile(
    r"^{0}(?:_\d+)?$".format(locations.DEFAULT_PROJECT)
)


def _complain_on_error(result):
    out, err, code = result
    stderr = err.decode(errors="replace")
    if code != 0:
        logger.warn("{stderr}", stderr=stderr)
        raise error.ProcessTerminated(code)
    logger.info("{stderr}", stderr=stderr)
    return result


class Tgz:

    exe_c = exe_x = "tar"

    def create(
        self,
        pathname,
        directory,
        files,
        images=(),
        run=utils.getProcessOutputAndValue,
    ):
        """Archive the files of the project in directory, and its images."""

        logger.info(create_archive, path=pathname)
        args = ["cfzh", pathname, "-C", directory] + files
        if images:
            logger.info(include_images, images=images)
            prjpath = filepath.FilePath(directory)
            imgs = prjpath.child(".images")
            try:
                imgs.remove()
            except OSError as e:
                if e.errno != errno.ENOENT:
                    return defer.fail(e)
            imgs.makedirs()
            for name, image in images:
                fp = filepath.FilePath(image)
                if fp.exists():
                    link = imgs.child(name)
                    fp.linkTo(link)
                    args.append("/".join(link.segmentsFrom(prjpath)))
        d = run(self.exe_c, args, os.environ)
        d.addCallback(_complain_on_error)
        if images:
            d.addBoth(pass_through(imgs.remove))
        return d

    def extract(
        self, pathname, destination, run=utils.getProcessOutputAndValue
    ):
        logger.info(extract_archive, path=destination)
        args = ["Sxfz", pathname, "-C", destination]
        d = run(self.exe_x, args, os.environ)
        return d.addCallback(_complain_on_error)


class BsdTgz(Tgz):

    exe_c = exe_x = "bsdtar"


def pass_through(function, *args, **kwds):
    def wrapper(arg):
        function(*args, **kwds)
        return arg

    return wrapper


class Project:

    _description = None
    _description_modified = False
    # The settings of the project, while it's open.
    project_settings = None

    def __init__(self, path, manager):
        if isinstance(path, str):
            path = filepath.FilePath(path)
        self._path = path
        self._manager = manager

    @property
    def path(self):
        return self._path.path

    @property
    def name(self):
        return self._path.basename()

    @property
    def _project(self):
        return self._path.child(locations.PROJECT_FILE)

    @property
    def project_file(self):
        return self._project.path

    def delete(self):
        try:
            self._path.remove()
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise

    def open(self, factory, settings=settings):
        """
        Load the project into factory.

        Raise ProjectNotExistsError if there is no project file and
        ProjectFormatError if it can't be read.
        """

        if self._manager.current == self:
            return
        report = Report()
        try:
            data = projectfile.upgrade(self.read_document(), report)
        except FileNotFoundError:
            raise errors.ProjectNotExistsError(self.name) from None
        # The project file is readable, so it's safe to close the current one.
        self.close(factory, settings)
        logger.debug(open_project, name=self.name)
        runtime_dir = os.path.join(locations.runtime_dir(), self.name)
        factory.runtime_dir = locations.ensure_private_dir(runtime_dir)
        project_settings = projectfile.restore(
            factory, data, report, self.path
        )
        report.log(logger)
        self.project_settings = project_settings
        settings.use_project(project_settings)
        settings.set_current_project(self.name)
        self._manager.current = self
        return self

    def close(self, factory, settings=settings):
        factory.reset()
        if self._manager.current:
            self._manager.current.project_settings = None
            self._manager.current = None
            settings.use_project(None)

    def create(self, overwrite=False, settings=settings):
        """Create the directory and a project file with the app settings."""

        try:
            self._path.makedirs()
        except OSError as e:
            if e.errno == errno.EEXIST:
                if overwrite:
                    self.delete()
                    return self.create(settings=settings)
                raise errors.ProjectExistsError(self.name)
            raise
        projectfile.create(self.project_file, settings.new_project_settings())
        logger.debug(create_project, name=self.name)
        return self

    def exists(self):
        return self._project.isfile()

    def save(self, factory):
        if not self._path.isdir():
            self._path.makedirs()
        projectfile.save(factory, self.project_settings, self.project_file)
        if self._description_modified:
            text = self._description
            with open(self._path.child("README").path, "wt") as fp:
                fp.write(text)
            self._description_modified = False

    def save_as(self, name, factory):
        if name == self.name:
            return
        self.save(factory)
        prj = self._manager.get_project(name)
        prj.create()
        dst = filepath.FilePath(prj.path)
        dst.remove()
        tools.copyTo(self._path, dst)
        return prj

    copy = save_as

    def rename(self, name, overwrite=False, settings=settings):
        if name == self.name:
            return
        new_prj = self._manager.get_project(name)
        new_prj.create(overwrite, settings)
        new_path = filepath.FilePath(new_prj.path)
        new_path.remove()
        self._path.moveTo(new_path)
        self._path = new_path
        if self == self._manager.current:
            settings.set_current_project(self.name)

    def get_description(self):
        if self._description is None:
            try:
                with open(self._path.child("README").path) as fp:
                    self._description = fp.read()
            except FileNotFoundError:
                self._description = ""
        return self._description

    def set_description(self, text):
        self._description = text
        self._description_modified = True

    def files(self):
        return (fp for fp in self._path.walk() if fp.isfile())

    def read_document(self):
        """Return the data of the project file, to edit it without opening."""

        return projectfile.read(self.project_file)

    def write_document(self, data):
        tomlfile.dump(data, self.project_file)

    def images(self):
        path = self._path.child(".images")
        if path.isdir():
            return path.listdir()
        return ()

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.name == other.name and self.path == other.path

    def __ne__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self._path)

    def __repr__(self):
        return "<Project name:{0.name} path={0.path}>".format(self)


class ProjectManager:

    archive = BsdTgz()
    current = None
    project_factory = Project

    def __init__(self, path=None):
        self._path = None if path is None else filepath.FilePath(path)

    @property
    def workspace(self):
        """The directory of the projects, from the settings unless given."""

        if self._path is not None:
            return self._path
        return filepath.FilePath(settings.get("workspace"))

    @property
    def path(self):
        return self.workspace.path

    def get_project(self, name):
        try:
            path = self.workspace.child(name)
        except filepath.InsecurePath:
            raise errors.InvalidNameError(name) from None
        return self.project_factory(path, self)

    def __iter__(self):
        if not self.workspace.isdir():
            return
        for path in self.workspace.children():
            if path.child(locations.PROJECT_FILE).isfile():
                yield self.project_factory(path, self)

    def import_prj(self, name, vbppath):
        """Extract an archive into a new project, migrating an old one."""

        try:
            project = self.get_project(name)
            project._path.makedirs()
        except errors.InvalidNameError as e:
            return defer.fail(e)
        except OSError as e:
            if e.errno == errno.EEXIST:
                return defer.fail(errors.ProjectExistsError(name))
            return defer.fail(e)
        deferred = self.archive.extract(vbppath, project.path)
        return deferred.addCallback(lambda _: self._finish_import(project))

    def _finish_import(self, project):
        if not project.exists():
            from virtualbricks.migrate import engine

            engine.migrate_imported_project(project.path).log(logger)
        if not project.exists():
            raise errors.InvalidArchiveError(
                f"{project.name}: the archive has no project file"
            )
        return project

    def export(self, output, directory, files, images=()):
        return self.archive.create(output, directory, files, images)

    def save_current(self, factory):
        if self.current:
            self.current.save(factory)

    def autosave(self, factory):
        try:
            self.save_current(factory)
        except Exception:
            logger.failure(autosave_error)

    def _create_and_open(self, name, factory, settings):
        project = self.get_project(name)
        project.create(settings=settings)
        return project.open(factory, settings)

    def restore_last(self, factory, settings=settings):
        """Open the last project, or create a new one if it can't be."""

        os.makedirs(os.path.join(self.path, "vimages"), exist_ok=True)
        name = settings.current_project()
        try:
            return self.get_project(name).open(factory, settings)
        except errors.ProjectNotExistsError:
            if DEFAULT_PROJECT_RE.match(name):
                try:
                    return self._create_and_open(name, factory, settings)
                except errors.ProjectExistsError:
                    pass
            logger.error(cannot_find_project, name=name)
        except errors.InvalidNameError:
            logger.error(cannot_find_project, name=name)
        except ProjectFormatError as exc:
            logger.error(cannot_open_project, name=name, error=exc)
        for i in itertools.count():  # pragma: no branch
            name = "{0}_{1}".format(locations.DEFAULT_PROJECT, i)
            try:
                return self._create_and_open(name, factory, settings)
            except errors.ProjectExistsError:
                pass


manager = ProjectManager()
