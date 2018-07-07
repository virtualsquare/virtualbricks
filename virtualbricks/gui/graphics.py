# -*- test-case-name: virtualbricks.tests.test_graphics -*-
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

import os
import os.path
import sys
import re
import pkgutil
from pkgutil import get_data
import shutil

from PIL import Image
import pygraphviz as pgv
import gtk.gdk

from virtualbricks.tools import is_running


__all__ = ["get_filename", "get_data", "get_image", "pixbuf_for_brick",
           "pixbuf_for_brick_at_size", "pixbuf_for_brick_type",
           "pixbuf_for_running_brick", "pixbuf_for_running_brick_at_size",
           "Node", "Topology", "get_data_filename"]


def get_data_filename(resource):
    syswide = os.path.join(sys.prefix, "share", "virtualbricks", resource)
    if os.path.exists(syswide):
        return syswide
    return get_filename("virtualbricks.gui", os.path.join("data", resource))


def get_filename(package, resource):
    loader = pkgutil.get_loader(package)
    mod = sys.modules.get(package) or loader.load_module(package)
    if mod is None or not hasattr(mod, "__file__"):
        return None
    parts = resource.split("/")
    parts.insert(0, os.path.dirname(mod.__file__))
    return os.path.join(*parts)


def get_image(name):
    return get_data_filename(name)


def has_custom_icon(brick):
    return "icon" in brick.config and brick.config["icon"]


def brick_icon(brick):
    if has_custom_icon(brick):
        return brick.config["icon"]
    else:
        return get_data_filename(brick.get_type().lower() + ".png")


def saturate_if_stopped(brick, pixbuf):
    if not is_running(brick):
        pixbuf.saturate_and_pixelate(pixbuf, 0.0, True)
    return pixbuf


def pixbuf_for_brick_at_size(brick, width, height):
    filename = brick_icon(brick)
    pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(filename, width, height)
    return saturate_if_stopped(brick, pixbuf)


def pixbuf_for_brick(brick):
    filename = brick_icon(brick)
    pixbuf = gtk.gdk.pixbuf_new_from_file(filename)
    return saturate_if_stopped(brick, pixbuf)


def pixbuf_for_brick_type(type):
    filename = get_data_filename("%s.png" % type.lower())
    if filename is None:
        return None
    return gtk.gdk.pixbuf_new_from_file(filename)


def pixbuf_for_running_brick(brick):
    return gtk.gdk.pixbuf_new_from_file(brick_icon(brick))


def pixbuf_for_running_brick_at_size(brick, witdh, height):
    return gtk.gdk.pixbuf_new_from_file_at_size(brick_icon(brick),
            witdh, height)


class Node:

    def __init__(self, topology, name, x, y, thresh=50):
        self.x = x
        self.y = y
        self.thresh = thresh
        self.name = name
        self.parent = topology

    def here(self, x, y):
        return (abs(x + self.parent.x_adj - self.x) < self.thresh and
                abs(y + self.parent.y_adj - self.y) < self.thresh)


class Topology:

    def __init__(self, widget, bricks, scale=1.00, orientation="LR",
                 tempdir="/tmp"):
        self.topowidget = widget
        self.tempdir = tempdir
        self.topo = pgv.AGraph()
        self.topo.graph_attr['rankdir'] = orientation
        self.topo.graph_attr['ranksep'] = '2.0'
        self.nodes = []
        self.x_adj = 0.0
        self.y_adj = 0.0

        # Add nodes
        sg = self.topo.add_subgraph([], name="switches_rank")
        sg.graph_attr['rank'] = 'same'
        for brick in bricks:
            self.topo.add_node(brick.name)
            n = self.topo.get_node(brick.name)
            n.attr['shape'] = 'none'
            n.attr['fontsize'] = '9'
            n.attr['image'] = brick_icon(brick)

        for b in bricks:
            loop = 0
            for e in b.plugs:
                if e.sock is not None:
                    if b.get_type() == 'Tap':
                        self.topo.add_edge(b.name, e.sock.brick.name)
                        e = self.topo.get_edge(b.name, e.sock.brick.name)
                    elif len(b.plugs) == 2:
                        if loop == 0:
                            self.topo.add_edge(e.sock.brick.name, b.name)
                            e = self.topo.get_edge(e.sock.brick.name, b.name)
                        else:
                            self.topo.add_edge(b.name, e.sock.brick.name)
                            e = self.topo.get_edge(b.name, e.sock.brick.name)
                    elif loop < (len(b.plugs) + 1) / 2:
                        self.topo.add_edge(e.sock.brick.name, b.name)
                        e = self.topo.get_edge(e.sock.brick.name, b.name)
                    else:
                        self.topo.add_edge(b.name, e.sock.brick.name)
                        e = self.topo.get_edge(b.name, e.sock.brick.name)
                    loop += 1
                    e.attr['dir'] = 'none'
                    e.attr['color'] = 'black'
                    e.attr['name'] = "      "
                    e.attr['decorate'] = 'true'

        #draw and save
        self.topo.write(self.get_topo_filename())
        self.topo.layout('dot')
        self.topo.draw(self.get_image_filename())
        self.topo.draw(self.get_plain_filename())

        img = Image.open(self.get_image_filename())
        x_siz, y_siz = img.size
        for line in open(self.get_plain_filename()).readlines():
            arg = re.split('\s+', line.rstrip('\n'))
            if arg[0] == 'graph':
                if float(arg[2]) != 0 and float(arg[3]) != 0:
                    x_fact = scale * (x_siz / float(arg[2]))
                    y_fact = scale * (y_siz / float(arg[3]))
                else:
                    x_fact = 1
                    y_fact = 1
            elif arg[0] == 'node':
                if float(arg[2]) != 0 and float(arg[3] != 0):
                    x = scale * (x_fact * float(arg[2]))
                    y = scale * (y_siz - y_fact * float(arg[3]))
                else:
                    x = scale * (x_fact)
                    y = scale * (y_siz - y_fact)
                self.nodes.append(Node(self, arg[1], x, y))
        # Display on the widget
        if scale < 1.00:
            img.resize((x_siz * scale, y_siz * scale))
            img.save(self.get_image_filename())

        self.topowidget.set_from_file(self.get_image_filename())

    def export(self, filename):
        shutil.copy(self.get_image_filename(), filename)

    def get_image_filename(self):
        return os.path.join(self.tempdir, "vde_topology.png")

    def get_plain_filename(self):
        return os.path.join(self.tempdir, "vde_topology.plain")

    def get_topo_filename(self):
        return os.path.join(self.tempdir, "vde.dot")
