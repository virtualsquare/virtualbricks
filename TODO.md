# TODO

## Console

- [ ] Add a control socket in the runtime folder, so that
  `virtualbricks --command ...` talks to a Virtualbricks that runs
  (14 §11, K6 C)

# IDEAS

## Config

- [ ] Name the holders of the lock in the refusals of the migration
  command and window too (13 §10)
- [ ] Add a `lock` setting, maybe, so a shared machine doesn't need
  `--lock user` at every start (13 §9 L5)
- [ ] Move `locations` into `config` (maybe)
- [ ] Drop the `log_link_loops` setting, maybe: a loop always stops a
  start (10 §13)

## Projects

- [ ] Run two Virtualbricks at once in different workspaces: a lock for
  each workspace, and runtime directories that tell apart two projects
  of the same name (13 §10)
  - `--lock none` lets the second one start, but nothing keeps them
    apart
- [ ] Switch to another workspace from the GUI, and list the workspaces
  used, which `state.toml` already has
- [ ] Open several projects at once (04 §11: D6 rules it out for now)
- [ ] Make new projects from templates (04 §11)
- [ ] Import an archive dropped on the Projects window (04 §3, §9)
- [ ] Open a project by dropping its file on the main window
- [ ] Switch projects from a popover on the main window's title, once
  the main window has a header bar (04 §3, direction B)

## GUI code

- [ ] Add build_ui in the tabs classes as well
- [ ] Extract the logic from the windows: windows take state and
  callbacks
- [ ] Move the GTK code outside `gui/` into it:
  `migrate/gui.py`, the GTK parts of `scripts/virtualbricks.py`
- [ ] Move `startstop_brick` out of VBGUI, where it doesn't belong
- [ ] Stop passing VBGUI around: set the transient window of a dialog
  another way
- [ ] Take the work of the tabs (on_open, on_save, ...) to the main
  window, which coordinates it
- [ ] Add an attribute to the Tab class that says whether it is the tab
  shown (maybe)
- [ ] Move the tab files inside `virtualbricks/gui/mainwindow/tabs`
- [ ] Drop ngettext from `count()` in `gui/mainwindow/bricks/tab.py`:
  its singular and plural are the same text

## Bricks and programs

- [ ] Give the router settings and a panel: it has neither (07 §10,
  10 §13, 11 §11, 12 §9)
- [ ] Decide how an icon is chosen for any brick or event, and where it
  shows (10 §13, 11 §11)
- [ ] Select several bricks to start, stop or delete them at once
  (07 §10)
- [ ] Disconnect a brick from its menu: today only its panel does it
  (07 §10)
- [ ] Offer New Brick in the Topology tab too: on its empty page and in
  its More menu (12 §9)
- [ ] Make a brick already plugged into a switch, from the switch's
  menu: a tap, a machine or a wire (12 §9)
- [ ] Name a duplicate as New Brick names a brick: `sw3`, not
  `copy_of_sw1` (12 §9)
- [ ] Set a tap's address after its process starts, through sudo:
  `address_mode`, `ip_address`, `netmask` and `gateway`; today nothing
  does (10 §13, 11 §11)
- [ ] Declare which settings a running brick takes without a restart,
  in place of the `cbset_<name>` methods (10 §13, 11 §11)
  - the switch's ports, hub mode and FSTP, all of Netemu, a machine's
    USB devices
- [ ] Keep notes of your own on a brick: a key, shown in its panel and
  above its table (10 §13, 11 §11)
- [ ] Check every value in `brick.set()` before assigning any, for the
  console too (11 §11)
- [ ] Offer HDA sound: a controller and its codec together, which no
  single entry of the sound cards can start (11 §11)
- [ ] Show the command line of a machine as it would start, in the
  Advanced section of its panel (11 §11)
- [ ] Add a Programs window: each program found, its version, what it
  lacks and the packages to install (10 §13, 12 §9)
  - the tooltip of a missing program in New Brick could open it
- [ ] Ask QEMU for other architectures the same way; only
  qemu-system-x86 is recorded (10 §13)
- [ ] Support Wirefilter along Netemu

## Events

- [ ] Repeat an event every so many seconds (08 §10)
- [ ] Run the actions in order, each after the previous one: today they
  all start together (08 §10)
- [ ] Show the output of a shell command in the Logs window (08 §10)
- [ ] Add an action that changes a brick's settings, as the console's
  `brick set sw1 ports=16` (08 §10, E5)

## Disk images

- [ ] Show the images of all projects: each file once, the projects and
  disks that use it, and the files of vimages no project uses, as the
  copies an import leaves (09 §11 S3, 04 §11)
  - a file nobody uses can be added to this project or moved to the
    trash
- [ ] Render the description as Markdown in the details, as the Readme
  tab renders the README; `<file>.md` is read as plain text (09 §11)
- [ ] Define the images once for the workspace and share them by name,
  if wanted (09 §11 S2)
- [ ] Compact an image with `qemu-img convert`, to give back the space
  of deleted data (09 §11)
- [ ] List and delete the snapshots of an image in its details, beyond
  the one that suspend and resume use (09 §11)
- [ ] Match images by checksum rather than name and size, for Find the
  File and the import (09 §11, 04 §11)
- [ ] Add an image by dropping its file on the library or on a disk
  (09 §11)

## Topology

- [ ] Redesign the icons / use freely available icons
- [ ] Name the plugs on the links, as a virtual machine's network cards
  (06 §9)
- [ ] Connect two bricks by dropping one on the other in the picture,
  as in the Bricks list (06 §9)
- [ ] Move bricks by hand, and keep where they are in the project
  (06 §9)
- [ ] Show a small overview of a big lab in a corner, with where the
  view is (06 §9)
- [ ] Show the events in the picture, next to the bricks they start
  (08 §10)

## Readme

- [ ] Give every button of the Readme tab a tooltip
- [ ] Make the buttons semi-transparent, and opaque under the pointer
- [ ] Round the corners of the buttons
- [ ] Show the pictures of the project's folder in the preview
  (05 §10, M7 B)
- [ ] Render GFM's tables and task lists, if READMEs need them (05 §10)
- [ ] Add buttons for bold, italic and lists to the editor (05 §10)
- [ ] Show the preview in the New Project dialog too, if wanted
  (05 §10)

## Logs window

- [ ] Fold the consecutive chunks of output of a program as one: group
  them, or buffer each process's output by lines (03 §10)
- [ ] Follow the desktop's dark theme, with the palette of the dark
  console mock-up (03 §10)
- [ ] Show a circled "i" for information: Adwaita's symbol is a
  lightbulb (03 §10)
- [ ] Open a single fold with the keyboard (03 §10)
- [ ] Draw the images in the buffer at the screen's scale: they are
  sharp only at scale 1 (03 §10)

## Docs

- [ ] Write CLAUDE.md: the rules for working on this project
  (e.g. no re-exports for names only typing or tests use)
- [ ] Document the project: layout, deployment, running the tests

## Console

- [ ] Answer in JSON for scripts, as `brick list --json` (14 §11)
- [ ] Import and export archives from the console (14 §11)
- [ ] Make new disk images from the console: `image new NAME SIZE`, with
  `qemu-img` (14 §11)
- [ ] Send a line to a brick's control monitor, `brick send vm1 "info
  status"`, and show its answer (14 §11)
- [ ] Show the console in a tab of the main window (14 §11)
- [ ] Run an event's actions one after the other, each waiting for the
  one before (14 §11)
- [ ] Take any unambiguous beginning of a word, as `ip` does:
  `br st sw1` (14 §11)

## Waiting

- [ ] Update the copyright notice

# DONE

- [x] Redesign the console: `noun verb arguments` for the bricks, the
  events, the images, the settings and the projects, with help, Tab
  completion and a history; `--no-gui` and `--run`; events start and stop
  with actions of their own, projects at format 2; the manual page
  `virtualbricks(1)` (cc1b47e…6975fc2), plan in
  `docs/redesign/14 - console-redesign.html`
- [x] Rename a brick or an event in the start and stop actions that name
  it (08 §10); a console command keeps its text
- [x] Say who holds the lock when a start is refused: the processes of
  `/proc/locks` and their users (13 §6)
- [x] Choose how many Virtualbricks run at once, the single-instance
  mode: `--lock system`, the default, `user` with a lock in
  `$XDG_RUNTIME_DIR`, or `none` (02 §14, 10 §13), plan in
  `docs/redesign/13 - single-instance-mode.html`
- [x] Redesign New Brick: a popover of the kinds, a name chosen for each
  new brick, its settings after the click; the window without a title or
  a label is gone (07 §10), plan in
  `docs/redesign/12 - new-brick-redesign.html` (87805d8, 9d35fb0)
- [x] Move the event editor and the image details onto drafts, so that
  `ConfigController` goes (11 §11): every panel is on a draft, and OK
  takes the numbers typed and not yet taken
- [x] Implement workspaces: `virtualbricks --workspace FOLDER` uses the
  projects of another folder for a run, the setting stays, and
  `state.toml` remembers the project open last in each workspace
- [x] Fix the segmentation fault of an action called from the popover
  menu of a brick or an event (and of a disk image, the same row): the
  row destroyed the popover in its "closed", which GTK emits in the middle
  of a click on an item; now it destroys it once idle
- [x] Redesign the configuration panels of the bricks: drafts between
  the panels and the bricks, rows from the schemas, the virtual
  machine's panel on the answers of its QEMU, `widgets.py` gone
  (a8ed7f3…ba4508c), plan in `docs/redesign/11 - panels-redesign.html`
- [x] Choose a machine's icon without an error, show the boot devices in
  words, delete `networkcards.py`: with the new panels
- [x] Move the design documents into docs/redesign, numbered in the order
  of the work, and bring them up to date
- [x] Record what the QEMU and VDE of every supported distribution have:
  virtualbricks/tests/data/programs, asked of the installed programs at
  start (0a51bf8)
- [x] Disk images redesign (eef911c…609fb21), plan in
  docs/redesign/09 - disk-images-redesign.html
- [x] Move the ksm utility functions in a separate module: ksm.py, tee
  through sudo, no sudo as root (a7af104)
- [x] Deprecate `virtualbricks/gui/windows/base.py`: gui/windows is gone,
  gui/dialogs/base.py has one Window class (678ef50, 972cc11)
- [x] Move the bricks and events tabs in a dedicated sub-package
  (3cbac0e)
- [x] Add tooltips to the bricks of the topology (f68ff36)
- [x] Structure the TODO list
- [x] Remove the global settings: a new project reuses the settings
  of the open one
- [x] Remove the sudo configuration from the settings
- [x] Document the protocol to inspect, export and import archives
- [x] Skip the GUI tests when no display is available
- [x] Redesign the buttons as an overlay like in the readme tag
- [x] Add zooming options
- [x] Nicer text (font, size, etc)
- [x] Remove the exports from `virtualbricks/config/__init__.py`
  and check that we can run `python -m virtualbricks.config.archive`
- [x] Redesign the brick tab
- [x] Move the preferences menu entry into files -> settings
- [x] Move all the project menu entries into the project menu
- [x] Move the messages menu entry into files -> logs

# Conventions

- One item per line, starting with a verb; detail indented below it.
- Sections by area, most urgent first.
- Blocked items go under Waiting, saying what they wait for.
- New ideas go under IDEAS, never straight into TODO, including what the
  Later section of a design page keeps for later. The maintainer moves an
  idea into TODO when it is to be done.
- When an item is done, tick it and move it to the top of DONE.
- An item that comes from a design page cites it: (07 §10) is §10 of
  `docs/redesign/07 - bricks-redesign.html`. When it is done, say so in
  that page's "Since then" too.
- Rules go in CLAUDE.md; TODOs about one spot in the code stay in
  code comments.
