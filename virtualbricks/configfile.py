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
import re
import shutil
import traceback
import contextlib
import logging

from virtualbricks import tools, console, settings


if False:  # pyflakes
    _ = str


log = logging.getLogger(__name__)


@contextlib.contextmanager
def backup(original, filename):
    created = False
    # create a new backup file of the project
    if os.path.isfile(original):
        shutil.copyfile(original, filename)
        created = True
    yield
    if created:
        # remove the project backup file
        os.remove(filename)


def restore_backup(filename, fbackup):
    # check if there's a project backup to restore and if its size is
    # different from current project file
    filename_back = filename + ".back"
    if os.path.isfile(fbackup):
        log.info("I found a backup project file, I'm going to restore it!")
        try:
            os.rename(filename, filename_back)
            log.info("Saved project to %s.", filename_back)
        except OSError, e:
            if e.errno == errno.EXDEV:
                try:
                    shutil.copyfile(filename, filename_back)
                except IOError:
                    log.warning("Cannot save to backup file %s.\n%s",
                                filename_back, traceback.format_exc())
                    log.error("Cannot create a backup of the broject.")
            elif e.errno == errno.ENOENT:
                pass
            else:
                log.warning("Cannot save to backup file %s.\n%s",
                            filename_back, traceback.format_exc())
                log.error("Cannot create a backup of the broject.")
        # restore backup file
        log.info("I found a backup project file, I'm going to restore it!")

        try:
            os.rename(fbackup, filename)
            log.info("Saved project to %s.", filename_back)
            log.error(_("A backup file for the current project has been "
                        "restored.\nYou can find more informations looking in "
                        "View->Messages."))
        except OSError, e:
            if e.errno == errno.EXDEV:
                try:
                    shutil.copyfile(fbackup, filename)
                    os.remove(fbackup)
                except IOError:
                    log.warning("Cannot restore backup file %s.\n%s",
                                fbackup, traceback.format_exc())
                    log.error("Cannot restore backup of the broject.")
                finally:
                    try:
                        os.remove(fbackup)
                    except OSError:
                        pass
            elif e.errno == errno.ENOENT:
                pass
            else:
                log.warning("Cannot restore backup file %s.\n%s",
                            fbackup, traceback.format_exc())
                log.error("Cannot restore backup of the broject.")


class ConfigFile:

    def save(self, factory, obj_or_str):
        """Save the current project.

        @param obj_or_str: The filename of file object where to save the
                           project.
        @type obj_or_str: C{str} or an object that implements the file
                          interface.
        """

        if isinstance(obj_or_str, basestring):
            filename = obj_or_str
            log.debug("CONFIG DUMP on " + filename)
            fp = None
            with backup(filename, filename + "~"):
                head, tail = os.path.split(filename)
                tmpfile = os.path.join(head, "." + tail + ".sav")
                with open(tmpfile, "w") as fp:
                    self.save_to(factory, fp)
                os.rename(tmpfile, filename)
        else:
            self.save_to(factory, obj_or_str)

    def save_to(self, factory, fileobj):
        with factory.lock():
            return self.__save_to(factory, fileobj)

    def __save_to(self, factory, fileobj):
        if factory.TCP:  # XXX:
            log.warning("configfile.save called when on server mode. "
                        "This must be considerated a bug in the code.")
            return

        # Remote hosts
        for r in factory.remote_hosts:
            fileobj.write('[RemoteHost:' + r.addr[0] + ']\n')
            fileobj.write('port=' + str(r.addr[1]) + '\n')
            fileobj.write('password=' + r.password + '\n')
            fileobj.write('baseimages=' + r.baseimages + '\n')
            fileobj.write('qemupath=' + r.qemupath + '\n')
            fileobj.write('vdepath=' + r.vdepath + '\n')
            fileobj.write('bricksdirectory=' + r.bricksdirectory + '\n')
            if r.autoconnect:
                fileobj.write('autoconnect=True\n')
            else:
                fileobj.write('autoconnect=False\n')

        # Disk Images
        for img in factory.disk_images:
            fileobj.write('[DiskImage:' + img.name + ']\n')
            fileobj.write('path=' + img.path + '\n')
            if img.host is not None:
                fileobj.write('host=' + img.host.addr[0] + '\n')
            if img.readonly is not False:
                fileobj.write('readonly=True\n')

        for e in factory.events:
            fileobj.write('[' + e.get_type() + ':' + e.name + ']\n')
            for k, v in e.cfg.iteritems():
                #Special management for actions parameter
                if k == 'actions':
                    tempactions = list()
                    for action in e.cfg.actions:
                        #It's an host shell command
                        if isinstance(action, console.ShellCommand):
                            tempactions.append("addsh " + action)
                        #It's a vb shell command
                        elif isinstance(action, console.VbShellCommand):
                            tempactions.append("add " + action)
                        else:
                            log.error("Error: unmanaged action type. Will not "
                                      "be saved!")
                            continue
                    fileobj.write(k + '=' + str(tempactions) + '\n')
                #Standard management for other parameters
                else:
                    fileobj.write(k + '=' + str(v) + '\n')

        for b in factory.bricks:
            fileobj.write('[' + b.get_type() + ':' + b.name + ']\n')
            for k, v in b.cfg.iteritems():
                # VMDisk objects don't need to be saved
                types = set(['hda', 'hdb', 'hdc', 'hdd', 'fda', 'fdb',
                             'mtdblock'])
                if (b.get_type() != "Qemu" or (b.get_type() == "Qemu" and k not
                                               in types)):
                    fileobj.write(k + '=' + str(v) + '\n')

        for b in factory.bricks:
            for sk in b.socks:
                if b.get_type() == 'Qemu':
                    fileobj.write('sock|' + b.name + "|" + sk.nickname + '|' +
                            sk.model + '|' + sk.mac + '|' + str(sk.vlan) +
                            '\n')
        for b in factory.bricks:
            for pl in b.plugs:
                if b.get_type() == 'Qemu':
                    if pl.mode == 'vde':
                        fileobj.write('link|' + b.name + "|" + pl.sock.nickname
                                      + '|' + pl.model + '|' + pl.mac + '|' +
                                      str(pl.vlan) + '\n')
                    else:
                        fileobj.write('userlink|' + b.name + '||' + pl.model +
                                      '|' + pl.mac + '|' + str(pl.vlan) + '\n')
                elif (pl.sock is not None):
                    fileobj.write('link|' + b.name + "|" + pl.sock.nickname +
                                  '\n')

    def restore(self, factory, str_or_obj):
        if isinstance(str_or_obj, basestring):
            filename = str_or_obj
            restore_backup(filename, filename + "~")
            log.info("Open %s project", filename)
            with open(filename) as fp:
                self.restore_from(factory, fp)
        else:
            self.restore_from(factory, str_or_obj)

    def restore_from(self, factory, fileobj):
        with factory.lock():
            return self.__restore_from(factory, fileobj)

    def __restore_from(self, factory, fileobj):
        l = fileobj.readline()
        b = None
        while (l):
            l = re.sub(' ', '', l)
            if re.search("\A.*sock\|", l) and len(l.split("|")) >= 3:
                l.rstrip('\n')
                log.debug("************************* sock detected")
                for bb in factory.bricks:
                    if bb.name == l.split("|")[1]:
                        if (bb.get_type() == 'Qemu'):
                            sockname = l.split('|')[2]
                            model = l.split("|")[3]
                            macaddr = l.split("|")[4]
                            vlan = l.split("|")[5]
                            pl = bb.add_sock(macaddr, model)

                            pl.vlan = int(vlan)
                            log.debug("added eth%d" % pl.vlan)

            if re.search("\A.*link\|", l) and len(l.split("|")) >= 3:
                l.rstrip('\n')
                log.debug("************************* link detected")
                for bb in factory.bricks:
                    if bb.name == l.split("|")[1]:
                        if (bb.get_type() == 'Qemu'):
                            sockname = l.split('|')[2]
                            model = l.split("|")[3]
                            macaddr = l.split("|")[4]
                            vlan = l.split("|")[5]
                            this_sock = "?"
                            if l.split("|")[0] == 'userlink':
                                this_sock = '_hostonly'
                            else:
                                for s in factory.socks:
                                    if s.nickname == sockname:
                                        this_sock = s
                                        break
                            if this_sock == '?':
                                log.warning("socket '%s' not found while "
                                            "parsing following line: %s\n. "
                                            "Skipping.", sockname, l)
                                continue
                            pl = bb.add_plug(this_sock, macaddr, model)

                            pl.vlan = int(vlan)
                            log.debug("added eth%d" % pl.vlan)
                        else:
                            bb.config_socks.append(
                                l.split('|')[2].rstrip('\n'))

            if l.startswith('['):
                ntype = l.lstrip('[').split(':')[0]
                name = l.split(':')[1].rstrip(']\n')

                log.info("new %s : %s", ntype, name)
                try:
                    if ntype == 'Event':
                        factory.newevent(ntype, name)
                        component = factory.get_event_by_name(name)
                    elif ntype == 'DiskImage':
                        log.debug("Found Disk image %s" % name)
                        path = ""
                        host = None
                        readonly = False
                        l = fileobj.readline()
                        while l and not l.startswith('['):
                            k, v = l.rstrip("\n").split("=")
                            if k == 'path':
                                path = str(v)
                            elif k == 'host':
                                host = factory.get_host_by_name(str(v))
                            elif k == 'readonly' and v == 'True':
                                readonly = True
                            l = fileobj.readline()
                        if not tools.NameNotInUse(factory, name):
                            continue
                        if host is None and not os.access(path, os.R_OK):
                            continue
                        img = factory.new_disk_image(name, path,
                                                          host=host)
                        img.set_readonly(readonly)
                        continue

                    elif ntype == 'RemoteHost':
                        log.debug("Found remote host %s" % name)
                        newr = None
                        for existing in factory.remote_hosts:
                            if existing.addr[0] == name:
                                newr = existing
                                break
                        if not newr:
                            newr = console.RemoteHost(factory, name)
                            factory.remote_hosts.append(newr)
                        l = fileobj.readline()
                        while l and not l.startswith('['):
                            k, v = l.rstrip("\n").split("=")
                            if k == 'password':
                                newr.password = str(v)
                            elif k == 'autoconnect' and v == 'True':
                                newr.autoconnect = True
                            elif k == 'baseimages':
                                newr.baseimage = str(v)
                            elif k == 'vdepath':
                                newr.vdepath = str(v)
                            elif k == 'qemupath':
                                newr.qemupath = str(v)
                            elif k == 'bricksdirectory':
                                newr.bricksdirectory = str(v)
                            l = fileobj.readline()
                        if newr.autoconnect:
                            newr.connect()
                        continue
                    else:  # elif ntype == 'Brick'
                        factory.newbrick(ntype, name)
                        component = factory.get_brick_by_name(name)

                except Exception, e:
                    log.exception("Bad config line: %s", l)
                    l = fileobj.readline()
                    continue

                l = fileobj.readline()
                parameters = []
                while (component and l and not l.startswith('[') and
                       not re.search("\A.*link\|", l) and
                       not re.search("\A.*sock\|", l)):
                    if len(l.split('=')) > 1:
                        #Special management for event actions
                        if l.split('=')[0] == "actions" and ntype == 'Event':
                            actions = eval(''.join(
                                l.rstrip('\n').split('=', 1)[1:]))
                            for action in actions:
                                #Initialize one by one
                                component.configure(action.split(' '))
                            l = fileobj.readline()
                            continue
                        parameters.append(l.rstrip('\n'))
                    l = fileobj.readline()
                if parameters:
                    component.configure(parameters)

                continue
            l = fileobj.readline()

        for b in factory.bricks:
            for c in b.config_socks:
                factory.connect_to(b, c)


_config = ConfigFile()


def save(factory, filename=None):
    if filename is None:
        filename = factory.settings.get("current_project")
    _config.save(factory, filename)


def safe_save(factory, filename=None):
    try:
        save(factory, filename)
    except Exception:
        log.exception("Error while saving configuration file")


def restore(factory, filename=None):
    if filename is None:
        filename = factory.settings.get("current_project")
    factory.reset()
    _config.restore(factory, filename)


def restore_last_project(factory):
    """Restore the last project if found or create a new one."""

    try:
        os.mkdir(settings.VIRTUALBRICKS_HOME)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    try:
        os.mkdir(factory.settings.get("baseimages"))
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    try:
        restore(factory)
    except IOError as e:
        if e.errno == errno.ENOENT:
            if (factory.settings.get("current_project") !=
                    settings.DEFAULT_PROJECT):
                log.error("Cannot find last project '%s': file not found. "
                          "A new project will be created with that path.",
                          factory.settings.get("current_project"))
        else:
            raise
