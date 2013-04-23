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

"""
Utility module to work with gtkbuilder.

When a new dialog is created a new glade project must be created. All the UI
definitions must live inside the `share/` package source directory and a new
entry must be added to setup.py's data_file.

Then a new class should subclass the `Dialog` class and define at least the
`resource` class attribute with the name of the file in `share/` directory. If
the `name` class attribute is not defined, the name of the new class should be
same of the main window in the ui definition.

Here the about dialog example.

1. First of all the UI definition. The file is `about.ui` in the `share/`
    directory. In this case the main widget/window is called "AboutDialog".

2. Class definition. In `virtualbricks.gui.dialogs` the class `AboutDialog` is
    defined. The `resource` class attribute points to the UI definition and the
    `name` class attribute is not defined because the class name's match the
    main window's name.

3. In the `__init__` all resources are initialized. It is much better to set
    here all the resource and not in setup.py because is easier to switch to
    another tools in the future. For example `pkgutil` in the standard library
    offer the `get_data()` function.

4. Add an entry in the setup.py, in this case:

    setup(...
        data_files=[...
            ("share/virtualbricks", ["share/about.ui"]),
            ...],
        ...
        )

5. Use the new code:

    dialogs.AboutDialog().run()

Note. Everytime a new dialog is created, a new gtk.Builder object is created,
this means that more than one dialogs of the same kind can live together. If
this is not desired is responsability of the programmer to do not (modal
dialogs, etc.). This means also that dialogs should be destroied. I'm not
really sure about this because when thare are no more references to the dialog
instance and the gc collect the object, the builder instance is collected too
and is the builder the only one that has an instance to the gtk.Dialog.

So, do not store a reference of the main widget or of the Dialog instance.

    # don't do this
    about = dialogs.AboutDialog()
    about.run()
    about.window # here the window is destroied
    # neither this
    awidget = dialogs.AboutDialog().get_object("awidget")


A note about Glade and the transition to gtk.Builder.

Glade supports gtk.builder but this must be specified in the project
paramentes. It is also possible to select the widget compatibility. The current
version of gtk in debian stable (squeeze) is 2.20, and 2.24 in debian testing
(wheeze) the, in a near future, new debian stable.

Exists a tools that help with the conversion, gtk-builder-convert, but its
results are not always excellent. A window at time conversion is highly
advised and possible with gtk-builder-convert.
"""

import os
import sys
import logging

import gtk

from virtualbricks import version


log = logging.getLogger(__name__)


def get_pixbuf(resource):
    filename = os.path.join(sys.prefix, "share", "pixmaps", resource)
    return gtk.gdk.pixbuf_new_from_file(filename)


def get_data(resource):
    log.debug("Loading resource from %s", resource)
    filename = os.path.join(sys.prefix, "share", "virtualbricks", resource)
    with open(filename) as fp:
        return fp.read()


class Base(object):
    """Base class to work with gtkbuilder files.

    @ivar domain: Translation domain.
    @type domain: C{str} or C{None}

    @ivar resource: A gtkbuilder UI definition resource that a data finder can
            load.
    @type resource: C{str}

    @ivar name: The name of the main widget that must be load.
    @type name: C{str} or C{None}. If C{None} the name of the class is used.
    """

    domain = 'virtualbricks'
    resource = None
    name = None

    def __init__(self):
        self.builder = builder = gtk.Builder()
        builder.set_translation_domain(self.domain)
        builder.add_from_string(get_data(self.resource))
        name = self.get_name()
        self.widget = builder.get_object(name)
        builder.connect_signals(self)

    def get_object(self, name):
        return self.builder.get_object(name)

    def get_name(self):
        if self.name:
            return self.name
        return self.__class__.__name__

    def show(self):
        self.widget.show()


class Dialog(Base):
    """Base class for all dialogs."""

    @property
    def window(self):
        return self.widget

    def show_all(self):
        self.widget.show_all()

    def run(self):
        self.widget.run()
        self.widget.destroy()


