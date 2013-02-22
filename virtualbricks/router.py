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

from virtualbricks.bricks import Brick


class Router(Brick):

    def __init__(self, _factory, _name):
        Brick.__init__(self, _factory, _name)
        self.pid = -1
        self.cfg.name = _name
        self.command_builder = {
                    "-M": self.console,
                    "-c": "configfile",
                    }
        self.on_config_changed()

    def get_parameters(self):
        return "Work in progress..."

    def prog(self):
        return self.settings.get("vdepath") + "/vde_router"

    def get_type(self):
        return 'Router'

    def on_config_changed(self):
        Brick.on_config_changed(self)

    def configured(self):
        return True
