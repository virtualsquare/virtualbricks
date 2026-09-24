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

"""Files written by Virtualbricks 2.1 and older, for the migration tests."""

import os

# From the old test suite.
CONFIG1 = """
[Image:martin]
path=/vimages/vtatpa.martin.qcow2

[Qemu:sender]
hda=martin
kvm=*
name=sender
privatehda=*
tdf=*

[Wirefilter:wf]

[Switch:sw1]

link|sender|sw1_port|rtl8139|00:aa:79:71:be:61
"""

# From the old test suite: the link is of a brick that isn't there.
PROJECT = """[Image:test_qcow2.qcow2]
path = /images/test qcow2.qcow2

[Image:vtatpa.martin.qcow2]
path = /images/vtatpa.martin.qcow2

[Qemu:test]
hda = vtatpa.martin.qcow2
name = test
privatehda = *
snapshot = *
use_virtio = *

link|sender|sw1|rtl8139|00:11:22:33:44:55
"""

# From the old test suite.
HOSTONLY_CONFIG = """[Qemu:vm]
name=vm

link|vm|_hostonly|rtl8139|00:11:22:33:44:55
"""

# The oldest layout, with every key of a virtual machine.
OLD_FORMAT = """
[Project:/home/user/.virtualbricks.vbl]
id=1
[DiskImage:vtatpa.qcow2]
path=/vimages/vtatpa.qcow2
[Qemu:test1]
tdf=
loadvm=
rtc=
kernel=
pon_vbevent=
ram=64
sdl=
privatefdb=
privatefda=
noacpi=
keyboard=it
portrait=
privatehdd=
serial=
privatehda=*
usbdevlist=
privatehdc=
privatehdb=
kvmsmem=1
soundhw=
kvmsm=
boot=
vga=
kernelenbl=
smp=1
machine=
gdbport=1234
device=
basemtdblock=
snapshot=*
icon=
initrdenbl=
gdb=
basefda=
basefdb=
vnc=
basehdd=
kvm=*
basehdb=
basehdc=
basehda=vtatpa.qcow2
privatemtdblock=
cdrom=
deviceen=
kopt=
vncN=1
novga=
poff_vbevent=
name=test1
argv0=qemu-system-i386
initrd=
usbmode=
cpu=
cdromen=
[SwitchWrapper:sw1]
numports=32
pon_vbevent=
poff_vbevent=
path=/var/run/switch/sck
"""

# A Netemu with two states, and an event with an action that isn't one.
WAN = """[Netemu:wan]
#Syntax used by the old versions (only one state); added for backwards compatibility only

delay=10
bandwidthsymm=

- #Syntax used by newer versions
states=2
state0.delay=10
state1.name=congested
state1.delay=200
state1.loss=2.5
state0.probability[1]=0.2
state1.probability[0]=0.5
transperiod=250

[Switch:sw1]

[Switch:sw2]
numports=500

[Event:boot]
actions=['add sw1 on', 'addsh logger hi', "__import__('os').system('id')"]
delay=3

link|wan||rtl8139|
link|wan|sw2_port||
"""

SETTINGS = """\
[Main]
term = /usr/bin/xterm
alt-term = /usr/bin/gnome-terminal
sudo = /usr/bin/gksu
kvm = False
ksm = False
cdroms =
python = False
femaleplugs = True
erroronloop = False
systray = True
workspace = {workspace}
current_project = {current_project}
cowfmt = qcow
show_missing = True
qemupath = /usr/bin
vdepath = /usr/bin
"""


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(text)
    return path


def write_project(workspace, name, text=CONFIG1, filename=".project"):
    """Write an old project directory; return the path of its file."""

    return write(os.path.join(workspace, name, filename), text)


def write_settings(path, workspace, current_project="lab"):
    text = SETTINGS.format(
        workspace=workspace, current_project=current_project
    )
    return write(path, text)
