# TODO

## Config

- [ ] Implement workspaces: allow projects in directories other than
  `~/.virtualbricks`
- [ ] Move `locations` into `config` (maybe)

## GUI

- [ ] Add build_ui in the tabs classes as well
- [ ] Extract the logic from the windows: windows take state and
  callbacks
- [ ] Move the GTK code outside `gui/` into it:
  `migrate/gui.py`, the GTK parts of `scripts/virtualbricks.py`
- [ ] Open a project by dropping its file on the main window
- [ ] Move startstop_brick method somewhere else, it does not belongs to VBGUI
- [ ] stop passing VBGUI around, use other utilities to set the transient
  window for a dialog
- [ ] Remove the responsibilities from the tabs (on_open, on_save, ...), it
  should be the responsibility of the main window to coordinate all the work
- [ ] Maybe add an attribute to the Tab class to tell if the given tab is the
  currently displayed tab
- [ ] There is a segmentation fault when calling an action from the brick or
  event popover menu

### Read Me tab
- [ ] Not all the buttons have a tooltip
- [ ] Make the buttons semi-transparent and opaque once overed
- [ ] Make the button's corners rounded

### Topology tab
- [ ] Redesign the icons / use freely available icons

### Bricks tab

 -  [ ] def count(bricks) -> str: idoes not requires ngettext. When text is the
    same in the 

## Tests

## Docs

- [ ] Write CLAUDE.md: the rules for working on this project
  (e.g. no re-exports for names only typing or tests use)
- [ ] Document the project: layout, deployment, running the tests

## Waiting

- [ ] Update the copyright notice

## Done

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
- [ ] Make the columns resizable
- [x] Move the preferences menu entry into files -> settings
- [x] Move all the project menu entries into the project menu
- [x] Move the messages menu entry into files -> logs
- [ ] Move the tab files inside virtualbricks/gui/mainwindow/tabs

# Conventions

- One item per line, starting with a verb; detail indented below it.
- Sections by area, most urgent first.
- Blocked items go under Waiting, saying what they wait for.
- When an item is done, tick it and move it to the top of Done.
- Rules go in CLAUDE.md; TODOs about one spot in the code stay in
  code comments.
