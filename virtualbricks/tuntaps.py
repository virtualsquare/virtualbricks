# -*- test-case-name: virtualbricks.tests.test_tuntaps -*-
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

from virtualbricks import bricks, link


if False:  # pyflakes
    _ = str


class CaptureConfig(bricks.Config):

    parameters = {"name": bricks.String(""),
                  "sock": bricks.String(""),
                  "iface": bricks.String("")}


class Capture(bricks.Brick):

    type = "Capture"
    _needsudo = True
    config_factory = CaptureConfig
    command_builder = {"-s": 'sock',
                       "*iface": "iface"}

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.config["name"] = name
        self.plugs.append(link.Plug(self))

    def restore_self_plugs(self):
        self.plugs.append(link.Plug(self))

    def clear_self_socks(self, sock=None):
        self.config["sock"] = ""

    def get_parameters(self):
        if self.config["iface"] == "":
            return _("No interface selected")
        if self.plugs[0].sock:
            return _("Interface %s plugged to %s ") % (
                self.config["iface"], self.plugs[0].sock.brick.name)
        return _("Interface %s disconnected") % self.config["iface"]

    def prog(self):
        return self.settings.get("vdepath") + "/vde_pcapplug"

    def console(self):
        return None

    def on_config_changed(self):
        if self.plugs[0].sock is not None:
            self.config["sock"] = self.plugs[0].sock.path.rstrip("[]")
        bricks.Brick.on_config_changed(self)

    def configured(self):
        return self.plugs[0].sock is not None and self.config["iface"]


class Tap(bricks.Brick):

    type = "Tap"
    _needsudo = True
    command_builder = {"-s": 'sock', "*tap": "name"}

    class config_factory(bricks.Config):

        parameters = {"name": bricks.String(""),
                      "sock": bricks.String(""),
                      "ip": bricks.String("10.0.0.1"),
                      "nm": bricks.String("255.255.255.0"),
                      "gw": bricks.String(""),
                      "mode": bricks.String("off")}

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.config["name"] = name
        self.plugs.append(link.Plug(self))

    def restore_self_plugs(self):
        self.plugs.append(link.Plug(self))

    def clear_self_socks(self, sock=None):
        self.config["sock"] = ""

    def get_parameters(self):
        if self.plugs[0].sock:
            return _("plugged to %s ") % self.plugs[0].sock.brick.name

        return _("disconnected")

    def prog(self):
        return self.settings.get("vdepath") + "/vde_plug2tap"

    def console(self):
        return None

    def on_config_changed(self):
        if self.plugs[0].sock is not None:
            self.config["sock"] = self.plugs[0].sock.path.rstrip("[]")
        bricks.Brick.on_config_changed(self)

    def configured(self):
        return self.plugs[0].sock is not None

    def post_poweron(self):
        # XXX: fixme
        self.start_related_events(on=True)
        if self.config["mode"] == 'dhcp':
            if self.needsudo():
                os.system(self.settings.get('sudo') + ' "dhclient ' + self.name
                          + '"')
            else:
                os.system('dhclient ' + self.name)
        elif self.config["mode"] == 'manual':
            if self.needsudo():
                    # XXX Ugly, can't we ioctls?
                    os.system(self.settings.get('sudo') + ' "/sbin/ifconfig ' +
                              self.name + ' ' + self.config["ip"] + ' netmask ' +
                              self.config["nm"] + '"')
                    if (len(self.config["gw"]) > 0):
                        os.system(self.settings.get('sudo') +
                                  ' "/sbin/route add default gw ' +
                                  self.config["gw"] + ' dev ' + self.name +
                                  '"')
            else:
                    os.system('/sbin/ifconfig ' + self.name + ' ' +
                              self.config["ip"] + ' netmask ' +
                              self.config["nm"])
                    if (len(self.config["gw"]) > 0):
                        os.system('/sbin/route add default gw ' +
                                  self.config["gw"] + ' dev ' + self.name)
        else:
            return
