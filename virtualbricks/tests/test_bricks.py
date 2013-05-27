import os
import errno
import signal
import sys
import warnings
import StringIO

from virtualbricks import base, bricks, errors
from virtualbricks.tests import unittest, stubs, echo_e, sleep_pid


class TestBricks(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.brick = stubs.BrickStub(self.factory, "test")

    def test_get_cbset(self):
        cbset = self.brick.get_cbset("supercalifragilistichespiralidoso")
        self.assertIs(cbset, None)

    def test_warnings(self):
        with warnings.catch_warnings(record=True)as w:
            warnings.simplefilter("always")
            self.brick.on_config_changed()
            self.assertEqual(len(w), 1)
            self.assertEquals(w[0].category, DeprecationWarning)

    def test_poweron(self):
        self.assertRaises(errors.BadConfigError, self.brick.poweron)
        self.brick.configured = lambda: True
        self.brick.poweron()

    def test_args(self):
        self.assertEqual(self.brick.build_cmd_line(), ["-a", "arg1", "-c",
                                                       "-d", "d"])
        self.assertEqual(self.brick.args(), ["true", "-a", "arg1", "-c", "-d",
                                             "d"])


class ProcessMixin(object):

    stdout = ""
    stderr = ""

    def out(self, data):
        self.stdout = data

    def err(self, data):
        self.stderr = data


class Process(ProcessMixin, bricks.Process):
    pass


class BaseTestProcess(object):

    def _get_kill_signals(self):
        return ((signal.SIGTERM, self.process_factory.terminate),
                (signal.SIGKILL, self.process_factory.kill))

    def test_kill(self):
        for signo, func in self._get_kill_signals():
            pd = self.process_factory(self._get_kill_program())
            pd.start()
            pd.join(0.01)
            func(pd)
            pd.join()
            self.assertIsNot(pd._pd, None)
            self.assertEqual(pd.stdout, "")
            self.assertEqual(pd.stderr, "")
            self.assertEqual(pd.poll(), -signo)
            with self.assertRaises(OSError) as cm:
                os.waitpid(pd._pd.pid, 0)
            self.assertEqual(cm.exception.errno, errno.ECHILD)


class TestProcess(BaseTestProcess, unittest.TestCase):

    process_factory = Process

    def _get_kill_program(self):
        return ["sleep", "1"]

    def test_simple(self):
        pd = self.process_factory(["true"])
        pd.start()
        pd.join()
        self.assertIsNot(pd._pd, None)
        self.assertEqual(pd.stdout, "")
        self.assertEqual(pd.stderr, "")
        self.assertEqual(pd._pd.returncode, 0)
        self.assertEqual(pd._raw, {})
        with self.assertRaises(OSError) as cm:
            os.waitpid(pd._pd.pid, 0)
        self.assertEqual(cm.exception.errno, errno.ECHILD)

    def test_out(self):
        pd = self.process_factory(["echo", "hello world"])
        pd.start()
        pd.join()
        self.assertIsNot(pd._pd, None)
        self.assertEqual(pd.stdout, "hello world\n")
        self.assertEqual(pd.stderr, "")
        self.assertEqual(pd._pd.returncode, 0)
        with self.assertRaises(OSError) as cm:
            os.waitpid(pd._pd.pid, 0)
        self.assertEqual(cm.exception.errno, errno.ECHILD)

    @unittest.skipIf(sys.executable is None, "sys.executable unavailable")
    def test_err(self):
        echo = os.path.abspath(echo_e.__file__)
        pd = self.process_factory([sys.executable, echo, "hello world"])
        pd.start()
        pd.join()
        self.assertIsNot(pd._pd, None)
        self.assertEqual(pd.stdout, "")
        self.assertEqual(pd.stderr, "hello world\n")
        self.assertEqual(pd._pd.returncode, 0)
        with self.assertRaises(OSError) as cm:
            os.waitpid(pd._pd.pid, 0)
        self.assertEqual(cm.exception.errno, errno.ECHILD)

    def test_terminate_on_a_terminated_child(self):
        pd = self.process_factory(["true"])
        pd.start()
        pd.join()
        with self.assertRaises(OSError) as cm:
            pd.terminate()
        self.assertEqual(cm.exception.errno, errno.ESRCH)


class Sudo(bricks.Sudo):

    process_factory = Process


class TestSudoProcess(BaseTestProcess, unittest.TestCase):

    process_factory = Sudo

    def _get_kill_program(self):
        return [sys.executable, os.path.abspath(sleep_pid.__file__), "1"]

    @unittest.skipIf(sys.executable is None, "sys.executable unavailable")
    def test_terminate_on_a_terminated_child(self):
        args = [sys.executable, os.path.abspath(sleep_pid.__file__), "0"]
        pd = self.process_factory(args)
        pd.start()
        pd.join()
        self.assertEqual(pd.terminate(), 1)

    @unittest.skipIf(sys.executable is None, "sys.executable unavailable")
    def test_kill(self):
        super(TestSudoProcess, self).test_kill()


class Brick(stubs.BrickStub):

    class config_factory(base.NewConfig):

        parameters = {"numports": base.SpinInt(32, 1, 128),
                      "hub": base.Boolean(False),
                      "fstp": base.Boolean(False),
                      "pon_vbevent": bricks.String(""),
                      "poff_vbevent": bricks.String("")}


class TestConfig(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.brick = Brick(self.factory, "test")

    def test_new_config(self):
        cfg = self.brick.cfg
        for name, typ in cfg.parameters.iteritems():
            self.assertIn(name, cfg)
            self.assertEqual(typ.default, cfg[name])
        numports, hub, fstp = [cfg.parameters[n] for n in ("numports", "hub",
                                                           "fstp")]
        self.assertEqual(numports.to_string(cfg["numports"]), "32")
        self.assertEqual(hub.to_string(cfg["hub"]), "")
        self.assertEqual(fstp.to_string(cfg["fstp"]), "")
        self.assertTrue(hub.from_string("*"))

    def test_save_to(self):
        sio = StringIO.StringIO()
        cfg = self.brick.cfg
        cfg.save_to(sio)
        out = ""
        self.assertEqual(sio.getvalue(), out)
        cfg["numports"] = 33
        cfg["fstp"] = True
        out = "fstp=*\nnumports=33\n"
        sio.truncate(0)
        cfg.save_to(sio)
        self.assertEqual(sio.getvalue(), out)

    def test_load_from(self):
        cfg = self.brick.cfg
        sio = StringIO.StringIO()
        sio.write("fstp=*\nnumports=33\n")
        sio.seek(0)
        self.assertEqual(cfg["numports"], 32)
        self.assertEqual(cfg["fstp"], False)
        cfg.load_from(sio)
        self.assertEqual(cfg["numports"], 33)
        self.assertEqual(cfg["fstp"], True)

        # a comment
        sio.truncate(0)
        sio.write("#numports=1")
        sio.seek(0)
        cfg.load_from(sio)
        self.assertEqual(cfg["numports"], 33)

        # a new section
        sio.truncate(0)
        sio.write("[Stub:test_stub]\nfstp=\nnumports=32\n")
        sio.seek(0)
        cfg.load_from(sio)
        self.assertEqual(cfg["numports"], 33)
        self.assertEqual(cfg["fstp"], True)
        self.assertEqual(sio.tell(), 0)

        # empty file
        sio.truncate(0)
        cfg.load_from(sio)
        self.assertEqual(cfg["numports"], 33)
        self.assertEqual(cfg["fstp"], True)
        self.assertEqual(sio.tell(), 0)

    def test_set(self):
        self.brick.cfg.set("numports=33")
        self.assertEqual(self.brick.cfg.numports, "33")

    def test_set_obj(self):
        cfg = self.brick.cfg
        cfg.set_obj("numports", 33)
        self.assertEqual(cfg.numports, "33")
        self.assertEqual(cfg["numports"], 33)

    def test_set_running(self):
        state = []

        class _Brick(Brick):

            def cbset_numports(self, value):
                state.append(value)

        brick = _Brick(self.factory, "test")
        brick.cfg.set("numports=33")
        self.assertEqual(len(state), 1)
        self.assertEqual(brick.cfg.numports, "33")
        brick.cfg.numports = "32"
        self.assertEqual(len(state), 2)
        self.assertEqual(state[1], "32")
        self.assertEqual(brick.cfg.numports, "32")

    def test_get_set_attr(self):
        self.brick.cfg.numports = "33"
        self.assertEqual(self.brick.cfg["numports"], 33)
