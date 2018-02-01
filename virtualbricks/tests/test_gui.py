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

from twisted.trial import unittest

import gtk

from virtualbricks import project, _settings
from virtualbricks.gui import gui, interfaces
from virtualbricks.tests import stubs


class WidgetStub:

    sensitive = True
    tooltip = ""

    def __init__(self):
        self.signals = {}

    def get_sensitive(self):
        return self.sensitive

    def set_sensitive(self, sensitive):
        self.sensitive = sensitive

    def get_tooltip_markup(self):
        return self.tooltip

    def set_tooltip_markup(self, tooltip):
        self.tooltip = tooltip

    def connect(self, signal, callback, *args):
        self.signals.setdefault(signal, []).append((callback, args))


class CheckButtonStub(WidgetStub):

    active = False

    def __init__(self):
        WidgetStub.__init__(self)
        self.signals["toggled"] = []

    def get_active(self):
        return self.active

    def set_active(self, active):
        self.active, active = active, self.active
        if self.active ^ active:
            for callback, args in self.signals["toggled"]:
                callback(self, *args)


class TestStateFramework(unittest.TestCase):

    def test_prerequisite(self):
        """
        A prerequisite return YES, NO or MAYBE. YES and MAYBE are considered
        both true in the ultimate stage.
        """

        for b, ret in (True, gui.YES), (False, gui.NO), (True, gui.MAYBE):
            pre = gui.CompoundPrerequisite(lambda: ret)
            if b:
                self.assertTrue(pre())
            else:
                self.assertFalse(pre())

    def test_yes_prerequisite(self):
        """
        Prerequisite can be more than one, if YES or NO is returned then the
        other prerequisites are not checked.
        """

        def prerequisite():
            l.append(True)

        for check, ret in (False, gui.NO), (True, gui.YES):
            l = []
            pre = gui.CompoundPrerequisite(lambda: ret, prerequisite)
            if check:
                self.assertTrue(pre())
            else:
                self.assertFalse(pre())
            self.assertEqual(l, [])

    def test_nested_prerequisite(self):
        """Prerequisite can be nested."""

        def prerequisite1():
            l[0] = 1

        def prerequisite2():
            l[1] = 1

        l = [0, 0]
        pre1 = gui.CompoundPrerequisite(lambda: gui.MAYBE, prerequisite1)
        pre2 = gui.CompoundPrerequisite(lambda: gui.YES, prerequisite2)
        pre = gui.CompoundPrerequisite(pre1, pre2)
        self.assertTrue(pre())
        self.assertEqual(l, [1, 0])

    def test_state(self):
        """
        The state object control other objects based on the prerequisites.
        """

        class Control:

            def react(self, status):
                self.status = status

        state = gui.State()
        state.add_prerequisite(lambda: True)
        control = Control()
        state.add_control(control)
        state.check()
        self.assertTrue(control.status)

    def test_checkbutton_state(self):
        """Test a checkbutton that controls another widgets."""

        TOOLTIP = "Disabled"
        manager = gui.StateManager()
        checkbutton = CheckButtonStub()
        widget = WidgetStub()
        self.assertTrue(widget.sensitive)
        self.assertEqual(widget.tooltip, "")
        manager.add_checkbutton_active(checkbutton, TOOLTIP, widget)
        self.assertFalse(widget.sensitive)
        self.assertEqual(widget.tooltip, TOOLTIP)

    def test_checkbutton_nonactive(self):
        """Enable a widget if the checkbutton is not active."""

        TOOLTIP = "Disabled"
        manager = gui.StateManager()
        checkbutton = CheckButtonStub()
        widget = WidgetStub()
        self.assertTrue(widget.sensitive)
        self.assertEqual(widget.tooltip, "")
        manager.add_checkbutton_not_active(checkbutton, TOOLTIP, widget)
        self.assertTrue(widget.sensitive)
        self.assertEqual(widget.tooltip, "")
        checkbutton.set_active(True)
        self.assertFalse(widget.sensitive)
        self.assertEqual(widget.tooltip, TOOLTIP)


class Readme(gui.ReadmeMixin, gui._Root):

    def __init__(self, manager):
        self.textview = gtk.TextView()
        self.manager = manager

    def set_text(self, text):
        self.textview.get_buffer().set_text(text)

    def get_object(self, name):
        if name == "readme_textview":
            return self.textview

    def init(self, factory):
        super(Readme, self).init(factory)

    def on_quit(self):
        super(Readme, self).on_quit()


class TestReadme(unittest.TestCase):

    def test_quit(self):
        DESC = "test"
        PROJECT = "test_project"
        factory = stubs.Factory()
        manager = project.ProjectManager(self.mktemp())
        prj = manager.get_project(PROJECT)
        prj.create()
        prj.open(factory, _settings.Settings(self.mktemp()))
        readme_tab = Readme(manager)
        readme_tab.init(factory)
        readme_tab.set_text(DESC)
        self.assertEqual(prj.get_description(), "")
        readme_tab.on_quit()
        self.assertEqual(prj.get_description(), DESC)


class DumbGui:

    def __init__(self, factory):
        self.brickfactory = factory


class TestController(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.Factory()
        self.gui = DumbGui(self.factory)
        self.brick = self.get_brick()
        self.controller = interfaces.IConfigController(self.brick)

    def get_brick(self):
        raise NotImplementedError()

    def get_object(self, name):
        return self.controller.get_object(name)

    def configure_brick(self):
        self.controller.configure_brick(self.gui)

    def get_config_view(self):
        self.controller.get_config_view(self.gui)

    def _assert_active_equal(self, name, status):
        self.assertEqual(self.controller.get_object(name).get_active(), status)

    def assert_active(self, name):
        self._assert_active_equal(name, True)

    def assert_not_active(self, name):
        self._assert_active_equal(name, False)

    def assert_spinbutton_value(self, name, value):
        self.assertEqual(self.controller.get_object(name).get_value_as_int(),
                         value)

    def assert_parameter_equal(self, name, value):
        self.assertEqual(self.brick.get(name), value)

    def assert_parameters_equal(self, names=(), values=(), **kwds):
        for name, value in zip(names, values):
            self.assert_parameter_equal(name, value)
        for name, value in kwds.iteritems():
            self.assert_parameter_equal(name, value)

    def assert_text_equal(self, name, text):
        self.assertEqual(self.controller.get_object(name).get_text(), text)


class TestSwitchController(TestController):

    def get_brick(self):
        from virtualbricks.switches import Switch
        return Switch(self.factory, "test")

    def test_view(self):
        """The initial status of the switch controller."""

        self.brick.set({"fstp": False, "hub": False, "numports": 2})
        self.get_config_view()
        self.assert_not_active("fstp_checkbutton")
        self.assert_not_active("hub_checkbutton")
        self.assert_spinbutton_value("ports_spinbutton", 2)

    def test_config(self):
        """Set the switch parameters."""

        self.assert_parameters_equal(("fstp", "hub", "numports"),
                                     (False, False, 32))
        self.get_object("fstp_checkbutton").set_active(True)
        self.get_object("hub_checkbutton").set_active(False)
        self.get_object("ports_spinbutton").set_value(31)
        self.configure_brick()
        self.assert_parameters_equal(("fstp", "hub", "numports"),
                                     (True, False, 31))


class TestSwitchWrapperController(TestController):

    PATH = "/foo/bar"

    def get_brick(self):
        from virtualbricks.switches import SwitchWrapper
        return SwitchWrapper(self.factory, "test")

    def test_view(self):
        """The initial status of the switch wrapper."""

        self.brick.set({"path": self.PATH})
        self.get_config_view()
        self.assert_text_equal("entry", self.PATH)

    def test_config(self):
        """Set the switch wrapper parameters."""

        self.assert_parameter_equal("path", "")
        self.get_object("entry").set_text(self.PATH)
        self.configure_brick()
        self.assert_parameter_equal("path", self.PATH)


class TestTapController(TestController):

    def get_brick(self):
        from virtualbricks.tuntaps import Tap
        return Tap(self.factory, "test")

    def test_view(self):
        """The initial status of the tap."""

        cfg = {"ip": "0.0.0.0",
               "nm": "0.0.0.0",
               "gw": "0.0.0.0",
               "mode": "dhcp"}
        self.brick.set(cfg)
        self.get_config_view()
        self.assert_text_equal("ip_entry", "0.0.0.0")
        self.assert_text_equal("nm_entry", "0.0.0.0")
        self.assert_text_equal("gw_entry", "0.0.0.0")
        self.assert_not_active("nocfg_radiobutton")
        self.assert_active("dhcp_radiobutton")
        self.assert_active("manual_radiobutton")
    test_view.todo = "Implement test utility for the plugmixin"

    def assert_initial(self):
        """Assert initial status."""

        self.assert_parameters_equal(ip="10.0.0.1",
                                     nm="255.255.255.0",
                                     gw="",
                                     mode="off")

    def test_config_nocfg(self):
        """Set the tap parameters for no network configuration."""

        self.assert_initial()
        self.get_object("nocfg_radiobutton").set_active(True)
        self.configure_brick()
        self.assert_parameters_equal(ip="10.0.0.1",
                                     nm="255.255.255.0",
                                     gw="",
                                     mode="off")

    def test_config_dhcp(self):
        """Set the tap parameters for dhcp."""

        self.assert_initial()
        self.get_object("dhcp_radiobutton").set_active(True)
        self.configure_brick()
        self.assert_parameters_equal(ip="10.0.0.1",
                                     nm="255.255.255.0",
                                     gw="",
                                     mode="dhcp")

    def test_config_manual(self):
        """Set the tap parameters for dhcp."""

        IP = "192.168.1.1"
        NM = "255.255.0.0"
        GW = "192.168.179.1"
        self.assert_initial()
        self.get_object("manual_radiobutton").set_active(True)
        self.get_object("ip_entry").set_text(IP)
        self.get_object("nm_entry").set_text(NM)
        self.get_object("gw_entry").set_text(GW)
        self.configure_brick()
        self.assert_parameters_equal(ip=IP, nm=NM, gw=GW, mode="manual")


class TestCaptureController(TestController):

    def get_brick(self):
        from virtualbricks.tuntaps import Capture
        return Capture(self.factory, "test")

    def test_view(self):
        """The initial status of the capture interface."""

        self.get_config_view()
    test_view.todo = "Implement test utility for the plugmixin"

    def test_config(self):
        """Set the capture interface parameters."""

        self.assert_parameter_equal("iface", "")
        self.fail("TODO")
    test_config.todo = "Implement test utility for the plugmixin"
