import os
import types
import functools
import difflib

from twisted.trial import unittest
from twisted.python import failure

from virtualbricks import settings

__builtins__["_"] = str
TEST_THREADS = 0x01
TEST_DEPLOYMENT = 0x02


def should_test_threads():
    return int(os.environ.get("VIRTUALBRICKS_TESTS", 0)) & TEST_THREADS


def should_test_deployment():
    return int(os.environ.get("VIRTUALBRICKS_TESTS", 0)) & TEST_DEPLOYMENT


def _id(obj):
    return obj


def Skip(reason):
    # This decorator is camelcase because otherwise importing it cause all the
    # tests to skip because trial look deep in test method, class, module
    def decorator(test_item):
        if not isinstance(test_item, (type, types.ClassType)):
            @functools.wraps(test_item)
            def skip_wrapper(*args, **kwargs):
                raise unittest.SkipTest(reason)
            test_item = skip_wrapper

        test_item.skip = reason
        return test_item
    return decorator


def skipIf(condition, reason):
    if condition:
        return Skip(reason)
    return _id


def skipUnless(condition, reason):
    if not condition:
        return Skip(reason)
    return _id


# from __future__ import (twisted.trail.unittest.TestCase.successResultOf,
#                         twisted.trail.unittest.TestCase.failureResultOf)
def successResultOf(self, deferred):
    """
    Return the current success result of C{deferred} or raise
    C{self.failException}.

    @param deferred: A L{Deferred<twisted.internet.defer.Deferred>} which
        has a success result.  This means
        L{Deferred.callback<twisted.internet.defer.Deferred.callback>} or
        L{Deferred.errback<twisted.internet.defer.Deferred.errback>} has
        been called on it and it has reached the end of its callback chain
        and the last callback or errback returned a non-L{failure.Failure}.
    @type deferred: L{Deferred<twisted.internet.defer.Deferred>}

    @raise SynchronousTestCase.failureException: If the
        L{Deferred<twisted.internet.defer.Deferred>} has no result or has a
        failure result.

    @return: The result of C{deferred}.
    """
    result = []
    deferred.addBoth(result.append)
    if not result:
        self.fail(
            "Success result expected on %r, found no result instead" % (
                deferred,))
    elif isinstance(result[0], failure.Failure):
        self.fail(
            "Success result expected on %r, "
            "found failure result instead:\n%s" % (
                deferred, result[0].getTraceback()))
    else:
        return result[0]


def failureResultOf(self, deferred, *expectedExceptionTypes):
    """
    Return the current failure result of C{deferred} or raise
    C{self.failException}.

    @param deferred: A L{Deferred<twisted.internet.defer.Deferred>} which
        has a failure result.  This means
        L{Deferred.callback<twisted.internet.defer.Deferred.callback>} or
        L{Deferred.errback<twisted.internet.defer.Deferred.errback>} has
        been called on it and it has reached the end of its callback chain
        and the last callback or errback raised an exception or returned a
        L{failure.Failure}.
    @type deferred: L{Deferred<twisted.internet.defer.Deferred>}

    @param expectedExceptionTypes: Exception types to expect - if
        provided, and the the exception wrapped by the failure result is
        not one of the types provided, then this test will fail.

    @raise SynchronousTestCase.failureException: If the
        L{Deferred<twisted.internet.defer.Deferred>} has no result, has a
        success result, or has an unexpected failure result.

    @return: The failure result of C{deferred}.
    @rtype: L{failure.Failure}
    """
    result = []
    deferred.addBoth(result.append)
    if not result:
        self.fail(
            "Failure result expected on %r, found no result instead" % (
                deferred,))
    elif not isinstance(result[0], failure.Failure):
        self.fail(
            "Failure result expected on %r, "
            "found success result (%r) instead" % (deferred, result[0]))
    elif (expectedExceptionTypes and
          not result[0].check(*expectedExceptionTypes)):
        expectedString = " or ".join([
            '.'.join((t.__module__, t.__name__)) for t in
            expectedExceptionTypes])

        self.fail(
            "Failure of type (%s) expected on %r, "
            "found type %r instead: %s" % (
                expectedString, deferred, result[0].type,
                result[0].getTraceback()))
    else:
        return result[0]


def restore_settings(olds):
    for k, v in olds.iteritems():
        settings.set(k, v)


def patch_settings(suite, **kwds):
    olds = dict((k, settings.get(k)) for k in kwds.iterkeys())
    suite.addCleanup(restore_settings, olds)
    suite.patch(settings, "store", lambda: None)
    for k, v in kwds.iteritems():
        settings.set(k, v)


def pformat_tree(tree, sep="", indent=2):
    lst = []
    n_cols = tree.get_n_columns()
    pformat_subtree(tree, tree.get_iter_root(), lst, n_cols, sep, indent, 0)
    return lst


def pformat_subtree(tree, itr, lst, columns, sep="", indent=2, level=0):
    while itr:
        row = tree.get(itr, *range(columns))
        lst.append("{0}{1}{2}".format(indent * level * " ", sep, row))
        pformat_subtree(tree, tree.iter_children(itr), lst, columns, sep,
                        indent, level + 1)
        itr = tree.iter_next(itr)


class GtkTestCase(unittest.TestCase):

    def assert_tree_model_equal(self, tree1, tree2, msg=None):
        self.assertEqual(tree1.get_n_columns(), tree2.get_n_columns())
        for i in range(tree1.get_n_columns()):
            self.assertEqual(tree1.get_column_type(i),
                             tree2.get_column_type(i))
        root1 = tree1.get_iter_root()
        root2 = tree2.get_iter_root()
        self.assert_subtree_model_equal(tree1, root1, tree2, root2, msg)

    def assert_subtree_model_equal(self, tree1, itr1, tree2, itr2, msg=None):
        self.assertEqual(type(itr1), type(itr2))
        while itr1 and itr2:
            if tuple(tree1[itr1]) != tuple(tree2[itr2]):
                diff = "\n".join(difflib.ndiff(pformat_tree(tree1),
                                               pformat_tree(tree2)))
                default = "Trees are different:\n" + diff
                self.fail(msg or default)
            self.assertEqual(tuple(tree1[itr1]), tuple(tree2[itr2]))
            self.assert_subtree_model_equal(tree1, tree1.iter_children(itr1),
                                            tree2, tree2.iter_children(itr2))
            itr1 = tree1.iter_next(itr1)
            itr2 = tree2.iter_next(itr2)

    def assert_page_complete(self, assistant, page_num, msg=""):
        page = assistant.get_nth_page(page_num)
        self.assertTrue(assistant.get_page_complete(page), msg)

    def assert_page_not_complete(self, assistant, page_num, msg=""):
        page = assistant.get_nth_page(page_num)
        self.assertFalse(assistant.get_page_complete(page), msg)

    def assert_visible(self, widget, msg=""):
        if not msg:
            msg = ("widget {0} is not visible when it is expected it "
                   "is.".format(widget))
        self.assertTrue(widget.get_visible(), msg)

    def assert_not_visible(self, widget, msg=""):
        if not msg:
            msg = ("widget {0} is visible when it is expected it is "
                   "not.".format(widget))
        self.assertFalse(widget.get_visible(), msg)

    def assert_current_page(self, assistant, num, msg=""):
        curr = assistant.get_current_page()
        if not msg:
            msg = ("Wrong assistant current page. Actual page is {0}, "
                   "expected {1}".format(curr, num))
        self.assertEqual(num, curr, msg)
