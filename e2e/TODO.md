The scenarios that would cover Virtualbricks fairly, by area, the most
used first: those written are ticked, with their feature file. Each says
what it checks besides the windows (a process, a file), and what it needs
that the tests can't do yet: those needs come first.

# What the scenarios need first

- [x] Never a double click by chance: GTK takes two presses on a widget
  within 400 ms and 5 px for a double click, and a list activates a row
  on a single press only, so adding sw2 right after sw1 did nothing. A
  click comes 0.5 s after the one before at least (`Browser.click` in
  `broadway.py`)
- [x] Type, as names and paths: `type()` in `harness.py` writes the text
  through AT-SPI, at the cursor of a widget, as an assistive tool does:
  the Broadway backend of GTK 3 takes some keys for accelerators and
  mnemonics (README.md, What it can't do yet)
- [x] Keys alone: Escape, Return, the Ctrl+L of the file choosers:
  `key()` in `harness.py`, in the window clicked last, once GTK says it is
  active: `broadwayd` gives a key to the window it focused, and focuses the
  window pressed only once it has handled the press
- [x] Drag: a press, moves and a release, for the picture of the Topology
  tab: `drag()` in `harness.py`; a row dropped on another is out of reach,
  see below
- [x] Start Virtualbricks with the options of a scenario: `--listen`,
  `--lock workspace`, `--connect`; and a second Virtualbricks beside it:
  the steps `Given Virtualbricks is running with OPTIONS`, `Given another
  Virtualbricks runs with OPTIONS`, `When I run virtualbricks --command
  WORDS`; their system lock is in the folder of the tests
- [ ] Run the scenarios on X11 too, on Xvfb, beside Broadway: a second
  kind of screen in `harness.py`, chosen with an option as `pytest --screen
  x11`, Broadway the default; the steps don't change. It needs `xvfb`, and
  `python-xlib` or `xdotool` for XTest, the input of X11; not tried yet,
  without Xvfb on the machine. It would test what most users run, and what
  Broadway can't: real keys and drag and drop. The work: the screen, its
  input with XTest, and its recording with `ffmpeg`. What differs:

  | | Broadway, now | Xvfb |
  | :- | :- | :- |
  | Find the widgets | AT-SPI | AT-SPI, the same |
  | Clicks, wheel, drags | the browser of `broadway.py` | XTest |
  | Text | through AT-SPI: GTK's Broadway backend takes some keys for accelerators | keys, as typed |
  | A row dropped on another | out of reach: no drag and drop | can be tested, once a row starts a drag |
  | Screenshot and video | `recording.py` decodes what `broadwayd` sends | `ffmpeg -f x11grab` records the display |
  | Window manager | none needed | none: GTK focuses its windows itself, but places them otherwise |
  | Tray icon | none | none either: Xvfb has no tray |

- [x] Make a disk image in a fixture, with `qemu-img create`, for the
  virtual machines and the Images tab: the step `Given the empty disk
  image disk.qcow2 of 1 GB, in my home folder`
- [x] Make a small archive of 2.1 in a fixture, a `.vbp` of the
  `.project` of `e2e/projects/DTN2hops_26_Feb_2026`: the step `Given the
  archive DTN2hops_26_Feb_2026.vbp of Virtualbricks 2.1, in my home
  folder`

# Bricks and links

- [x] Run a switch for a while, then stop it
  "A switch runs for a while, then stops", `bricks.feature`
- [x] Join two switches with a wire
  "A wire joins two switches", `bricks.feature`
- [x] Start all the bricks with Start All, then stop them with Stop All
  "Start All starts the bricks that can start, Stop All stops them",
  `bricks.feature`
- [ ] Open a tunnel: a tunnel server and a tunnel client of this
  computer, each on a switch
  both run, the client connected; `@needs-vde_cryptcab`
- [ ] Start a router between two switches
  `@needs-vde_router`, which this machine lacks
- [x] Run a switch wrapper on a switch that a fixture starts
  "A switch wrapper runs on a switch that another program runs",
  `bricks.feature`
- [x] See why a brick can't start: a switch wrapper without a path
  "A switch wrapper without a control folder can't start, and its row
  says why", `bricks.feature`
- [x] See a brick whose program fails: a `vde_switch` that exits at once
  "A switch whose program fails at once shows the error and the output of
  the program", `bricks.feature`
- [x] Change the settings of a switch with the buttons of its panel:
  ports and hub mode, then OK
  "The buttons of the settings of a switch change its ports and its hub
  mode", `bricks.feature`
- [x] Cancel the settings of a switch: nothing changes
  "Cancel leaves the settings of a switch as they were", `bricks.feature`
- [x] Leave the settings of a switch with Escape: nothing changes
  "Escape leaves the settings of a switch as they were", `bricks.feature`
- [x] Duplicate a brick from its menu
  "Duplicate copies a brick with its settings, under its name with the
  next free number",
  `bricks.feature`
- [x] Delete a brick from its menu, after the confirmation
  "Delete removes a brick, once confirmed", `bricks.feature`
- [x] Show only the running bricks with the switch over the list
  "The switch over the list shows only the running bricks, with their
  process", `bricks.feature`
- [x] Quit while a switch runs
  "Quit is refused while a switch runs, and the switch still runs",
  `bricks.feature`
- [x] Add a switch, quit and start again
  "A switch added is in the project after a quit, and shows at the next
  start", `bricks.feature`

## Virtual machines

- [ ] Start a virtual machine with an empty disk, headless, and stop it
  QEMU runs with the disk of the project, and quits;
  `@needs-qemu-system-x86_64`, a disk image of a fixture
- [ ] Connect a virtual machine to a switch, with Connect To in its menu
  its row says "eth0 on sw1"; started, QEMU's command line has the
  socket of sw1
- [ ] Pause and continue a running virtual machine from Process in its
  menu
  its row says so, and QEMU's monitor too

### Disk images

- [ ] Add a new empty disk from the Images tab
  the file is in the image folder, of the size and format chosen;
  `@needs-qemu-img`
- [x] Add an existing disk image from a file, copied into the image
  folder
  "A disk image of my home folder, added from the Images tab, is copied
  into the image folder", `images.feature`
- [ ] Add an existing disk image from a file, used where it is
  its row has the path of the file, and no copy is made
- [ ] Give a virtual machine a disk image
  the row of the image names the machine; in use while it runs
- [ ] Remove a disk image, after the dialog that lists the disks that
  lose it
  the file stays, or goes to the trash when no project uses it
- [ ] Find the file of an image whose file is missing, as debian13 of
  DTN2hops_26_Feb_2026
  the row says the file is missing, then the file found
- [ ] See the details of an image: what `qemu-img info` says

# Projects

- [x] Make a new project from the Projects window, with the name it
  suggests
  "A new project made in the Projects window, with the name it suggests,
  opens", `projects.feature`
- [x] Open another project from the Projects window
  "Another project opened from the Projects window shows its bricks",
  `projects.feature`
- [x] Open another project while a brick runs: refused
  "Another project doesn't open while a brick runs, and the brick still
  runs", `projects.feature`
- [x] Open the project open last at the next start, after opening
  another one
  "The project opened last opens at the next start", `projects.feature`
- [x] Duplicate a project, with the name it suggests
  its folder is a copy of the other
  "A project duplicated with the name it suggests is a copy of the other,
  and opens", `projects.feature`
- [x] Remove a project from the Projects window, after the confirmation
  its folder goes to the trash, or is deleted without one
  "A project removed from the Projects window goes to the trash, once
  confirmed" and "A project removed from a workspace on a drive without a
  trash is deleted for good, once confirmed", `projects.feature`
- [x] Import the archive of 2.1, DTN2hops_26_Feb_2026.vbp
  converted at the import: the main window lists its 13 bricks
  "An archive of Virtualbricks 2.1 is converted at its import, and
  opens", `projects.feature`
- [x] Export a project to an archive, then import it under another name
  the archive has the project, its path typed in the file chooser; not its
  private disks yet, which need a virtual machine
  "A project exported to an archive, then imported with the name it
  suggests, has its bricks", `projects.feature`
- [ ] Rename a project
  its folder has the new name; needs typing

## Migration

- [x] Migrate a project of 2.1 and the settings at the first start, and
  open the project that was open last
  "An old project is migrated at the first start", `migration.feature`
- [x] Start again without migrating again
  "The next start doesn't migrate again", `migration.feature`
- [x] Run two switches of a migrated project and the link between them
  "Two switches of a migrated project and the link between them run",
  `migration.feature`
- [x] Migrate a project of 2.1 copied into the workspace at the next
  start, and keep the project open last
  "An old project copied into the workspace is migrated",
  `migration.feature`
- [ ] See a project of 2.1 that can't be converted
  its row says ✗ Failed, its message shows under the list, its old file
  stays as it was
- [ ] Migrate a project of 2.1 that is a single file in the workspace
  it becomes a folder with `project.toml`
- [ ] Close the migration window while it migrates
  what is migrated stays, the rest is migrated at the next start; the
  project open last may not be saved yet
- [ ] Save the report of the migration
  the file has the rows and the messages; needs typing for the path

# Events

- [ ] Make an event that starts sw1 after 2 seconds, with the name it
  suggests, and start it
  its row counts down, then sw1 runs; `@needs-vde_switch`
- [ ] Run an event now, from its menu
- [ ] Stop an event while it waits
  sw1 never starts
- [ ] Start an event when a brick starts: When It Starts in the menu of
  sw1
- [ ] See an event without actions: it can't start, and its row says why

# Settings

- [ ] Change a setting of the application in Preferences, a switch
  `settings.toml` has it, and the next start too
- [ ] Change a setting of the project in Preferences, This project
  `project.toml` has it

# Messages window

- [ ] Read the messages of the run, among them a brick that failed,
  with the output of its program folded behind a toggle

# Topology

- [ ] See the picture of the lab, and zoom it with the buttons
  the zoom level changes; AT-SPI can't see the drawing itself
- [x] Drag the picture of the lab, zoomed in
  its scroll bar moves as the pointer
  "The picture of the lab, zoomed in, moves with the pointer that drags
  it", `topology.feature`
- [ ] Export the picture of the lab to a PNG file
  the file is a PNG; needs typing for the path

# Readme

- [ ] See the README of a project in the Readme tab, rendered
  a project of a fixture with a README
- [ ] Edit the README, then see it in the preview
  the file README has the text; needs typing

# Command line and sockets

- [x] Start a brick with `--command` while the windows show it
  its row says Running
  "A switch started with --command runs, and the windows show it",
  `command-line.feature`
- [x] Open the windows of another Virtualbricks with `--connect`, and
  start a brick there
  the brick runs on the other one, and still runs once the windows quit
  "The windows of another Virtualbricks start a switch there, and close
  without stopping it", `command-line.feature`
- [x] Start a second Virtualbricks on the same workspace with
  `--lock workspace`
  it exits with the reason; the first one goes on
  "A second Virtualbricks in the same workspace exits, saying why, and the
  first goes on", `command-line.feature`

# Out of reach on Broadway

- The tray icon: Broadway has no system tray
- A tap and a capture interface that run: they need `CAP_NET_ADMIN`
- A file dropped from the desktop on the Projects window
- A row of bricks dropped on another, which connects the two: GTK 3 on
  Broadway has no drag and drop (`gdkdnd-broadway.c` finds no window under
  the pointer). Besides, the rows never start a drag: a `GtkListBoxRow` has
  no window of its own, so its `drag_source_set` never gets the press, on
  X11 too; on Xvfb, a scenario could check it, see the needs

# Conventions

- One item per line, starting with a verb, the use case in words; detail
  indented below it: what it checks besides the windows, and what it
  needs.
- Sections by area, the most used first; what the scenarios need comes
  before them all.
- A scenario written is ticked where it is, with its name and its
  feature file.
