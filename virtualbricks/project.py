# -*- test-case-name: virtualbricks.tests.test_project -*-
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

import os
import errno
import itertools
import re
import six

from twisted.internet import utils, error, defer
from twisted.python import filepath

from virtualbricks import (settings, configfile, log, errors, _configparser,
                           tools)


logger = log.Logger()
__metaclass__ = type

create_archive = log.Event("Create archive in {path}")
extract_archive = log.Event("Extract archive in {path}")
open_project = log.Event("Restoring project {name}")
import_project = log.Event("Importing project from {path} as {name}")
create_project = log.Event("Create project {name}")
write_project = log.Event("Writing new .project file")
rebase_error = log.Event("Error on rebase")
rebase = log.Event("Rebasing {cow} to {basefile}")
remap_image = log.Event("Mapping {original} to {new}")
extract_project = log.Event("Extracting project")
cannot_find_project = log.Event("Cannot find project \"{name}\". "
                                "A new project will be created.")
include_images = log.Event("Including the following images to the project: "
                           "{images}.")
save_images = log.Event("Move virtual machine's images")
DEFAULT_PROJECT_RE = re.compile(r"^{0}(?:_\d+)?$".format(
    settings.DEFAULT_PROJECT))


def _complain_on_error(result):
    out, err, code = result
    if code != 0:
        logger.warn(err)
        raise error.ProcessTerminated(code)
    logger.info(err)
    return result


class Tgz:

    exe_c = exe_x = "tar"

    def create(self, pathname, files, images=(),
               run=utils.getProcessOutputAndValue):
        logger.info(create_archive, path=pathname)
        args = ["cfzh", pathname, "-C", settings.VIRTUALBRICKS_HOME] + files
        if images:
            logger.info(include_images, images=images)
            prjpath = filepath.FilePath(settings.VIRTUALBRICKS_HOME)
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

    def extract(self, pathname, destination,
                run=utils.getProcessOutputAndValue):
        logger.info(extract_archive, path=destination)
        args = ["Sxfz", pathname, "-C", destination]
        d = run(self.exe_x, args, os.environ)
        return d.addCallback(_complain_on_error)


class BsdTgz(Tgz):

    exe_c = exe_x = "bsdtar"


class ProjectEntry:

    def __init__(self, sections, links):
        self.sections = sections
        self.links = links

    @classmethod
    def from_fileobj(cls, fileobj):
        links = []
        sections = {}
        for item in _configparser.Parser(fileobj):
            if isinstance(item, tuple):
                links.append(item)
            else:
                sections[(item.type, item.name)] = dict(item)
        return cls(sections, links)

    def _filter(self, fltr):
        return [(s, self.sections[s]) for s in self.sections if fltr(s)]

    def has_image(self, name):
        return ("Image", name) in self.sections

    def get_images(self):
        return self._filter(lambda k: k[0] == "Image")

    def remap_image(self, name, path):
        if self.has_image(name):
            self.sections[("Image", name)]["path"] = path

    def get_bricks(self):
        # XXX: every time a new brick type is added or a a type is changed this
        # method must change too. fix this
        bricks = set(["Qemu", "Switch", "SwitchWrapper", "Tap", "Capture",
                      "Wirefilter", "Netemu", "Wire", "TunnelConnect",
                      "TunnelListen", "Router"])
        return self._filter(lambda k: k[0] in bricks)

    def get_events(self):
        return self._filter(lambda k: k[0] == "Event")

    def get_virtualmachines(self):
        return self._filter(lambda k: k[0] == "Qemu")

    def get_disks(self):
        disks = {}
        for header, section in self.get_virtualmachines():
            for dev in "hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock":
                if dev in section:
                    disks.setdefault(header[1], []).append((dev, section[dev]))
        return disks

    def device_for_image(self, name):
        for (typ, vmname), section in self.get_virtualmachines():
            for dev in "hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock":
                if dev in section and section[dev] == name:
                    yield vmname, dev

    def _dump_section(self, fileobj, header, section):
        fileobj.write("[{0[0]}:{0[1]}]\n".format(header))
        for name in section:
            fileobj.write("{0} = {1}\n".format(name, section[name]))
        fileobj.write("\n")

    def dump(self, fileobj):
        for header, section in self.get_images():
            self._dump_section(fileobj, header, section)
        for header, section in self.get_events():
            self._dump_section(fileobj, header, section)
        for header, section in self.get_bricks():
            self._dump_section(fileobj, header, section)
        for link in self.links:
            fileobj.write("{0}\n".format("|".join(link)))

    def save(self, project):
        with project._project.open("w") as fp:
            self.dump(fp)


def pass_through(function, *args, **kwds):
    def wrapper(arg):
        function(*args, **kwds)
        return arg
    return wrapper


class Project:

    _description = None
    _description_modified = False

    def __init__(self, path, manager):
        if isinstance(path, six.string_types):
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
        return self._path.child(".project")

    def delete(self):
        try:
            self._path.remove()
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise

    def open(self, factory, settings=settings):
        if self._manager.current == self:
            return
        if not self.exists():
            raise errors.ProjectNotExistsError(self.name)
        self.close(factory, settings)
        logger.debug(open_project, name=self.name)

        # save the old setting parameters
        # Bug #1410679
        old_proj = settings.get("current_project")
        old_vbhome = settings.VIRTUALBRICKS_HOME
        # save new setting parameters
        # Bug #1410679
        settings.set("current_project", self.name)
        settings.VIRTUALBRICKS_HOME = self.path
        settings.store()

        try:
            configfile.restore(factory, self._project.path)
        except EnvironmentError as e:
            # if an exception is raised then revert settings to the
            # default values
            # Bug #1410679
            settings.set("current_project", old_proj)
            settings.VIRTUALBRICKS_HOME = old_vbhome
            settings.store()
            if e.errno in (errno.ENOENT, errno.ENOTDIR):
                raise errors.ProjectNotExistsError(self.name)
            raise
        # if an exception is raised, this value is not changed, i.e. it
        # is the default
        self._manager.current = self
        return self

    def close(self, factory, settings=settings):
        factory.reset()
        if self._manager.current:
            self._manager.current = None
            settings.VIRTUALBRICKS_HOME = settings.DEFAULT_HOME

    def create(self, overwrite=False):
        try:
            self._path.makedirs()
        except OSError as e:
            if e.errno == errno.EEXIST:
                if overwrite:
                    self.delete()
                    return self.create()
                raise errors.ProjectExistsError(self.name)
            raise
        self._project.touch()
        logger.debug(create_project, name=self.name)
        return self

    def exists(self):
        try:
            self.create().delete()
            return False
        except errors.ProjectExistsError:
            return True

    def save(self, factory, _avoid_lop=False):
        try:
            configfile.save(factory, self._project.path)
        except IOError as e:
            if e.errno == errno.ENOENT:
                if not _avoid_lop:
                    self.create()
                    return self.save(factory, True)
            raise
        if self._description_modified:
            self._path.child("README").setContent((self._description).encode("utf-8"))
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
        new_prj.create(overwrite)
        new_path = filepath.FilePath(new_prj.path)
        new_path.remove()
        self._path.moveTo(new_path)
        self._path = new_path
        if self == self._manager.current:
            settings.set("current_project", self.name)
            settings.VIRTUALBRICKS_HOME = self.path
            settings.store()

    def get_description(self):
        if self._description is None:
            try:
                self._description = self._path.child("README").getContent()
            except IOError as e:
                if e.errno != errno.ENOENT:
                    raise
                self._description = ""
        return self._description

    def set_description(self, text):
        self._description = text
        self._description_modified = True

    def files(self):
        return (fp for fp in self._path.walk() if fp.isfile())

    def get_descriptor(self):
        with self._project.open() as fp:
            return ProjectEntry.from_fileobj(fp)

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
        if path is None:
            path = settings.get("workspace")
        self._path = filepath.FilePath(path)
        try:
            self._path.makedirs()
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

    @property
    def path(self):
        return self._path.path

    def get_project(self, name):
        try:
            path = self._path.child(name)
            return self.project_factory(path, self)
        except filepath.InsecurePath:
            raise errors.InvalidNameError(name)

    def __iter__(self):
        for path in self._path.children():
            if path.child(".project").isfile():
                yield self.project_factory(path, self)

    def import_prj(self, name, vbppath):
        project = self.get_project(name)
        try:
            project.create()
        except Exception as e:
            return defer.fail(e)
        logger.debug(extract_project)
        deferred = self.archive.extract(vbppath, project.path)
        return deferred.addCallback(lambda _: project)

    def export(self, output, files, images=()):
        return self.archive.create(output, files, images)

    def save_current(self, factory):
        if self.current:
            self.current.save(factory)

    def restore_last(self, factory, settings=settings):
        """Restore the last project if found or create a new one."""

        try:
            os.makedirs(os.path.join(settings.get("workspace"), "vimages"))
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
        name = settings.get("current_project")
        project = self.get_project(name)
        try:
            return project.open(factory, settings)
        except errors.ProjectNotExistsError:
            if DEFAULT_PROJECT_RE.match(name):
                project.create(name)
                project.open(factory, settings)
                return project
            else:
                logger.error(cannot_find_project, name=name)
                for i in itertools.count():
                    name = "{0}_{1}".format(settings.DEFAULT_PROJECT, i)
                    project = self.get_project(name)
                    try:
                        project.create(name)
                        project.open(factory, settings)
                        return project
                    except errors.ProjectExistsError:
                        pass


class ProjectManager2(ProjectManager):

    def upgrade(self, fpath):
        basename = fpath.basename().strip(" \t.") + "_"
        for c in itertools.count():
            try:
                prj = self.get_project(basename + str(c))
                prj.create()
                fpath.moveTo(prj._project)
                return prj
            except errors.ProjectExistsError:
                pass

    def get_project(self, name):
        try:
            prj = ProjectManager.get_project(self, name)
        except errors.InvalidNameError:
            fp = filepath.FilePath(name)
            if not fp.isfile():
                raise
            prj = self.upgrade(fp)
        return prj

    def open(self, name, factory, settings=settings, oldformat=True):
        prj = self.get_project(name)
        return prj.open(factory, settings)


manager = ProjectManager2()
