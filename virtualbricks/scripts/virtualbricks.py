# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2019 Virtualbricks team

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


import sys


def make_application(config):
    from virtualbricks.gui import gui

    return gui.Application(config)


def make_plain_application(config):
    """The application without the windows: no GTK is loaded."""

    from virtualbricks import brickfactory

    return brickfactory.Application(config)


def run():
    from virtualbricks import app

    config = app.Options()
    app.parse_options(config)
    if config["command"]:
        # no lock, no reactor, no GTK: the Virtualbricks that runs has them
        from virtualbricks import i18n
        from virtualbricks.console import client

        i18n.install()
        sys.exit(client.main(config["words"], config["socket"]))
    if config["no-gui"]:
        factory = make_plain_application
    else:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        from twisted.internet import gtk3reactor

        gtk3reactor.install()
        factory = make_application
    app.run_app(app.LockedApplication(factory), config)
