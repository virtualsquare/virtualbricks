"""
Programmatic replacement for ``virtualbricks/gui/data/about.ui``.

The UI is the Virtualbricks "About" dialog: a ``Gtk.AboutDialog`` with the
program name, version, copyright, license, website, authors, artists and logo.
"""

from typing import List

import gi

from virtualbricks.gui.windows.base import _Dialog

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gtk

from virtualbricks import __version__
from virtualbricks.gui import graphics
from virtualbricks.i18n import _

TRANSLATION_DOMAIN = "virtualbricks"


COPYRIGHT = """\
Copyright © 2019 Virtualbricks team
VDE - Copyright © 2003-2011 Renzo Davoli.
QEMU - Copyright © 2005-2011 Fabrice Bellard.
QEMU is a trademark of Fabrice Bellard.
Icons by Fabio Viola, Licensed under CC BY-NC-SA 3.0. See COPYING for more details.
Debian package created and maintained by Francesco Namuri (franam@debian.org)."""

COMMENTS = "Virtualbricks is a GNU/Linux desktop gui for Qemu and VDE."

WEBSITE = "https://github.com/virtualsquare/virtualbricks"

LICENSE = """\
This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License along
with this program; if not, write to the Free Software Foundation, Inc.,
51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA."""

# Glade stores these as a single newline separated string; Gtk.Builder splits
# them on "\n" to build the string array the properties expect.
AUTHORS: List[str] = [
    "Daniele Lacamera",
    "Francesco Apollonio",
    "Simone Abbati",
    "Pierre-Louis Bonicoli",
    "Rainer Haage",
    "Fabio Viola",
    "Marco Giusti <marco.giusti@posteo.de>",
    "Carlo Caini",
    "Alessandro Paoletti",
    "Danilo Belvedere",
    "Nicola Tentoni",
]

ARTISTS: List[str] = """\
All the icons are created by Fabio Viola
and released under the terms of
CC BY-NC-SA v.3
(http://creativecommons.org/licenses/by-nc-sa/3.0/)


Icons 'Connect' and 'Disconnect' are fairly
based on 'plug' icon created by cablout
(http://openclipart.org/user-detail/caboulot)
(Public Domain)

Icons 'Wire' and 'Wirefilter' are fairly
based on 'tango network wired' icon
created by warszawianka
(http://openclipart.org/user-detail/warszawianka)
(Public Domain)

Icon 'Event' is fairly based on 'tango
appointment new' icon created by
warszawianka
(http://openclipart.org/user-detail/warszawianka)
(Public Domain)
""".split("\n")

# Same file referenced by the Glade ``logo`` property; Gtk.Builder resolved it
# relative to the .ui file, i.e. virtualbricks/gui/data/virtualbricks.png.
LOGO_RESOURCE = "virtualbricks.png"


class AboutDialog(_Dialog):

    AboutDialog: Gtk.AboutDialog

    def __init__(self) -> None:
        self.build_ui()

    def build_ui(self) -> None:
        dialog = self.AboutDialog = Gtk.AboutDialog()
        dialog.set_can_focus(False)
        dialog.set_modal(True)
        dialog.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        dialog.set_program_name("Virtualbricks")
        dialog.set_version(__version__)
        dialog.set_copyright(_(COPYRIGHT))
        dialog.set_comments(_(COMMENTS))
        dialog.set_website(WEBSITE)
        dialog.set_license(_(LICENSE))
        dialog.set_authors(AUTHORS)
        dialog.set_artists(ARTISTS)

        logo_filename = graphics.get_image(LOGO_RESOURCE)
        if logo_filename is not None:
            dialog.set_logo(GdkPixbuf.Pixbuf.new_from_file(logo_filename))

        # TODO: Glade placeholder for the titlebar slot, nothing to create.

        # Internal child "vbox" (created by Gtk.Dialog itself).
        vbox = dialog.get_content_area()
        vbox.set_can_focus(False)
        vbox.set_orientation(Gtk.Orientation.VERTICAL)
        vbox.set_spacing(2)
        # Internal child "action_area": Glade sets can_focus=False,
        # layout_style=END, expand=False, fill=False, position=0. These are
        # Gtk.Dialog defaults and Gtk.Dialog.get_action_area() is deprecated,
        # so it is left untouched.
        # TODO: Glade placeholders in the action area and the vbox, nothing
        # to create.

        dialog.connect("response", self.on_AboutDialog_response)

    def get_root_widget(self) -> Gtk.AboutDialog:
        return self.AboutDialog

    def show(self, parent=None):
        if parent is not None:
            self.get_root_widget().set_transient_for(parent)
        self.get_root_widget().show()

    def on_AboutDialog_response(
        self, dialog: Gtk.AboutDialog, response_id: int, data=None
    ) -> None:
        dialog.destroy()
