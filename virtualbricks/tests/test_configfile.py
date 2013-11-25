import os
import StringIO

from twisted.python import log, filepath

from virtualbricks import configfile, configparser
from virtualbricks.tests import unittest, stubs, LoggingObserver


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
        with original.create() as fp:
            fp.write("a")
        fbackup = original.sibling(original.basename() + "~")
        self.assertFalse(fbackup.exists())
        with configfile.backup(original, fbackup):
            self.assertTrue(fbackup.exists())
            self.assertTrue(original.getContent(), fbackup.getContent())
        self.assertFalse(fbackup.exists())

    def test_save(self):
        def save_to_string(f, fileobj):
            self.assertTrue(filename)
            self.assertTrue(os.path.exists(fileobj.name))
            tmpfile.append(fileobj.name)

        config = configfile.ConfigFile()
        config.save_to = save_to_string
        filename = self.mktemp()
        tmpfile = []
        config.save(None, filename)
        self.assertFalse(os.path.exists(tmpfile[0]))

    def test_restore(self):
        config = configfile.ConfigFile()
        self.assertRaises(IOError, config.restore, None, self.mktemp())

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
        link = configparser.Link("sock", BRICKNAME, "name", "model", "mac")
        configfile.SockBuilder().load_from(stubs.FactoryStub(), link)
        self.assertEqual(len(observer), 1)
        self.assertEqual(observer[0]["brick"], BRICKNAME)

    def test_sock_builder(self):
        """Create a sock from a Link object."""

        BRICKNAME = "new_brick"
        factory = stubs.FactoryStub()
        brick = factory.new_brick("vm", BRICKNAME)
        link = configparser.Link("sock", BRICKNAME, None, None, None)
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
        link = configparser.Link("link", BRICKNAME, "name", "model", "mac")
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
        link = configparser.Link("link", BRICKNAME, SOCKNAME, "model", "mac")
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
        link = configparser.Link("link", BRICKNAME, NICKNAME, "model", "mac")
        configfile.LinkBuilder().load_from(factory, link)
        self.assertEqual(len(brick.plugs), 1)


class TestParser(unittest.TestCase):

    def test_iter(self):
        sio = StringIO.StringIO(CONFIG1)
        parser = configparser.Parser(sio)
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
        parser = configparser.Parser(StringIO.StringIO(line))
        expected = tuple(line.split("|"))
        self.assertEqual(list(parser), [expected])

    def test_name_does_not_start_with_letter(self):
        """Bricks' name must start with a letter."""

        line = "link|1-brick|switchwrapper_port|rtl8139|00:aa:1a:a2:b8:ec"
        parser = configparser.Parser(StringIO.StringIO(line))
        self.assertEqual(list(parser), [])

    def test_hostonly_link(self):
        """Test a hostonly link."""

        line = "link|vm|_hostonly|rtl8139|00:11:22:33:44:55"
        parser = configparser.Parser(StringIO.StringIO(line))
        expected = tuple(line.split("|"))
        self.assertEqual(list(parser), [expected])

    def test_link_ends_with_new_line(self):
        """
        Where links are parsed, a new line character can appears at the end of
        the line.
        """

        line = "link|vm|_hostonly|rtl8139|00:11:22:33:44:55\n"
        parser = configparser.Parser(StringIO.StringIO(line))
        expected = tuple(line[:-1].split("|"))
        self.assertEqual(list(parser), [expected])
