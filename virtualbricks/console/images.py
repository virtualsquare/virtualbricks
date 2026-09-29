# -*- test-case-name: virtualbricks.tests.console.test_images -*-
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

"""The commands of the disk images: image list, add, show, set, rename, delete."""

from __future__ import annotations

import os

from virtualbricks.bricks.virtualmachine import is_virtualmachine
from virtualbricks.console.command import (
    Arg,
    CommandError,
    Named,
    Pair,
    command,
)
from virtualbricks.console.output import table
from virtualbricks.i18n import N_, _

IMAGE = Named(
    lambda factory, name: factory.get_image_by_name(name),
    lambda factory: [image.name for image in factory.iter_disk_images()],
    N_("No image named {name}"),
)


def _users(factory, image) -> list[str]:
    """The disks that use image: vm1 hda."""

    return [
        f"{brick.name} {disk.device}"
        for brick in factory.bricks
        if is_virtualmachine(brick)
        for disk in brick.disks()
        if disk.image is image
    ]


def _description(pairs):
    text = None
    for key, value in pairs:
        if key != "description":
            raise CommandError(
                _("An image has no key {key}: only description").format(
                    key=key
                )
            )
        text = value
    return text


@command("image", "list", help=N_("The disk images and their users"))
def list_(context):
    factory = context.factory
    images = list(factory.iter_disk_images())
    if not images:
        return [_("No images")]
    rows = [
        (image.name, image.path, ", ".join(_users(factory, image)))
        for image in images
    ]
    return table(rows, [_("NAME"), _("FILE"), _("USED BY")])


@command(
    "image",
    "add",
    Arg("NAME"),
    Arg("PATH"),
    Arg("KEY=VALUE", Pair(), many=True, optional=True),
    help=N_("Add an image file to the project; description= says what it is"),
    example='image add debian ~/images/debian.qcow2 description="Debian 13"',
)
def add(context, name, path, key_value):
    factory = context.factory
    description = _description(key_value) or ""
    name = factory.normalize_name(name)
    path = context.path(path)
    if not os.path.isfile(path):
        raise CommandError(_("No file {path}").format(path=path))
    return [factory.new_disk_image(name, path, description).name]


@command(
    "image",
    "show",
    Arg("NAME", IMAGE),
    help=N_("An image's file, description and users"),
)
def show(context, name):
    image = name
    users = _users(context.factory, image)
    lines = [image.name, image.path]
    if image.description:
        lines.append(image.description)
    lines.append(
        _("used by {disks}").format(disks=", ".join(users))
        if users
        else _("used by no machine")
    )
    return lines


@command(
    "image",
    "set",
    Arg("NAME", IMAGE),
    Arg("KEY=VALUE", Pair(), many=True),
    help=N_("Change the description of an image"),
)
def set_(context, name, key_value):
    name.set_description(_description(key_value))


@command(
    "image",
    "rename",
    Arg("NAME", IMAGE),
    Arg("NEW"),
    help=N_("Rename an image, in the disks that use it too"),
)
def rename(context, name, new):
    context.factory.rename(name, new)
    return [name.name] if name.name != new else []


@command(
    "image",
    "delete",
    Arg("NAME", IMAGE),
    help=N_(
        "Remove an image from the project; its file and the private copies"
        " stay"
    ),
)
def delete(context, name):
    disks = context.factory.remove_disk_image(name)
    return [
        _("{brick} {device} has no image now").format(
            brick=disk.vm.name, device=disk.device
        )
        for disk in disks
    ]
