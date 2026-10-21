# Bugs

Bugs found and not fixed yet, by area, each with how it was seen. A fixed
one leaves the list. Those marked *Later* belong to the remote control,
the control socket and the windows of `--connect`, which is experimental
in 3.0: they wait until after it.

## Control socket

- [ ] *Later.* **`Changed` comes after the answer of `BrickStop`.** Over
  AMP 2, with `Follow`, the `Changed` push of a brick that stops (`pid`
  None) comes after the answer of `BrickStop`, every time.
  `virtualbricks-control`(7) promises that "once a command is answered,
  the program has what it changed", and `BrickStart` keeps the promise.
  Seen on 3.0.0.dev3, on 6 October 2026, with a switch:

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
  `virtualbricks/console/control.py`. Probably the Deferred of the stop
  fires before the end of the process, which makes the `Changed`. The
  windows of `--connect` can show a stopped brick as running for a
  moment.

## Bricks

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

- [ ] **A README picture with too many pixels is read on Ubuntu 26.04 and
  Debian testing.** `read_picture()` (`virtualbricks/gui/markdownview.py`)
  turns down a picture of more than `PICTURE_PIXELS` with
  `loader.set_size(0, 0)` on `size-prepared`, so that the loader gives up
  before it takes the memory. With gdk-pixbuf 2.44, installed with
  `glycin-loaders`, the loader goes on, and the whole picture comes back:
  2.44.5 and glycin-loaders 2.1.5 on Ubuntu 26.04, 2.44.8 and 2.2.2 on
  Debian testing. With the 2.42.10 of Ubuntu 24.04 and the 2.42.12 of
  Debian 13 it gives up. Seen on 3.0.0.dev6, on 20 October 2026:
  `TestReadPicture.test_too_many_pixels` in
  `virtualbricks/tests/gui/test_markdownview.py` failed in containers of
  Ubuntu 26.04 and Debian testing with their packages
  (`tools/targetsuite.py`), and passed in those of Ubuntu 24.04 and Debian
  13. A large picture in the Readme tab wasn't tried.

## Remote windows

- [ ] *Later.* **The windows of `--connect` turn KSM on in this
  computer.** At their start, `RemoteApplication.install_settings()`
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
  home and `set_ksm` replaced, called it with `True`. Likely fix, a small
  one: a way to load the settings without starting KSM, a parameter or a
  split of `load_settings()`, for `RemoteApplication`.
- [ ] *Later.* **The windows of `--connect` write all the settings of
  this computer at quit.** `run()` (`virtualbricks/main.py`) registers
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
  `store_settings()` of the quit wrote `"xterm"` back. Likely fix, a small
  one: no `store_settings` at quit for the windows, which write their
  settings as they change; best fixed with the one under Settings.
- [ ] *Later.* **The windows of `--connect` show a brick that is starting
  as stopped.** Here a starting brick reads Starting, with Rename… and
  Delete… disabled and a Stop that calls its start off. The facts that
  the follower pushes of a brick are `running` and `pid` alone
  (`virtualbricks/remote/follower.py`), and a brick of the copy has no
  start of its own (`virtualbricks/remote/mirror.py`), so `starting()`
  is false there: the row says Stopped, its button Start, and Rename…
  and Delete… are enabled. The Virtualbricks that runs the bricks
  refuses a delete or a rename all the same, and its stop calls the
  start off. Seen on 3.0.0.dev6, on 20 October 2026, reading the code
  while fixing "A brick that is starting counts as stopped"; not run.
  Likely fix: a `starting` fact, pushed when a start begins and ends, and
  the copy's `starting()` reading it.

## Settings

- [ ] *Later.* **Two Virtualbricks on one computer undo each other's
  settings.**
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
  old value again. Likely fix: each write reads the file again and
  writes only the keys that changed, which may need a design page; with
  it, the write at quit of the windows of `--connect`, under Remote
  windows.

## Tests

- [ ] **Some unit tests need the programs of the bricks installed.**
  `README.md` says that the tests need neither QEMU nor VDE, but these
  fail without them:
  - 26 tests that check the answer of `brick new switch` or `brick new
    tap`, to which the console adds "vde_switch isn't installed" or
    "vde_plug2tap isn't installed": in `test_control.py`,
    `test_general.py` and `test_terminal.py` of
    `virtualbricks/tests/console/`, `test_eventaction.py` of
    `virtualbricks/tests/bricks/`, and `virtualbricks/tests/test_app.py`;
  - `TestNew.test_a_name` and `test_named_after_the_kind` in
    `virtualbricks/tests/console/test_bricks.py`, where `brick new qemu`
    adds "qemu-system-i386 isn't installed";
  - `TestAudioDriver.test_not_listed` and `test_unknown_yet` and
    `TestDraft.test_failed` in `virtualbricks/tests/test_settingsdraft.py`,
    whose problems have one more, "No program x-terminal-emulator on this
    computer";
  - `TestStart.test_environment` in
    `virtualbricks/tests/bricks/test_command.py`, without `vde_cryptcab`,
    and at times `test_resume` or `test_warnings` of the same class with
    it.

  Seen on 3.0.0.dev6, on 20 October 2026, in containers of Ubuntu 24.04
  and 26.04 with their packages, without these programs; once vde2 was
  installed, the first group passed. As root there, five more failed,
  which expect a permission error: two in
  `virtualbricks/tests/config/test_workspace.py`, two in
  `virtualbricks/tests/test_locks.py`, and one in
  `virtualbricks/tests/gui/dialogs/test_projectname.py`.

- [ ] **"The file chooser of the image of DTN2hops, on its file" fails
  under load.** The scenario of `e2e/features/pictures.feature` fails at
  `And in the file chooser, I select debian13.qcow2 of my Downloads
  folder`: "Not in 10 s: a file chooser shows". Alone it passes, in about
  40 s, much longer than the others. Seen on 3.0.0.dev6, on 20 October
  2026, with `pytest --count 10 -n 5 -k
  test_the_file_chooser_of_the_image_of_dtn2hops_on_its_file`: 8 of 10
  failed on a2602080, 4 of 10 with the fix of "A brick that is starting
  counts as stopped" in the tree; once in a run of every scenario with
  `-n 8`. What makes it slow, and the file chooser late, wasn't looked
  into.
