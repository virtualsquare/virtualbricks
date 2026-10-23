# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2026 Virtualbricks team

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
The trash of the desktop, through Gio.

The application gives it to the workspace, ``projects.trasher``, which can't
import Gio itself: it has to work without a desktop.
"""

from gi.repository import Gio, GLib

from virtualbricks import errors


class DesktopTrash:
    """Move files to the trash of the user's desktop."""

    def can_trash(self, path: str) -> bool:
        try:
            info = Gio.File.new_for_path(path).query_info(
                Gio.FILE_ATTRIBUTE_ACCESS_CAN_TRASH,
                Gio.FileQueryInfoFlags.NONE,
                None,
            )
        except GLib.Error:
            return False
        return info.get_attribute_boolean(Gio.FILE_ATTRIBUTE_ACCESS_CAN_TRASH)

    def trash(self, path: str) -> None:
        """Move path to the trash; TrashNotSupportedError if it has none."""

        try:
            Gio.File.new_for_path(path).trash(None)
        except GLib.Error as exc:
            not_supported = Gio.IOErrorEnum.NOT_SUPPORTED
            if exc.matches(Gio.io_error_quark(), not_supported):
                raise errors.TrashNotSupportedError(path) from None
            raise OSError(exc.message) from None
