# End-to-end tests

The end-to-end tests start Virtualbricks as a user does, click in its
windows and quit it, and check what really happened: the processes of the
bricks, the exit status. Each test is a scenario, written in words in a
`.feature` file:

```gherkin
Scenario: A switch runs for a while, then stops
  Given Virtualbricks is running
  When I add the switch sw1
  And I start sw1
  Then sw1 is running
  When I wait 5 seconds
  Then sw1 is still running
  When I stop sw1
  Then sw1 is stopped
  When I quit Virtualbricks
  Then Virtualbricks has quit
```

[pytest-bdd](https://pytest-bdd.readthedocs.io/) makes a pytest test of each
scenario, and runs each line with the Python function of its words: a step.
Writing a test is writing a scenario with the steps there are, and adding
the steps that are missing.

## Run them

They need, besides the Python packages of the project:

- `broadwayd`, GTK's HTML5 display server (`libgtk-3-bin`)
- `dbus-daemon`, which every desktop has
- AT-SPI, the accessibility bus (`at-spi2-core`), and its typelib
  (`gir1.2-atspi-2.0`)
- the programs of the bricks of each scenario, as `vde_switch` (`vde-switch`,
  or `vde2` on older releases)
- `ffmpeg`, for the videos of the scenarios that fail; without it, they have
  only a screenshot

```sh
sudo apt install libgtk-3-bin at-spi2-core gir1.2-atspi-2.0 ffmpeg
pip install --group e2e
```

From the root of the sources:

```sh
pytest                                   # every scenario
pytest -k switch_runs                    # the scenarios with these words
pytest --gherkin-terminal-reporter -vv   # each scenario, step by step
pytest -s                                # with what the steps print
pytest --count 20 -k switch_runs         # 20 times: is it flaky?
pytest --record-all -k switch_runs       # a video, also if it passes
```

`pytest` runs the end-to-end tests, and those of `recording.py`
(`testpaths` in `pyproject.toml`); `trial` runs the others. A scenario takes
a few seconds.

- Nothing shows on your screen, and nothing reaches your desktop: the
  windows are on `broadwayd`, with a session bus of their own.
- Each scenario has a Virtualbricks of its own, with a temporary home,
  settings and workspace, and `--lock none`: the tests run beside your own
  Virtualbricks, and never touch it.
- Without the programs above, the tests are skipped, saying what is missing;
  a scenario tagged `@needs-vde_switch` is skipped without `vde_switch`.

## The files

| File | What it has |
| :- | :- |
| `features/*.feature` | The scenarios, a file for each area: `bricks.feature`, …; in folders too: see [Group the scenarios](#group-the-scenarios) |
| `steps.py` | The steps: what each line of a scenario does |
| `projects/` | The projects of Virtualbricks 2.1 of the scenarios, a folder each, with its `.project` |
| `TODO.md` | The scenarios, written and to write, by area, and what they need that the tests can't do yet |
| `test_features.py` | Makes a test of each scenario of `features/` |
| `conftest.py` | The fixtures: `desktop`, shared, and `virtualbricks`, for each scenario; the report of a step that fails, `--record-all` |
| `harness.py` | What the steps drive: `Virtualbricks`, with `find`, `click`, `choose`, `row`, `children`, …; the `Desktop` and its `Screen`s |
| `a11y.py` | The widgets, as a screen reader sees them, through AT-SPI |
| `broadway.py` | The mouse: a browser of `broadwayd`, whose clicks and wheel reach GTK as a user's do; it keeps what the screen shows |
| `recording.py` | The screenshot and the video of a scenario, from what the browser kept |
| `test_recording.py` | The tests of `recording.py` |

## Write a scenario

1. **Say the use case in words**, as a user would do it: what they do, in
   order, and what they expect to see or to happen.
2. **Write it as a scenario**, in the `.feature` file of its area, or in a
   new one with a `Feature:` line and a sentence about the area. `Given`
   says how things are before, `When` what the user does, `Then` what must
   be true after; `And` repeats the word before. Use the steps of the table
   below.
3. **Run it.** pytest says which lines have no step; to have them all, with
   the code to start from:

   ```sh
   pytest --generate-missing --feature e2e/features
   ```

4. **Add the steps that are missing**, in `steps.py`: see
   [Add a step](#add-a-step).
5. **Run it until it passes**, then **twenty times in a row**: see [Is a
   scenario flaky?](#is-a-scenario-flaky).
6. **Check that it fails** when Virtualbricks is broken: see [Check that a
   scenario fails](#check-that-a-scenario-fails).
7. **Read it again as a user**: each line says something a user would say;
   the details of the windows are in the steps.

Some rules:

- A scenario is one use case. When two start alike, the start can go in a
  `Background:` of the feature.
- A brick has the name Virtualbricks gives it: the first switch is `sw1`, the
  first virtual machine `vm1`, the first router `r1`. The step that adds it
  checks the name.
- Tag a scenario with `@needs-PROGRAM` for each program its bricks run
  (`@needs-vde_switch`, `@needs-qemu-system-x86_64`): without it, the
  scenario is skipped, not failed.
- Prefer the steps of a user to those of the screen: `When I start sw1`, not
  `When I click the button "Start sw1"`. A scenario that needs a step of the
  screen often says that a step of a user is missing.

### The steps

The steps of a user:

| Step | What it does |
| :- | :- |
| `Given Virtualbricks is running` | Starts Virtualbricks, and waits for its main window |
| `When I add the switch sw1` | New Brick, the kind, then OK on its settings; the new brick must be named `sw1`. Any kind of New Brick: `the virtual machine vm1`, `the router r1`, … |
| `When I start sw1` | Its Start button; it must run, with new processes |
| `When I stop sw1` | Its Stop button; it must stop |
| `When I wait 5 seconds` | Waits |
| `When I quit Virtualbricks` | File, then Quit |
| `When I start Virtualbricks again` | Starts it with its settings, as after it ran before, on a new screen, and waits for a window |
| `Then sw1 is running` | Its row says Running, and the processes of its start run |
| `Then sw1 is still running` | The same |
| `Then sw1 is stopped` | Its row says Stopped, and no process of it runs: those of its start have quit, and none has its sockets |
| `Then sw1 is not running` | The same |
| `Then Virtualbricks has quit` | It exited with 0, and no brick runs any more |
| `Then the main window shows the project lab` | Its title names the project |
| `Then the list of bricks has`, with a table under it | The rows of the list, all of them and in order, scrolled through, once they are those of the table: the name of each brick, its detail and its state |

The steps of the migration of Virtualbricks 2.1:

| Step | What it does |
| :- | :- |
| `Given the project DTN2hops_26_Feb_2026 of Virtualbricks 2.1` | A copy of `projects/DTN2hops_26_Feb_2026` in the workspace |
| `Given the settings of Virtualbricks 2.1, with DTN2hops_26_Feb_2026 open last` | `~/.virtualbricks.conf`, of the workspace of the tests, in place of the settings: the next start is the first |
| `When I start Virtualbricks for the first time` | Starts it without its settings, as after 2.1, and waits for a window |
| `When I close the migration window` | Its button Close |
| `Given Virtualbricks migrated DTN2hops_26_Feb_2026 at its first start` | The first start, the migration of the project, and its window closed |
| `Then the migration window shows` | Waits until it shows |
| `Then the migration window doesn't show` | Waits until it doesn't |
| `Then the migration window lists`, with a table under it | The rows of its list, all of them and in order, once they are those of the table, whose first line has the titles of the columns |
| `Then DTN2hops_26_Feb_2026 is migrated` | The migration ends, no row of the window failed, and the project has its `project.toml` |

A step with a table under it takes all the rows of a list, in order: the
first line of the table has the titles of the columns, each other line a
row. The rows of the migration window, and those of the bricks:

```gherkin
Then the migration window lists
  | Project              | Bricks | Status      |
  | .virtualbricks.conf  | —      | ✓ Migrated  |
  | DTN2hops_26_Feb_2026 | 13     | ⚠ 1 warning |
```

```gherkin
Given Virtualbricks is running
When I add the switch sw1
Then the list of bricks has
  | Brick | Detail            | State   |
  | sw1   | Switch · 32 ports | Stopped |
```

The steps of the screen, for any widget, by its role and its name:

| Step | What it does |
| :- | :- |
| `When I click the button "New Brick"` | Clicks the widget, once it shows and is enabled |
| `When I choose "Quit" in the menu "File"` | The menu of the menu bar, then its item |
| `Then the label "No Bricks Yet" shows` | Waits until the widget shows |
| `Then the label "No Bricks Yet" doesn't show` | Waits until it doesn't |
| `And I print the widgets` | Prints the widgets that show, with their roles and names (`pytest -s`) |

## Add a step

A step is a function of `steps.py`, under the decorator of its words:

```python
@when(words("I stop {name:Brick}"))
def stop_brick(virtualbricks, name):
    virtualbricks.click("button", f"Stop {name}")
    virtualbricks.find("button", f"Start {name}")
```

- `@given`, `@when` and `@then` say which lines it is for; `@step`, any of
  them.
- `words()` reads the words as [parse](https://github.com/r1chardj0n3s/parse)
  does: `{name:Brick}` takes the name of a brick, `{seconds:d}` a number,
  `"{name}"` a text in quotes. The function gets them by name.
- A table under a line, as in Gherkin, comes to its step as `datatable`, a
  list of rows, each a list of texts.
- `virtualbricks` is the Virtualbricks of the scenario
  (`harness.Virtualbricks`). Its methods that wait, wait ten seconds at
  most, then fail saying what they waited for:

  | Method | What it does |
  | :- | :- |
  | `find(role, name, within=None)` | The widget, once it shows |
  | `shows(role, name, within=None)` | The widget if it shows now, else None |
  | `gone(role, name, within=None)` | Waits until it doesn't show |
  | `enabled(role, name, within=None)` | The widget, once it shows and is enabled |
  | `click(role, name, within=None)` | Clicks it, once it shows and is enabled |
  | `choose(item, menu)` | A menu of the menu bar, then its item |
  | `row(name)` | The row of a list with that name, for `within=` |
  | `rows(within)` | The rows of the list in a scroll pane, from the first to the last, each the names of its labels: the wheel scrolls through it |
  | `names(role, within=None)` | The names of the widgets of that role that show now |
  | `wait_for(get, what)` | What `get()` returns, once it is true |
  | `children()` | The processes that Virtualbricks started and run |
  | `bricks(name=None)` | The processes with sockets in the run folder of the tests; with a name, those of that brick |
  | `describe()` | The widgets that show, one a line |
  | `home`, `workspace`, `settings` | Its home, its workspace, and its settings file, which a step can remove |

- Another fixture can keep what the steps of a scenario share, as
  `brick_processes` keeps the processes of each brick started.
- A `Then` checks what really happened, not only what the windows say: a
  process, a file, an exit status.
- A step never sleeps to wait for something: it waits for it, with `find` or
  `wait_for`. Only `When I wait 5 seconds` sleeps.
- A step of a user says it in the words of Virtualbricks; the clicks are
  inside.

### The role and the name of a widget

A step finds a widget as a screen reader does: by its role, as `button`,
`label`, `menu`, `menu item`, `toggle button`, `list item`, `page tab`, and
by its name, the text of its label, or the name given to the screen
readers. To see them, add `And I print the widgets` where the scenario is,
and run it with `pytest -s`; a step that fails prints them too:

```text
[list item] ''
  [filler] ''
    [label] 'sw1'
    [label] 'Switch · 32 ports'
    [label] 'Stopped'
  [button] 'Start sw1'
  [button] 'Menu of sw1'
```

A button with only an icon needs a name: `icon_button()` of
`virtualbricks/gui/mainwindow/tab.py` gives it one, for its tooltip and for
the screen readers. Without a name, a widget can't be found, by the tests nor
by a screen reader.

## Group the scenarios

The scenarios of an area are a `.feature` file of their own:
`bricks.feature`, `projects.feature`, …; when there are many, a folder of
them, as `features/network/wires.feature`. `test_features.py` makes a test
of each scenario of `features/` and its folders: a new file needs nothing
else.

To run a group, tag it. A tag on `Feature:` is on each of its scenarios, a
tag on a `Scenario:` on that one; `-m` runs the scenarios of a tag:

```gherkin
@network
Feature: Wires
  A wire joins two bricks.

  @smoke
  Scenario: A wire between two switches
    …
```

```sh
pytest -m network      # the scenarios of the feature
pytest -m smoke        # those tagged @smoke
pytest -m "not slow"   # all but those tagged @slow
```

pytest warns of a tag it doesn't know (`PytestUnknownMarkWarning`): name
each in `markers`, in `[tool.pytest.ini_options]` of `pyproject.toml`.
`@needs-PROGRAM` is not one: `conftest.py` makes it a skip.

```toml
markers = [
    "network: the scenarios of wires",
    "smoke: a few scenarios, to run first",
]
```

The ways to group, and what each does:

| How | What it does |
| :- | :- |
| A `.feature` file, in `features/` or a folder of it | A test of each scenario, with nothing else to change |
| A tag on `Feature:`, as `@network` | On each of its scenarios: `pytest -m network` |
| A tag on a `Scenario:`, as `@smoke` | On that one: `pytest -m smoke`; `-m "not slow"` leaves some out |
| `Rule:`, in a feature | Groups some of its scenarios, each `Rule:` with a `Background:` of its own |
| The name of a feature, as `-k Wires` | Selects nothing: a test is `test_features.py::test_` and the name of its scenario, so `-k` knows only the words of the scenario |
| Another test file, as `test_network.py` with `scenarios("features/network")` | Each of its scenarios runs twice: `test_features.py` makes a test of it too |

A test file for each feature, in place of `test_features.py`, would run with
`pytest e2e/test_network.py`, and in a JUnit XML report (`--junitxml`) each
file would be a class of its own, where today all are
`e2e.test_features`; but a feature without its test file would never run,
and nothing would say so. Allure groups the scenarios by `Feature:` anyway.

## Is a scenario flaky?

A scenario that passes once may fail the next time: a step that clicks
before the widget is there, a wait too short for a slower machine. Run it
many times, with [pytest-repeat](https://github.com/pytest-dev/pytest-repeat):

```sh
pytest --count 20 -k switch_runs
```

Each run is a test of its own, with a Virtualbricks, a home and a screen of
its own; the third of twenty is
`test_a_switch_runs_for_a_while_then_stops[3-20]`. The summary says how many
failed, as `2 failed, 18 passed`, and each failure has its report. Add `-x`
to stop at the first one. A scenario is done when the twenty pass.

## Check that a scenario fails

A test that never fails tests nothing. Once a scenario passes, break what it
checks, run it, and see it fail, at the step that should.

The folders of `E2E_PYTHONPATH` come first on the `PYTHONPATH` of
Virtualbricks, so a `sitecustomize.py` there breaks it for one run, without
a change to the code. For the switch scenario, a `vde_switch` that exits at
once:

```sh
mkdir -p /tmp/break
printf '#!/bin/sh\nexit 1\n' > /tmp/break/vde_switch
chmod +x /tmp/break/vde_switch
cat > /tmp/break/sitecustomize.py <<'EOF'
from virtualbricks import programs

find = programs.find_program
programs.find_program = lambda name, folder: (
    "/tmp/break/vde_switch" if name == "vde_switch" else find(name, folder)
)
EOF
E2E_PYTHONPATH=/tmp/break pytest -k switch_runs
```

`And I start sw1` fails, waiting for the button `Stop sw1`, and the
widgets show the error of Virtualbricks: `Process terminated. process ended
with exit code 1`. A break can be an edit of the code too; then undo it, and
`git diff` must show only the scenario and its steps.

## When a step fails

The report says the step that failed, what it waited for, the widgets that
showed then, and the output of Virtualbricks:

```text
The step that failed: And I start sw1
Its screen: screenshot.png and recording.webm in /tmp/pytest-of-…
The widgets that show:
[application] '__main__.py'
  [frame] 'Virtualbricks (project: new_project, workspace: ~/workspace)'
  …
AssertionError: Not in 10 s: the button 'Stop sw1' shows
```

The files of each scenario stay in `/tmp/pytest-of-$USER/`, for the last
three runs: its home, its settings, its workspace with the project,
`output.log`, the output of Virtualbricks, and `broadway.log`, that of its
`broadwayd`; `desktop0/` has the log of `dbus-daemon`.

### The screenshot and the video

A scenario that fails has two more files in its folder, which the end of
the run lists under "screenshots and videos":

- `screenshot.png`: the screen when the step failed, as a user would have
  seen it, with the dialogs and the menus that showed.
- `recording.webm`: the screen from the start of Virtualbricks to the step
  that failed; when it started again, its screens one after the other. A
  browser plays it.

Both show the pointer, a red dot, and the step at the bottom; the step that
failed is in red. In the video each change of the screen shows half a
second at least, so the clicks can be followed: Virtualbricks makes them
faster than the eye; the waits last as long as they did.

`--record-all` records every scenario, also those that pass: for one at a
time, as `pytest --record-all -k switch_runs`. Each takes a second or two
more.

The browser keeps what `broadwayd` sends, the images of the windows,
compressed, and where they are; nothing is decoded while the scenario runs.
When it ends, `recording.py` decodes them as `broadway.js` does, draws the
screen with cairo and gives the frames to `ffmpeg`. Without `ffmpeg` there
is only the screenshot.

## With Claude Code

The `/e2e` skill of the project, in `.claude/skills/e2e/`, does the steps of
[Write a scenario](#write-a-scenario) from a use case in words:

```text
/e2e add a switch, start it, wait 5 seconds, stop it, then quit
```

It writes the scenario with the steps there are, adds the missing ones, runs
it, checks that it fails when what it guards is broken, and tells what it
chose. Read the scenario as you would one of a contributor: it is the test.

## How it works

- `desktop`, once for all the tests, starts a `dbus-daemon` in a folder of
  its own in `/tmp`; AT-SPI starts on that bus when it is first asked. The
  variables of your desktop (`DISPLAY`, the buses) are out of the
  environment of the tests and of Virtualbricks.
- `virtualbricks`, for each scenario, makes a home with `settings.toml` and
  a workspace; `Given Virtualbricks is running` starts a `broadwayd`, then
  `python -m virtualbricks --noterm --lock none --workspace …` on this
  checkout, in English, on it, and waits for its main window. Each
  Virtualbricks has its own `broadwayd`: `broadwayd` aborts when a program
  it shows quits. One that quit starts again on a new `broadwayd`, and its
  output goes on in `output.log`. The settings turn off the alert of missing programs,
  which depends on the machine and would take the clicks; GTK's animations
  are off, so a popover is where it ends up at once.
- `a11y.py` finds the widgets through AT-SPI, as a screen reader does, and
  knows only the process the test started.
- `broadway.py` is a browser of `broadwayd`: it speaks the protocol of
  `broadway.js`, keeps the windows as `broadwayd` shows them, and sends the
  pointer at the middle of a widget. A click goes through GTK as a user's
  does: hidden, covered or disabled widgets don't get it. So does a turn of
  the wheel: a row scrolled out of its list doesn't show, so `rows()`
  turns it, as a user does, and waits for the scroll bar to move. It keeps
  the images of the windows too, for `recording.py`: see [The screenshot
  and the video](#the-screenshot-and-the-video).

## What it can't do yet

- Type: the browser sends only the pointer, so names and paths can't be
  typed in. `broadway.js` sends a key as `k` and `K` with its keysym: the
  browser can do the same.
- GTK 4: the browser speaks the Broadway of GTK 3.
- Clean up after a `pytest` that is killed, by `kill` or `timeout`:
  `dbus-daemon`, `broadwayd` and AT-SPI stay, with their folder in
  `/tmp/vb-e2e-*`. Ctrl-C cleans up.
