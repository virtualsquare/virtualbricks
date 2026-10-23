---
name: e2e
description: Write an end-to-end test of Virtualbricks from a use case told in plain words - a Gherkin scenario in e2e/features/, with the steps it lacks in e2e/steps.py - run it, and check that it fails when what it guards is broken.
when_to_use: When asked for an end-to-end test, an e2e test or a scenario of a use case, or to test something "as a user does" in the windows of Virtualbricks.
argument-hint: <the use case, in plain words>
---

# An end-to-end scenario from a use case in words

The use case: $ARGUMENTS

(If nothing follows "The use case:", it is the one the user just told.)

`e2e/README.md` is the guide for contributors; this is its "Write a
scenario", done for them. Read it first, and `e2e/STEPS.md`, the steps
there are and how to add one; then `e2e/steps.py` and the features in
`e2e/features/`.

## Steps

1. **Read the use case as steps of a user**: what they do, in order, and
   what they expect after each. When the words don't say what to check,
   take what a user would expect, and say so in the report. Ask only when
   two readings make two different tests.
2. **Pick the feature file** of its area in `e2e/features/`, or make one: a
   `Feature:` line and a sentence about the area.
3. **Write the scenario** with the steps there are, steps of a user before
   those of the screen; the names of bricks as Virtualbricks gives them (the
   first switch `sw1`, the first virtual machine `vm1`); `@needs-PROGRAM` for
   each program its bricks run.
4. **List the missing steps**:
   `pytest --generate-missing --feature e2e/features`. Add each to
   `e2e/steps.py`, in its section, with `words()`, by the rules of "Add a
   step" in `e2e/STEPS.md`: a `Then` checks what really happened (a
   process, a file, an exit status); no sleeping to wait; the clicks
   inside a step of a user. Add each to the table of its kind in
   `e2e/STEPS.md` too.
5. **Find the roles and names** of the widgets: put `And I print the
   widgets` where you are and run with `pytest -s`, or read the report of a
   step that fails. Take the print step out after. When a step fails, look
   at the `screenshot.png` its report names: a dialog or a menu in the way
   shows there.
6. **Run it** with `pytest -k <words of the scenario's name>` until it
   passes, then twenty times: `pytest --count 20 -k <the same words>`; all
   twenty must pass. Don't lengthen a timeout to make it pass: find what it
   waits for.
7. **Check that it fails**: break what it guards, run it, see the step that
   should fail fail, then undo the break. The guide's "Check that a scenario
   fails" has how.
8. **Run every scenario** (`pytest`), and `black e2e/`, `ruff check e2e/`,
   `pyflakes e2e/`.
9. **Report**: the scenario as written, the steps added, the twenty runs,
   which step failed when it was broken and how it was broken, and what you
   chose that the words didn't say.

## Rules

- Change `harness.py`, `a11y.py` or `broadway.py` only for something the
  steps can't do yet, as typing, and say so in the report.
- Only the fixtures start programs. Never stop a process the tests didn't
  start: theirs have their folder in `/tmp/vb-e2e-*`. The user may run their
  own Virtualbricks meanwhile: it is not yours.
- Break Virtualbricks for step 7 without editing it, when you can: a
  `sitecustomize.py` in a folder of `E2E_PYTHONPATH` (the guide has one).
  The user may run their own Virtualbricks from this checkout. A break that
  edits the code is undone before anything else; `git diff` must show only
  the scenario and its steps.
- Text, as a name or a path, is typed with `type()`; a key alone, as Escape,
  Return or Ctrl+L, with `key()`, in the window clicked last. A row dropped on
  another can't be done: GTK 3 on Broadway has no drag and drop; say so.
- A widget without a name can't be found: give it one in the code of
  Virtualbricks (`icon_button()` of `gui/mainwindow/tab.py`), which helps the
  screen readers too, and say so.
