import time
import threading

from virtualbricks import errors, brickfactory
from virtualbricks.tests import unittest, must_test_threads, stubs


class TestFactory(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()

    def test_reset_config(self):
        self.factory.reset()
        self.assertEquals(self.factory.bricks, [])
        self.assertEquals(self.factory.events, [])
        self.factory.new_brick("stub", "test_brick")
        self.factory.reset()
        self.assertEquals(self.factory.bricks, [])
        self.assertEquals(self.factory.events, [])

    def test_newbrick(self):
        self.assertRaises(errors.InvalidNameError, self.factory.newbrick, "stub",
                          "")
        self.factory.newbrick("stub", "test_brick")
        self.assertRaises(errors.InvalidNameError, self.factory.newbrick, "stub",
                          "test_brick")

    def test_newevent(self):
        self.assertRaises(errors.InvalidNameError, self.factory.newevent, "event",
                          "")
        self.factory.newevent("event", "test_event")
        self.assertRaises(errors.InvalidNameError, self.factory.newevent, "event",
                          "test_event")
        self.assertTrue(self.factory.newevent("Event", "event1"))
        self.assertFalse(self.factory.newevent("eVeNt", "event2"))


@unittest.skipUnless(must_test_threads(), "threads tests non enabled")
class TestThreadingLocking(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()

    def test_configfile_synchronized(self):
        st1 = [False]
        st2 = [None]

        def save1(_):
            st1[0] = True
            time.sleep(0.02)
            st1[0] = False

        def save2():
            time.sleep(0.01)
            stubs.ConfigFileStub(self.factory).restore(None)
            st2[0] = st1[0]

        cfs = stubs.ConfigFileStub(self.factory, save1)
        t = threading.Thread(target=save2)
        t.start()
        cfs.save(None)
        t.join()
        self.assertIs(st2[0], False)

    def test_lock(self):
        lock = self.factory.lock()
        try:
            acquired = lock.acquire()
            self.assertTrue(acquired)
            self.assertEqual(lock._RLock__count, 1)
        finally:
            lock.release()
        with self.factory.lock():
            self.assertEqual(lock._RLock__count, 1)
