import os
import StringIO

from virtualbricks import base
from virtualbricks.tests import unittest


marker = object()
DUMP = """bool=
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


class Config1(base.NewConfig):

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

class TestNewConfig(unittest.TestCase):

    def setUp(self):
        self.cfg1 = Config1()
        self.cfg2 = Config2()

    def test_hierarchy(self):
        for cfg in self.cfg1, self.cfg2:
            for p in "str", "int", "float", "bool", "obj":
                self.assertIn(p, cfg.parameters)
                self.assertIn(p, cfg)
        self.assertIn("spinint", self.cfg2)

    def test_defaults(self):
        for p, v in (("str", "a"), ("int", 42), ("float", 0.0),
                     ("bool", True), ("obj", marker), ("spinint", 32)):
            self.assertEqual(self.cfg2[p], v)

    def _test_string(self, getter):
        for p, v in (("str", "a"), ("int", "42"), ("float", "0.0"),
                     ("bool", "*"), ("obj", marker), ("spinint", "32")):
            self.assertEqual(getter(self.cfg2, p), v)

    def test_get(self):
        self._test_string(base.NewConfig.get)

    def test_getattr(self):
        self._test_string(getattr)

    def test_save_to(self):
        sio = StringIO.StringIO()
        self.cfg2.save_to(sio)
        self.assertEqual(sio.getvalue(), "\n")
        self.cfg2["bool"] = False
        self.cfg2["float"] = 0.1
        self.cfg2["int"] = 43
        self.cfg2["spinint"] = 31
        self.cfg2["str"] = "b"
        sio.seek(0)
        self.cfg2.save_to(sio)
        self.assertEqual(sio.getvalue(), DUMP)

    def test_restore_from(self):
        sio = StringIO.StringIO(DUMP)
        sio.seek(-1, os.SEEK_END)
        sio.write("# this is a comment")
        sio.seek(0)
        self.cfg2.load_from(sio)
        for p, v in (("bool", False), ("float", 0.1), ("int", 43),
                     ("spinint", 31), ("str", "b")):
            self.assertEqual(self.cfg2[p], v)
        cur = sio.tell()
        sio.seek(0, os.SEEK_END)
        self.assertEqual(cur, sio.tell())

    def test_restore_advanced(self):
        sio = StringIO.StringIO(DUMP2)
        sio.seek(0)
        self.cfg2.load_from(sio)
        for p, v in (("bool", True), ("float", 0.0), ("int", 43),
                     ("spinint", 32), ("str", "a")):
            self.assertEqual(self.cfg2[p], v)
        self.assertEqual(sio.tell(), 7)

    def test_dict_interface(self):
        self.assertIn("str", self.cfg2)
        self.cfg2["str"] = "b"
        self.assertRaises(ValueError, self.cfg2.__setitem__, "str2", "b")
        self.assertEquals(self.cfg2["str"], "b")
        self.assertEquals(len(self.cfg2), 6)
        self.assertEquals(sorted(self.cfg2.keys()), ["bool", "float", "int",
                                                     "obj", "spinint", "str"])

    def test_old_interface(self):
        self.assertEquals(list(sorted(self.cfg2.iteritems())),
                          [("bool", "*"), ("float", "0.0"), ("int", "42"),
                           ("obj", marker), ("spinint", "32"), ("str", "a")])
