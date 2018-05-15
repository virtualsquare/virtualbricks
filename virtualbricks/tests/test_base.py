# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2018 Virtualbricks team

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import os
import copy
import six

if six.PY3:
    def seek_end(fileobj):
        fileobj.seek(0, os.SEEK_END)
else:
    def seek_end(fileobj):
        fileobj.seek(-1, os.SEEK_END)

from virtualbricks import base, _configparser
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

    def _assert_basic_types_equals(self, cfg1, cfg2):
        self.assertEqual(cfg1["str"], cfg2["str"])
        self.assertEqual(cfg1["int"], cfg2["int"])
        self.assertEqual(cfg1["float"], cfg2["float"])
        self.assertEqual(cfg1["bool"], cfg2["bool"])
        self.assertEqual(cfg1["spinint"], cfg2["spinint"])

    def test_deepcopy(self):
        cfg = copy.deepcopy(self.config2)
        self._assert_basic_types_equals(cfg, self.config2)
        self.assertIsNot(cfg, self.config2)
        self.assertIsNot(cfg["obj"], self.config2["obj"])

    def test_copy(self):
        cfg = copy.copy(self.config2)
        self._assert_basic_types_equals(cfg, self.config2)
        self.assertIsNot(cfg, self.config2)
        self.assertIs(cfg["obj"], self.config2["obj"])


class TestTypes(unittest.TestCase):

    def test_spinint(self):
        """SpinInt can convert integers to and from strings."""

        spinint = base.SpinInt()
        val = 42
        string = spinint.to_string(val)
        self.assertIdentical(type(string), str)
        self.assertEqual(spinint.from_string(string), val)

    def test_spinint_not_in_range(self):
        """Values should be in range."""

        spinint = base.SpinInt(2, 1, 3)
        self.assertRaises(ValueError, spinint.to_string, 0)
        self.assertRaises(ValueError, spinint.from_string, "4")

    def test_spinfloat(self):
        """SpinFloat can convert floats to and from strings."""

        spinfloat = base.SpinFloat()
        # val = 42.2
        val = 0.1 + 0.1 + 0.1
        string = spinfloat.to_string(val)
        self.assertIdentical(type(string), str)
        self.assertEqual(spinfloat.from_string(val), val)

    def test_spinfloat_not_in_range(self):
        """Valuese should be in range."""

        spinfloat = base.SpinFloat(2, 0.2, 0.3)
        self.assertRaises(ValueError, spinfloat.to_string, 0.1)
        self.assertRaises(ValueError, spinfloat.from_string, "0.1")


class TestBase(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.brick = BaseStub(self.factory, "base")

    def test_save_to(self):
        sio = six.StringIO()
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
        sio = six.StringIO(DUMP)
        seek_end(sio)
        sio.write("# this is a comment")
        sio.seek(0)
        section = next(iter(_configparser.Parser(sio)))
        self.brick.load_from(section)
        for p, v in (("bool", False), ("float", 0.1), ("int", 43),
                     ("spinint", 31), ("str", "b")):
            self.assertEqual(self.brick.config[p], v)
        cur = sio.tell()
        sio.seek(0, os.SEEK_END)
        self.assertEqual(cur, sio.tell())

#     def test_restore_advanced(self):
#         sio = StringIO.StringIO(DUMP2)
#         itr = iter(configfile.Parser(sio))
#         section = next(itr)
#         self.brick.load_from(section)
#         for p, v in (("bool", True), ("float", 0.0), ("int", 42),
#                      ("spinint", 32), ("str", "a")):
#             self.assertEqual(self.brick.config[p], v)
#         self.assertRaises(StopIteration, next, itr)
#         self.assertEqual(sio.tell(), 7)
