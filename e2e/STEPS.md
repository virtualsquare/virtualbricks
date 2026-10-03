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
| `Given Virtualbricks is running with --listen` | Starts it with the options, as the shell splits them, in place of `--lock none`, and waits for its main window; with `--listen` alone, until it listens on the socket of its workspace too. With `--connect`, these are the windows of the other Virtualbricks, which runs the bricks: see the steps of another Virtualbricks |
| `When I add the switch sw1` | New Brick, the kind, then OK on its settings; the new brick must be named `sw1`. Any kind of New Brick: `the virtual machine vm1`, `the router r1`, … |
| `When I join sw1 and sw2 with the wire w1` | New Brick, Wire, then sw1 for its left end and sw2 for its right end, and OK; the new wire must be named `w1` |
| `When I start sw1` | Its Start button; it must run, with new processes, but a switch wrapper, which runs no program |
| `When I try to start wr1` | A click on its Start, also when it is disabled, as a user may click it |
| `When I stop sw1` | Its Stop button; it must stop |
| `When I give sw1 34 ports and hub mode, with the buttons of its settings` | Configure… in its menu, the + or the - of Ports until it says 34, Hub mode turned on, then OK |
| `When I give sw1 34 ports and hub mode in its settings, then cancel` | The same, then Cancel |
| `When I give sw1 34 ports and hub mode in its settings, then press Escape` | The same, then Escape |
| `When I turn on "No display" in the settings of vm1, on its page Display` | Configure… in its menu; the page, in the list at the left of its settings, then the switch of the setting, which must be the other way, turned on, or off with `turn off`; then OK |
| `When I terminate vm1, from its menu` | Process and its number, in its menu, then Terminate: SIGTERM, which a machine stops at, where its Stop asks the system of the machine to stop; then it can start again, and the processes of its start have quit |
| `When I duplicate sw1 from its menu` | Duplicate, in its menu; then the list has one more brick |
| `When I delete sw2 from its menu, and confirm` | Delete…, in its menu, then Yes to the question that names it |
| `When I start all the bricks` | Start All; each brick whose row said Stopped must run, with the process its row tells, and Start All must start no other |
| `When I stop all the bricks` | Stop All; each brick that ran must be able to start again |
| `When I show only the running bricks` | Running, of the switch over the list; then it is on |
| `When I show all the bricks` | All, of the switch over the list; then it is on |
| `When I wait 5 seconds` | Waits |
| `When I quit Virtualbricks` | File, then Quit |
| `When I start Virtualbricks again` | Starts it with its settings, as after it ran before, on a new screen, and waits for a window |
| `Given the workspace is on a drive without a trash` | A folder in `/dev/shm` for the workspace, before Virtualbricks starts: a file system in memory that the system mounts, where the desktop makes no trash; removed once Virtualbricks has stopped |
| `When I open the Projects window` | Projects…, in the menu Projects |
| `When I make a new project with the name it suggests, new_project-2` | New…, in the Projects window: its name must be the one the dialog suggests; then Create, and the dialog closes |
| `When I save the project` | Save, in the menu Projects: the open project, with its README |
| `When I open the project new_project` | In the Projects window, its row, then Open in its details; the window closes |
| `When I try to open the project new_project` | The same, without waiting for the window to close |
| `When I duplicate the project new_project with the name it suggests, new_project-copy` | In the Projects window, its row, then Duplicate… in its details: the name of the copy must be the one the dialog suggests; then Duplicate, with Open the copy as it is, and the dialog closes |
| `When I remove the project new_project, and move it to the trash` | In the Projects window, its row, then Remove… in the menu of its details; the question that names it says its folder goes to the trash: Move to Trash, and the question closes |
| `When I remove the project new_project, which can't go to the trash, and delete it permanently` | The same, where the question has no Move to Trash and says the drive of the workspace has no trash: Delete Permanently |
| `When I import the archive lab.vbp of my home folder with the name it suggests, lab` | Import…, in the menu Projects; in the window, the button of the file, then Home and the archive in the file chooser, and Open; the name must be the one the window suggests; then Import, with Open the project as it is, until the window says how it ended |
| `When I import the archive new_project.vbp of my home folder, typing its path, with the name it suggests, new_project-2` | The same, where in the file chooser, once clicked, Ctrl+L shows the entry of its location: the path of the archive typed there, then Return once Open is enabled |
| `When I close the Import Project window` | Its button Close |
| `When I export the project to new_project.vbp of my home folder` | Export…, in the menu Projects, for the open project; the window suggests the archive in the home; then Export, and Close once it says where it exported it |
| `Then sw1 is running` | Its row says Running, and the processes of its start run; when no step started it, as with `--command`, the process its row tells, which has its sockets |
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
| `Then the main window shows the project lab on this computer` | The windows of another Virtualbricks: their title names the project and where it runs |
| `Then the Projects window says "Cannot open new_project: …"` | A label of the window has the text, as the bar over its list |
| `Then the Projects window doesn't list new_project` | No row of its list has the project |
| `Then the Import Project window says "Imported as "lab"."` | A label of the window has the text |
| `Then the folder of new_project-2 has project.toml` | The folder of the project in the workspace has the file of a project, which TOML reads, with its format |
| `Then the folder of new_project-copy is a copy of that of new_project` | It has project.toml, and the two folders of the workspace have the same files, with the same bytes |
| `Then the archive new_project.vbp of my home folder has the bricks`, with a table under it | The bricks of the project.toml of the archive, all of them and in order: the name of each and its type |
| `Then the folder of new_project is in the trash` | The workspace has no folder new_project, and the trash of the home has it: a `.trashinfo` with its path, and the folder, with its project.toml |
| `Then the folder of new_project is deleted, and in no trash` | The workspace has no folder new_project, and no trash has its path: neither that of the home, nor `.Trash/UID` and `.Trash-UID` at the top of the drive of the workspace |
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
| `Given a vde_switch that writes these lines, and exits with 3`, with a text under it | The same as `writes "no switch today"`, with the lines of the text, written at once |
| `Then the messages window has the message of sw1: "Process terminated. process ended with exit code 3"` | A line of the messages comes from sw1 and says the text |
| `Then the messages window has the output of sw1: "no switch today", and 2 more lines folded` | A line of the messages comes from sw1: the first line of the output of its program, after `2>`, and its toggle, `▸ 2 more lines`; no line of them shows under it |
| `When I unfold the output of sw1 in the messages window` | A click on the toggle of the output of sw1, a run of the text of the window; then it says `▾` |
| `Then the messages window has the output of sw1, unfolded`, with a text under it | The first line of the text is that of the output of sw1, with its toggle unfolded, `▾ 2 more lines`; the others show under it |

The steps of a switch that another program runs, for a switch wrapper:

| Step | What it does |
| :- | :- |
| `Given a switch that another program runs` | A `vde_switch` that the tests run, not Virtualbricks, in the runtime folder of the tests; it quits at the end of the scenario |
| `When I give wr1 the control folder of that switch` | Configure… in its menu, the folder typed in Control folder, then OK; its row says the folder |
| `Then the switch that another program runs still runs` | Its process runs, and its socket is there |

The steps of another Virtualbricks, of the same user, with the same home and
workspace:

| Step | What it does |
| :- | :- |
| `Given another Virtualbricks runs with --no-gui --listen` | Starts it with the options: its main window shows, or, with `--no-gui`, it listens on the socket of `--listen` alone |
| `When I start another Virtualbricks with --lock workspace` | The same, without waiting for it: it may exit |
| `When I run virtualbricks --command brick start sw1` | `virtualbricks --command` and the words, as the shell splits them, in the workspace of the scenario; it must exit with 0 |
| `Then the other Virtualbricks exits with 1, saying "Another Virtualbricks is running …"` | It exits with the status, and its output has the text |
| `Then the other Virtualbricks names the process of Virtualbricks` | Its output says `Held by process PID`, that of the first |
| `Then sw1 runs in the other Virtualbricks` | The processes of its start are the other's, and the windows of it run none |

The steps of the events, in the tab Events:

| Step | What it does |
| :- | :- |
| `When I make an event that starts sw1 after 2 seconds, with the name it suggests, new_event` | New Event, in the tab Events: the name must be the one the dialog suggests; the seconds typed in Wait, then Create; in the settings of the event, Add Action, Start a brick and the brick, then OK |
| `When I make an event that starts sw2 at once, with the name it suggests, new_event` | The same, with 0 seconds in Wait |
| `When I make an event without actions, with the name it suggests, new_event` | New Event, in the tab Events, with the name it suggests: Create, then OK in the settings of the event |
| `When I start the event new_event` | Its Start, in the tab Events; then it waits: its Stop shows |
| `When I stop the event new_event while it waits` | Its Stop, in the tab Events, while its row says Waiting; then its Start shows, and its row says Ready |
| `When I run the event new_event now, from its menu` | Run Now, in its menu, in the tab Events; then the menu closes |
| `When I choose new_event in When It Starts, in the menu of sw1` | In the menu of the brick, When It Starts or When It Stops, then the event, and Escape, as a choice leaves the menu open. The choices of a menu of GTK 3 don't tell AT-SPI which is on: the row of the event says it, `· when sw1 starts` |
| `Then new_event counts down from 2 seconds, then starts sw1` | Its row says `Waiting · 2 s`, then `Waiting · 1 s`, each in turn, while no process of sw1 runs; then Ready, and a process of sw1 runs |
| `Then the list of events has`, with a table under it | The rows of the tab Events, all of them and in order, once they are those of the table: the name of each event, its detail and its state; with only the titles of the columns, no event, as the tab says No Events Yet |

The steps of a row of the tab Bricks that find it by its name take an event
too, in the tab Events: `Then new_event can't start: "Add an action to
new_event first"`, `When I try to start new_event`, `Then new_event is not
configured`. A step of a brick needs the tab Bricks: `When I open the tab
Bricks` first, after a step of the events.

The steps of the picture of the lab, in the tab Topology:

| Step | What it does |
| :- | :- |
| `When I zoom in on the picture of the lab 5 times` | The tab Topology, then its Zoom In, so many times; or its Zoom Out, with `zoom out` |
| `When I zoom the picture of the lab back to 100%` | The tab Topology, then its zoom level, whose tooltip says Zoom to 100% |
| `Then the zoom level of the picture of the lab is 150%` | The zoom level of the tab says it, as the screen readers read it: AT-SPI can't see the drawing itself |
| `When I export the picture of the lab to lab.png of my home folder, typing its path` | The tab Topology, More, then Export as Image…; in the file chooser, the path typed in Name in place of the name it suggests, then Save, and it closes |
| `Then the file lab.png of my home folder is a PNG image, not blank` | The file has the bytes of a PNG at its start, cairo reads it, and its pixels aren't all alike |
| `When I drag the picture of the lab 100 pixels to the left` | A press on the background, under the bricks, which are a row in the middle of its height, a move to the left or to the right, and a release; the picture must be wider than the tab |
| `Then the picture of the lab moved 100 pixels to the left` | Its horizontal scroll bar moved as much the other way |

The steps of the tab Readme:

| Step | What it does |
| :- | :- |
| `Given the project new_project has the README`, with a text under it | The folder of the project in the workspace, with a `project.toml` if it has none, and the text in its `README`; before Virtualbricks starts, which opens `new_project` at its first start |
| `When I open the tab Readme` | Its page tab, in the main window, until it is the one that shows; any tab, as `the tab Bricks` |
| `When I write the README in the Readme tab`, with a text under it | The tab Readme, its Edit, then the text typed in its editor |
| `When I show the preview of the README` | The Preview of the tab Readme |
| `Then the Readme tab shows the README rendered`, with a table under it | The runs of text of the preview, all of them and in order, a line at a time: the text of each, without the spaces at its ends, and its style, as AT-SPI tells it: `large`, `bold`, `italic`, `monospace`, or none |
| `Then the README file of new_project has`, with a text under it | The file `README` of the folder of the project has the text, once Virtualbricks has written it, as it does when it saves the project |

The steps of the Settings window:

| Step | What it does |
| :- | :- |
| `When I turn off "Enable systray" in the Settings window, on its page Application` | Settings, in the menu File; on the page, the switch of the label, which must be the other way, turned off, or on with `turn on`; then OK, and the window closes |
| `When I open the Settings window` | Settings, in the menu File |
| `Then the page Application of the Settings window has "Enable systray" off` | The page, then the switch of the label: it is off, or on |
| `Then settings.toml has`, with a table under it | The settings of the table in the settings file, a name and a value each, the value as TOML writes it, once Virtualbricks has written them |
| `Then project.toml has the settings`, with a table under it | The same, in the table `settings` of the file of the project |

The steps of the disk images:

| Step | What it does |
| :- | :- |
| `Given the empty disk image disk.qcow2 of 1 GB, in my home folder` | Made with `qemu-img create`, of MB or GB of 1000, as Virtualbricks counts them, in the format of its extension: `qcow2` or `raw` |
| `Given the empty disk image disk.qcow2 of 1 GB, in my home folder, with the snapshot clean` | The same, then the snapshot, made with `qemu-img snapshot -c` |
| `When I add an existing image, disk.qcow2 of my home folder, with the name it suggests, disk` | The tab Images, Add Image, then Existing Image…; in the dialog, the button of the file, then Home and the file in the file chooser, and Open; the name must be the one the dialog suggests; then Add, with Copy it to the image folder as it is, and the dialog closes |
| `When I add an existing image, disk.qcow2 of my home folder, used where it is, with the name it suggests, disk` | The same, with Use it where it is in place of the copy |
| `When I add a new empty disk, disk, of 20 MB in the format raw` | The tab Images, Add Image, then New Empty Disk…; in the dialog, the name typed, the size typed in Size, its unit and the format chosen in their lists, the folder as it is, the image folder; then Create, and the dialog closes |
| `When I give vm1 the image disk, on its disk hda` | Configure… in its menu; on the page Disks of its settings, Add Disk and the device, then the image in the picker of the new disk; then OK |
| `When I open the details of disk` | Details…, in its menu, in the tab Images; then they show, with its name |
| `When I remove the image disk, which the disk vm1 (hda) loses, and move its file to the trash` | Remove…, in its menu, in the tab Images: the dialog asks to remove it, and says that the disks lose it, `The disk vm1 (hda) will have no image.`; Also move the file to the trash turned on, then Remove, and the dialog closes |
| `When I remove the image disk, which the disk vm1 (hda) loses, and whose file new_project uses too` | The same, where the dialog says `The project new_project uses the file too: it stays.`, and offers nothing for the file; then Remove |
| `When I find the file of debian13, debian13.qcow2 of my home folder` | Find the File…, in its menu, in the tab Images; in the dialog, which asks where the file is, the button of the file, then Home and the file in the file chooser, and Open; then Use This File, and the dialog closes |
| `Then the list of images has`, with a table under it | The rows of the tab Images, all of them and in order, once they are those of the table: the name of each image, its detail without the space its file takes (`… on disk`), which depends on the file system, and its state |
| `Then the image folder has disk.qcow2, a copy of that of my home folder` | `vimages` of the workspace has the file, with the same bytes, and the home still has it |
| `Then project.toml has the image disk, of disk.qcow2 in the image folder` | The image in the file of the project has the file of the image folder |
| `Then project.toml has the image disk, of disk.qcow2 of my home folder` | The same, with the file of the home |
| `Then project.toml has the disk hda of vm1, without an image` | The disk of the machine, in the file of the project, has no image |
| `Then the image folder has no copy of disk.qcow2` | The home still has the file, and no file of `vimages`, if there is one, has its bytes |
| `Then the image folder has disk.raw, a raw disk of 20 MB` | `vimages` has the file, which `qemu-img info` says is of the format, with a disk of the size, up to a sector more |
| `Then the details of disk have`, with a table under it | The facts of the table, a name and a value each, as File or Format, are those of the details of the image, which show, once it has read its file |
| `Then the details of disk say what qemu-img info says of disk.qcow2 of the image folder` | The facts of the details are those of `qemu-img info` of the file: File, its path with `~` for the home; Format; Size, the disk and the space it takes, in MB and GB of 1000; Snapshots, if any; and Changed, when the file changed, which isn't of `qemu-img` |
| `Then vm1 runs on a private copy of disk.qcow2 of the image folder` | It runs, and a disk of its QEMU, after `-hda` or another device, is a file of its own whose backing file is that of the image folder, as `qemu-img info -U` says |
| `Then the file disk.raw of the image folder is in the trash` | `vimages` has it no more, and the trash of the home has it: a `.trashinfo` with its path, and the file |
| `Then the image folder still has disk.raw, in no trash` | `vimages` has the file, and the trash of the home doesn't |

The steps of the migration of Virtualbricks 2.1:

| Step | What it does |
| :- | :- |
| `Given the project DTN2hops_26_Feb_2026 of Virtualbricks 2.1` | A copy of `projects/DTN2hops_26_Feb_2026` in the workspace |
| `Given the archive DTN2hops_26_Feb_2026.vbp of Virtualbricks 2.1, in my home folder` | The archive that 2.1 exported of `projects/DTN2hops_26_Feb_2026`, in the home: its `.project`, without images, in a tar compressed with gzip |
| `Given the settings of Virtualbricks 2.1, with DTN2hops_26_Feb_2026 open last` | `~/.virtualbricks.conf`, of the workspace of the tests, in place of the settings: the next start is the first |
| `Given the project lab of Virtualbricks 2.1, whose .project is`, with a text under it | A folder lab in the workspace, whose `.project` has the text; the steps keep it, to check it later |
| `Given the project DTN2hops_26_Feb_2026 of Virtualbricks 2.1, as the single file lab.vbl in the workspace` | Its `.project`, as a file of the workspace, as the versions before 2.1 kept a project |
| `Given the projects lab01 to lab40 of Virtualbricks 2.1, copies of DTN2hops_26_Feb_2026` | So many copies of `projects/DTN2hops_26_Feb_2026` in the workspace: a word and a number, of as many digits in both |
| `When I start Virtualbricks for the first time` | Starts it without its settings, as after 2.1, and waits for a window |
| `When I close the migration window` | Its button Close |
| `When I close the migration window while it migrates` | Its button Close, once a project of the workspace has its `project.toml`; the window shows until it closes. The buttons are found without a search through the list, as the window answers AT-SPI only between two projects |
| `When I select lab in the migration window` | Its row; then the messages under the list are those of lab |
| `When I save the report of the migration to report.txt of my home folder, typing its path` | Save report…; in the file chooser, the path typed in Name in place of the name it suggests, then Save, and it closes |
| `Given Virtualbricks migrated DTN2hops_26_Feb_2026 at its first start` | The first start, the migration of the project, and its window closed |
| `Then the migration window shows` | Waits until it shows |
| `Then the migration window doesn't show` | Waits until it doesn't |
| `Then the migration window lists`, with a table under it | The rows of its list, all of them and in order, once they are those of the table, whose first line has the titles of the columns |
| `Then DTN2hops_26_Feb_2026 is migrated` | The migration ends, no row of the window failed, and the project has its `project.toml` |
| `Then lab isn't migrated` | Its folder in the workspace has no `project.toml` |
| `Then the migration window shows the error of lab: ".project:4 …"` | Under the list, the messages are those of lab, and one is the text, of that level: `error`, `warning` or `info` |
| `Then the old file lab/.project of the workspace stays as it was` | The file, which a step gave, has the same bytes |
| `Then some of the projects are migrated, and the others not` | The old projects that have their `project.toml` are those of the close of the window, as they were then, no other: the migration stopped there; some have none |
| `Then the projects not migrated before are migrated, and the others stay as they were` | The migration ends; each old project has its `project.toml`, and those of before the close the same, not written again |
| `Then the file report.txt of my home folder has`, with a text under it | The file has the text, line by line, the spaces at the end of a line aside |

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
- A text under a line, between two lines of `"""`, comes to its step as
  `docstring`, without the indentation of the `"""`.
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
  | `click_text(widget, index, length)` | Clicks the middle of length characters of the text of the widget, from the index of the character in `a11y.text()`: a link or a toggle of a text view, which must show. GTK 3 counts the images of a text view in the offsets of AT-SPI, not in its text: `a11y.offset()` turns one into the other |
  | `spin(name, by, within=None)` | Clicks the + of the spin button `by` times, or its - `-by` times; after each click, its value changes |
  | `type(text, role, name=None, within=None, over=False)` | Clicks it, once it shows and is enabled, a spin button in its text, left of its - and +, and types text at its cursor; then it has the text: see [What it can't do yet](README.md#what-it-cant-do-yet). With `over`, in place of the text it has, as a user who selects it all first |
  | `key(keys, window)` | Presses keys, as `Escape`, `Return` or `Control+l`, in window, a frame or a dialog, once it is active: click in it first, as the keys go to the window clicked last. Text goes with `type()` |
  | `drag(start, end, ready=None)` | Presses at start, a point of the screen, moves to end and releases there; `ready()`, if given, right before the press, half a second after the click before |
  | `choose(item, menu)` | A menu of the menu bar, then its item |
  | `row(name)` | The row of a list with that name, for `within=` |
  | `rows(within)` | The rows of the list in a scroll pane, from the first to the last, each the names of its labels: the wheel scrolls through it |
  | `names(role, within=None)` | The names of the widgets of that role that show now |
  | `wait_for(get, what)` | What `get()` returns, once it is true |
  | `children(parent=None)` | The processes that Virtualbricks, or the process `parent`, started and run; for the windows of another, those of the other |
  | `command_line(pid)` | The words of the command line of a process; none once it has quit |
  | `bricks(name=None)` | The processes with sockets in the run folder of the tests, as words of their command line or in one, as the `path=` of QEMU; with a name, those of that brick |
  | `describe()` | The widgets that show, one a line |
  | `start(*options)` | Starts it with the options of a scenario, and waits for its main window; with `--listen` alone, until it listens; with `--no-gui`, only that |
  | `launch(*options)` | Starts it with the options, without waiting |
  | `run(*options)` | Runs it, as with `--command`, until it exits: its exit status, its output and its errors |
  | `listens()` | Whether a Virtualbricks listens on the socket of `--listen` alone of its workspace |
  | `lab` | The Virtualbricks that runs the bricks it shows: itself, or the other one, for the windows of `--connect` |
  | `home`, `workspace`, `settings` | Its home, its workspace, and its settings file, which a step can remove; a step can move the workspace before Virtualbricks starts |

- `other_virtualbricks` is another Virtualbricks of the same user, not
  started, with the same home and workspace; its files are in the folder
  `other` of the scenario.
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
