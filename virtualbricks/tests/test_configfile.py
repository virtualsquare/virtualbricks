import os
import StringIO

from twisted.python import log, filepath

from virtualbricks import configfile, configparser
from virtualbricks.tests import unittest, stubs


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

    def test_restore_backup(self):
        observer = stubs.LoggingObserver()
        log.addObserver(observer.emit)
        self.addCleanup(log.removeObserver, observer.emit)
        filename = filepath.FilePath(self.mktemp())
        filename.touch()
        fbackup = filename.sibling(filename.basename() + "~")
        configfile.restore_backup(filename, fbackup)
        self.assertEqual(len(observer.msgs), 1)
        self.assertFalse(observer.msgs[0]["isError"])
        fbackup.touch()
        self.assertTrue(fbackup.isfile())
        configfile.restore_backup(filename, fbackup)
        self.assertFalse(os.path.isfile(filename.path + ".back"))
        self.assertEqual(len(observer.msgs), 3)
        self.assertTrue(observer.msgs[-1]["isError"])
        self.assertFalse(fbackup.isfile())

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
