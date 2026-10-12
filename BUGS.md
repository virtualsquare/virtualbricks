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

- [ ] **An exported archive is readable only by its owner.** The export
  writes the archive to a temporary file made by `tempfile.mkstemp()`,
  which creates it with mode 0600 whatever the umask, and renames it to the
  `.vbp` at the end, so the archive keeps 0600 (`write_archive()` in
  `virtualbricks/config/archive.py`). The import, instead, gives the folder
  it makes the permissions of a normal folder ("mkdtemp made the folder
  private; a project folder isn't", in `move_into_place()` of
  `virtualbricks/config/importing.py`). Seen on 3.0.0.dev3, on 7 October
  2026, writing `virtualbricks-vbp`(5): an export with the umask 022 gave
  `-rw-------` for the archive, also with `compression = "gzip"`, as the
  same file is written either way.
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

## Workspaces

- [ ] **The workspace is read three times at start, and the run may not
  use the folder it locked.** Without `--workspace`, the start reads the
  `workspace` setting from the files three times:
  - for the locks (step 2 of page 27): `take_locks()` in
    `virtualbricks/main.py`, through `startup_workspace()` in
    `virtualbricks/migrate/engine.py`, which reads the settings of 2.1 if
    they are to be converted, else `settings.toml`, with the migration's
    own reader (`_startup_settings()`);
  - for the migration (step 6): `startup_migration()`, the same files
    again;
  - for the run (step 9): `install_workspace()` in
    `virtualbricks/app.py`, `get_setting("workspace")` after
    `load_settings()`.

  Each makes it a folder with `workspace_folder()` in
  `virtualbricks/locations.py`.

  Another Virtualbricks of yours may write `settings.toml` between the
  first reading and the last: one that runs beside it with
  `--lock workspace` writes the whole file at each change of a setting
  and at quit (see "Two Virtualbricks on one computer undo each other's
  settings", under Settings), and its Settings window changes the
  workspace for the next start. The run then works in a folder whose lock
  it doesn't hold, and holds the lock of a folder it doesn't use: another
  Virtualbricks can start in the same workspace, with `--workspace`. The
  gap is short, but the GUI keeps it open as long as its migration window
  is. Page 27 recommends reading it once, at step 2 (O6, open). Seen on
  3.0.0.dev3, on 12 October 2026, reviewing the start-up against page 27:
  in an isolated home, with
  `--lock workspace`, `take_locks()` locked the folder `w1` of the
  setting; the setting was then written as `w2`, and
  `install_workspace()` gave the run `w2`; a `take_locks()` with
  `--workspace w2` after it wasn't refused.
