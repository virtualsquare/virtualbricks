# -*- test-case-name: virtualbricks.tests.test_tuntaps -*-
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
from collections import OrderedDict as odict

from virtualbricks import bricks, link, settings
from virtualbricks._spawn import abspath_vde

if False:  # pyflakes
    _ = str


class PrivilegedBrick(bricks.Brick):

    def needsudo(self):
        return os.geteuid() != 0
class CaptureConfig(bricks.Config):

    parameters = {"iface": bricks.String("")}


class Capture(PrivilegedBrick):

    type = "Capture"
    config_factory = CaptureConfig

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.plugs.append(link.Plug(self))
        self.command_builder = odict((("-s", self.sock_path),
                                      ("*iface", "iface")))

    def sock_path(self):
        if self.plugs[0].sock:
            return self.plugs[0].sock.path.rstrip("[]")
        return ""

    def get_parameters(self):
        if self.config["iface"] == "":
            return _("No interface selected")
        if self.plugs[0].sock:
            return _("Interface %s plugged to %s ") % (
                self.config["iface"], self.plugs[0].sock.brick.name)
        return _("Interface %s disconnected") % self.config["iface"]

    def prog(self):
        return abspath_vde('vde_pcapplug')

    def open_console(self):
        pass

    def configured(self):
        return self.plugs[0].sock and self.config["iface"]


class TapConfig(bricks.Config):

    parameters = {"ip": bricks.String("10.0.0.1"),
                  "nm": bricks.String("255.255.255.0"),
                  "gw": bricks.String(""),
                  "mode": bricks.String("off")}


class Tap(PrivilegedBrick):

    type = "Tap"
    config_factory = TapConfig

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.plugs.append(link.Plug(self))
        self.command_builder["-s"] = self.sock_path
        self.command_builder["*tap"] = self.get_name

    def sock_path(self):
        if self.plugs[0].sock:
            return self.plugs[0].sock.path.rstrip("[]")
        return ""

    def get_parameters(self):
        if self.configured():
            return _("plugged to %s ") % self.plugs[0].sock.brick.name
        return _("disconnected")

    def prog(self):
        return abspath_vde('vde_plug2tap')

    def open_console(self):
        pass

    def configured(self):
        return bool(self.plugs[0].sock)

    def post_poweron(self):
        # XXX: fixme
        self.start_related_events(on=True)
        if self.config["mode"] == 'dhcp':
            if self.needsudo():
                os.system(settings.get('sudo') + ' "dhclient ' + self.name
                          + '"')
            else:
                os.system('dhclient ' + self.name)
        elif self.config["mode"] == 'manual':
            if self.needsudo():
                    # XXX Ugly, can't we ioctls?
                    os.system(settings.get('sudo') + ' "/sbin/ifconfig ' +
                              self.name + ' ' + self.config["ip"] + ' netmask ' +
                              self.config["nm"] + '"')
                    if (len(self.config["gw"]) > 0):
                        os.system(settings.get('sudo') +
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
