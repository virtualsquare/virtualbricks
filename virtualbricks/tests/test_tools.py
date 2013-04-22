from virtualbricks import tools
from virtualbricks.tests import unittest


class MockLock(object):

    def __init__(self):
        self.c = 0

    def __enter__(self):
        self.c += 1

    def __exit__(self, exc_type, exc_value, traceback):
        pass


class TestSynchronize(unittest.TestCase):

    def setUp(self):
        self.lock = MockLock()
        old, tools._lock = tools._lock, self.lock
        def unpatch_lock():
            tools._lock = old
        self.addCleanup(unpatch_lock)

    def test_sincronized(self):
        foo_s = tools.synchronized(lambda: None)
        foo_s()
        self.assertEqual(self.lock.c, 1)
        foo_s = tools.synchronized(tools._lock)(lambda: None)
        foo_s()
        self.assertEqual(self.lock.c, 2)

    def test_sincronize_with(self):
        lock = MockLock()
        foo_s = tools.synchronize_with(lock)(lambda: None)
        foo_s()
        self.assertEqual(lock.c, 1)
        foo_s()
        self.assertEqual(lock.c, 2)

