from threading import Thread, Timer
from virtualbricks.logger import ChildLogger
from virtualbricks.brickfactory import *
from virtualbricks.tcpproto import *
import time, socket, sys, hashlib, select

class TcpServer(ChildLogger, Thread):
	def __init__(self, factory, password, port=1050):
		self.port = port
		self.factory = factory
		self.logger = factory.logger
		self.listening = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.proto = VirtualbricksTCPPROTO()
		ChildLogger.__init__(self, self.logger)
		self.password = password
		Thread.__init__(self)
		self.factory.connect("brick-stopped", self.cb_brick_stopped)
		self.factory.connect("brick-started", self.cb_brick_started)
		self.sock = None

	def cb_brick_started(self, model, name=""):
		if (self.sock):
			self.sock.send("brick-started " + name + '\n')

	def cb_brick_stopped(self, model, name=""):
		if (self.sock):
			self.sock.send("brick-stopped " + name + '\n')

	def run(self):
		self.info("TCP server started.")
		try:
			self.listening.bind(("0.0.0.0", self.port))
			self.listening.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
			self.listening.listen(1)
		except Exception:
			print "socket error"
			self.factory.quit()
			sys.exit(1)

		finally:
			while(self.factory.running_condition):
				p = select.poll()
				p.register(self.listening, select.POLLIN)
				if len(p.poll(1000)) > 0:
						try:
							(sock, addr) = self.listening.accept()

						except Exception:
							print "socket error"
							self.factory.quit()
							sys.exit(1)
						self.info("Connection from %s" % str(addr))
						self.sock = sock
						randfile = open("/dev/urandom", "r")
						challenge = randfile.read(256)
						sha = hashlib.sha256()
						sha.update(self.password)
						sha.update(challenge)
						hashed = sha.digest()
						sock.send(self.proto.HELO())
						sock.send(challenge)
						p_cha = select.poll()
						p_cha.register(sock, select.POLLIN)
						try:
							if len(p_cha.poll(5000)) > 0:
								rec = sock.recv(len(hashed))
								if rec == hashed:
									self.info("%s: Client authenticated.", str(addr))
									sock.send("OK\n")
									self.serve_connection(sock)
								else:
									self.info("%s: Authentication failed. " % str(addr))
									sock.send("FAIL\n")
							else:
								self.info("%s: Challenge timeout", str(addr))
						except:
							pass

						sock.close()
						self.sock = None

	def serve_connection(self, sock):
		p = select.poll()
		p.register(sock, select.POLLIN)
		rec=''
		while(self.factory.running_condition):
			while(p.poll(100)):
				recs = sock.recv(4000)
				for rec in recs.split('\n'):
				#	self.factory.parse(rec.rstrip('\n'), console=sock)
					if self.factory.parse(rec.rstrip('\n'), console=sock):
						sock.send("OK\n")
					else:
						sock.send("FAIL\n")

			for b in self.factory.bricks:
				if b.proc:
					pz = b.proc.poll()
					if pz is not None:
						b.poweroff()
