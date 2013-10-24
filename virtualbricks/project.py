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
import tarfile
import itertools
import re

from twisted.internet import utils, error, defer
from twisted.python import filepath

from virtualbricks import (settings, configfile, log, errors, configparser,
                           tools)


logger = log.Logger()
__metaclass__ = type

create_archive = log.Event("Create archive in {path}")
extract_archive = log.Event("Extract archive in {path}")
restore_project = log.Event("Restoring project {name}")
import_project = log.Event("Importing project from {path} as {name}")
create_project = log.Event("Create project {name}")
write_project = log.Event("Writing new .project file")
rebase_error = log.Event("Error on rebase")
# log.msg("Rebase failed, try manually", isError=True)
rebase = log.Event("Rebasing {cow} to {basefile}")
cannot_find_project = log.Event("Cannot find project \"{name}\". "
                                "A new project will be created.")
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

    def create(self, pathname, files):
        logger.info(create_archive, path=pathname)
        args = ["cfz", pathname, "-C", settings.VIRTUALBRICKS_HOME] + files
        d = utils.getProcessOutputAndValue(self.exe_c, args, os.environ)
        d.addCallback(_complain_on_error)
        return d

    def extract(self, pathname, destination):
        logger.info(extract_archive, path=pathname)
        args = ["Sxfz", pathname, "-C", destination]
        d = utils.getProcessOutputAndValue(self.exe_x, args, os.environ)
        d.addCallback(_complain_on_error)
        return d


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
        for item in configparser.Parser(fileobj):
            if isinstance(item, tuple):
                links.append(item)
            else:
                sections[(item.type, item.name)] = dict(item)
        return cls(sections, links)

    def _filter(self, fltr):
        return [(s, self.sections[s]) for s in self.sections if fltr(s)]

    def get_images(self):
        return self._filter(lambda k: k[0] == "Image")

    def get_bricks(self):
        bricks = set(["Qemu", "Switch", "SwitchWrapper", "Tap", "Capture",
                      "Wirefilter", "Wire", "TunnelConnect", "TunnelListen",
                      "Router"])
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

    def _dump_section(self, fileobj, header, section):
        fileobj.write("[{0[0]}:{0[1]}]\n".format(header))
        for name, value in section.iteritems():
            fileobj.write("{0} = {1}\n".format(name, value))
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


class Archive:

    def __init__(self, filename):
        self.archive = tarfile.open(filename)

    def get_member(self, name):
        return self.archive.getmember(name)

    def get_project(self):
        project = self.archive.getmember(".project")
        return ProjectEntry.from_fileobj(self.archive.extractfile(project))


class ProjectManager:

    archive = BsdTgz()

    def __iter__(self):
        path = filepath.FilePath(settings.get("workspace"))
        return (p.basename() for p in path.children() if
                p.child(".project").isfile())

    def open(self, name, factory):
        workspace = filepath.FilePath(settings.get("workspace"))
        try:
            path = workspace.child(name)
        except filepath.InsecurePath:
            raise errors.InvalidNameError(name)

        try:
            return self.restore(Project(path), factory)
        except EnvironmentError as e:
            if e.errno in (errno.ENOENT, errno.ENOTDIR):
                raise errors.ProjectNotExistsError(name)

    def restore(self, project, factory):
        logger.debug(restore_project, name=project.name)
        self.close(factory)
        global current
        current = project
        settings.set("current_project", project.name)
        settings.VIRTUALBRICKS_HOME = project.path
        settings.store()
        project.restore(factory)
        return project

    def _create(self, name, project, factory, open=False):
        try:
            project.filepath.makedirs()
        except OSError as e:
            if e.errno == errno.EEXIST:
                raise errors.ProjectExistsError(name)
            else:
                raise
        else:
            project.filepath.child(".project").touch()
            logger.debug(create_project, name=name)
            if open:
                return self.restore(project, factory)
            return project

    def create(self, name, factory, open=True):
        workspace = filepath.FilePath(settings.get("workspace"))
        try:
            path = workspace.child(name)
        except filepath.InsecurePath:
            raise errors.InvalidNameError(name)
        return self._create(name, Project(path), factory, open)

    def close(self, factory):
        factory.reset()
        global current
        if current:
            current = None
            settings.VIRTUALBRICKS_HOME = settings.DEFAULT_HOME

    def export(self, output, files):
        return self.archive.create(output, files)

    def import_(self, prjname, pathname, factory, image_mapper, open=True):
        """Import a project in the current workspace."""

        logger.debug(import_project, path=pathname, name=prjname)
        try:
            prjentry = Archive(pathname).get_project()
        except KeyError:
            raise errors.InvalidArchiveError(".project file not found.")
        deferred = image_mapper(prjentry.get_images())
        deferred.addCallback(self._remap_images_cb, prjentry)
        deferred.addCallback(self._create_cb, prjname, factory)
        deferred.addCallback(self._import_cb, prjentry, pathname)
        if open:
            deferred.addCallback(self.restore, factory)
        return deferred

    def _remap_images_cb(self, dct, prjentry):
        for header, section in prjentry.get_images():
            if header[1] in dct and dct[header[1]]:
                prjentry.sections[header]["path"] = dct[header[1]]

    def _create_cb(self, _, name, factory):
        return self.create(name, factory, False)

    def _import_cb(self, project, prjentry, pathname):
        deferred = self.archive.extract(pathname, project.path)
        deferred.addCallback(self._dump_cb, project, prjentry)
        deferred.addCallback(self._rebase_cb, prjentry)
        return deferred

    def _dump_cb(self, _, project, prjentry):
        logger.debug(write_project)
        with project.filepath.child(".project").open("w") as fp:
            prjentry.dump(fp)
        return project

    def _rebase_cb(self, project, prjentry):
        def check_rebase(result):
            for success, status in result:
                if not success:
                    logger.error(rebase_error, log_failure=status)
            return project

        disks = prjentry.get_disks()
        images = dict(prjentry.get_images())
        dl = []
        for vmname in disks:
            for dev, iname in disks[vmname]:
                cow = project.filepath.child("{0}_{1}.cow".format(vmname, dev))
                if cow.exists() and ("Image", iname) in images:
                    backing_file = images[("Image", iname)]["path"]
                    logger.debug(rebase, cow=cow.path, basefile=backing_file)
                    dl.append(self._real_rebase(backing_file, cow.path))
        return defer.DeferredList(dl).addCallback(check_rebase)

    def _real_rebase(self, backing_file, cow):
        args = ["rebase", "-u", "-b", backing_file, cow]
        d = utils.getProcessOutputAndValue("qemu-img", args, os.environ)
        d.addCallback(_complain_on_error)
        return d


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
        configfile.restore(factory, self.dot_project().path)

    def save(self, factory):
        configfile.save(factory, self.dot_project().path)

    def save_as(self, name, factory):
        self.save(factory)
        dst = self.filepath.sibling(name)
        tools.copyTo(self.filepath, dst)

    def files(self):
        return (fp for fp in self.filepath.walk() if fp.isfile())

    def dot_project(self):
        return self.filepath.child(".project")


def restore_last_project(factory):
    """Restore the last project if found or create a new one."""

    try:
        os.mkdir(settings.get("workspace"))
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    name = settings.get("current_project")
    try:
        return manager.open(name, factory)
    except errors.ProjectNotExistsError:
        if DEFAULT_PROJECT_RE.match(name):
             return manager.create(name, factory, open=True)
        else:
            logger.error(cannot_find_project, name=name)
            for i in itertools.count():
                name = "{0}_{1}".format(settings.DEFAULT_PROJECT, i)
                try:
                     return manager.create(name, factory, open=True)
                except errors.ProjectExistsError:
                    pass


restore_last = restore_last_project
