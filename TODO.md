# TODO

## Config

- [ ] Let the terminal be a command with a place for the console, so that
  any terminal works: `gnome-terminal -- {command}`, `foot {command}`
  (23 §12, S6 C)

## Projects

- [ ] Import an archive dropped on the Projects window (04 §3, §9)
- [ ] Drop the import message window

## Bricks and programs

- [ ] Ask QEMU for other architectures the same way; only
  qemu-system-x86 is recorded (10 §13)
- [ ] Switchwrapper not configured if the path does not exist / switch
  is not started

# IDEAS

## Config

- [ ] Name the holders of the lock in the refusals of the migration
  command and window too, and those of the workspace lock (13 §10, 21 §14)
- [ ] Add a `lock` setting, maybe, so a shared machine doesn't need
  `--lock user` at every start, nor the workspace of the settings
  `--lock workspace` (13 §9 L5, 21 §14)
- [ ] Follow a setting that another Virtualbricks of yours changes, without
  a restart (21 §14)
- [ ] Move `locations` into `config` (maybe)
- [ ] Drop the `log_link_loops` setting, maybe: a loop always stops a
  start (10 §13, 23 §12)
- [ ] Show what KSM saves in its row of the Settings window: the pages
  shared, from `/sys/kernel/mm/ksm/pages_sharing` (23 §12)
- [ ] Change the settings of a project that isn't open, from the Projects
  window (23 §12)

## Projects

- [ ] Switch to another workspace from the GUI, and list the workspaces
  used, which `state.toml` already has; the switch takes the lock of the
  new workspace and releases the old one's (21 §14)
- [ ] Open several projects at once (04 §11: D6 rules it out for now)
- [ ] Make new projects from templates (04 §11)
- [ ] Open a project by dropping its file on the main window
- [ ] Switch projects from a popover on the main window's title, once
  the main window has a header bar (04 §3, direction B)
- [ ] Let the Projects window get narrower once a project with a README
  is selected: asked for 600 pixels, it stays at 911 (on develop too)

## GUI code

- [ ] Add build_ui in the tabs classes as well
- [ ] Move the GTK code outside `gui/` into it:
  `migrate/gui.py`, the GTK parts of `cli.py`
- [ ] Stop passing MainWindow around: set the transient window of a
  dialog another way
- [ ] Take the work of the tabs (on_open, on_save, ...) to the main
  window, which coordinates it
- [ ] Add an attribute to the Tab class that says whether it is the tab
  shown (maybe)
- [ ] Move the tab files inside `virtualbricks/gui/mainwindow/tabs`

## Bricks and programs

- [ ] Give the router settings and a panel: it has neither (07 §10,
  10 §13, 11 §11, 12 §9)
- [ ] Decide how an icon is chosen for any brick or event, and where it
  shows (10 §13, 11 §11)
- [ ] Select several bricks to start, stop or delete them at once
  (07 §10, 24 §10): the Delete dialog would say what goes with all of
  them
- [ ] Let the console's `brick delete` send a machine's private copies to
  the trash too, as the Delete dialog does; a Virtualbricks started with
  `--no-gui` has no trash, so there they would be deleted for good
  (24 §10)
- [ ] Undo a delete, as GNOME's applications do, if the engine can one
  day put a brick or an event back, with its links, the actions and
  settings that named it, and a machine's private copies (24 §5, D1 B)
- [ ] Disconnect a brick from its menu: today only its panel does it
  (07 §10)
- [ ] Say Paused in the row of a brick that Pause stopped, until
  Continue: today the row says Running, and only `/proc` knows; for a
  machine, maybe QEMU's own `stop` and `cont`, whose monitor answers while
  it is paused, and says so
- [ ] Offer New Brick in the Topology tab too: on its empty page and in
  its More menu (12 §9)
- [ ] Make a brick already plugged into a switch, from the switch's
  menu: a tap, a machine or a wire (12 §9)
- [ ] Set a tap's address after its process starts, through sudo:
  `address_mode`, `ip_address`, `netmask` and `gateway`; today nothing
  does (10 §13, 11 §11)
- [ ] Declare which settings a running brick takes without a restart,
  in place of the `cbset_<name>` methods (10 §13, 11 §11)
  - the switch's ports, hub mode and FSTP, all of Netemu, a machine's
    USB devices
  - short of that, name them for what they are: `on_<name>_changed`, or
    the like; `draft.py` looks them up by name too
- [ ] Keep notes of your own on a brick: a key, shown in its panel and
  above its table (10 §13, 11 §11)
- [ ] Check every value in `brick.update_config()` before assigning any,
  for the console too (11 §11)
- [ ] Change one setting of a brick without a mapping of one:
  `brick.update_config({setting: value})` in the brick menu and in New
  Event
- [ ] Offer HDA sound: a controller and its codec together, which no
  single entry of the sound cards can start (11 §11)
- [ ] Show the command line of a machine as it would start, in the
  Advanced section of its panel (11 §11)
- [ ] Add a Programs window: each program found, its version, what it
  lacks and the packages to install (10 §13, 12 §9)
  - the tooltip of a missing program in New Brick could open it
- [ ] Support Wirefilter along Netemu

## Events

- [ ] Repeat an event every so many seconds (08 §10)
- [ ] Run the actions in order, each after the previous one: today they
  all start together (08 §10)
- [ ] Show the output of a shell command in the Logs window (08 §10)
- [ ] Add an action that changes a brick's settings, as the console's
  `brick set sw1 ports=16` (08 §10, E5)

## Disk images

- [ ] Make renaming a virtual machine safe for its private disks: it can
  overwrite a disk that is in the way, or leave the disks half renamed
  - since 2928039 `VirtualMachine.set_name()`, which every rename goes
    through, calls `_rename_private_disks()` in
    `bricks/virtualmachine.py`: it moves `<old>_<dev>.cow` and its
    backups (`.cow.bak-…`) to `<new>_<dev>.cow` with `os.rename()`,
    one file after the other, and nothing is checked first
  - a file in the way is replaced without a word, and what was in it is
    lost. No machine owns such a file, but it can be there: the disk of a
    machine that was deleted, or one that the rename bug fixed in 2928039
    left behind. Before it, the GUI and the console renamed `a` to `b`
    without moving `a_hda.cow`, and `b` started a new, empty
    `b_hda.cow`; renaming `b` back to `a` now moves the empty disk over
    the one that holds the machine's data
  - if a move fails halfway (permissions, a read-only folder), the disks
    moved so far have the new name and the rest the old one. The machine
    keeps its old name, because `set_name()` raises before it sets it, so
    it no longer finds the disks already moved and starts new ones
  - what could be done: check every target before moving anything, and
    refuse the rename naming the file in the way (the rename dialog and
    `brick rename` show the error); if a move fails, move back the files
    already moved
  - since 32a9ef3 the Delete dialog sends a machine's private copies to
    the trash (24 D4), so fewer of them are left in the way; the console's
    `brick delete` still leaves them, and the Rename dialog shows a
    refusal of the folder in red (08e07e5)

- [ ] Show the images of all projects: each file once, the projects and
  disks that use it, and the files of shared_images no project uses, as the
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
- [ ] Render GFM's tables and task lists, if READMEs need them (05 §10)
- [ ] Add buttons for bold, italic and lists to the editor (05 §10)
- [ ] Show the preview in the New Project dialog too, if wanted
  (05 §10)

## Logs window

- [ ] Fold the consecutive chunks of output of a program as one: the
  output is buffered by lines now, but the lines of each read are still
  a message of their own (03 §10)
- [ ] Show the colours of the ANSI sequences of a program's output:
  `terminal.Lines` drops them (03 Since then)
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

- [ ] Answer in JSON for scripts, as `brick list --json` (14 §11); the
  control socket's protocol carries them as they are (15 §11), and AMP as
  `AmpList` boxes (16 §10)
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
- [ ] More keys of readline: Alt+. for the last argument of the command
  before, as a brick's name, and Ctrl+_ to undo an edit
- [ ] Attach an interactive console to the Virtualbricks that runs,
  `virtualbricks --attach`, with the editing, history and completion of
  its terminal; the completion needs a request of its own, or the copy of
  the remote windows (15 §11, 19 §13)
- [ ] Answer `--command` in the language of its own terminal, not in
  that of the Virtualbricks that runs (15 §11)
- [ ] Follow what changes through the JSON control socket, `watch`, for
  a status bar or a script (15 §11, 19 §13); over AMP, `Follow` does it
- [ ] Open the sockets of a setting, for a Virtualbricks started from the
  desktop's menu, which has no options (16 §10)
- [ ] The workspace in the greeting of the control sockets and in the
  answer of `status` (21 §14)
- [ ] A command that lists the Virtualbricks of yours that run, with their
  workspaces and sockets (21 §14)
- [ ] Answers as data for the typed AMP commands: new optional keys of
  their answers, which keep protocol 2, first for `BrickList`, `BrickShow`
  and `Status` (20 §10 T3 B)
- [ ] A client of the typed AMP commands in Python without Twisted, on
  `console/ampbox.py`, for scripts (20 §11)
- [ ] Carry the answers longer than 64 KiB over AMP, spread over several
  keys, if one is ever needed (16 §9 M5 B)
- [ ] Read the token and the client certificates again without a
  restart, to let a client go at once (17 §12)
- [ ] Tokens that allow less: `status` and `brick list` only, or no shell
  actions from another machine, or remote windows that only look; today a
  connection can do all that the console does (17 §12, 19 §13)
- [ ] Make the certificate of Virtualbricks, and a client's, from
  Virtualbricks, and show its fingerprint to check on the client, as ssh
  does on the first connection (17 §12)
- [ ] Name the process that holds a port, as the locks name theirs
  (17 §12)
- [ ] Slow down an address that sends wrong proofs of the token (17 §12)
- [ ] Listen on the other types of Twisted's endpoints, as `systemd` for a
  socket that systemd opens (17 §12)
- [ ] Run the tests of the AMP socket on Twisted 22.1 too: they patch
  `amp._log`, which 22.1 doesn't have (17)

## Remote windows

- [ ] A Connect… item in the File menu, with the lab machines used before,
  kept in `state.toml`, and back to this machine without a restart
  (19 §13)
- [ ] Several lab machines at once, a window each (19 §13)
- [ ] Send files to the lab machine, as images, ISO files and kernels, and
  browse its files (19 §13)
- [ ] Import and export archives over the connection (19 §13)
- [ ] The long work on images over a connection, as jobs: the copy of Add
  Image, Save as a New Image and Merge; `JobProgress` and `JobDone` as
  pushes, `JobCancel` (19 §13, R13 A)
- [ ] Open the display of a machine there: a VNC viewer here, through the
  connection, with the VNC of QEMU on the loopback of the lab machine
  (19 §13)
- [ ] The data of `ProjectNames` and `ProjectSummary` as optional keys of
  `ProjectList` and `ProjectShow`, once answers are data (19 §13)
- [ ] Windows and a lab machine of different versions (19 §13)
- [ ] The messages of the lab machine in the language of the desktop
  (19 §13)
- [ ] Show who else is connected to the lab machine (19 §13)
- [ ] Terminate over a connection, with a command of the console that
  stops a machine with `SIGTERM` (19 §13)
- [ ] Show the version of the lab machine in About (19 §13)
- [ ] Read the icon of a machine, and the description beside an image
  file, from the lab machine (19 §13)

## End-to-end tests

- [ ] Type text in the windows, as names and paths: the browser of
  `e2e/broadway.py` sends keys as `broadway.js` does, `k` and `K` with a
  keysym
- [ ] Write the scenarios of the main use cases: projects, events, disk
  images, virtual machines, the topology; they are listed in
  `e2e/TODO.md`
- [ ] Stop `dbus-daemon` and `broadwayd` of the tests when `pytest` is
  killed, with the parent-death signal
- [ ] Run the end-to-end scenarios on X11 too, on Xvfb, beside Broadway:
  real keys, and drag and drop; `e2e/TODO.md` compares the two

# DONE

- [x] Update the copyright notice to 2026: the headers, COPYING, the
  About dialog and the `--help` text; in the About dialog VDE is
  2003-2025 (vdeplug4) and QEMU 2003-2026, as `qemu -version` says
- [x] Hashes in contents.toml, thought over and discarded: the benefit is
  small for its cost; revisit if there is new interest (26 rev 2). Only a
  fingerprint of the disk's contents, recorded when a private disk is
  made, would confirm its image reliably at import
  - found meanwhile: a damaged gzipped archive imports without an error
    when bsdtar or tarfile reads it: only GNU tar checks the CRC (26 §3)

- [x] Run mypy at each commit: a local hook, with the mypy of `.venv`,
  which has the stubs of GTK 3

- [x] Type every module in full: `app.py`, `errors.py`, `gui/gui.py` and
  `scripts/` too. mypy checks them all strictly, the bodies of the
  functions too (`check_untyped_defs`), with no list of modules to keep:
  it finds no error. A Failure's exception and its type may be None for
  mypy, so they are asserted where they are read

- [x] Type `brickfactory.py` in full, checked strictly: the bricks, the
  events and the images of the factory have their types, and what reads
  them asks a brick whether it is a machine or a Netemu by its class; over
  a connection, a brick, an event or an image made that the copy hasn't
  fails, instead of giving None

- [x] Type `gui/mainwindow/` in full, checked strictly: the rows, the lists
  and the tabs of rows are generic over their objects; the methods named as
  a GTK one, with another signature, are renamed (`new_item()`,
  `show_state()`, `lay_out()`, `remove_disk()`, `remove_card()`,
  `remove_image()`, `disks_changed()`, `action_rows()`); the right click
  on the status icon opens its menu again, a TypeError before

- [x] Type `gui/dialogs/` in full, checked strictly: the `local` of an
  engine is `Literal[True]` or `Literal[False]`, so `if engine.local:`
  narrows `Engine`; an `Owner` writes changes of any type, as a setting's
  kind says; GTK's maybe-`None` that can't be are asserted with why

- [x] Type the modules of `gui/` but `gui.py`: `form.py`, `graphics.py`,
  `imageinfo.py`, `markdownview.py`, `messages.py` and `pathentry.py`,
  checked strictly; `engine.Engine` is the engine the windows take, local or
  over a connection, and `Draft.get()` gives an `Any`, as a setting's kind
  says

- [x] No mypy error in `qemu/`, `vde.py` and `programs.py`: the cache of
  the answers of the programs keeps the type of each; `qemu/` is checked
  strictly

- [x] Type `virtualbricks/remote/` in full, checked strictly: the mixins of
  the AMP connection see what it gives them through `follower.Connection`,
  for mypy only; the guards `is_virtualmachine()`, `is_event()` and
  `is_disk_image()` are `TypeIs`, which narrows the other branch too

- [x] Type `engine.py`, `i18n.py`, `ksm.py`, `locations.py`,
  `observable.py`, `settingsdraft.py`, `terminal.py` and `topology.py` in
  full, checked strictly; the topology leaves out the cards in the
  host-only network, which made it fail

- [x] Type `virtualbricks/bricks/` in full, checked strictly: `is_event()`
  and `is_disk_image()` are type guards, as `is_virtualmachine()`, and
  replace the casts after them; the fields of the brick configurations are
  annotated; `Tunnel` is what both ends of a tunnel share

- [x] Type `virtualbricks/console/` in full, checked strictly; ampgen
  writes `LINES` and `PAIR` typed

- [x] Type `virtualbricks/config/` in full, checked strictly: mypy knows
  the schemas as attrs classes (`define` imported, not assigned)

- [x] Check the types: mypy and mypy-zope in the dev group, its
  configuration in `pyproject.toml` with the modules typed in full checked
  strictly, the stubs of GTK 3 (`PYGOBJECT_STUB_CONFIG`), and
  `tools/typecoverage.py`, the annotations of each module

- [x] Redesign Rename and Delete: Rename asks the name as Rename Project
  does, selected, with why a name can't be used under it; one Delete
  dialog for a brick and an event says what goes with it; a delete clears
  the actions and the When It Starts or Stops that name the item; a
  running brick has Delete greyed; a machine's private copies go to the
  trash with it (24)

- [x] Redesign the Settings window: a page for each owner of settings, the
  rows of the schema, Cancel and OK on drafts, folders that say what they
  hold, menus for the terminal and the audio driver; private copies always
  qcow2, and the warning of KSM only when the settings ask for it (23)

- [x] Show the pictures of the project's folder in the preview of the
  Readme tab, over a connection too (`ReadmePicture`); any other picture
  stays its text, and so do those of the Projects window (05 §10, M7 B)

- [x] The report of Allure of the end-to-end tests, with the screenshot
  and the video of a scenario that fails; the results and the history in
  git, to publish it

- [x] Duplicate names a copy after its brick or event, with the number at
  the end increased to the first free one: `sw2` for `sw1`, `node2` for
  `node`; not `copy_of_sw1` (12 §9)

- [x] `virtualbricks --connect` alone opens the windows of a Virtualbricks
  of yours on this machine, the one that listens on the socket of
  `--listen` alone of its workspace: that of `--workspace`, or the only
  one that listens; the windows call it "this computer" (19 §13)

- [x] Screenshots and videos of the end-to-end scenarios that fail, drawn
  from what `broadwayd` sends to the browser of the tests, with the pointer
  and the step; `pytest --record-all` records every scenario

- [x] End-to-end tests: scenarios in words in `e2e/features/`, which
  `pytest` runs with pytest-bdd; Virtualbricks on `broadwayd` with a
  session bus of its own, the widgets found through AT-SPI and clicked by
  a browser of `broadwayd`; `/e2e`, a skill of Claude Code, writes a
  scenario from a use case in words; guide in `e2e/README.md`

- [x] Document the protocols of the control sockets, the JSON one and
  protocols 1 and 2 of AMP, with the proof of the token:
  `virtualbricks-control(7)` and `docs/control-protocols.html`
- [x] Open the windows of another Virtualbricks: `virtualbricks --connect
  DESCRIPTION`, over AMP (19): the copy of the project there, kept up to
  date by `Follow`; what the windows do goes through an engine,
  `LocalEngine` here and `RemoteEngine` over the connection, by the typed
  commands of protocol 2 and the commands of the windows (20 §11); the
  facts, files, projects and settings of the lab machine; paths typed with
  the completion of its folders; its consoles in a terminal here;
  `startstop_brick` out of VBGUI on the way; plan in
  `docs/redesign/19 - remote-gui.html`
- [x] Run two Virtualbricks at once in different workspaces (13 §10, 15
  §11): `--lock workspace`, which `--workspace` implies, one for each
  workspace; `.virtualbricks.lock` in the workspace, held in every mode
  but `none`; a runtime folder for each workspace, named by a key of its
  path, with its `.control`, so `--command` reaches either, by
  `--workspace` or as the only one that listens; plan in
  `docs/redesign/21 - workspaces-side-by-side.html`
- [x] A typed AMP command for each command of the console, made from its
  table (16 §9 M2 B): protocol 2, beside protocol 1 on the same socket;
  `Hello` takes the protocols of the program and agrees on one for the
  connection; `console/ampgen.py` writes `console/ampcommands.py`, and
  `tests/data/amp-protocol-2.txt` keeps the protocol; plan in
  `docs/redesign/20 - typed-amp-commands.html`
- [x] Teach `--command` AMP too: with `protocol=amp` it talks to an AMP
  socket, on unix, tcp or ssl, through `console/ampbox.py`, which reads
  and writes the boxes of AMP without Twisted
- [x] Listen on `tcp` and `ssl` sockets too, on this machine and across
  the network, with a way to know who connects (16 §9 M6, §10):
  `--socket tcp:PORT` on this machine, `ssl:PORT:privateKey=FILE` on any
  address; each client proves the token of `~/.config/virtualbricks/token`
  with an HMAC, neither end sending it, or shows a certificate of
  `caCertsDir=`; `--command` talks to `tcp:HOST:PORT`; plan in
  `docs/redesign/17 - network-sockets.html`
- [x] Open a second control socket that speaks Twisted's AMP, for
  programs written with Twisted; both sockets open at the same time
  (15 §10 Q3, §11): `--socket [DESCRIPTION]`, in the syntax of Twisted's
  endpoints, `unix:PATH:protocol=amp`, once for each socket; plan in
  `docs/redesign/16 - amp-socket.html`
- [x] Turn the control socket off, with `--no-control` or a setting, if
  anyone wants a Virtualbricks that can't be reached (15 §11): without
  `--socket`, a Virtualbricks listens nowhere (16)
- [x] Add a control socket in the runtime folder, so that
  `virtualbricks --command ...` talks to a Virtualbricks that runs
  (14 §11, K6 C): every Virtualbricks listens on `.control`, or on the
  path of `--socket`; JSON lines, a lock of its own; plan in
  `docs/redesign/15 - control-socket.html`
- [x] Give the console line the keys of readline, in the Python shell
  too: Ctrl+R and Ctrl+S search the history; Ctrl+B, Ctrl+F, Alt+B, Alt+F,
  Ctrl+Left and Ctrl+Right move; Ctrl+D, Ctrl+W, Alt+Backspace, Alt+D,
  Ctrl+U and Ctrl+K delete, Ctrl+Y puts back; Ctrl+T and Alt+T swap
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

- Sections by area, most urgent first.
- Blocked items go under Waiting, saying what they wait for.
- New ideas go under IDEAS, never straight into TODO, including what the
  Later section of a design page keeps for later. The maintainer moves an
  idea into TODO when it is to be done.
- An item that comes from a design page cites it: (07 §10) is §10 of
  `docs/redesign/07 - bricks-redesign.html`. When it is done, say so in
  that page's "Since then" too.
- Rules go in CLAUDE.md; TODOs about one spot in the code stay in
  code comments.
