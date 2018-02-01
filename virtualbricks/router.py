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

from virtualbricks import bricks
from virtualbricks._spawn import abspath_vde


class Router(bricks.Brick):

    type = "Router"

    class config_factory(bricks.Config):

        parameters = {"name": bricks.String("")}

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.config["name"] = name
        self.command_builder = {"-M": self.console, "-c": "configfile"}

    def get_parameters(self):
        return "Work in progress..."

    def prog(self):
        return abspath_vde('vde_router')

    def configured(self):
        return True
