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

"""
Windows and dialogs built in Python, converted from the Glade files in
``virtualbricks/gui/data``.

Only the classes used outside this package are exported.
"""

from .about import AboutDialog
from .attachevent import AttachEventDialog
from .captureconfig import CaptureConfigController
from .commitimagedialog import CommitImageDialog
from .confirmdialog import (
    DeleteBrickConfirmDialog,
    DeleteEventConfirmDialog,
    DeleteLinkConfirmDialog,
)
from .disklibrary import DisksLibraryWindow
from .ethernetdialog import EditEthernetDialog
from .eventconfig import EventConfigController
from .loadimagedialog import LoadImageDialog
from .logging import LoggingWindow
from .netemuconfig import NetemuConfigController
from .newbrick import NewBrickDialog
from .importdialog import ImportDialog
from .projectname import ProjectNameDialog
from .projects import ProjectsWindow, RemoveDialog
from .qemuconfig import QemuConfigController
from .renamedialog import RenameDialog
from .settings import SettingsDialog
from .switchconfig import SwitchConfigController
from .switchwrapperconfig import SwitchWrapperConfigController
from .tapconfig import TapConfigController
from .tunnelcconfig import TunnelClientConfigController
from .tunnellconfig import TunnelListenConfigController
from .usbdev import UsbDevDialog
from .virtualbricks import ProgressBar, VBGUI
from .wireconfig import WireConfigController

__all__ = [
    "AboutDialog",
    "AttachEventDialog",
    "CaptureConfigController",
    "CommitImageDialog",
    "DeleteBrickConfirmDialog",
    "DeleteEventConfirmDialog",
    "DeleteLinkConfirmDialog",
    "DisksLibraryWindow",
    "EditEthernetDialog",
    "EventConfigController",
    "ImportDialog",
    "LoadImageDialog",
    "LoggingWindow",
    "NetemuConfigController",
    "NewBrickDialog",
    "ProgressBar",
    "ProjectNameDialog",
    "ProjectsWindow",
    "QemuConfigController",
    "RemoveDialog",
    "RenameDialog",
    "SettingsDialog",
    "SwitchConfigController",
    "SwitchWrapperConfigController",
    "TapConfigController",
    "TunnelClientConfigController",
    "TunnelListenConfigController",
    "UsbDevDialog",
    "VBGUI",
    "WireConfigController",
]
