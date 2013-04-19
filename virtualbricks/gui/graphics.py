# coding: utf-8

##	Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
##	Copyright (C) 2011 Virtualbricks team
##
##	This program is free software; you can redistribute it and/or
##	modify it under the terms of the GNU General Public License
##	as published by the Free Software Foundation; version 2.
##
##	This program is distributed in the hope that it will be useful,
##	but WITHOUT ANY WARRANTY; without even the implied warranty of
##	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
##	GNU General Public License for more details.
##
##	You should have received a copy of the GNU General Public License
##	along with this program; if not, write to the Free Software
##	Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

import logging

import Image
import ImageEnhance
import os
import pygraphviz as pgv
import re

from virtualbricks.settings import MYPATH

log = logging.getLogger('virtualbricks.gui')

def ImgPrefix():
	if os.access("/usr/share/pixmaps/Switch.png", os.R_OK):
		return "/usr/share/pixmaps/"
	else:
		return "/usr/local/share/pixmaps/"

class Icon:

	def __init__(self, component):
	#if component.get_type()!="Qemu":
		self.component = component
		self.ready = False
		self.base = ""
		self.grey = ""

	def has_custom_icon(self):
		return ('icon' in self.component.cfg.keys()) and self.component.cfg.icon != ""

	def set_from_file(self, filename):

		newname = MYPATH + "/qemuicon_" + self.component.name + ".png"
		if self.has_custom_icon() and self.component.cfg.icon != newname:
			src = Image.open(filename).resize((48,48),Image.ANTIALIAS)
			src.convert('RGBA').save(newname)
			filename = self.component.cfg.icon = newname

		self.base = filename
		self.grey = "/tmp/"+os.path.basename(filename).split('.')[0]+"_grey.png"
		try:
			os.unlink(self.grey)
		except:
			pass
		self.make_grey()

	def set_from_bricktype(self):
		self.set_from_file(ImgPrefix() + self.component.get_type() + ".png")

	def make_grey(self):
		if not os.access(self.base, os.R_OK):
			return
		if not os.access(self.grey, os.R_OK):
			try:
				src = Image.open(self.base).convert('RGB', palette=Image.ADAPTIVE).convert('L')
				bri = ImageEnhance.Brightness(src)
				bri.enhance(2.0).save(self.grey, transparency = 0)
			except:
				log.debug("Cannot create grey image: defaulting to base")
				self.grey = self.base
		self.ready = True


	def get_img(self):
		if self.has_custom_icon():
			self.set_from_file(self.component.cfg.icon)
		if not self.ready:
			self.set_from_bricktype()
		if hasattr(self.component,"proc"):
			if self.component.proc is not None:
				return self.base
			else:
				return self.grey
		elif hasattr(self.component,"active"):
			if self.component.active:
				return self.base
			else:
				return self.grey
		else:
			return self.base

class Node:
	def __init__(self, topology, name, x, y, thresh = 50):
		self.x = x
		self.y = y
		self.thresh = thresh
		self.name = name
		self.parent = topology
	def here(self, x, y):
		if abs(x + self.parent.x_adj - self.x) < self.thresh and abs(y + self.parent.y_adj - self.y) < self.thresh:
			return True
		else:
			return False

class Topology():

	def __init__(self, widget, bricks_model, scale=1.00, orientation="LR", export=None, tempdir="/tmp/"):
		self.topowidget = widget
		self.topo = pgv.AGraph()

		self.topo.graph_attr['rankdir']=orientation


		self.topo.graph_attr['ranksep']='2.0'
		self.nodes = []
		self.x_adj = 0.0
		self.y_adj = 0.0

		# Add nodes
		sg = self.topo.add_subgraph([],name="switches_rank")
		sg.graph_attr['rank'] = 'same'
		for row in bricks_model:
			b = row[0]
			self.topo.add_node(b.name)
			n = self.topo.get_node(b.name)
			n.attr['shape']='none'
			n.attr['fontsize']='9'
			n.attr['image'] = b.icon.get_img()

		for row in bricks_model:
			b = row[0]
			loop = 0
			for e in b.plugs:
				if e.sock is not None:
					if (b.get_type() == 'Tap'):
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
					loop+=1
					e.attr['dir'] = 'none'
					e.attr['color'] = 'black'
					e.attr['name'] = "      "
					e.attr['decorate']='true'

		#draw and save
		self.topo.write(tempdir+"vde.dot")
		self.topo.layout('dot')
		self.topo.draw(tempdir+"vde_topology.png")
		self.topo.draw(tempdir+"vde_topology.plain")

		img = Image.open(tempdir+"vde_topology.png")
		x_siz, y_siz = img.size
		for line in open(tempdir+"vde_topology.plain").readlines():
			#arg  = line.rstrip('\n').split(' ')
			arg = re.split('\s+', line.rstrip('\n'))
			if arg[0] == 'graph':
				if(float(arg[2]) != 0 and float(arg[3]) !=0 ):
					x_fact = scale * (x_siz / float(arg[2]))
					y_fact = scale * (y_siz / float(arg[3]))
				else:
					x_fact = 1
					y_fact = 1
			elif arg[0] == 'node':
				if(float(arg[2]) !=0 and float(arg[3] != 0)):
					x = scale * (x_fact * float(arg[2]))
					y = scale * (y_siz - y_fact * float(arg[3]))
				else:
					x = scale * (x_fact)
					y = scale * (y_siz - y_fact)
				self.nodes.append(Node(self, arg[1],x,y))
		# Display on the widget
		if scale < 1.00:
			img.resize((x_siz * scale, y_siz * scale)).save(tempdir+"vde_topology.png")

		self.topowidget.set_from_file(tempdir+"vde_topology.png")
		if export:
			img.save(export)
