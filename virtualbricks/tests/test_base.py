import os
import StringIO

from virtualbricks import base
from virtualbricks.tests import unittest, stubs


marker = object()
DUMP = """[Stub:base]
bool=
float=0.1
int=43
spinint=31
str=b

"""
DUMP2 = """int=43
[newbrick:test]
spinint=31
str=b

"""


class Config1(base.Config):

    parameters = {
        "str": base.String("a"),
        "int": base.String("b"),
        "float": base.Float(0.0),
        "bool": base.Boolean(True),
        "obj": base.Object(marker)
    }


class Config2(Config1):

    parameters = {
        "int": base.Integer(42),
        "spinint": base.SpinInt(32, 1, 128),
    }


class BaseStub(base.Base):

    type = "Stub"
    config_factory = Config2


class TestConfig(unittest.TestCase):

    def setUp(self):
        self.config1 = Config1()
        self.config2 = Config2()

    def test_hierarchy(self):
        for config in self.config1, self.config2:
            for p in "str", "int", "float", "bool", "obj":
                self.assertIn(p, config.parameters)
                self.assertIn(p, config)
        self.assertIn("spinint", self.config2)

    def test_defaults(self):
        for p, v in (("str", "a"), ("int", 42), ("float", 0.0),
                     ("bool", True), ("obj", marker), ("spinint", 32)):
            self.assertEqual(self.config2[p], v)

    def _test_string(self, getter):
        for p, v in (("str", "a"), ("int", "42"), ("float", "0.0"),
                     ("bool", "*"), ("obj", marker), ("spinint", "32")):
            self.assertEqual(getter(self.config2, p), v)

    def test_get(self):
        self._test_string(base.Config.get)

    def test_getattr(self):
        self._test_string(getattr)

    def test_dict_interface(self):
        self.assertIn("str", self.config2)
        self.config2["str"] = "b"
        self.assertRaises(ValueError, self.config2.__setitem__, "str2", "b")
        self.assertEquals(self.config2["str"], "b")
        self.assertEquals(len(self.config2), 6)
        self.assertEquals(sorted(self.config2.keys()), ["bool", "float", "int",
                                                     "obj", "spinint", "str"])


class TestBase(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.brick = BaseStub(self.factory, "base")

    def test_save_to(self):
        sio = StringIO.StringIO()
        self.brick.save_to(sio)
        self.assertEqual(sio.getvalue(), "[Stub:base]\n\n")
        self.brick.config["bool"] = False
        self.brick.config["float"] = 0.1
        self.brick.config["int"] = 43
        self.brick.config["spinint"] = 31
        self.brick.config["str"] = "b"
        sio.seek(0)
        self.brick.save_to(sio)
        self.assertEqual(sio.getvalue(), DUMP)

    def test_restore_from(self):
        sio = StringIO.StringIO(DUMP)
        sio.seek(-1, os.SEEK_END)
        sio.write("# this is a comment")
        sio.seek(0)
        # skip the first line
        sio.readline()
        self.brick.load_from(sio)
        for p, v in (("bool", False), ("float", 0.1), ("int", 43),
                     ("spinint", 31), ("str", "b")):
            self.assertEqual(self.brick.config[p], v)
        cur = sio.tell()
        sio.seek(0, os.SEEK_END)
        self.assertEqual(cur, sio.tell())

    def test_restore_advanced(self):
        sio = StringIO.StringIO(DUMP2)
        sio.seek(0)
        self.brick.load_from(sio)
        for p, v in (("bool", True), ("float", 0.0), ("int", 43),
                     ("spinint", 32), ("str", "a")):
            self.assertEqual(self.brick.config[p], v)
        self.assertEqual(sio.tell(), 7)
