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
- [ ] Type, as names and paths (TODO.md, End-to-end tests): Rename, the
  search, the README, the paths of the file choosers (Ctrl+L)
- [ ] Drag: a press, moves and a release, for a row dropped on another,
  which connects the two bricks, and for the picture of the Topology tab
- [ ] Start Virtualbricks with the options of a scenario: `--listen`,
  `--lock workspace`, `--connect`; and a second Virtualbricks beside it
- [ ] Make a disk image in a fixture, with `qemu-img create`, for the
  virtual machines and the Images tab
- [ ] Make a small archive of 2.1 in a fixture, a `.vbp` of the
  `.project` of `e2e/projects/DTN2hops_26_Feb_2026`

# Bricks and links

- [x] Run a switch for a while, then stop it
  "A switch runs for a while, then stops", `bricks.feature`
- [ ] Join two switches with a wire
  the wire runs with the sockets of both
- [ ] Start all the bricks with Start All, then stop them with Stop All
  each brick that can start runs; then none runs
- [ ] Open a tunnel: a tunnel server and a tunnel client of this
  computer, each on a switch
  both run, the client connected; `@needs-vde_cryptcab`
- [ ] Start a router between two switches
  `@needs-vde_router`, which this machine lacks
- [ ] Run a switch wrapper on a switch that a fixture starts
  its row stops saying Not configured once it has the path; needs typing
- [ ] See why a brick can't start: a switch wrapper without a path
  its row says Not configured, Start does nothing, no process
- [ ] See a brick whose program fails: a `vde_switch` that exits at once
  its row says Stopped, the error shows, and the messages window has the
  output of the program
- [ ] Change the settings of a switch with the buttons of its panel:
  ports and hub mode, then OK
  its row says the ports; the next `vde_switch` runs with them
- [ ] Cancel the settings of a switch: nothing changes
  the row, and `project.toml` after a quit
- [ ] Duplicate a brick from its menu
  the copy has the name Virtualbricks gives it and the same settings
- [ ] Delete a brick from its menu, after the confirmation
  its row goes, and `project.toml` loses it after a quit
- [ ] Show only the running bricks with the switch over the list
- [ ] Quit while a switch runs
  refused, "Cannot close virtualbricks: there are running bricks"; the
  switch still runs
- [ ] Add a switch, quit and start again
  `project.toml` has sw1, and the main window shows it

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
- [ ] Add an existing disk image from a file
  copied into the image folder, or used where it is; needs typing
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

- [ ] Make a new project from the Projects window, with the name it
  suggests
  the main window shows it; its folder has `project.toml`
- [ ] Open another project from the Projects window
  the main window shows its bricks; refused while a brick runs
- [ ] Open the project open last at the next start, after opening
  another one
- [ ] Duplicate a project, with the name it suggests
  its folder is a copy of the other
- [ ] Remove a project from the Projects window, after the confirmation
  its folder goes to the trash, or is deleted without one
- [ ] Import the archive of 2.1, DTN2hops_26_Feb_2026.vbp
  converted at the import: the main window lists its 13 bricks; needs
  typing for the path, and the archive of a fixture
- [ ] Export a project to an archive, then import it under another name
  the archive has the project and its private disks; needs typing
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
- [ ] Export the picture of the lab to a PNG file
  the file is a PNG; needs typing for the path

# Readme

- [ ] See the README of a project in the Readme tab, rendered
  a project of a fixture with a README
- [ ] Edit the README, then see it in the preview
  the file README has the text; needs typing

# Command line and sockets

- [ ] Start a brick with `--command` while the windows show it
  its row says Running; needs `--listen`
- [ ] Open the windows of another Virtualbricks with `--connect`, and
  start a brick there
  the brick runs on the other one; needs a second Virtualbricks
- [ ] Start a second Virtualbricks on the same workspace with
  `--lock workspace`
  it exits with the reason; the first one goes on

# Out of reach on Broadway

- The tray icon: Broadway has no system tray
- A tap and a capture interface that run: they need `CAP_NET_ADMIN`
- A file dropped from the desktop on the Projects window

# Conventions

- One item per line, starting with a verb, the use case in words; detail
  indented below it: what it checks besides the windows, and what it
  needs.
- Sections by area, the most used first; what the scenarios need comes
  before them all.
- A scenario written is ticked where it is, with its name and its
  feature file.
