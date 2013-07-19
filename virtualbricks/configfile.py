# -*- test-case-name: virtualbricks.tests.test_configfile -*-
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
import os.path
import errno
import traceback
import contextlib

from twisted.python import filepath

from virtualbricks import _compat, settings, configparser


if False:  # pyflakes
    _ = str


log = _compat.getLogger(__name__)
link_type_error = log.declare("Cannot find link of type {link.type}",
                              log.LogLevel.warn)
brick_not_found = log.declare("Cannot find brick {brick}, skipping line "
                              "{line}", log.LogLevel.warn)
sock_not_found = log.declare("Cannot find sock {sockname}, skipping line "
                             "{line}", log.LogLevel.warn)
link_added = log.declare("Added {type} to {brick}", log.LogLevel.info)


@contextlib.contextmanager
def backup(original, fbackup):
    try:
        original.copyTo(fbackup)
    except OSError as e:
        if e.errno == errno.ENOENT:
            yield
    else:
        yield
        fbackup.remove()


def restore_backup(filename, fbackup):
    filename_back = filename.sibling(filename.basename() + ".back")
    created = False
    try:
        filename.moveTo(filename_back)
        created = True
    except OSError as e:
        if e.errno == errno.ENOENT:
            pass
        else:
            log.warning("Cannot save to backup file %s.\n%s",
                        filename_back, traceback.format_exc())
            log.error("Cannot create a backup of the broject.")
    else:
        log.info("Saved project to %s.", filename_back)
    try:
        fbackup.moveTo(filename)
    except OSError, e:
        if created:
            created = False
            filename_back.moveTo(filename)
        if e.errno == errno.ENOENT:
            pass
        else:
            log.warning("Cannot restore backup file %s.\n%s",
                        fbackup, traceback.format_exc())
            log.error("Cannot restore backup of the broject.")
    else:
        log.error(_("A backup file for the current project has been "
                    "restored.\nYou can find more informations looking in "
                    "View->Messages."))
    if created:
        filename_back.remove()


class ImageBuilder:

    def __init__(self, factory, name):
        self.factory = factory
        self.name = name

    def load_from(self, section):
        log.debug("Found Disk image %s" % self.name)
        path = dict(section).get("path", "")
        if self.factory.is_in_use(self.name):
            log.info("Skipping disk image, name %s already in "
                     "use", self.name)
        elif not os.access(path, os.R_OK):
            log.info("Cannot access image file, skipping")
        else:
            return self.factory.new_disk_image(self.name, path)


class SockBuilder:

    def __init__(self, factory):
        self.factory = factory

    def load_from(self, sock):
        brick = self.factory.get_brick_by_name(sock.owner)
        if brick:
            brick.add_sock(sock.mac, sock.model)
            link_added(type=sock.type, brick=sock.owner)
        else:
            brick_not_found(brick=sock.owner, line="|".join(sock))


class LinkBuilder:

    def __init__(self, factory):
        self.factory = factory

    def load_from(self, link):
        brick = self.factory.get_brick_by_name(link.owner)
        if brick:
            sock = self.factory.get_sock_by_name(link.sockname)
            if sock:
                brick.add_plug(sock, link.mac, link.model)
                link_added(type=link.type, brick=link.owner)
            else:
                sock_not_found(sockname=link.sockname, line="|".join(link))
        else:
            brick_not_found(brick=link.owner, line="|".join(link))


class ConfigFile:

    def save(self, factory, str_or_obj):
        """Save the current project.

        @param obj_or_str: The filename of file object where to save the
                           project.
        @type obj_or_str: C{str} or an object that implements the file
                          interface.
        """

        if isinstance(str_or_obj, (basestring, filepath.FilePath)):
            if isinstance(str_or_obj, basestring):
                fp = filepath.FilePath(str_or_obj)
            log.debug("CONFIG DUMP on " + fp.path)
            with backup(fp, fp.sibling(fp.basename() + "~")):
                tmpfile = fp.sibling("." + fp.basename() + ".sav")
                with tmpfile.open("w") as fd:
                    self.save_to(factory, fd)
                tmpfile.moveTo(fp)
        else:
            self.save_to(factory, str_or_obj)

    def save_to(self, factory, fileobj):
        for img in factory.disk_images:
            fileobj.write('[Image:' + img.name + ']\n')
            fileobj.write('path=' + img.path + '\n')
            fileobj.write("\n")

        for event in factory.events:
            event.save_to(fileobj)

        socks = []
        plugs = []
        for brick in iter(factory.bricks):
            brick.save_to(fileobj)
            if brick.get_type() == "Qemu":
                socks.extend(brick.socks)
            plugs.extend(brick.plugs)

        for sock in socks:
            t = "sock|{s.brick.name}|{s.nickname}|{s.model}|{s.mac}\n"
            fileobj.write(t.format(s=sock))

        for plug in plugs:
            if plug.brick.get_type() == 'Qemu':
                if plug.configured():
                    t = ("link|{p.brick.name}|{p.sock.nickname}|{p.model}|"
                         "{p.mac}\n")
                else:
                    t = "link|{p.brick.name}||{p.model}|{p.mac}\n"
                fileobj.write(t.format(p=plug))
            elif plug.sock is not None:
                t = "link|{p.brick.name}|{p.sock.nickname}\n"
                fileobj.write(t.format(p=plug))

    def restore(self, factory, str_or_obj):
        if isinstance(str_or_obj, (basestring, filepath.FilePath)):
            if isinstance(str_or_obj, basestring):
                fp = filepath.FilePath(str_or_obj)
            restore_backup(fp, fp.sibling(fp.basename() + "~"))
            log.info("Open %s project", fp.path)
            with fp.open() as fd:
                self.restore_from(factory, fd)
        else:
            self.restore_from(factory, str_or_obj)

    def restore_from(self, factory, fileobj):
        for item in configparser.Parser(fileobj):
            # if isinstance(item, tuple):  # links
            #     brick = factory.get_brick_by_name(item.owner)
            #     if item.type == "sock":
            #         brick.add_sock(item.mac, item.model)
            #     elif item.type == "link":
            #         sock = factory.get_sock_by_name(item.sockname)
            #         brick.add_plug(sock, item.mac, item.model)
            if isinstance(item, tuple):  # links
                self.build_link(factory, item.type).load_from(item)
            else:
                self.build_type(factory, item.type, item.name).load_from(item)

    def build_link(self, factory, type):
        if type == "sock":
            return SockBuilder(factory)
        elif type == "link":
            return LinkBuilder(factory)
        else:
            link_type_error(type=type)

    def build_type(self, factory, type, name):
        if type == "Image":
            return ImageBuilder(factory, name)
        elif type == "Event":
            return factory.new_event(name)
        else:
            return factory.new_brick(type, name)


_config = ConfigFile()


def save(factory, filename=None):
    if filename is None:
        filename = os.path.join(settings.get("workspace"),
                                settings.get("current_project"), ".project")
    _config.save(factory, filename)


def safe_save(factory, filename=None):
    try:
        save(factory, filename)
    except Exception:
        log.exception("Error while saving configuration file")


def restore(factory, filename=None):
    if filename is None:
        filename = os.path.join(settings.get("workspace"),
                                settings.get("current_project"), ".project")
    _config.restore(factory, filename)
