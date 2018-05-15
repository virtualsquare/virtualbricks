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
import six

from twisted.python import log, filepath

from virtualbricks import configfile, _configparser
from virtualbricks.tests import unittest, stubs, LoggingObserver, Skip

def file_text_from_bytes(filepath):
    return filepath.getContent().decode('utf8')
def file_bytes_from_text(content):
    return content.encode('utf-8')
CONFIG1 = """
[Image:martin]
path=/vimages/vtatpa.martin.qcow2

[Qemu:sender]
hda=martin
kvm=*
name=sender
privatehda=*
tdf=*

[Wirefilter:wf]

[Switch:sw1]

link|sender|sw1_port|rtl8139|00:aa:79:71:be:61
"""


class TestConfigFile(unittest.TestCase):

    def add_observer(self):
        observer = LoggingObserver()
        log.addObserver(observer.emit)
        self.addCleanup(log.removeObserver, observer.emit)
        return observer

    def create_config_backup(self):
        config = filepath.FilePath(self.mktemp())
        config.touch()
        backup = config.sibling(config.basename() + "~")
        return config, backup

    def test_exported_interface(self):
        """
        Test the exported interface. If the interface change, this test
        should change accordingly.
        """

        self.assertEqual(configfile.__all__,
            ["BrickBuilder", "ConfigFile", "EventBuilder", "ImageBuilder",
             "LinkBuilder", "SockBuilder", "log_events", "restore",
             "safe_save", "save"])

    def test_exported_log_events(self):
        """
        Test the log events exported by configfile. If the list of events
        changes, this test should change accordingly.
        """
        self.assertEqual(configfile.log_events,
            [configfile.link_type_error, configfile.brick_not_found,
             configfile.sock_not_found, configfile.link_added,
             configfile.cannot_save_backup, configfile.project_saved,
             configfile.cannot_restore_backup, configfile.backup_restored,
             configfile.image_found, configfile.skip_image,
             configfile.skip_image_noa, configfile.config_dump,
             configfile.open_project, configfile.config_save_error])

    def test_restore_backup_does_not_exists(self):
        """Try to restore a backup that does not exists."""

        observer = self.add_observer()
        config, backup = self.create_config_backup()
        configfile.restore_backup(config, backup)
        self.assertEqual(len(observer.msgs), 1)
        self.assertFalse(observer.msgs[0]["isError"])
        self.assertFalse(config.sibling(config.basename() + ".back").exists())
        self.assertTrue(config.exists())

    def test_restore_backup(self):
        """Restore a backup."""

        # observer = self.add_observer()
        config, backup = self.create_config_backup()
        backup.touch()
        configfile.restore_backup(config, backup)
        self.assertFalse(config.sibling(config.basename() + ".back").exists())
        self.assertFalse(backup.exists())
        self.assertTrue(config.exists())

    def test_backup_context(self):
        filename = self.mktemp()
        original = filepath.FilePath(filename)
        with open(original.path,"wt") as fp:
            fp.write("a")
        fbackup = original.sibling(original.basename() + "~")
        self.assertFalse(fbackup.exists())
        with configfile.backup(original, fbackup):
            self.assertTrue(fbackup.exists())
            self.assertTrue(file_text_from_bytes(original), fbackup.getContent())
        self.assertFalse(fbackup.exists())

    def test_save(self):
        """Save a project."""

        factory = stubs.Factory()
        factory.new_brick("switch", "sw")
        fp = filepath.FilePath(self.mktemp())
        config = configfile.ConfigFile()
        config.save(factory, fp)
        self.assertEqual(file_text_from_bytes(fp), "[Switch:sw]\n\n")

    def test_restore(self):
        """Restore a project."""
	#NB -> Twisted FilePath returns files opened in binary mode
        factory = stubs.Factory()
        fp = filepath.FilePath(self.mktemp())
        fp.setContent(file_bytes_from_text(CONFIG1))
        config = configfile.ConfigFile()
        config.restore(factory, fp)
        self.assertIsNotNone(factory.get_brick_by_name("sender"))

    def _add_observer(self, event=None):
        observer = LoggingObserver()
        if event:
            self.addCleanup(event.tap(observer, configfile.logger.publisher))
        return observer

    def test_sock_builder_does_not_find_brick(self):
        """
        The sock builder does not find the sock owner, no exception is raised
        and a warning is emitted.
        """

        BRICKNAME = "new_brick"
        observer = self._add_observer(configfile.brick_not_found)
        link = _configparser.Link("sock", BRICKNAME, "name", "model", "mac")
        configfile.SockBuilder().load_from(stubs.FactoryStub(), link)
        self.assertEqual(len(observer), 1)
        self.assertEqual(observer[0]["brick"], BRICKNAME)

    def test_sock_builder(self):
        """Create a sock from a Link object."""

        BRICKNAME = "new_brick"
        factory = stubs.FactoryStub()
        brick = factory.new_brick("vm", BRICKNAME)
        link = _configparser.Link("sock", BRICKNAME, None, None, None)
        configfile.SockBuilder().load_from(factory, link)
        self.assertEqual(len(factory.socks), 1)
        self.assertIs(factory.socks[0].brick, brick)

    def test_link_builder_brick_not_found(self):
        """
        The sock builder does not find the sock owner, no exception is raised
        and a warning is emitted.
        """

        BRICKNAME = "new_brick"
        observer = self._add_observer(configfile.brick_not_found)
        link = _configparser.Link("link", BRICKNAME, "name", "model", "mac")
        configfile.LinkBuilder().load_from(stubs.FactoryStub(), link)
        self.assertEqual(len(observer), 1)
        self.assertEqual(observer[0]["brick"], BRICKNAME)

    def test_link_builder_sock_not_found(self):
        """
        The link builder does not find the sock, no exception is raised and a
        warning is emitted.
        """

        BRICKNAME = "new_brick"
        SOCKNAME = "nonexistent_sock"
        factory = stubs.FactoryStub()
        observer = self._add_observer(configfile.sock_not_found)
        brick = factory.new_brick("vm", BRICKNAME)
        self.assertEqual(len(brick.plugs), 0)
        link = _configparser.Link("link", BRICKNAME, SOCKNAME, "model", "mac")
        configfile.LinkBuilder().load_from(factory, link)
        self.assertEqual(len(brick.plugs), 0)
        self.assertEqual(len(observer), 1)
        self.assertEqual(observer[0]["sockname"], SOCKNAME)

    def test_link_builder(self):
        """Create a link from a Link object."""

        BRICKNAME = "new_brick"
        factory = stubs.FactoryStub()
        brick = factory.new_brick("vm", BRICKNAME)
        brick.add_sock()
        self.assertEqual(len(brick.plugs), 0)
        NICKNAME = "{0}_sock_eth0".format(BRICKNAME)
        link = _configparser.Link("link", BRICKNAME, NICKNAME, "model", "mac")
        configfile.LinkBuilder().load_from(factory, link)
        self.assertEqual(len(brick.plugs), 1)


class TestParser(unittest.TestCase):

    def test_iter(self):
        sio = six.StringIO(CONFIG1)
        parser = _configparser.Parser(sio)
        itr = iter(parser)
        sec1 = next(itr)
        self.assertEqual(sec1.type, "Image")
        self.assertEqual(sec1.name, "martin")
        sec2 = next(itr)
        self.assertEqual(sec2.type, "Qemu")
        self.assertEqual(sec2.name, "sender")
        sec3 = next(itr)
        self.assertEqual(sec3.type, "Wirefilter")
        self.assertEqual(sec3.name, "wf")
        sec4 = next(itr)
        self.assertEqual(sec4.type, "Switch")
        self.assertEqual(sec4.name, "sw1")
        link = next(itr)
        self.assertEqual(link, ("link", "sender", "sw1_port", "rtl8139",
                                "00:aa:79:71:be:61"))

    def test_link_with_minus(self):
        """
        Bricks' name can contains the following characters (in regex notation):
        [\w.-]. Check that the parser parse correctly the links.
        """

        line = "link|vm1-ng|switchwrapper_port|rtl8139|00:aa:1a:a2:b8:ec"
        parser = _configparser.Parser(six.StringIO(line))
        expected = tuple(line.split("|"))
        self.assertEqual(list(parser), [expected])

    def test_name_does_not_start_with_letter(self):
        """Bricks' name must start with a letter."""

        line = "link|1-brick|switchwrapper_port|rtl8139|00:aa:1a:a2:b8:ec"
        parser = _configparser.Parser(six.StringIO(line))
        self.assertEqual(list(parser), [])

    def test_hostonly_link(self):
        """Test a hostonly link."""

        line = "link|vm|_hostonly|rtl8139|00:11:22:33:44:55"
        parser = _configparser.Parser(six.StringIO(line))
        expected = tuple(line.split("|"))
        self.assertEqual(list(parser), [expected])

    def test_link_ends_with_new_line(self):
        """
        Where links are parsed, a new line character can appears at the end of
        the line.
        """

        line = "link|vm|_hostonly|rtl8139|00:11:22:33:44:55\n"
        parser = _configparser.Parser(six.StringIO(line))
        expected = tuple(line[:-1].split("|"))
        self.assertEqual(list(parser), [expected])


OLD_CONFIG_FILE = """
[Project:/home/user/.virtualbricks.vbl]
id=1
[DiskImage:vtatpa.qcow2]
path=@@IMAGEPATH@@
[Qemu:test1]
tdf=
loadvm=
rtc=
kernel=
pon_vbevent=
ram=64
sdl=
privatefdb=
privatefda=
noacpi=
keyboard=it
portrait=
privatehdd=
serial=
privatehda=*
usbdevlist=
privatehdc=
privatehdb=
kvmsmem=1
soundhw=
kvmsm=
boot=
vga=
kernelenbl=
smp=1
machine=
gdbport=1234
device=
basemtdblock=
snapshot=*
icon=
initrdenbl=
gdb=
basefda=
basefdb=
vnc=
basehdd=
kvm=*
basehdb=
basehdc=
basehda=vtatpa.qcow2
privatemtdblock=
cdrom=
deviceen=
kopt=
vncN=1
novga=
poff_vbevent=
name=test1
argv0=qemu-system-i386
initrd=
usbmode=
cpu=
cdromen=
[SwitchWrapper:sw1]
numports=32
pon_vbevent=
poff_vbevent=
path=/var/run/switch/sck
"""


def is_section(obj):
    return isinstance(obj, _configparser.Section)


class FakeSection:

    def __init__(self, type, name):
        self.type = type
        self.name = name

    def __eq__(self, other):
        return other.__eq__(self)

    def __ne__(self, other):
        return not self.__eq__(other)


class SectionCmp:

    def __init__(self, section):
        self.section = section

    @property
    def type(self):
        return self.section.type

    @property
    def name(self):
        return self.section.name

    def __eq__(self, other):
        return self.type == other.type and self.name == other.name

    def __ne__(self, other):
        return not self.__eq__(other)


def get_section(parser, type, name):
    for obj in parser:
        if is_section(obj) and obj.type == type and obj.name == name:
            return obj


class TestParseOldConfig(unittest.TestCase):

    def setUp(self):
        self.image = self.mktemp()
        content = OLD_CONFIG_FILE.replace("@@IMAGEPATH@@", self.image, 1)
        self.fp = six.StringIO(content)

    def test_sections(self):
        parser = _configparser.Parser(self.fp)
        sections = [
            FakeSection("Project", "/home/user/.virtualbricks.vbl"),
            FakeSection("DiskImage", "vtatpa.qcow2"),
            FakeSection("Qemu", "test1"),
            FakeSection("SwitchWrapper", "sw1"),
        ]
        self.assertEqual([SectionCmp(s) for s in parser if is_section(s)],
                         sections)

    def test_disk_image(self):
        parser = _configparser.Parser(self.fp)
        diskimage = get_section(parser, "DiskImage", "vtatpa.qcow2")
        self.assertIsNot(diskimage, None)
        self.assertEqual(dict(diskimage), {"path": self.image})

    def test_switch_wrapper(self):
        parser = _configparser.Parser(self.fp)
        sw = get_section(parser, "SwitchWrapper", "sw1")
        self.assertIsNot(sw, None)
        self.assertEqual(dict(sw), {"numports": "32", "pon_vbevent": "",
                                    "poff_vbevent": "",
                                    "path": "/var/run/switch/sck"})


class TestLoadOldConfig(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.Factory()
        fp = filepath.FilePath(self.mktemp())
        self.image = self.mktemp()
        filepath.FilePath(self.image).touch()
        filecontent = OLD_CONFIG_FILE.replace(
            "@@IMAGEPATH@@", self.image, 1).encode('ascii')
        fp.setContent(filecontent)
        configfile.restore(self.factory, fp)

    def test_sw(self):
        """Test that the switchwrapper is resumed with right values."""

        sw = self.factory.get_brick_by_name("sw1")
        self.assertIsNotNone(sw)
        self.assertEqual(sw.get("path"), "/var/run/switch/sck")
        self.assertEqual(sw.get("pon_vbevent"), "")
        self.assertEqual(sw.get("poff_vbevent"), "")

    def test_vm(self):
        """Test that the virtual machine is resumed with right values."""

        vm = self.factory.get_brick_by_name("test1")
        self.assertIsNotNone(vm)
        self.assertEqual(vm.get("keyboard"), "it")
        self.assertEqual(vm.get("privatehda"), True)
        self.assertEqual(vm.get("kvm"), True)
        self.assertEqual(vm.get("snapshot"), True)
        self.assertEqual(vm.get("usbdevlist"), [])
        self.assertEqual(vm.get("hda").image.path, os.path.abspath(self.image))
        self.assertEqual(vm.get("pon_vbevent"), "")
        self.assertEqual(vm.get("poff_vbevent"), "")

    def test_image(self):
        """Test that all the disk images are restored."""

        image = self.factory.get_image_by_name("vtatpa.qcow2")
        self.assertIsNotNone(image)
