from threading import Thread, Timer
from virtualbricks.logger import ChildLogger
from virtualbricks.brickfactory import *
from virtualbricks.tcpproto import *
import time, socket, sys, hashlib, select

class TcpServer(ChildLogger, Thread):
	def __init__(self, factory, port=1050):
		self.port = port
		self.factory = factory
		self.logger = factory.logger
		self.listening = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.proto = VirtualbricksTCPPROTO()
		ChildLogger.__init__(self, self.logger)
		Thread.__init__(self)

	def run(self):
		self.info("TCP server started.")
		try:
			self.listening.bind(("0.0.0.0", self.port))
			self.listening.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
			self.listening.listen(1)
		except Exception:
			print "error"
		finally:
			while(self.factory.running_condition):
				p = select.poll()
				p.register(self.listening, select.POLLIN)
				if len(p.poll(1000)) > 0:
						(sock, addr) = self.listening.accept()
						self.info("Connection from %s" % str(addr))
						randfile = open("/dev/urandom", "r")
						challenge = randfile.read(256)
						sha = hashlib.sha256()
						sha.update("passw0rd")
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

	def serve_connection(self, sock):
		p = select.poll()
		p.register(sock, select.POLLIN)
		rec=''
		while(self.factory.running_condition):
			while(p.poll(100)):
				rec = sock.recv(4000)
				if self.factory.parse(rec.rstrip('\n'), console=sock):
					sock.send("OK\n")
				else:
					sock.send("FAIL\n")


