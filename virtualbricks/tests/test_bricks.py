import warnings

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

    parameters = [("numports", base.SpinInt(32, 1, 128)),
                  ("hub", base.Boolean(False)),
                  ("fstp", base.Boolean(False))]


class TestConfig(unittest.TestCase):

    def test_new_config(self):
        cfg = SwitchConfig(None)
        for name, typ in cfg.parameters:
            self.assertIn(name, cfg)
            self.assertEqual(typ.default, cfg[name])
        numports, hub, fstp = [p[1] for p in cfg.parameters]
        self.assertEqual(numports.to_string(cfg["numports"]), "32")
        self.assertEqual(hub.to_string(cfg["hub"]), "False")
        self.assertEqual(fstp.to_string(cfg["fstp"]), "False")
        self.assertTrue(hub.from_string("*"))

    def test_set(self):
        cfg = SwitchConfig(None)
        cfg.set("numports=33")
        self.assertEqual(cfg.numports, "33")

    def test_set_obj(self):
        cfg = SwitchConfig(None)
        cfg.set_obj("numports", 33)
        self.assertEqual(cfg.numports, 33)

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
        self.assertEqual(brick.cfg.hub, False)
        self.assertEqual(brick.cfg.numports, "33")
