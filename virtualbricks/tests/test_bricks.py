import warnings
import StringIO

from virtualbricks import base, bricks
from virtualbricks.tests import unittest, stubs


class TestBricks(unittest.TestCase):

    def test_get_cbset(self):
        brick = bricks.Brick(stubs.FactoryStub(), "test")
        cbset = brick.get_cbset("supercalifragilistichespiralidoso")
        self.assertIs(cbset, None)

    def test_warnings(self):
        brick = bricks.Brick(stubs.FactoryStub(), "test")
        with warnings.catch_warnings(record=True)as w:
            warnings.simplefilter("always")
            brick.on_config_changed()
            self.assertEqual(len(w), 1)
            self.assertEquals(w[0].category, DeprecationWarning)

    # def test_basic_interface(self):
    #     factory = stubs.FactoryStub()
    #     brick = bricks.Brick(factory, "test")


class SwitchConfig(base.NewConfig):

    parameters = {"numports": base.SpinInt(32, 1, 128),
                  "hub": base.Boolean(False),
                  "fstp": base.Boolean(False)}


class TestConfig(unittest.TestCase):

    def test_new_config(self):
        cfg = SwitchConfig(None)
        for name, typ in cfg.parameters.iteritems():
            self.assertIn(name, cfg)
            self.assertEqual(typ.default, cfg[name])
        numports, hub, fstp = [cfg.parameters[n] for n in ("numports", "hub",
                                                           "fstp")]
        self.assertEqual(numports.to_string(cfg["numports"]), "32")
        self.assertEqual(hub.to_string(cfg["hub"]), "")
        self.assertEqual(fstp.to_string(cfg["fstp"]), "")
        self.assertTrue(hub.from_string("*"))

    def test_save_to(self):
        sio = StringIO.StringIO()
        cfg = SwitchConfig(stubs.BrickStub(stubs.FactoryStub(), "test_stub"))
        cfg.save_to(sio)
        out = "[Stub:test_stub]\n"
        self.assertEqual(sio.getvalue(), out)
        cfg["numports"] = 33
        cfg["fstp"] = True
        out = "[Stub:test_stub]\nfstp=*\nnumports=33\n"
        sio.truncate(0)
        cfg.save_to(sio)
        self.assertEqual(sio.getvalue(), out)

    def test_load_from(self):
        cfg = SwitchConfig(stubs.BrickStub(stubs.FactoryStub(), "test_stub"))
        sio = StringIO.StringIO()
        sio.write("fstp=*\nnumports=33\n")
        sio.seek(0)
        self.assertEqual(cfg["numports"], 32)
        self.assertEqual(cfg["fstp"], False)
        cfg.load_from(sio)
        self.assertEqual(cfg["numports"], 33)
        self.assertEqual(cfg["fstp"], True)

        # a comment
        sio.truncate(0)
        sio.write("#numports=1")
        sio.seek(0)
        cfg.load_from(sio)
        self.assertEqual(cfg["numports"], 33)

        # a new section
        sio.truncate(0)
        sio.write("[Stub:test_stub]\nfstp=\nnumports=32\n")
        sio.seek(0)
        cfg.load_from(sio)
        self.assertEqual(cfg["numports"], 33)
        self.assertEqual(cfg["fstp"], True)
        self.assertEqual(sio.tell(), 0)

        # empty file
        sio.truncate(0)
        cfg.load_from(sio)
        self.assertEqual(cfg["numports"], 33)
        self.assertEqual(cfg["fstp"], True)
        self.assertEqual(sio.tell(), 0)

    def test_set(self):
        cfg = SwitchConfig(None)
        cfg.set("numports=33")
        self.assertEqual(cfg.numports, "33")

    def test_set_obj(self):
        cfg = SwitchConfig(None)
        cfg.set_obj("numports", 33)
        self.assertEqual(cfg.numports, "33")
        self.assertEqual(cfg["numports"], 33)

    def test_set_running(self):
        state = []

        class Brick(object):

            def __init__(self):
                self.cfg = SwitchConfig(self)

            def cbset_numports(self, value):
                state.append(value)

        brick = Brick()
        brick.cfg.set("numports=33")
        self.assertEqual(len(state), 1)
        self.assertEqual(brick.cfg.numports, "33")

    def test_get_set_attr(self):
        cfg = SwitchConfig(None)
        cfg.numports = "33"
        self.assertEqual(cfg["numports"], 33)
