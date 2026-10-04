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
the steps that are missing: [STEPS.md](STEPS.md) lists them, and tells
how to add one.

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
pytest -n 8                              # eight scenarios at a time
pytest --alluredir=allure-results        # the results, for Allure
```

`pytest` runs the end-to-end tests, and those of `recording.py`
(`testpaths` in `pyproject.toml`); `trial` runs the others. A scenario takes
a few seconds; with `-n 8`, all of them take about as long as the longest:
13 s on a computer of eight cores.

With `-n`, the workers of pytest-xdist get the tests in an order that keeps
them busy alike: a long test beside a short one, by what each took in the
runs before, which pytest keeps in its cache, `.pytest_cache`. A new test is
taken for as long as the others; `conftest.py` says how.

- Nothing shows on your screen, and nothing reaches your desktop: the
  windows are on `broadwayd`, with a session bus of their own.
- Each scenario has a Virtualbricks of its own, with a temporary home,
  settings and workspace, and `--lock none` unless the scenario gives
  another: the tests run beside your own Virtualbricks, and never touch it.
  Their lock of `--lock system`, `user` and `workspace` is in their own
  folder, not `/tmp/virtualbricks.lock`, which yours may hold.
- Without the programs above, the tests are skipped, saying what is missing;
  a scenario tagged `@needs-vde_switch` is skipped without `vde_switch`.

## The files

| File | What it has |
| :- | :- |
| `features/*.feature` | The scenarios, a file for each area: `bricks.feature`, …; in folders too: see [Group the scenarios](#group-the-scenarios) |
| `steps.py` | The steps: what each line of a scenario does |
| `STEPS.md` | The steps there are, and how to add one |
| `projects/` | The projects of Virtualbricks 2.1 of the scenarios, a folder each, with its `.project` |
| `TODO.md` | The scenarios, written and to write, by area, and what they need that the tests can't do yet |
| `test_features.py` | Makes a test of each scenario of `features/` |
| `conftest.py` | The fixtures: `desktop`, shared, and `virtualbricks` and `other_virtualbricks`, for each scenario; the report of a step that fails, `--record-all` |
| `harness.py` | What the steps drive: `Virtualbricks`, with `find`, `click`, `key`, `drag`, `choose`, `row`, `children`, …; the `Desktop` and its `Screen`s |
| `a11y.py` | The widgets, as a screen reader sees them, through AT-SPI |
| `broadway.py` | The mouse and the keys: a browser of `broadwayd`, whose clicks, drags, wheel and keys reach GTK as a user's do; it keeps what the screen shows |
| `recording.py` | The screenshot and the video of a scenario, from what the browser kept |
| `test_recording.py` | The tests of `recording.py` |
| `../allurerc.mjs` | The configuration of the report of Allure |

## Write a scenario

1. **Say the use case in words**, as a user would do it: what they do, in
   order, and what they expect to see or to happen.
2. **Write it as a scenario**, in the `.feature` file of its area, or in a
   new one with a `Feature:` line and a sentence about the area. `Given`
   says how things are before, `When` what the user does, `Then` what must
   be true after; `And` repeats the word before. Use the steps there are:
   see [STEPS.md](STEPS.md).
3. **Run it.** pytest says which lines have no step; to have them all, with
   the code to start from:

   ```sh
   pytest --generate-missing --feature e2e/features
   ```

4. **Add the steps that are missing**, in `steps.py`: see
   [Add a step](STEPS.md#add-a-step).
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

A module that imports Twisted's reactor, as `brickfactory` and those of
`gui/`, can't be imported by `sitecustomize.py`: the default reactor would
be installed before Virtualbricks installs that of GTK, and Virtualbricks
wouldn't start (`ReactorAlreadyInstalledError` in `output.log`). Patch it
once Virtualbricks imports it, with a finder of imports first in
`sys.meta_path`:

```python
import importlib.abc
import importlib.util
import sys


class After(importlib.abc.MetaPathFinder):
    """Runs patch on the module name, once it is imported."""

    def __init__(self, name, patch):
        self.name = name
        self.patch = patch

    def find_spec(self, fullname, path, target=None):
        if fullname != self.name:
            return None
        sys.meta_path.remove(self)
        spec = importlib.util.find_spec(fullname)
        run = spec.loader.exec_module

        def exec_module(module):
            run(module)
            self.patch(module)

        spec.loader.exec_module = exec_module
        return spec


def patch(brickfactory):
    # the quit sees no running brick
    brickfactory.is_running = lambda brick: False


sys.meta_path.insert(0, After("virtualbricks.brickfactory", patch))
```

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
`broadwayd`; `other/` has those of the other Virtualbricks, if the scenario
has one, whose widgets and output the report has too; `desktop0/` has the
log of `dbus-daemon`.

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
more. With `-n`, the list at the end is missing: the step that failed says
the folder.

The browser keeps what `broadwayd` sends, the images of the windows,
compressed, and where they are; nothing is decoded while the scenario runs.
When it ends, `recording.py` decodes them as `broadway.js` does, draws the
screen with cairo and gives the frames to `ffmpeg`. Without `ffmpeg` there
is only the screenshot.

## The report of Allure

[Allure](https://allurereport.org/) makes a report of the scenarios, as web
pages: each with its steps, how long each took and the one that failed,
grouped by `Feature:`, with their tags. `allure-pytest-bdd`, of the group
`e2e`, writes the results of a run in the folder of `--alluredir=`, a file
for each scenario; Allure 3, of Node.js, makes the report of them, with
`allurerc.mjs`, at the root of the sources:

```sh
pytest -n 8 --alluredir=allure-results --clean-alluredir
rm -rf allure-report       # the report before, see below
npx allure@3 generate      # the report, in allure-report/
npx allure@3 open          # the report, in the browser
```

Write `--alluredir=` with its `=`: given as `--alluredir allure-results`,
pytest takes the folder for one of the tests to run before it knows the
option, and stops: "Defining 'pytest_plugins' in a non-top-level
conftest". `--clean-alluredir` leaves only the results of this run; without
it, a scenario run again shows as a retry.

The results are in git, to publish the report: `allure-results/`, those of
the last run, and `allure-history.jsonl`, the history of the runs, to
which `generate` adds the run of `allure-results/`, and whose trends the
report shows. Commit them together after a run whose report you publish;
`allure-report/` is left out of git. `npx` downloads Allure the first
time.

Remove `allure-report/` before `generate`. Allure 3 can't clean it:
`generate` writes the report in `allure-report/awesome/`, and moves it up
to `allure-report/` only if that is the one folder there. With the report
before still in place, the new one stays in `awesome/`, and `open` shows
the old one: a single run, with no history.

A scenario that fails has the screenshot and the video of its screen, of
the other Virtualbricks too if it has one, and `stdout`: what pytest
printed of the step that failed, the widgets that showed and the output
of Virtualbricks. With `--record-all`, each scenario has its screenshot and
video. The tests of `recording.py` aren't scenarios, and aren't in the
report; nor is a scenario skipped before its first step, as one tagged
`@needs-PROGRAM` without that program.

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
  checkout, in English, on it, and waits for its main window; the step
  `… with OPTIONS` gives it those of the scenario. It starts through a few
  lines of Python, `LAUNCH` in `harness.py`, which put its system lock in
  the folder of the tests. `other_virtualbricks` is a second one, of the
  same user, for `--connect`, `--command` and the locks. Each Virtualbricks
  has its own `broadwayd`: `broadwayd` aborts when a program it shows
  quits. One that quit starts again on a new `broadwayd`, and its
  output goes on in `output.log`. The settings turn off the alert of missing programs,
  which depends on the machine and would take the clicks; GTK's animations
  are off, so a popover is where it ends up at once.
- `a11y.py` finds the widgets through AT-SPI, as a screen reader does, and
  knows only the process the test started; it writes the text typed in
  them too, as an assistive tool does.
- `broadway.py` is a browser of `broadwayd`: it speaks the protocol of
  `broadway.js`, keeps the windows as `broadwayd` shows them, and sends the
  pointer at the middle of a widget. A click goes through GTK as a user's
  does: hidden, covered or disabled widgets don't get it. So does a turn of
  the wheel: a row scrolled out of its list doesn't show, so `rows()`
  turns it, as a user does, and waits for the scroll bar to move. A click
  comes half a second after the one before at least: GTK takes two clicks
  on a widget within 400 ms for a double click (`Browser.click` says when
  it happened). A drag is a press, moves and a release. A key goes as
  `broadway.js` sends it, and `broadwayd` gives it to the window that has
  the focus then: the one pressed last, once it has handled the press, so
  `key()` waits until GTK says the window is active. It keeps the images of
  the windows too, for `recording.py`: see [The screenshot and the
  video](#the-screenshot-and-the-video).

## What it can't do yet

- Text as keys: `broadway.js` sends a key as `k` and `K` with its keysym,
  but the Broadway backend of GTK 3 leaves unset the modifiers that a key
  consumes, which GTK reads anyway (`_gtk_key_hash_lookup`): a key then
  sometimes matches an accelerator or a mnemonic, as a "p" Ctrl+P, which
  opens Settings, and a "b" the Alt+B of the tab Bricks. So `type()`
  writes the text through AT-SPI, as an assistive tool does, and GTK
  inserts it as if typed. `key()` sends a key alone, as Escape, Return or
  the Ctrl+L of a file chooser: one that the window has with no other
  modifier.
- Drag and drop: the Broadway backend of GTK 3 has none
  (`gdkdnd-broadway.c` finds no window under the pointer), so a row of
  bricks dropped on another can't be tested. A widget that follows the
  pointer itself, as the picture of the tab Topology, can.
- GTK 4: the browser speaks the Broadway of GTK 3.
- Clean up after a `pytest` that is killed, by `kill` or `timeout`:
  `dbus-daemon`, `broadwayd` and AT-SPI stay, with their folder in
  `/tmp/vb-e2e-*`, and the workspaces on a drive without a trash, in
  `/dev/shm/vb-e2e-*`. Ctrl-C cleans up.
