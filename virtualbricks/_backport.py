# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Backport module for twisted 12.0 (debian)
"""

import sys

from twisted.python import log
from twisted.python.failure import Failure
from twisted.internet.error import ReactorNotRunning


def react(main, argv, _reactor=None):
    """
    Call C{main} and run the reactor until the L{Deferred} it returns fires.

    This is intended as the way to start up an application with a well-defined
    completion condition.  Use it to write clients or one-off asynchronous
    operations.  Prefer this to calling C{reactor.run} directly, as this
    function will also:

      - Take care to call C{reactor.stop} once and only once, and at the right
        time.
      - Log any failures from the C{Deferred} returned by C{main}.
      - Exit the application when done, with exit code 0 in case of success and
        1 in case of failure. If C{main} fails with a C{SystemExit} error, the
        code returned is used.

    @param main: A callable which returns a L{Deferred}.  It should take as
        many arguments as there are elements in the list C{argv}.

    @param argv: A list of arguments to pass to C{main}.

    @param _reactor: An implementation detail to allow easier unit testing.  Do
        not supply this parameter.

    @since: 12.3
    """
    if _reactor is None:
        from twisted.internet import reactor as _reactor
    finished = main(_reactor, *argv)
    codes = [0]

    stopping = []
    _reactor.addSystemEventTrigger('before', 'shutdown', stopping.append, True)

    def stop(result, stopReactor):
        if stopReactor:
            try:
                _reactor.stop()
            except ReactorNotRunning:
                pass

        if isinstance(result, Failure):
            if result.check(SystemExit) is not None:
                code = result.value.code
            else:
                log.err(result, "main function encountered error")
                code = 1
            codes[0] = code

    def cbFinish(result):
        if stopping:
            stop(result, False)
        else:
            _reactor.callWhenRunning(stop, result, True)

    finished.addBoth(cbFinish)
    _reactor.run()
    sys.exit(codes[0])


__all__ = ['react']
