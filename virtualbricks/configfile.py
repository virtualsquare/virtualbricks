# -*- test-case-name: virtualbricks.tests.test_configfile -*-
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
import os.path
import errno
import traceback
import contextlib
import six
from twisted.python import filepath
from zope.interface import implementer

from virtualbricks import interfaces, settings, _configparser, log


if False:  # pyflakes
    _ = str


__all__ = ["BrickBuilder", "ConfigFile", "EventBuilder", "ImageBuilder",
           "LinkBuilder", "SockBuilder", "log_events", "restore", "safe_save",
           "save"]


logger = log.Logger()
link_type_error = log.Event("Cannot find link of type {type}")
brick_not_found = log.Event("Cannot find brick {brick}, skipping line {line}")
sock_not_found = log.Event("Cannot find sock {sockname}, skipping line {line}")
link_added = log.Event("Added {type} to {brick}")
cannot_save_backup = log.Event("Cannot save to backup file {filename}.\n"
                               "{traceback}")
project_saved = log.Event("Saved project to {filename}.")
cannot_restore_backup = log.Event("Cannot restore backup file {filename}.\n"
                                  "{traceback}")
backup_restored = log.Event("A backup file for the current project has been "
                            "restored.\nYou can find more informations "
                            "looking in View->Messages.")
image_found = log.Event("Found Disk image {name}")
skip_image = log.Event("Skipping disk image, name '{name}' already in use")
skip_image_noa = log.Event("Cannot access image file, skipping")
config_dump = log.Event("CONFIG DUMP on {path}")
open_project = log.Event("Open project at {path}")
config_save_error = log.Event("Error while saving configuration file")

log_events = [link_type_error,
              brick_not_found,
              sock_not_found,
              link_added,
              cannot_save_backup,
              project_saved,
              cannot_restore_backup,
              backup_restored,
              image_found,
              skip_image,
              skip_image_noa,
              config_dump,
              open_project,
              config_save_error]


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
            logger.error(cannot_save_backup, filename=filename_back,
                         traceback=traceback.format_exc())
    else:
        logger.info(project_saved, filename=filename_back)
    try:
        fbackup.moveTo(filename)
    except OSError as e:
        if created:
            created = False
            filename_back.moveTo(filename)
        if e.errno == errno.ENOENT:
            pass
        else:
            logger.warn(cannot_restore_backup, filename=fbackup,
                        traceback=traceback.format_exc())
    else:
        logger.warn(backup_restored, hide_to_user=True)
    if created:
        filename_back.remove()


@contextlib.contextmanager
def freeze_notify(obj):
    obj.set_restore(True)
    try:
        yield
    finally:
        obj.set_restore(False)


@implementer(interfaces.IBuilder)
class SockBuilder:

    def load_from(self, factory, sock):
        brick = factory.get_brick_by_name(sock.owner)
        if brick:
            brick.add_sock(sock.mac, sock.model)
            logger.info(link_added, type=sock.type, brick=sock.owner)
        else:
            logger.warn(brick_not_found, brick=sock.owner, line="|".join(sock))


@implementer(interfaces.IBuilder)
class LinkBuilder:

    def load_from(self, factory, link):
        brick = factory.get_brick_by_name(link.owner)
        if brick:
            sock = factory.get_sock_by_name(link.sockname)
            if sock:
                brick.connect(sock, link.mac, link.model)
                logger.info(link_added, type=link.type, brick=link.owner)
            else:
                logger.warn(sock_not_found, sockname=link.sockname,
                            line="|".join(link))
        else:
            logger.warn(brick_not_found, brick=link.owner, line="|".join(link))


def link_builder_factory(context):
    if context.type == "sock":
        return SockBuilder()
    elif context.type == "link":
        return LinkBuilder()


interfaces.registerAdapter(link_builder_factory, _configparser.Link,
                           interfaces.IBuilder)


@implementer(interfaces.IBuilder)
class ImageBuilder:

    def __init__(self, name):
        self.name = name

    def load_from(self, factory, section):
        logger.debug(image_found, name=self.name)
        path = dict(section).get("path", "")
        if factory.is_in_use(self.name):
            logger.info(skip_image, name=self.name)
        elif not os.access(path, os.R_OK):
            logger.info(skip_image_noa)
        else:
            return factory.new_disk_image(self.name, path)


@implementer(interfaces.IBuilder)
class EventBuilder:

    def __init__(self, name):
        self.name = name

    def load_from(self, factory, section):
        event = factory.new_event(self.name)
        with freeze_notify(event):
            event.load_from(section)


@implementer(interfaces.IBuilder)
class BrickBuilder:

    def __init__(self, type, name):
        self.type = type
        self.name = name

    def load_from(self, factory, section):
        brick = factory.new_brick(self.type, self.name)
        with freeze_notify(brick):
            brick.load_from(section)


@implementer(interfaces.IBuilder)
class SectionConsumer:

    def load_from(self, factory, section):
        for n, v in section:
            pass


def brick_builder_factory(context):
    if context.type == "Image":
        return ImageBuilder(context.name)
    elif context.type == "Event":
        return EventBuilder(context.name)
    else:
        return BrickBuilder(context.type, context.name)


class CompatibleBuilder:

    incompatibles = frozenset()

    def __init__(self, type, name):
        self.type = type
        self.name = name

    def transform(self, attr, value):
        raise NotImplementedError()

    def load_from(self, factory, section):
        params = []
        for attr, value in section:
            if attr in self.incompatibles:
                t = self.trasform(attr, value)
                if t:
                    params.append(t)
            else:
                params.append((attr, value))
        return BrickBuilder(self.type, self.name).load_from(factory, params)


@implementer(interfaces.IBuilder)
class CompatibleVMBuilder(CompatibleBuilder):

    type = "Qemu"
    incompatibles = frozenset(["basehda", "basehdb", "basehdc", "basehdd",
                               "basefda", "basefdb", "basemtdblock",
                               "usbdevlist"])

    def __init__(self, name):
        self.name = name

    def trasform(self, attr, value):
        if attr.startswith("base"):
            return attr[4:], value
        return


@implementer(interfaces.IBuilder)
class CompatibleSwitchWrapperBuilder(CompatibleBuilder):

    type = "SwitchWrapper"
    incompatibles = frozenset(["numports"])

    def __init__(self, name):
        self.name = name

    def trasform(self, attr, value):
        return


def compatible_brick_builder_factory(context):
    if context.type == "Project":
        return SectionConsumer()
    elif context.type == "DiskImage":
        context.type = "Image"
    elif context.type == "Qemu":
        return CompatibleVMBuilder(context.name)
    elif context.type == "SwitchWrapper":
        return CompatibleSwitchWrapperBuilder(context.name)
    return brick_builder_factory(context)


interfaces.registerAdapter(compatible_brick_builder_factory,
                           _configparser.Section, interfaces.IBuilder)


class ConfigFile:

    def save(self, factory, str_or_obj):
        """Save the current project.

        @param obj_or_str: The filename of file object where to save the
                           project.
        @type obj_or_str: C{str} or an object that implements the file
                          interface.
        """

        if isinstance(str_or_obj, (six.string_types, filepath.FilePath)):
            if isinstance(str_or_obj, six.string_types):
                fp = filepath.FilePath(str_or_obj)
            else:
                fp = str_or_obj
            logger.debug(config_dump, path=fp.path)
            with backup(fp, fp.sibling(fp.basename() + "~")):
                tmpfile = fp.sibling("." + fp.basename() + ".sav")
                with open(tmpfile.path, "wt") as fd:
                    self.save_to(factory, fd)
                tmpfile.moveTo(fp)
        else:
            self.save_to(factory, str_or_obj)

    def save_to(self, factory, fileobj):
        for img in factory.disk_images:
            img.save_to(fileobj)

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
            plug.save_to(fileobj)

    def restore(self, factory, str_or_obj):
        if isinstance(str_or_obj, (six.string_types, filepath.FilePath)):
            if isinstance(str_or_obj, six.string_types):
                fp = filepath.FilePath(str_or_obj)
            else:
                fp = str_or_obj
            restore_backup(fp, fp.sibling(fp.basename() + "~"))
            logger.info(open_project, path=fp.path)
            with open(fp.path,"rt") as fd:
                self.restore_from(factory, fd)
        else:
            self.restore_from(factory, str_or_obj)

    def restore_from(self, factory, fileobj):
        with freeze_notify(factory):
            for item in _configparser.Parser(fileobj):
                interfaces.IBuilder(item).load_from(factory, item)


_config = ConfigFile()


def save(factory, filename=None):
    if filename is None:
        workspace = settings.get("workspace")
        project = settings.get("current_project")
        filename = os.path.join(workspace, project, ".project")
    _config.save(factory, filename)


def safe_save(factory, filename=None):
    try:
        save(factory, filename)
    except Exception:
        logger.exception(config_save_error)


def restore(factory, filename=None):
    if filename is None:
        workspace = settings.get("workspace")
        project = settings.get("current_project")
        filename = os.path.join(workspace, project, ".project")
    _config.restore(factory, filename)
