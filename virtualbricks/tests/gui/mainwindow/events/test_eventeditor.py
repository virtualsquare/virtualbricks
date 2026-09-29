# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2019 Virtualbricks team

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

"""
The settings of an event: its delay, its actions read into rows and saved
back, the kinds and their subjects, adding and removing actions; all on a
draft, which OK applies.
"""

from virtualbricks import console
from virtualbricks.bricks.draft import Draft, apply
from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui.mainwindow.events import eventeditor
    from virtualbricks.gui.mainwindow.events.eventeditor import (
        MAX_DELAY,
        EventEditor,
    )
    from virtualbricks.bricks.eventinfo import Action, Kind


def vb(command):
    return console.VbShellCommand(command)


def sh(command):
    return console.ShellCommand(command)


def commands(event):
    """The actions of event as the project file keeps them."""

    return [(type(action), str(action)) for action in event.config.actions]


class EditorTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        for name in ("sw1", "sw2"):
            self.factory.new_brick("switch", name)
        self.boot = self.factory.new_event("boot")
        self.event = self.factory.new_event("start-lab")

    def edit(self, delay=5, *actions):
        self.event.set({"delay": delay, "actions": list(actions)})
        editor = EventEditor(Draft(self.event))
        self.addCleanup(editor.panel.destroy)
        return editor

    def rows(self, editor):
        return [
            (
                row.kind_combo.get_active_id(),
                self.subject(row),
            )
            for row in editor.rows()
        ]

    def subject(self, row):
        if isinstance(row.subject, Gtk.Entry):
            return row.subject.get_text()
        return row.subject.get_active_id()

    def choices(self, row):
        model = row.subject.get_model()
        return [entry[0] for entry in model]

    def ok(self, editor):
        """What OK does: the numbers typed, then the draft."""

        editor.commit()
        apply(editor.draft)


class TestReadingAnEvent(EditorTestCase):

    def test_each_kind(self):
        editor = self.edit(
            5,
            vb("sw1 on"),
            vb("sw2 off"),
            vb("boot on"),
            vb("boot off"),
            vb("sw1 config ports=8"),
            sh("ping -c 3 10.0.0.254"),
        )
        self.assertEqual(editor.delay.get_value_as_int(), 5)
        self.assertEqual(
            self.rows(editor),
            [
                ("start-brick", "sw1"),
                ("stop-brick", "sw2"),
                ("start-event", "boot"),
                ("stop-event", "boot"),
                ("console", "sw1 config ports=8"),
                ("shell", "ping -c 3 10.0.0.254"),
            ],
        )

    def test_the_kinds(self):
        row = self.edit(5, vb("sw1 on")).rows()[0]
        labels = [entry[0] for entry in row.kind_combo.get_model()]
        self.assertEqual(
            labels,
            [
                "Start a brick",
                "Stop a brick",
                "Start an event",
                "Stop an event",
                "",
                "Console command",
                "Shell command",
            ],
        )
        # the empty one is a line
        model = row.kind_combo.get_model()
        separator = eventeditor._is_separator
        self.assertTrue(separator(model, model.get_iter(4)))
        self.assertFalse(separator(model, model.get_iter(0)))

    def test_the_bricks_and_the_events(self):
        # an event doesn't start itself
        editor = self.edit(5, vb("sw1 on"), vb("boot on"))
        brick, event = editor.rows()
        self.assertEqual(self.choices(brick), ["sw1", "sw2"])
        self.assertEqual(self.choices(event), ["boot"])

    def test_a_missing_brick(self):
        editor = self.edit(5, vb("vm9 on"))
        [row] = editor.rows()
        self.assertEqual(self.choices(row), ["sw1", "sw2", "vm9 (missing)"])
        self.assertEqual(self.subject(row), "vm9")
        self.ok(editor)
        self.assertEqual(
            commands(self.event), [(console.VbShellCommand, "vm9 on")]
        )

    def test_the_event_itself(self):
        # not missing, but not a choice either
        editor = self.edit(5, vb("start-lab off"))
        [row] = editor.rows()
        self.assertEqual(row.kind, Kind.STOP_EVENT)
        self.assertEqual(self.choices(row), ["boot", "start-lab"])

    def test_a_delay(self):
        editor = self.edit(0, vb("sw1 on"))
        self.assertEqual(editor.delay.get_value_as_int(), 0)
        adjustment = editor.delay.get_adjustment()
        self.assertEqual(adjustment.get_lower(), 0)
        self.assertEqual(adjustment.get_upper(), MAX_DELAY)

    def test_the_words(self):
        editor = self.edit()
        wait, spin, then = editor.panel.get_children()[0].get_children()
        self.assertEqual(wait.get_text(), "Wait")
        self.assertIs(spin, editor.delay)
        self.assertEqual(then.get_text(), "seconds, then:")
        self.assertEqual(editor.add_button.get_label(), "Add Action")
        self.assertIs(editor.widget, editor.panel)


class TestSaving(EditorTestCase):

    def test_unchanged(self):
        actions = [
            vb("sw1 on"),
            vb("boot off"),
            vb("vm9 on"),
            vb("sw1 config ports=8"),
            sh(" ls -l"),
        ]
        editor = self.edit(5, *actions)
        before = commands(self.event)
        self.ok(editor)
        self.assertEqual(commands(self.event), before)
        self.assertEqual(self.event.config.delay, 5)

    def test_unchanged_as_written(self):
        # the rows would write "sw1 on", but nothing changed
        editor = self.edit(5, vb("sw1  on"))
        changed = []
        self.event.changed.connect(changed.append)
        self.assertEqual(editor.draft.changes(), {})
        self.ok(editor)
        self.assertEqual(
            commands(self.event), [(console.VbShellCommand, "sw1  on")]
        )
        self.assertEqual(changed, [])

    def test_on_the_draft(self):
        editor = self.edit(5, vb("sw1 on"))
        editor.delay.set_value(12)
        editor.rows()[0].kind_combo.set_active_id("stop-brick")
        self.assertEqual(
            editor.draft.changes(),
            {"delay": 12, "actions": [vb("sw1 off")]},
        )
        # the event waits for OK
        self.assertEqual(self.event.config.delay, 5)
        self.assertEqual(
            commands(self.event), [(console.VbShellCommand, "sw1 on")]
        )

    def test_the_delay(self):
        editor = self.edit(5, vb("sw1 on"))
        editor.delay.set_value(12)
        self.ok(editor)
        self.assertEqual(self.event.config.delay, 12)

    def test_a_delay_typed(self):
        # and not yet taken by the spin button
        editor = self.edit(5, vb("sw1 on"))
        editor.delay.set_text("30")
        self.ok(editor)
        self.assertEqual(self.event.config.delay, 30)

    def test_without_a_subject(self):
        editor = self.edit(5, vb("sw1 on"), sh("ls"))
        editor.rows()[1].subject.set_text("  ")
        self.ok(editor)
        self.assertEqual(
            commands(self.event), [(console.VbShellCommand, "sw1 on")]
        )


class TestChangingAnAction(EditorTestCase):

    def test_a_brick_stays_a_brick(self):
        editor = self.edit(5, vb("sw2 on"))
        [row] = editor.rows()
        row.kind_combo.set_active_id("stop-brick")
        self.assertEqual(self.subject(row), "sw2")
        self.ok(editor)
        self.assertEqual(
            commands(self.event), [(console.VbShellCommand, "sw2 off")]
        )

    def test_a_missing_brick_stays(self):
        editor = self.edit(5, vb("vm9 on"))
        [row] = editor.rows()
        row.kind_combo.set_active_id("stop-brick")
        self.assertEqual(self.choices(row), ["sw1", "sw2", "vm9 (missing)"])
        row.subject.set_active_id("sw1")
        self.ok(editor)
        self.assertEqual(
            commands(self.event), [(console.VbShellCommand, "sw1 off")]
        )

    def test_to_an_event(self):
        editor = self.edit(5, vb("sw2 on"))
        [row] = editor.rows()
        row.kind_combo.set_active_id("start-event")
        self.assertEqual(self.choices(row), ["boot"])
        self.assertEqual(self.subject(row), "boot")

    def test_to_a_command(self):
        editor = self.edit(5, vb("sw2 on"))
        [row] = editor.rows()
        row.kind_combo.set_active_id("console")
        self.assertIsInstance(row.subject, Gtk.Entry)
        # in place of the choice of a brick
        self.assertEqual(row.subject_box.get_children(), [row.subject])
        self.assertEqual(row.subject.get_text(), "")
        self.assertEqual(
            row.subject.get_placeholder_text(),
            "A command of the console, as “vm1 config ram=512”",
        )
        row.subject.set_text("sw2 config ports=4")
        # a command stays a command
        row.kind_combo.set_active_id("shell")
        self.assertEqual(row.subject.get_text(), "sw2 config ports=4")
        self.assertEqual(
            row.subject.get_placeholder_text(),
            "A command for the shell of the host",
        )
        self.ok(editor)
        self.assertEqual(
            commands(self.event),
            [(console.ShellCommand, "sw2 config ports=4")],
        )

    def test_no_event_to_choose(self):
        self.factory.del_event(self.boot)
        editor = self.edit(5, vb("sw1 on"))
        [row] = editor.rows()
        row.kind_combo.set_active_id("start-event")
        self.assertEqual(self.choices(row), [])
        self.assertIsNone(row.action())
        self.ok(editor)
        self.assertEqual(commands(self.event), [])


class TestTheSubjectAlone(EditorTestCase):

    def test_another_brick(self):
        editor = self.edit(5, vb("sw1 on"))
        editor.rows()[0].subject.set_active_id("sw2")
        self.assertEqual(editor.draft.changes(), {"actions": [vb("sw2 on")]})

    def test_another_command(self):
        editor = self.edit(5, sh("ls"))
        editor.rows()[0].subject.set_text("ls -l")
        self.assertEqual(editor.draft.changes(), {"actions": [sh("ls -l")]})


class TestAddingAndRemoving(EditorTestCase):

    def test_add(self):
        editor = self.edit(5, vb("sw2 on"))
        editor.add_button.clicked()
        self.assertEqual(
            self.rows(editor), [("start-brick", "sw2"), ("start-brick", "sw1")]
        )
        self.ok(editor)
        self.assertEqual(
            commands(self.event),
            [
                (console.VbShellCommand, "sw2 on"),
                (console.VbShellCommand, "sw1 on"),
            ],
        )

    def test_add_without_bricks(self):
        for brick in list(self.factory.bricks):
            self.factory.del_brick(brick)
        editor = self.edit()
        editor.add_button.clicked()
        [row] = editor.rows()
        self.assertIsNone(row.action())

    def test_remove(self):
        editor = self.edit(5, vb("sw1 on"), vb("sw2 on"), sh("ls"))
        editor.rows()[1].remove_button.clicked()
        self.assertEqual(
            self.rows(editor), [("start-brick", "sw1"), ("shell", "ls")]
        )
        self.ok(editor)
        self.assertEqual(
            commands(self.event),
            [(console.VbShellCommand, "sw1 on"), (console.ShellCommand, "ls")],
        )

    def test_remove_the_last(self):
        # nothing left, nothing fails
        editor = self.edit(5, vb("sw1 on"))
        editor.rows()[0].remove_button.clicked()
        self.ok(editor)
        self.assertEqual(commands(self.event), [])

    def test_the_rows(self):
        editor = self.edit(5, vb("sw1 on"), sh("ls"))
        first, second = editor.rows()
        self.assertEqual(
            first.remove_button.get_tooltip_text(), "Remove the action"
        )
        # the kinds as wide as each other
        self.assertIn(second.kind_combo, editor._kinds.get_widgets())
        self.assertEqual(first.action(), Action(Kind.START_BRICK, "sw1"))


class TestWaiting(EditorTestCase):

    def test_waiting(self):
        editor = self.edit(5, vb("sw1 on"))
        self.assertFalse(editor.running())
        self.event.scheduled = object()
        self.assertTrue(editor.running())
        self.assertEqual(
            editor.running_words(),
            "start-lab is waiting: when the wait is over, it runs its actions"
            " as they are then; a new delay counts from its next start.",
        )
