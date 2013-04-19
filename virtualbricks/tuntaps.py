#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
Copyright (C) 2011 Virtualbricks team

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; version 2.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""

import os

from virtualbricks.bricks import Brick
from virtualbricks.link import Plug


class Capture(Brick):

    def __init__(self, _factory, _name):
        Brick.__init__(self, _factory, _name)
        self.pid = -1
        self.cfg.name = _name
        self.command_builder = {"-s": 'sock', "*iface": "iface"}
        self.cfg.sock = ""
        self.cfg.iface = ""
        self.plugs.append(Plug(self))
        self._needsudo = True

    def restore_self_plugs(self):
        self.plugs.append(Plug(self))

    def clear_self_socks(self, sock=None):
        self.cfg.sock = ""

    def get_parameters(self):
        if (self.cfg.iface == ""):
            return _("No interface selected")
        if self.plugs[0].sock:
            return _("Interface %s plugged to %s ") % (
                self.cfg.iface, self.plugs[0].sock.brick.name)
        return _("Interface %s disconnected") % self.cfg.iface

    def prog(self):
        return self.settings.get("vdepath") + "/vde_pcapplug"

    def get_type(self):
        return 'Capture'

    def console(self):
        return None

    def on_config_changed(self):
        if (self.plugs[0].sock is not None):
            self.cfg.sock = self.plugs[0].sock.path.rstrip("[]")
        if (self.proc is not None):
            self.need_restart_to_apply_changes = True
        Brick.on_config_changed(self)

    def configured(self):
        return (self.plugs[0].sock is not None and self.cfg.iface != "")


class Tap(Brick):

    def __init__(self, _factory, _name):
        Brick.__init__(self, _factory, _name)
        self.pid = -1
        self.cfg.name = _name
        self.command_builder = {"-s": 'sock', "*tap": "name"}
        self.cfg.sock = ""
        self.plugs.append(Plug(self))
        self._needsudo = True
        self.cfg.ip = "10.0.0.1"
        self.cfg.nm = "255.255.255.0"
        self.cfg.gw = ""
        self.cfg.mode = "off"

    def restore_self_plugs(self):
        self.plugs.append(Plug(self))

    def clear_self_socks(self, sock=None):
        self.cfg.sock = ""

    def get_parameters(self):
        if self.plugs[0].sock:
            return _("plugged to %s ") % self.plugs[0].sock.brick.name

        return _("disconnected")

    def prog(self):
        return self.settings.get("vdepath") + "/vde_plug2tap"

    def get_type(self):
        return 'Tap'

    def console(self):
        return None

    def on_config_changed(self):
        if (self.plugs[0].sock is not None):
            self.cfg.sock = self.plugs[0].sock.path.rstrip("[]")
        if (self.proc is not None):
            self.need_restart_to_apply_changes = True
        Brick.on_config_changed(self)

    def configured(self):
        return (self.plugs[0].sock is not None)

    def post_poweron(self):
        self.start_related_events(on=True)
        if self.cfg.mode == 'dhcp':
            if self.needsudo():
                os.system(self.settings.get('sudo') + ' "dhclient ' + self.name
                          + '"')
            else:
                os.system('dhclient ' + self.name)
        elif self.cfg.mode == 'manual':
            if self.needsudo():
                    # XXX Ugly, can't we ioctls?
                    os.system(self.settings.get('sudo') + ' "/sbin/ifconfig ' +
                              self.name + ' ' + self.cfg.ip + ' netmask ' +
                              self.cfg.nm + '"')
                    if (len(self.cfg.gw) > 0):
                        os.system(self.settings.get('sudo') +
                                  ' "/sbin/route add default gw ' +
                                  self.cfg.gw + ' dev ' + self.name +
                                  '"')
            else:
                    os.system('/sbin/ifconfig ' + self.name + ' ' + self.cfg.ip
                              + ' netmask ' + self.cfg.nm)
                    if (len(self.cfg.gw) > 0):
                        os.system('/sbin/route add default gw ' + self.cfg.gw +
                                  ' dev ' + self.name)
        else:
            return
