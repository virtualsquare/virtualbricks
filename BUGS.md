# Bugs

Bugs found and not fixed yet, by area, each with how it was seen. A fixed
one leaves the list.

## Control socket

- [ ] **`Changed` comes after the answer of `BrickStop`.** Over AMP 2, with
  `Follow`, the `Changed` push of a brick that stops (`pid` None) comes
  after the answer of `BrickStop`, every time. `virtualbricks-control`(7)
  promises that "once a command is answered, the program has what it
  changed", and `BrickStart` keeps the promise. Seen on 3.0.0.dev3, on 6
  October 2026, with a switch:

  ```
  ask BrickStart
  Changed brick sw2 {'pid': 430716}
  answer {'lines': ['sw2 runs, process 430716']}
  ask BrickStop
  answer {'lines': ['sw2 stopped']}
  Changed brick sw2 {'pid': None}
  ```

  In one run, two `Changed brick sw2 {'pid': None}` came after the answer.
  The answer of a typed command waits for `pushes_first()`
  (`virtualbricks/remote/follower.py`), from `_responder()` in
  `virtualbricks/console/control.py`.

## Signals

- [ ] **Two SIGTERMs in a row hang `--no-gui -l FILE`.** The second SIGTERM
  arrived while the handler of the first was writing "Received SIGTERM,
  shutting down." to the log file: the process stays, ignores further
  SIGTERMs, and its socket doesn't answer. Seen on 6 October 2026 with
  `pkill` matching both `timeout` and the `python` it ran, so each sent one;
  Python 3.10, Twisted 26.4.0. The Python stack, from `py-bt` in gdb, has
  Twisted's `sigTerm()` in `sigTerm()`, both at the `self._block.acquire()`
  of `threading._RLock`, through `LogFile.write()`, which
  `twisted.python.threadable` synchronizes. That lock is the pure Python
  `RLock`: the signal came after the first `_block.acquire()` returned and
  before `_owner` was set, so the second handler waits for a lock that its
  own thread holds. The log file of `-l` is a `LogFile` (`_log_file` in
  `virtualbricks/cli.py`); the standard output takes no such lock.
  `sigInt()` logs the same way, so two Ctrl+C might hang it too (not
  tried).

## Archives

- [ ] **A gzip archive names the temporary file in its header.** Without
  `qemu-img`, the export compresses the archive with
  `gzip.GzipFile(fileobj=..., mtime=0)` (`_Output` in
  `virtualbricks/config/archive.py`), which takes the name of the file
  from `fileobj.name`: the header of the archive holds the name of the
  unfinished archive, `.lab.vbp.XXXXXXXX.part`, with the flag FNAME.
  `gunzip -N` restores the tar under that hidden name, and `gzip -lN`
  lists it. Seen on 3.0.0.dev3, on 7 October 2026, writing
  `virtualbricks-vbp`(5):

  ```
  $ gzip -lN < lab.vbp
           compressed        uncompressed  ratio uncompressed_name
                  617               10240  94.4% .gz.vbp.2or1v0ic.part
  ```
- [ ] **An image left unset at the import is dropped, and the private
  copies can't follow it.** With Leave unset, the import writes the image
  without a path (`place_images()` in `virtualbricks/config/importing.py`),
  and the project drops it when it opens: the Images tab is empty, and the
  disks have no image. Find the File…, which points the private copies at
  the file found with `qemu-img rebase -u` (`relink()` in
  `virtualbricks/config/images.py`), can't be used. The private copies of
  the archive keep the image of the other computer as backing file; once
  the disks get an image in their settings, the first start of each
  machine moves its copy aside as `.bak-` and the date, and makes a new one
  (`_ensure_private_image_cow()` in
  `virtualbricks/bricks/virtualmachine.py`): what was done in the machines
  is set aside. Keeping the image, with its path of the other computer,
  would let Find the File… rebase them. Seen on 3.0.0.dev3, on 13 October
  2026, writing the tutorial `tutorial-import` of the guide, with the
  archive of 2.1 `DTN2hops_26_Feb_2026.vbp` (four private disks, not their
  image), imported with Leave unset. The Logs window had:

  ```
  Import   .project:1: [Image:debian13] /home/carlo/VB_images/
           debian13.qcow2 not found, kept in the library
  Import   images.debian13: left unset: give its disks an image in
           their settings
  Import   bricks.node1.disks.hda: its image is unset, the private disk
           is left as it is
  Project  images.debian13: has no path, image dropped
  Project  bricks.node1.disks.hda.image: no image named "debian13"
  ```

  and the same two lines of `node1` for `node2` to `node4`. The first line,
  of the conversion of 2.1, says the image is kept; the fifth, that it's
  dropped.

## Remote windows

- [ ] **The windows of `--connect` turn KSM on in this computer.** At
  their start, `RemoteApplication.install_settings()`
  (`virtualbricks/gui/app.py`) calls `load_settings()`
  (`virtualbricks/config/settings.py`), which ends with
  `set_ksm(enable=True)` when the `settings.toml` of this computer has
  `kernel_samepage_merging = true`. With KSM off, that runs
  `sudo tee /sys/kernel/mm/ksm/run`: with an askpass helper, a window
  asks for the password of root; without one, `sudo -n` turns KSM on
  where no password is asked, and fails at once elsewhere. Nothing of the
  windows needs it. The bricks run on the computer of `--connect`, and
  KSM is a setting of that computer: the Settings window shows it on the
  page of that computer (`BRICKS` in
  `virtualbricks/gui/dialogs/settings.py`). Of the settings of this
  computer, the windows read only `terminal`, `tray_icon` and
  `warn_missing_programs` (`WINDOWS` there). Nor does anything wait for
  it: the warning at start of the windows reads the KSM of the computer
  there (`warn()` in `virtualbricks/gui/app.py`), not
  `ksm_started()`. Page 27 has the remote windows load "those of this
  computer, without KSM" (§3, step 8). Seen on 3.0.0.dev3, on 9 October
  2026, reading the start-up code for page 27, then in the old
  `virtualbricks/gui/app.py`; checked again on 12 October 2026 with the
  new start-up: `install_settings()`, with that setting in an isolated
  home and `set_ksm` replaced, called it with `True`.
- [ ] **The windows of `--connect` write all the settings of this
  computer at quit.** `run()` (`virtualbricks/main.py`) registers
  `store_settings` before the shutdown in every mode, and
  `RemoteApplication` keeps the one of `app.Application`, which
  writes the whole `settings.toml` from the copy it read at the start.
  The windows have nothing left to write by then: the three settings of
  this computer that they change, on the page This computer of the
  Settings window, are written as they change (`_write_here()` in
  `virtualbricks/gui/dialogs/settings.py`, which writes the whole file
  too). So the write at quit can only undo what another Virtualbricks of
  this computer changed while the windows were open: the one whose
  windows they are, when `--connect` names a socket of this computer, or
  any other of yours. It is the case of the windows in "Two Virtualbricks
  on one computer undo each other's settings", under Settings. Seen on
  3.0.0.dev3, on 12 October 2026, reviewing the start-up against page
  27: in an isolated home, the windows read a `settings.toml` with
  `terminal = "xterm"`, another process wrote `"kitty"`, and the
  `store_settings()` of the quit wrote `"xterm"` back.

## Settings

- [ ] **Two Virtualbricks on one computer undo each other's settings.**
  Each process reads all of `settings.toml` at its start and writes all
  of its own copy back: at each change, from the Settings window or the
  console, and at quit (`store_settings` before shutdown, registered by
  `run()` in `virtualbricks/main.py`). A change made in
  one is lost when the other writes next. Two processes share the file
  when the windows of `--connect` show a Virtualbricks of the same
  computer, which take no lock, and when two run side by side with
  `--lock workspace`. Seen on 3.0.0.dev3, on 9 October 2026, reading the
  start-up code for page 27; checked with two Python processes on one
  `settings.toml`: the first loaded it, the second set `terminal` and
  wrote it, the first wrote its copy as at quit, and `terminal` had its
  old value again.

## Virtual machines

- [ ] **The settings of a new machine can fail to ask QEMU what it has.**
  Once, New Brick, then Virtual machine, showed the alert `Cannot ask
  /usr/bin/qemu-system-i386 what it has` (`qemu_error`, logged by
  `not_answered()` or `answered()` of
  `virtualbricks/gui/mainwindow/bricks/config/vm/panel.py`) and stopped
  the scenario. The reason isn't known: with `--no-term` the failure goes
  only to the Logs window, and the alert says no more. The questions of
  `programs.run()` have no timeout, so QEMU itself failed or exited
  badly, or its answer didn't parse. Seen on 3.0.0.dev3, on 13 October
  2026, in the scenario "The settings of a virtual machine, on its page
  Machine" of `e2e/features/pictures.feature`, eight scenarios at a time,
  one of them running a machine; not again in 60 more runs, the scenario
  16 times at once and the feature 4 times, with a `sitecustomize.py` in
  `E2E_PYTHONPATH` that printed every failure logged.

## Main window

- [ ] **The tray icon prints a GTK critical on Broadway.** Each start of
  the windows on GTK's Broadway backend prints
  `Gtk-CRITICAL **: gtk_widget_get_scale_factor: assertion
  'GTK_IS_WIDGET (widget)' failed`, so the output of every e2e scenario
  has it, whatever the scenario does. It comes from the `Gtk.StatusIcon`
  that `MainWindow.build_ui()` (`virtualbricks/gui/mainwindow/window.py`)
  makes with the picture `virtualbricks.png`, hidden until its setting
  says otherwise. On X11 the same `Gtk.StatusIcon(visible=False,
  pixbuf=...)` prints nothing; on Wayland it wasn't tried. Probably GTK
  gives a status icon its widgets only on X11, and setting the picture
  elsewhere asks the scale factor of a widget that isn't there. Nothing
  else was seen wrong: Broadway has no tray anyway (`e2e/TODO.md`). Seen
  on 3.0.0.dev3, on 13 October 2026, in the output of the e2e scenarios;
  `G_DEBUG=fatal-criticals`, with Python's `faulthandler` registered for
  SIGTRAP, put it at the `Gtk.StatusIcon(...)` of `build_ui()`.

## User guide

- [ ] **The pictures of the guide don't shrink to the window: the page
  scrolls sideways.** In a browser window narrower than a page and its
  widest picture, the HTML of the guide (`help/html/C/`, and its copy on
  the website) keeps the pictures at their size and scrolls sideways:
  below about 980 px for the pages with a picture of the main window, 902
  px wide (`first-lab`, `bricks`, `images`, …), below about 1070 px for
  `tutorial-import`, whose pictures are in numbered steps, indented more,
  and at any phone width. `yelp.js` scales a figure down to its column
  (`yelp_figure_init()`), but the column grows to the picture: in the CSS
  of yelp-xsl 42.1, `main` is a row flexbox, and `main > div.page` keeps
  `min-width: auto`, so it isn't narrower than its widest picture. With
  `main > div.page { min-width: 0; }` added, the pictures scale down and
  nothing scrolls, at 700 px and at 1000 px. Yelp wasn't tried. Seen on
  3.0.0.dev3, on 15 October 2026, in headless Chromium, with the
  `scrollWidth` of each page with pictures at 700, 900, 1000, 1050, 1100
  and 1280 px; first noticed on 14 October, in `tutorial-import`.
