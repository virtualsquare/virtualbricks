import os

from virtualbricks.logger import ChildLogger
from virtualbricks import errors


class Plug(ChildLogger):

    def __init__(self, brick):
        ChildLogger.__init__(self, brick)
        self.brick = brick
        self.sock = None
        self.antiloop = False
        self.mode = 'vde'

    def configured(self):
        return self.sock is not None

    def connected(self):
        if self.antiloop:
            if self.settings.get('erroronloop'):
                raise errors.NotConnected('Network loop detected!')
            self.antiloop = False
            return False

        self.antiloop = True
        if self.sock is None or self.sock.brick is None:
            self.antiloop = False
            return False
        self.sock.brick.poweron()

        if self.sock.brick.homehost is None and self.sock.brick.proc is None:
            self.antiloop = False
            return False
        for p in self.sock.brick.plugs:
            if not p.connected():
                self.antiloop = False
                return False
        self.antiloop = False
        return True

    def connect(self, sock):
        if sock is None:
            return False
        else:
            sock.plugs.append(self)
            self.sock = sock
            return True

    def disconnect(self):
        self.sock = None


class Sock(object):

    def __init__(self, brick, name=""):
        self.brick = brick
        self.path = name
        self.nickname = name
        self.plugs = []
        self.mode = "sock"
        self.brick.factory.socks.append(self)

    def get_free_ports(self):
        return int(self.brick.cfg.numports) - len(self.plugs)

    def has_valid_path(self):
        return os.access(os.path.dirname(self.path), os.W_OK)
