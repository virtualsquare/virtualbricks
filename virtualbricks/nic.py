# -*- test-case-name: virtualbricks.tests.test_nic -*-
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
The MAC addresses of the network cards of the virtual machines.

A MAC address is six octets, written "52:54:00:12:34:56". The two lowest
bits of the first octet say what kind of address it is:

- bit 0, I/G: 0 for the address of one card, unicast; 1 for a group,
  multicast. A card must have a unicast address.
- bit 1, U/L: 0 for a universally administered address, whose first three
  octets are an OUI that the IEEE assigned to a vendor; 1 for a locally
  administered address, which no vendor owns and anyone can pick.

A virtual card has no vendor, so its address should be locally
administered. Two ways of choosing one are common:

- Linux gives an interface that has no address of its own, such as a veth
  or a tap device, the address of ``eth_random_addr()``: six random octets,
  with the multicast bit cleared and the local bit set. That leaves 46
  random bits.
- QEMU gives a card started without ``mac=`` the address
  52:54:00:12:34:56, the last octet increased for each card, and libvirt
  picks 52:54:00 followed by three random octets. 0x52 has the local bit
  set, and the prefix tells a virtual card at a glance, but it leaves 24
  random bits, and every QEMU and libvirt machine shares the prefix,
  possibly on the same bridge.

Virtualbricks used to pick 00:aa followed by four random octets: a
universally administered address, in a block where the IEEE has assigned
OUIs to Intel (00:aa:00 to 00:aa:02), Cisco and others. It now picks the
addresses as Linux does: every address is a valid unicast one that no
vendor owns, and with 46 random bits a thousand cards on the same network
share an address about once in 140 million times. The addresses already in
a project are kept, and the user can still type any address.
"""

import os
import re

# Six octets, in hexadecimal, separated by colons.
MAC_PATTERN = r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}"


def random_mac() -> str:
    """
    Return a random unicast MAC address, locally administered.

    The same as Linux's eth_random_addr(): six random octets, then the
    multicast bit of the first octet is cleared and the local bit set.
    """

    octets = bytearray(os.urandom(6))
    octets[0] = octets[0] & 0xFE | 0x02
    return ":".join(f"{octet:02x}" for octet in octets)


def is_valid_mac(mac: str) -> bool:
    """Whether mac is written as a MAC address: six octets, in hexadecimal."""

    return re.fullmatch(MAC_PATTERN, mac) is not None
