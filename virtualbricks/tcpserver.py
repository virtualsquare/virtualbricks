from virtualbricks.logger import ChildLogger
from virtualbricks.tcpproto import *
import time, socket, sys, hashlib, select
from threading import Thread

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
			print "socket error (1)"
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
							print "socket error (2)"
							self.factory.quit()
							sys.exit(1)
						self.info("Connection from %s" % str(addr))
						self.sock = sock
						self.sock.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
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
						if len(p_cha.poll(5000)) > 0:
							rec = sock.recv(len(hashed))
							if rec == hashed:
								self.info("%s: Client authenticated.", str(addr))
								sock.send("OK\n")
								self.master_address = addr
								self.serve_connection(sock)
							else:
								self.info("%s: Authentication failed. " % str(addr))
								sock.send("FAIL\n")
						else:
							self.info("%s: Challenge timeout", str(addr))

						sock.close()
						self.sock = None
						self.info("Connection from %s closed.", str(addr))
			self.listening.close()

	def remote_wire_request(self, req):
		if (len(req) == 0):
			return False
		args = req.rstrip('\n').split(' ')
		if len(args) != 4 or args[0] != 'udp':
			print "Len args: %d" % len(args)
			print "Args[0]=%s" % args[0]
			return False
		for b in self.factory.bricks:
			if b.name == args[2]:
				w = PyWire(self.factory, args[1])
				w.set_remoteport(args[3])
				w.connect(b)
				w.poweron()
				return True
		print "Brick not found: " + args[2]
		return False


	def serve_connection(self, sock):
		p = select.poll()
		p.register(sock, select.POLLIN)
		rec=''
		while(self.factory.running_condition):
			if len(p.poll(100)) > 0:
				try:
					recs = sock.recv(4000)
				except:
					print "RECV error."
					return
				print recs,
				for rec in recs.split('\n'):
					if self.factory.parse(rec.rstrip('\n'), console=sock):
						try:
							sock.send("OK\n")
						except:
							print "Send error"
							return
					else:
						try:
							sock.send("FAIL\n")
						except:
							print "Send error"
							return

		for b in self.factory.bricks:
			if b.proc is not None:
				pz = b.proc.poll()
				if pz is not None:
					b.poweroff()
