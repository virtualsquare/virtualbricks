# The steps of the end-to-end tests

A step is what a line of a scenario does: a Python function of `steps.py`,
under the decorator of its words. This file lists the steps there are, and
tells how to add one; [README.md](README.md) tells how to run the scenarios
and write one.

## The steps there are

The steps of a user:

| Step | What it does |
| :- | :- |
| `Given Virtualbricks is running` | Starts Virtualbricks, and waits for its main window |
| `When I add the switch sw1` | New Brick, the kind, then OK on its settings; the new brick must be named `sw1`. Any kind of New Brick: `the virtual machine vm1`, `the router r1`, … |
| `When I join sw1 and sw2 with the wire w1` | New Brick, Wire, then sw1 for its left end and sw2 for its right end, and OK; the new wire must be named `w1` |
| `When I start sw1` | Its Start button; it must run, with new processes, but a switch wrapper, which runs no program |
| `When I try to start wr1` | A click on its Start, also when it is disabled, as a user may click it |
| `When I stop sw1` | Its Stop button; it must stop |
| `When I give sw1 34 ports and hub mode, with the buttons of its settings` | Configure… in its menu, the + or the - of Ports until it says 34, Hub mode turned on, then OK |
| `When I give sw1 34 ports and hub mode in its settings, then cancel` | The same, then Cancel |
| `When I duplicate sw1 from its menu` | Duplicate, in its menu; then the list has one more brick |
| `When I delete sw2 from its menu, and confirm` | Delete…, in its menu, then Yes to the question that names it |
| `When I start all the bricks` | Start All; each brick whose row said Stopped must run, with the process its row tells, and Start All must start no other |
| `When I stop all the bricks` | Stop All; each brick that ran must be able to start again |
| `When I show only the running bricks` | Running, of the switch over the list; then it is on |
| `When I show all the bricks` | All, of the switch over the list; then it is on |
| `When I wait 5 seconds` | Waits |
| `When I quit Virtualbricks` | File, then Quit |
| `When I start Virtualbricks again` | Starts it with its settings, as after it ran before, on a new screen, and waits for a window |
| `When I open the Projects window` | Projects…, in the menu Projects |
| `When I make a new project with the name it suggests, new_project-2` | New…, in the Projects window: its name must be the one the dialog suggests; then Create, and the dialog closes |
| `When I open the project new_project` | In the Projects window, its row, then Open in its details; the window closes |
| `When I try to open the project new_project` | The same, without waiting for the window to close |
| `When I duplicate the project new_project with the name it suggests, new_project-copy` | In the Projects window, its row, then Duplicate… in its details: the name of the copy must be the one the dialog suggests; then Duplicate, with Open the copy as it is, and the dialog closes |
| `When I import the archive lab.vbp of my home folder with the name it suggests, lab` | Import…, in the menu Projects; in the window, the button of the file, then Home and the archive in the file chooser, and Open; the name must be the one the window suggests; then Import, with Open the project as it is, until the window says how it ended |
| `When I close the Import Project window` | Its button Close |
| `Then sw1 is running` | Its row says Running, and the processes of its start run |
| `Then sw1 is still running` | The same |
| `Then w1 runs with the sockets of sw1 and sw2` | It runs, and a `vde_plug` of its start is in the socket of each switch: the one its `vde_switch` listens on |
| `Then sw1 is stopped` | Its row says Stopped, and no process of it runs: those of its start have quit, and none has its sockets |
| `Then sw1 is not running` | The same |
| `Then sw1 runs with 34 ports, as a hub` | It runs, and its `vde_switch` has `-n 34` and `-x` |
| `Then no brick runs` | No row of the list says Running, and no process of a brick runs: neither those that the steps started nor any with a socket of the tests; Virtualbricks runs no program |
| `Then wr1 is not configured` | Its row says Not configured, its Start is disabled, and no process has its sockets |
| `Then wr1 can't start: "Configure wr1 first"` | Its Start is disabled, and the state in its row says why, in its tooltip, which the screen readers read |
| `Then Virtualbricks has quit` | It exited with 0, and no brick runs any more |
| `Then Virtualbricks hasn't quit` | It still runs, and its main window shows |
| `Then the main window shows the project lab` | Its title names the project |
| `Then the Projects window says "Cannot open new_project: …"` | A label of the window has the text, as the bar over its list |
| `Then the Import Project window says "Imported as "lab"."` | A label of the window has the text |
| `Then the folder of new_project-2 has project.toml` | The folder of the project in the workspace has the file of a project, which TOML reads, with its format |
| `Then the folder of new_project-copy is a copy of that of new_project` | It has project.toml, and the two folders of the workspace have the same files, with the same bytes |
| `Then the list of bricks has`, with a table under it | The rows of the list, all of them and in order, scrolled through, once they are those of the table: the name of each brick, its detail and its state; with only the titles of the columns, no brick, as the tab says No Bricks Yet |
| `Then the list of bricks shows only sw1, with its process` | Its row alone, once it says Running and, in place of its summary, a process of its start, which still runs |
| `Then project.toml has the bricks`, with a table under it | The bricks of the file of the project, all of them and in order: the name of each and its type |
| `Then project.toml has sw1 with`, with a table under it | Its settings in the file of the project, a name and a value each, the value as TOML writes it |
| `Then project.toml has sw2 with the settings of sw1` | The two bricks have the same settings in the file of the project |

The steps of a program that fails:

| Step | What it does |
| :- | :- |
| `Given a vde_switch that writes "no switch today" and exits with 3` | A script in place of `vde_switch`, in the folder of the VDE programs of the project that Virtualbricks opens at its first start, `new_project`; before Virtualbricks starts |
| `Then an error says "Process terminated. process ended with exit code 3"` | The alert Error shows, with the text |
| `When I close the error` | Its button Close |
| `When I open the messages window` | Logs, in the menu File |
| `Then the messages window has the output of sw1: "no switch today"` | A line of the messages comes from sw1 and has the text, as its program wrote it, after `2>` when on its standard error |

The steps of a switch that another program runs, for a switch wrapper:

| Step | What it does |
| :- | :- |
| `Given a switch that another program runs` | A `vde_switch` that the tests run, not Virtualbricks, in the runtime folder of the tests; it quits at the end of the scenario |
| `When I give wr1 the control folder of that switch` | Configure… in its menu, the folder typed in Control folder, then OK; its row says the folder |
| `Then the switch that another program runs still runs` | Its process runs, and its socket is there |

The steps of the disk images:

| Step | What it does |
| :- | :- |
| `Given the empty disk image disk.qcow2 of 1 GB, in my home folder` | Made with `qemu-img create`, of MB or GB of 1000, as Virtualbricks counts them, in the format of its extension: `qcow2` or `raw` |
| `When I add an existing image, disk.qcow2 of my home folder, with the name it suggests, disk` | The tab Images, Add Image, then Existing Image…; in the dialog, the button of the file, then Home and the file in the file chooser, and Open; the name must be the one the dialog suggests; then Add, with Copy it to the image folder as it is, and the dialog closes |
| `Then the list of images has`, with a table under it | The rows of the tab Images, all of them and in order, once they are those of the table: the name of each image, its detail without the space its file takes (`… on disk`), which depends on the file system, and its state |
| `Then the image folder has disk.qcow2, a copy of that of my home folder` | `vimages` of the workspace has the file, with the same bytes, and the home still has it |
| `Then project.toml has the image disk, of disk.qcow2 in the image folder` | The image in the file of the project has the file of the image folder |

The steps of the migration of Virtualbricks 2.1:

| Step | What it does |
| :- | :- |
| `Given the project DTN2hops_26_Feb_2026 of Virtualbricks 2.1` | A copy of `projects/DTN2hops_26_Feb_2026` in the workspace |
| `Given the archive DTN2hops_26_Feb_2026.vbp of Virtualbricks 2.1, in my home folder` | The archive that 2.1 exported of `projects/DTN2hops_26_Feb_2026`, in the home: its `.project`, without images, in a tar compressed with gzip |
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
  | `disabled(role, name, within=None)` | The widget, once it shows and is disabled |
  | `click(role, name, within=None, enabled=True)` | Clicks it, once it shows and is enabled; with `enabled=False`, also if it is disabled |
  | `spin(name, by, within=None)` | Clicks the + of the spin button `by` times, or its - `-by` times; after each click, its value changes |
  | `type(text, role, name=None, within=None)` | Clicks it, once it shows and is enabled, and types text at its cursor; then it has the text: see [What it can't do yet](README.md#what-it-cant-do-yet) |
  | `choose(item, menu)` | A menu of the menu bar, then its item |
  | `row(name)` | The row of a list with that name, for `within=` |
  | `rows(within)` | The rows of the list in a scroll pane, from the first to the last, each the names of its labels: the wheel scrolls through it |
  | `names(role, within=None)` | The names of the widgets of that role that show now |
  | `wait_for(get, what)` | What `get()` returns, once it is true |
  | `children(parent=None)` | The processes that Virtualbricks, or the process `parent`, started and run |
  | `command_line(pid)` | The words of the command line of a process; none once it has quit |
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
readers; a widget without a name, as the entry of a setting, has that of
the label of it, as a screen reader says it. To see them, add
`And I print the widgets` where the scenario is, and run it with
`pytest -s`; a step that fails prints them too:

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
