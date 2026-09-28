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
The configuration panels of the bricks, shown in the Bricks tab of the main
window: one module for each kind of brick, and the parts of the panel of a
virtual machine, its disks and the picker of their images.

The panels on drafts, of :mod:`.panel`, are in ``PANELS``, by the type of
their brick; ``new_panel()`` makes one on a new draft of its brick. The others
are still adapters of ``IConfigController``, until they move.

Only the names that code outside this package imports from it are exported;
the tests import the others from their modules.
"""

from .captureconfig import CapturePanel
from .netemuconfig import NetemuPanel
from .qemuconfig import QemuConfigController
from .switchconfig import SwitchPanel
from .switchwrapperconfig import SwitchWrapperPanel
from .tapconfig import TapPanel
from .tunnelcconfig import TunnelConnectPanel
from .tunnellconfig import TunnelListenPanel
from .wireconfig import WirePanel

__all__ = [
    "PANELS",
    "QemuConfigController",
    "new_panel",
]

# The panels on drafts, by the type of their brick.
PANELS = {
    "Capture": CapturePanel,
    "Netemu": NetemuPanel,
    "Switch": SwitchPanel,
    "SwitchWrapper": SwitchWrapperPanel,
    "TunnelConnect": TunnelConnectPanel,
    "Tap": TapPanel,
    "TunnelListen": TunnelListenPanel,
    "Wire": WirePanel,
}


def new_panel(brick, gui=None):
    """The panel of brick on a new draft, or None if it has none yet."""

    panel = PANELS.get(brick.get_type())
    if panel is None:
        return None
    return panel(brick.draft_factory(brick), gui)
