import StringIO

from virtualbricks import console, errors
from virtualbricks.tests import unittest, stubs


class TestProtocol(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.stdout = StringIO.StringIO()
        self.stdout.sendLine = self.stdout.write

    def parse(self, cmd):
        return console.parse(self.factory, cmd, self.stdout)

    def get_value(self):
        ret = self.stdout.getvalue()
        self.stdout.seek(0)
        self.stdout.truncate()
        return ret

    def test_new_brick(self):
        self.parse("new stub test")
        self.assertEquals(len(self.factory.bricks), 1)
        self.assertEquals(self.factory.bricks[0].name, "test")
        self.assertEquals(self.factory.bricks[0].get_type(), "Stub")
        self.parse("new stub t+")
        self.assertEqual(self.get_value(),
                         "Name must contains only letters, "
                         "numbers, underscores, hyphens and points, t+")
        cmd = "new stub"
        self.parse(cmd)
        self.assertEqual(self.get_value(), "invalid command %s" % cmd)
        cmd = "new"
        self.parse(cmd)
        self.assertEqual(self.get_value(), "invalid command %s" % cmd)

    def test_new_event(self):
        self.parse("new event test_event")
        self.assertEquals(len(self.factory.events), 1)
        self.assertEquals(self.factory.events[0].name, "test_event")
        self.assertEquals(self.factory.events[0].get_type(), "Event")
