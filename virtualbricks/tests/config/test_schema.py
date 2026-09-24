# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2019 Virtualbricks team

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

import copy

from twisted.trial import unittest

from virtualbricks.config import schema
from virtualbricks.config.report import Report
from virtualbricks.config.schema import (
    Bool,
    Choice,
    Float,
    Int,
    IPv4,
    Kind,
    ListOf,
    Mac,
    Path,
    Record,
    Ref,
    Str,
)


@schema.define
class Disk:

    image = schema.field(Ref("image"), default="")
    private = schema.field(Bool(), default=False)


@schema.define
class Machine:

    name = schema.field(Str(), default="vm", label="Name", help="The name")
    ram = schema.field(Int(1, 1024), default=64)
    loss = schema.field(Float(0, 100), default=0.0)
    kvm = schema.field(Bool(), default=False)
    tags = schema.field(ListOf(Str()), factory=list)
    event = schema.field(Ref("event"), default="")
    hda = schema.field(
        Ref("image"), default="", path=("disks", "hda", "image")
    )
    privatehda = schema.field(
        Bool(), default=False, path=("disks", "hda", "private")
    )
    boot = schema.field(Record(Disk), factory=Disk)


class TestDescribe(unittest.TestCase):

    def test_values(self):
        kind = Kind()
        self.assertEqual(kind.format(True), "true")
        self.assertEqual(kind.format(False), "false")
        self.assertEqual(kind.format("a"), '"a"')
        self.assertEqual(kind.format([]), "an empty list")
        self.assertEqual(kind.format([1]), "the default list")
        self.assertEqual(kind.format(3), "3")


class TestKind(unittest.TestCase):

    def test_base(self):
        kind = Kind()
        self.assertIsNone(kind.check(object()))
        self.assertEqual(kind.to_data(1), 1)
        self.assertEqual(kind.from_data(1, Report(), ""), 1)
        self.assertRaises(ValueError, kind.parse, "x")


class TestBool(unittest.TestCase):

    def test_check(self):
        Bool().check(True)
        self.assertRaises(ValueError, Bool().check, 1)

    def test_parse(self):
        for text in ("true", " Yes ", "ON", "1"):
            self.assertIs(Bool().parse(text), True)
        for text in ("false", "no", "Off", "0"):
            self.assertIs(Bool().parse(text), False)
        self.assertRaises(ValueError, Bool().parse, "maybe")


class TestInt(unittest.TestCase):

    def test_types(self):
        Int().check(3)
        self.assertRaises(ValueError, Int().check, True)
        self.assertRaises(ValueError, Int().check, 1.5)
        self.assertRaises(ValueError, Int().check, "1")

    def test_range(self):
        kind = Int(1, 10)
        kind.check(1)
        kind.check(10)
        with self.assertRaisesRegex(ValueError, "11 is outside 1–10"):
            kind.check(11)
        with self.assertRaisesRegex(ValueError, "0 is less than 1"):
            Int(1).check(0)
        with self.assertRaisesRegex(ValueError, "5 is more than 4"):
            Int(max=4).check(5)
        Int(1).check(100)
        Int(max=4).check(-100)

    def test_parse(self):
        self.assertEqual(Int(1, 10).parse(" 7 "), 7)
        with self.assertRaisesRegex(ValueError, "is not an integer"):
            Int().parse("seven")
        self.assertRaises(ValueError, Int(1, 10).parse, "70")


class TestFloat(unittest.TestCase):

    def test_accepts_integers(self):
        Float().check(3)
        self.assertEqual(Float().to_data(3), 3.0)
        value = Float().from_data(3, Report(), "")
        self.assertEqual(value, 3.0)
        self.assertIsInstance(value, float)

    def test_invalid(self):
        self.assertRaises(ValueError, Float().check, "3")
        self.assertRaises(ValueError, Float(0, 1).from_data, 2, Report(), "")

    def test_parse(self):
        self.assertEqual(Float().parse("2.5"), 2.5)
        self.assertRaises(ValueError, Float().parse, "x")


class TestStrings(unittest.TestCase):

    def test_str(self):
        Str().check("")
        self.assertRaises(ValueError, Str().check, 1)
        self.assertEqual(Str().parse("x"), "x")

    def test_pattern(self):
        kind = Str(r"\d+", "a number")
        kind.check("12")
        kind.check("")
        with self.assertRaisesRegex(ValueError, '"ab" is not a number'):
            kind.check("ab")

    def test_path_and_ref(self):
        Path().check("/x")
        self.assertEqual(Ref("image").target, "image")

    def test_mac(self):
        Mac().check("00:aa:79:71:be:61")
        Mac().check("")
        with self.assertRaisesRegex(ValueError, "not a MAC address"):
            Mac().check("00:gg:79:71:be:61")

    def test_ipv4(self):
        IPv4().check("10.0.0.1")
        self.assertRaises(ValueError, IPv4().check, "")
        self.assertRaises(ValueError, IPv4().check, "10.0.0")
        self.assertRaises(ValueError, IPv4().check, 1)
        IPv4(optional=True).check("")

    def test_choice(self):
        kind = Choice("off", "dhcp")
        kind.check("dhcp")
        with self.assertRaisesRegex(ValueError, "is not one of off, dhcp"):
            kind.check("manual")
        self.assertRaises(ValueError, kind.check, 1)


class TestRecord(unittest.TestCase):

    def test_record(self):
        kind = Record(Disk)
        kind.check(Disk())
        self.assertRaises(ValueError, kind.check, {})
        self.assertEqual(
            kind.to_data(Disk("a", True)), {"image": "a", "private": True}
        )
        self.assertEqual(
            kind.from_data({"image": "a", "private": True}, Report(), "d"),
            Disk("a", True),
        )
        with self.assertRaisesRegex(ValueError, "is not a table"):
            kind.from_data("a", Report(), "d")
        self.assertEqual(kind.format(Disk()), "{…}")


class TestListOf(unittest.TestCase):

    def test_check(self):
        kind = ListOf(Int(), length=2)
        kind.check([1, 2])
        self.assertRaises(ValueError, kind.check, (1, 2))
        self.assertRaises(ValueError, kind.check, [1])
        self.assertRaises(ValueError, kind.check, [1, "2"])
        with self.assertRaisesRegex(ValueError, "at least 1 needed"):
            ListOf(Int(), min_length=1).check([])

    def test_data(self):
        kind = ListOf(Float())
        self.assertEqual(kind.to_data([1, 2]), [1.0, 2.0])
        self.assertEqual(kind.format([1.0]), "[1.0]")

    def test_from_data_drops_bad_items(self):
        report = Report()
        kind = ListOf(Int())
        self.assertEqual(kind.from_data([1, "x", 3], report, "l"), [1, 3])
        self.assertEqual(
            [str(m) for m in report],
            ["l[1]: 'x' is not an integer, item dropped"],
        )

    def test_from_data_invalid(self):
        self.assertRaises(ValueError, ListOf(Int()).from_data, 1, Report(), "")
        kind = ListOf(Int(), length=2)
        self.assertRaises(ValueError, kind.from_data, [1, "x"], Report(), "")


class TestFields(unittest.TestCase):

    def test_validation_on_init_and_assignment(self):
        with self.assertRaisesRegex(ValueError, "ram: 0 is outside 1–1024"):
            Machine(ram=0)
        machine = Machine()
        with self.assertRaisesRegex(ValueError, "kvm: "):
            machine.kvm = "yes"
        machine.ram = 128
        self.assertEqual(machine.ram, 128)

    def test_introspection(self):
        self.assertEqual(
            schema.names(Machine),
            [
                "name",
                "ram",
                "loss",
                "kvm",
                "tags",
                "event",
                "hda",
                "privatehda",
                "boot",
            ],
        )
        self.assertEqual(schema.names(Machine()), schema.names(Machine))
        self.assertIsInstance(schema.kind_of(Machine, "ram"), Int)
        self.assertRaises(KeyError, schema.kind_of, Machine, "nope")
        attribute = schema.fields(Machine)[0]
        self.assertEqual(schema.info(attribute).label, "Name")
        self.assertEqual(schema.info(attribute).help, "The name")
        self.assertEqual(schema.default(Machine, "ram"), 64)
        self.assertEqual(schema.default(Machine, "tags"), [])
        self.assertRaises(KeyError, schema.default, Machine, "nope")

    def test_values(self):
        machine = Machine(ram=100)
        values = schema.values(machine)
        self.assertEqual(values["ram"], 100)
        self.assertEqual(len(values), 9)

    def test_make_class(self):
        cls = schema.make_class(
            "Made", {"size": schema.field(Int(0, 9), default=1)}, (Disk,)
        )
        made = cls()
        self.assertEqual(schema.names(made), ["image", "private", "size"])
        self.assertRaises(ValueError, setattr, made, "size", 10)
        self.assertRaises(AttributeError, setattr, made, "other", 1)
        plain = schema.make_class(
            "Plain", {"a": schema.field(Int(), default=0)}
        )
        self.assertEqual(plain().a, 0)

    def test_copies_are_independent(self):
        machine = Machine()
        other = copy.deepcopy(machine)
        other.tags.append("x")
        self.assertEqual(machine.tags, [])


class TestDump(unittest.TestCase):

    def test_every_field_with_paths(self):
        data = schema.dump(Machine(hda="deb", privatehda=True))
        self.assertEqual(
            data,
            {
                "name": "vm",
                "ram": 64,
                "loss": 0.0,
                "kvm": False,
                "tags": [],
                "event": "",
                "disks": {"hda": {"image": "deb", "private": True}},
                "boot": {"image": "", "private": False},
            },
        )

    def test_exclude(self):
        data = schema.dump(Disk(), exclude=("private",))
        self.assertEqual(data, {"image": ""})


class TestLoad(unittest.TestCase):

    def setUp(self):
        self.report = Report()

    def messages(self):
        return [str(m) for m in self.report]

    def test_round_trip(self):
        machine = Machine(ram=10, tags=["a"], hda="deb", boot=Disk("x", True))
        loaded = schema.load(Machine, schema.dump(machine), self.report)
        self.assertEqual(loaded, machine)
        self.assertEqual(self.messages(), [])

    def test_missing_and_invalid(self):
        data = schema.dump(Machine())
        del data["name"]
        data["ram"] = 5000
        data["kvm"] = "yes"
        data["disks"]["hda"]["image"] = 3
        loaded = schema.load(Machine, data, self.report, "bricks.vm")
        self.assertEqual(loaded, Machine())
        self.assertEqual(
            self.messages(),
            [
                'bricks.vm.name: missing, using the default "vm"',
                "bricks.vm.ram: 5000 is outside 1–1024, using the default 64",
                "bricks.vm.kvm: 'yes' is not true or false, using the default "
                "false",
                "bricks.vm.disks.hda.image: 3 is not a string, using the "
                'default ""',
            ],
        )

    def test_missing_list_default(self):
        data = schema.dump(Machine())
        del data["tags"]
        schema.load(Machine, data, self.report)
        self.assertEqual(
            self.messages(), ["tags: missing, using the default []"]
        )

    def test_missing_intermediate_table(self):
        data = schema.dump(Machine())
        data["disks"] = "none"
        loaded = schema.load(Machine, data, self.report, "vm")
        self.assertEqual(loaded.hda, "")
        self.assertIn("vm.disks: unknown field, dropped", self.messages())
        self.assertIn(
            'vm.disks.hda.image: missing, using the default ""',
            self.messages(),
        )

    def test_unknown_fields(self):
        data = schema.dump(Machine())
        data["color"] = "red"
        data["disks"]["hda"]["size"] = 3
        data["disks"]["hdb"] = {"image": "x"}
        data["boot"]["extra"] = 1
        data["other"] = {"a": 1}
        schema.load(Machine, data, self.report, "vm", ignore={"other"})
        # A record reports its own unknown fields while it's loaded.
        self.assertEqual(
            self.messages(),
            [
                "vm.boot.extra: unknown field, dropped",
                "vm.disks.hda.size: unknown field, dropped",
                "vm.disks.hdb: unknown field, dropped",
                "vm.color: unknown field, dropped",
            ],
        )

    def test_ignore_is_only_for_top_level_keys(self):
        data = schema.dump(Disk())
        data["x"] = {"private": 1}
        schema.load(Disk, data, self.report, ignore={"private"})
        self.assertEqual(self.messages(), ["x: unknown field, dropped"])

    def test_exclude(self):
        loaded = schema.load(
            Disk, {"image": "a"}, self.report, exclude={"private"}
        )
        self.assertEqual(loaded, Disk("a"))
        self.assertEqual(self.messages(), [])


class TestParse(unittest.TestCase):

    def test_parse(self):
        self.assertEqual(schema.parse(Machine, "ram", "32"), 32)
        self.assertIs(schema.parse(Machine(), "kvm", "yes"), True)
        self.assertRaises(KeyError, schema.parse, Machine, "nope", "1")
        self.assertRaises(ValueError, schema.parse, Machine, "tags", "a")


class TestReferences(unittest.TestCase):

    def test_references(self):
        machine = Machine(event="boot", hda="deb")
        self.assertEqual(
            list(schema.references(machine)),
            [("event", "event", "boot"), ("hda", "image", "deb")],
        )
        self.assertEqual(list(schema.references(Machine())), [])

    def test_rename(self):
        machine = Machine(event="boot", hda="deb")
        self.assertTrue(
            schema.rename_references(machine, "image", "deb", "ubuntu")
        )
        self.assertEqual(machine.hda, "ubuntu")
        self.assertEqual(machine.event, "boot")
        self.assertFalse(
            schema.rename_references(machine, "image", "deb", "x")
        )
        self.assertFalse(
            schema.rename_references(machine, "event", "deb", "x")
        )
