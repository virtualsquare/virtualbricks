import os, re, Image, pygraphviz as pgv

def ImgPrefix():
	return "./"

class Icon:

	def __init__(self, brick):
	#if brick.get_type()!="Qemu":
		self.brick = brick
		self.ready = False

	def set_from_file(self, filename):
		self.base = filename
		self.grey = os.path.basename(filename).split('.')[0]+"_grey.png"
		self.make_grey()

	def set_from_bricktype(self):
		self.set_from_file(ImgPrefix() + self.brick.get_type() + ".png")

	def make_grey(self):
		if not os.access(self.base, os.R_OK):
			return
		if not os.access(self.grey, os.R_OK):
				# the reason for the existence of this class, so far.
			src = Image.open(self.base).convert('RGB', palette=Image.ADAPTIVE).convert('L').save(self.grey, transparency = 0)
			#except:
			#	self.debug("Cannot create grey image: defaulting to base")
			#	self.grey = self.base
		self.ready = True


	def get_img(self):
		if not self.ready:
			self.set_from_bricktype()
		if self.brick.proc is not None:
			return self.base
		else:
			return self.grey

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
	DOUBLECLICKTIME = 600

	def __init__(self, widget, bricks):
		self.topowidget = widget
		self.topo = pgv.AGraph()
		self.topo.graph_attr['rankdir']='LR'
		#self.topo.graph_attr['rankdir']='TB'
		self.topo.graph_attr['ranksep']='1.2'
		self.nodes = []
		self.x_adj = 0.0
		self.y_adj = 0.0

		self.clicktime = 0

		# Add nodes
		sg = self.topo.add_subgraph([],name="switches_rank")
		sg.graph_attr['rank'] = 'same'
		for b in bricks:
		### I would like to use this code, but pygraphviz has a bug.
		#	if b.get_type() == 'Switch' or b.get_type().startswith('Wire'):
		#		sg.add_node(b.name)
		#		n = sg.get_node(b.name)
		#		print n
		#		n.attr['shape']='none'
		#		n.attr['fontsize']='9'
		#		n.attr['image']=b.get_type()+'.png'
		#	else:
				self.topo.add_node(b.name)
				n = self.topo.get_node(b.name)
				n.attr['shape']='none'
				n.attr['fontsize']='9'
				n.attr['image'] = b.icon.get_img()


		for b in bricks:
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
		self.topo.write("/tmp/vde.dot")
		self.topo.layout('dot')
		self.topo.draw("/tmp/vde_topology.png")
		self.topo.draw("/tmp/vde_topology.plain")

		img = Image.open("/tmp/vde_topology.png")
		x_siz, y_siz = img.size
		for line in open("/tmp/vde_topology.plain").readlines():
			#arg  = line.rstrip('\n').split(' ')
			arg  = re.split('\s+', line.rstrip('\n'))
			if arg[0] == 'graph':
				x_fact = x_siz / float(arg[2])
				y_fact = y_siz / float(arg[3])
			elif arg[0] == 'node':
				x = x_fact * float(arg[2])
				y = y_siz - y_fact * float(arg[3])
				self.nodes.append(Node(self, arg[1],x,y))
		# Display on the widget
		self.topowidget.set_from_file("/tmp/vde_topology.png")
