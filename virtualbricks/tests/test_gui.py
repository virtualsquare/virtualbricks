from twisted.trial import unittest

import gtk

from virtualbricks.gui import gui, _gui
from virtualbricks.tests import stubs, create_manager
from virtualbricks.tests.test_project import TestBase


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

        for b, ret in (True, _gui.YES), (False, _gui.NO), (True, _gui.MAYBE):
            pre = _gui.CompoundPrerequisite(lambda: ret)
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

        for check, ret in (False, _gui.NO), (True, _gui.YES):
            l = []
            pre = _gui.CompoundPrerequisite(lambda: ret, prerequisite)
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
        pre1 = _gui.CompoundPrerequisite(lambda: _gui.MAYBE, prerequisite1)
        pre2 = _gui.CompoundPrerequisite(lambda: _gui.YES, prerequisite2)
        pre = _gui.CompoundPrerequisite(pre1, pre2)
        self.assertTrue(pre())
        self.assertEqual(l, [1, 0])

    def test_state(self):
        """
        The state object control other objects based on the prerequisites.
        """

        class Control:

            def react(self, status):
                self.status = status

        state = _gui.State()
        state.add_prerequisite(lambda: True)
        control = Control()
        state.add_control(control)
        state.check()
        self.assertTrue(control.status)

    def test_checkbutton_state(self):
        """Test a checkbutton that controls another widgets."""

        TOOLTIP = "Disabled"
        manager = _gui.StateManager()
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
        manager = _gui.StateManager()
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

    def __init__(self):
        self.textview = gtk.TextView()

    def get_buffer(self):
        return self.textview.get_buffer()

    def get_object(self, name):
        if name == "readme_textview":
            return self.textview

    def init(self, factory):
        super(Readme, self).init(factory)

    def on_quit(self):
        super(Readme, self).on_quit()


class TestReadme(TestBase, unittest.TestCase):

    def setUp(self):
        pass

    def test_quit(self):
        DESC = "test"
        PROJECT = "test_project"
        factory = stubs.FactoryStub()
        _, manager = create_manager(self, factory)
        project = manager.create(PROJECT)
        project.restore(factory)
        readme_tab = Readme()
        readme_tab.init(factory)
        readme_tab.get_buffer().set_text(DESC)
        self.assertEqual(project.get_description(), "")
        readme_tab.on_quit()
        self.assertEqual(project.get_description(), DESC)
