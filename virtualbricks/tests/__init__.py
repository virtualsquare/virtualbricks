import os
import types
import functools

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


def backup_settings(lst):
    return dict((k, settings.get(k)) for k in lst)


def restore_settings(olds):
    for k, v in olds.iteritems():
        settings.set(k, v)


def patch_settings(suite, **kwds):
    olds = backup_settings(kwds.keys())
    suite.addCleanup(restore_settings, olds)
    for k, v in kwds.iteritems():
        settings.set(k, v)
