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
import sys
import re
import shutil
import traceback
import contextlib
import threading
import logging

from virtualbricks import tools
from virtualbricks.console import ShellCommand, RemoteHost,  VbShellCommand


if False:  # pyflakes
    _ = str


log = logging.getLogger(__name__)

# this is a brand new lock, different from the one in
# virtualbricks.brickfactory
synchronized = tools.synchronize_with(threading.RLock())


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
        if os.path.isfile(filename):
            os.remove(filename)


def restore_backup(filename, fbackup, factory):
    # check if there's a project backup to restore and if its size is
    # different from current project file
    if os.path.isfile(fbackup):
        log.info("I found a backup project file, I'm going to restore it!")
        if os.path.isfile(filename):
            log.info("Corrupted file moved to %s.back", filename)
            shutil.copyfile(filename, filename + ".back")
        # restore backup file
        shutil.copyfile(fbackup, filename)
        os.remove(fbackup)
        log.error(_("A backup file for the current project has been restored."
                    "\nYou can find more informations looking in "
                    "View->Messages."))


class ConfigFile:

    def __init__(self, factory):
        self.factory = factory

    @synchronized
    def save(self, obj_or_str):
        """Save the current project.

        @param obj_or_str: The filename of file object where to save the
                           project.
        @type obj_or_str: C{str} or an object that implements the file
                          interface.
        """

        if self.factory.TCP:  # XXX:
            log.warning("configfile.save called when on server mode. "
                        "This must be considerated a bug in the code.\n"
                        + "Stack trace:\n" + tools.stack_trace())
            return

        if isinstance(obj_or_str, basestring):
            filename = obj_or_str
            log.debug("CONFIG DUMP on " + filename)
            fp = None
            fbackup = os.path.join(self.factory.settings.get(
                "bricksdirectory"), ".vb_current_project.vbl")

            with backup(filename, fbackup):
                with open(filename, "w+") as fp:
                    self.save_to(fp)
        else:
            self.save_to(obj_or_str)

    @synchronized
    def save_to(self, fileobj):
        if self.factory.TCP:  # XXX:
            log.warning("configfile.save called when on server mode. "
                        "This must be considerated a bug in the code.")
            return

        # Remote hosts
        for r in self.factory.remote_hosts:
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
        for img in self.factory.disk_images:
            fileobj.write('[DiskImage:' + img.name + ']\n')
            fileobj.write('path=' + img.path + '\n')
            if img.host is not None:
                fileobj.write('host=' + img.host.addr[0] + '\n')
            if img.readonly is not False:
                fileobj.write('readonly=True\n')

        for e in self.factory.events:
            fileobj.write('[' + e.get_type() + ':' + e.name + ']\n')
            for k, v in e.cfg.iteritems():
                #Special management for actions parameter
                if k == 'actions':
                    tempactions = list()
                    for action in e.cfg.actions:
                        #It's an host shell command
                        if isinstance(action, ShellCommand):
                            tempactions.append("addsh " + action)
                        #It's a vb shell command
                        elif isinstance(action, VbShellCommand):
                            tempactions.append("add " + action)
                        else:
                            self.factory.factory.err(self.factory,
                                    "Error: unmanaged action type. "
                                    "Will not be saved!")
                            continue
                    fileobj.write(k + '=' + str(tempactions) + '\n')
                #Standard management for other parameters
                else:
                    fileobj.write(k + '=' + str(v) + '\n')

        for b in self.factory.bricks:
            fileobj.write('[' + b.get_type() + ':' + b.name + ']\n')
            for k, v in b.cfg.iteritems():
                # VMDisk objects don't need to be saved
                types = set(['hda', 'hdb', 'hdc', 'hdd', 'fda', 'fdb',
                             'mtdblock'])
                if (b.get_type() != "Qemu" or (b.get_type() == "Qemu" and k not
                                               in types)):
                    fileobj.write(k + '=' + str(v) + '\n')

        for b in self.factory.bricks:
            for sk in b.socks:
                if b.get_type() == 'Qemu':
                    fileobj.write('sock|' + b.name + "|" + sk.nickname + '|' +
                            sk.model + '|' + sk.mac + '|' + str(sk.vlan) +
                            '\n')
        for b in self.factory.bricks:
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

    def restore(self, str_or_obj):
        if isinstance(str_or_obj, basestring):
            filename = str_or_obj
            fbackup = os.path.join(self.factory.settings.get(
                "bricksdirectory"), ".vb_current_project.vbl")
            restore_backup(filename, fbackup, self.factory)
            log.info("Open %s project", filename)
            with open(filename) as fp:
                self.restore_from(fp)
        else:
            self.restore_from(str_or_obj)

    def restore_from(self, fileobj):
        l = fileobj.readline()
        b = None
        while (l):
            l = re.sub(' ', '', l)
            if re.search("\A.*sock\|", l) and len(l.split("|")) >= 3:
                l.rstrip('\n')
                self.factory.debug("************************* sock detected")
                for bb in self.factory.bricks:
                    if bb.name == l.split("|")[1]:
                        if (bb.get_type() == 'Qemu'):
                            sockname = l.split('|')[2]
                            model = l.split("|")[3]
                            macaddr = l.split("|")[4]
                            vlan = l.split("|")[5]
                            pl = bb.add_sock(macaddr, model)

                            pl.vlan = int(vlan)
                            self.factory.debug("added eth%d" % pl.vlan)

            if re.search("\A.*link\|", l) and len(l.split("|")) >= 3:
                l.rstrip('\n')
                self.factory.debug("************************* link detected")
                for bb in self.factory.bricks:
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
                                for s in self.factory.socks:
                                    if s.nickname == sockname:
                                        this_sock = s
                                        break
                            if this_sock == '?':
                                self.factory.warning("socket '" + sockname +
                                    "' not found while parsing following "
                                    "line: " + l + "\n. Skipping.")
                                continue
                            pl = bb.add_plug(this_sock, macaddr, model)

                            pl.vlan = int(vlan)
                            self.factory.debug("added eth%d" % pl.vlan)
                        else:
                            bb.config_socks.append(
                                l.split('|')[2].rstrip('\n'))

            if l.startswith('['):
                ntype = l.lstrip('[').split(':')[0]
                name = l.split(':')[1].rstrip(']\n')

                self.factory.info("new %s : %s", ntype, name)
                try:
                    if ntype == 'Event':
                        self.factory.newevent(ntype, name)
                        component = self.factory.geteventbyname(name)
                    elif ntype == 'DiskImage':
                        self.factory.debug("Found Disk image %s" % name)
                        path = ""
                        host = None
                        readonly = False
                        l = fileobj.readline()
                        while l and not l.startswith('['):
                            k, v = l.rstrip("\n").split("=")
                            if k == 'path':
                                path = str(v)
                            elif k == 'host':
                                host = self.factory.get_host_by_name(str(v))
                            elif k == 'readonly' and v == 'True':
                                readonly = True
                            l = fileobj.readline()
                        if not tools.NameNotInUse(self.factory, name):
                            continue
                        if host is None and not os.access(path, os.R_OK):
                            continue
                        img = self.factory.new_disk_image(name, path,
                                                          host=host)
                        img.set_readonly(readonly)
                        continue

                    elif ntype == 'RemoteHost':
                        self.factory.debug("Found remote host %s" % name)
                        newr = None
                        for existing in self.factory.remote_hosts:
                            if existing.addr[0] == name:
                                newr = existing
                                break
                        if not newr:
                            newr = RemoteHost(self.factory, name)
                            self.factory.remote_hosts.append(newr)
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
                        self.factory.newbrick(ntype, name)
                        component = self.factory.getbrickbyname(name)

                except Exception, err:
                    self.factory.exception("--------- Bad config line:" +
                                            str(err))
                    traceback.print_exc(file=sys.stdout)

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

        for b in self.factory.bricks:
            for c in b.config_socks:
                self.factory.connect_to(b, c)
