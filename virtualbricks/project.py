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

from twisted.internet import utils, error, defer
from twisted.python import filepath

from virtualbricks import settings, configfile, _compat, errors, configparser


log = _compat.getLogger(__name__)
__metaclass__ = type


def _complain_on_error(result):
    out, err, code = result
    if code != 0:
        log.warning(err)
        raise error.ProcessTerminated(code)
    log.msg(err)
    return result


class Tgz:

    def create(self, pathname, files):
        log.msg("Create archive " + pathname)
        args = ["cvvfz", pathname, "-C", settings.VIRTUALBRICKS_HOME] + files
        d = utils.getProcessOutputAndValue(self.exe_c, args, os.environ)
        d.addCallback(_complain_on_error)
        return d

    def extract(self, pathname, destination):
        log.msg("Extract archive " + pathname)
        args = ["Sxvvfz", pathname, "-C", destination]
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
        try:
            project = self.archive.getmember(".project")
        except KeyError:
            pass
        else:
            return ProjectEntry.from_fileobj(self.archive.extractfile(project))


class ProjectManager:

    archive = BsdTgz()

    def __iter__(self):
        path = filepath.FilePath(settings.get("workspace"))
        return (p.basename() for p in path.children() if
                p.child(".project").isfile())

    def open(self, name, factory, create=False):
        workspace = filepath.FilePath(settings.get("workspace"))
        try:
            path = workspace.child(name)
        except filepath.InsecurePath:
            raise errors.InvalidNameError(name)
        if not path.isdir():
            if create:
                return self._create(name, Project(path), factory, open=True)
            else:
                raise errors.ProjectNotExistsError(name)
        return self._open(Project(path), factory)

    def _open(self, project, factory):
        project.filepath.child(".project").touch()
        self.close()
        global current
        current = project
        project.restore(factory)
        settings.set("current_project", project.name)
        settings.VIRTUALBRICKS_HOME = project.path
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
            if open:
                return self._open(project, factory)
            return project

    def create(self, name, factory, open=True):
        if isinstance(name, basestring):
            workspace = filepath.FilePath(settings.get("workspace"))
            try:
                path = workspace.child(name)
            except filepath.InsecurePath:
                raise errors.InvalidNameError(name)
        else:  # type(name) == filepath.FilePath
            path = name
        return self._create(name, Project(path), factory, open)

    def close(self):
        global current
        if current:
            current = None
            settings.VIRTUALBRICKS_HOME = settings.DEFAULT_HOME

    def export(self, output, files):
        return self.archive.create(output, files)

    def import_(self, prjname, pathname, factory, image_mapper, open=True):
        """Import a project in the current workspace."""

        prjentry = Archive(pathname).get_project()
        if prjentry is None:
            raise errors.InvalidArchiveError(".project file not found.")
        deferred = image_mapper(prjentry.get_images())
        deferred.addCallback(self._remap_images_cb, prjentry)
        deferred.addCallback(self._create_cb, prjname, factory)
        deferred.addCallback(self._import_cb, prjentry, pathname)
        if open:
            def restore(project):
                project.restore(factory)
                return project
            deferred.addCallback(restore)
        return deferred

    def _remap_images_cb(self, dct, prjentry):
        for header, section in prjentry.get_images():
            if header[1] in dct:
                prjentry.sections[header]["path"] = dct[header[1]]
        # return prjentry

    def _create_cb(self, _, name, factory):
        return self.create(self, name, factory, False)

    def _import_cb(self, project, prjentry, pathname):
        deferred = self.archive.extract(pathname, project.path)
        deferred.addCallback(self._dump_cb, project, prjentry)
        deferred.addCallback(self._rebase_cb, prjentry)
        return deferred

    def _dump_cb(self, _, project, prjentry):
        with project.filepath.child(".project").open("w") as fp:
            prjentry.dump(fp)
        return project

    def _rebase_cb(self, project, prjentry):
        def check_rebase(result):
            for success, status in result:
                if not success:
                    log.err(status, show_to_user=False)
                    log.msg("Rebase failed, try manually", isError=True)
            return project

        disks = prjentry.get_disks()
        images = prjentry.get_images()
        dl = []
        for vmname in disks:
            for dev, iname in disks[vmname]:
                cow = project.child("{0}_{1}.cow".format(vmname, dev))
                if cow.exists():
                    backing_file = images[iname]["path"]
                    dl.append(self._real_rebase, backing_file, cow.path)
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
        configfile.restore(factory, self.filepath.child(".project").path)

    def save(self, factory):
        configfile.save(factory, self.filepath.child(".project").path)

    def files(self):
        return (fp for fp in self.filepath.walk() if fp.isfile())


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
        log.error("Cannot find last project '" + name + "'. A new project "
                  "will be created with that name.")
        return manager.create(name, factory, open=True)
