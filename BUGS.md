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

## Bricks

- [ ] **A brick that is starting counts as stopped.** `must_stop()`
  (`virtualbricks/bricks/__init__.py`) asks `is_running()`, which is
  `proc is not None`, and a start sets `proc` only once it spawns the
  program: after the bricks it plugs into are up and `prepare()` is done.
  In between, `quit` isn't refused: Virtualbricks says "Bye!", and the
  program is spawned while it shuts down, with nothing to stop it.
  `must_stop()` also guards deleting and renaming a brick and closing the
  project; `Brick.starting()` tells a start under way. Seen on
  3.0.0.dev6, on 19 October 2026, with `--no-gui --workspace FOLDER -l
  FILE` and `brick start sw1`, `brick list`, `brick stop sw1` and `brick
  list` read from a file, before the console ran piped lines one after
  the other: the log had "Bye!", then "Starting: /usr/bin/vde_switch …",
  and no "Process terminated". No `vde_switch` was left after; what ended
  it wasn't looked into, nor what a virtual machine would do.

- [ ] **A Netemu takes a negative delay, bandwidth or buffer size.**
  `delay`, `bandwidth` and `buffer_size`, and their `_right_to_left`, are
  `Int()` with no minimum (`virtualbricks/bricks/netemu.py`). With one,
  an older project that has such a value would be read with a warning and
  the default, so the reading needs a word too. Seen on 3.0.0.dev6, on 19
  October 2026, with `--no-gui`: `brick set ne1 delay=-5 bandwidth=-1
  buffer_size=-100` was taken, `project.toml` kept the three, and `brick
  start ne1` ran `wirefilter` with `-d -5`, which `brick list` summed up
  as `a ↔ b · -5 ms`. What wirefilter does with them wasn't looked into.

## Machines

- [ ] **A plug card added after a socket card moves it.** The cards of a
  machine are kept in two lists, the plug cards first, then the socket
  cards, and numbered by their place: `eth0`, `eth1`… in the console and
  in the summary of the brick (`_card()` in
  `virtualbricks/bricks/brickinfo.py`), and in that order on QEMU's
  command line (`command()` in `virtualbricks/bricks/virtualmachine.py`).
  A draft keeps the same order: `add_card()` there puts a new card after
  the other plugs. So a plug card added after a socket card moves the
  socket card one place on, and its number changes; the order of the
  cards that the guest sees would change too, which is from the code, not
  tried. The name of the socket card, which other bricks plug into,
  stays. Seen on 3.0.0.dev5, on 18 October 2026, in the console: `brick
  card add vm1 socket` answered `vm1 eth0: socket vm1:sock_eth0`, then
  `brick card add vm1 plug vm2:sock_eth0` answered `vm1 eth0: plugged into
  vm2:sock_eth0`, and `brick list` had `eth0 on vm2 · eth1 as a socket`.

## Platforms

- [ ] **Virtualbricks doesn't start on Twisted 22.1.** That is the Twisted
  of Ubuntu 22.04, a supported target. `class
  ControlFactory(protocol.Factory[Any])` in
  `virtualbricks/console/control.py`, there since f117c701, raises
  `TypeError: 'type' object is not subscriptable` when imported: the
  `Factory` of Twisted 22.1 isn't generic yet. `virtualbricks.app` imports
  it, so `--no-gui` and the windows both stop there. Seen on 3.0.0.dev6, on
  19 October 2026, with Python 3.10 and `twisted==22.1.0` in a venv. With
  that base class made subscriptable for the run, the other modules import,
  but for those of the windows and `topology.py`, not tried: the venv has
  no `gi` and no `pygraphviz`.

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
