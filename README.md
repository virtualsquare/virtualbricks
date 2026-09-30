# Virtualbricks

Virtualbricks is a frontend for the management of Qemu Virtual Machines
(VMs) and VDE virtualized network devices (switches, channel emulators,
etc.). Although it can be used to manage isolated VMs, its peculiar aim
is to design and manage testbeds consisting of many VMs interconnected
by VDE elements. In other words, it allows to extend the concept of VM
to testbeds, which thanks to Virtualbricks can become entirely
software-defined.

## Requirements

Virtualbricks needs Python 3.10 or newer and GTK 3.

pip installs the Python libraries that Virtualbricks depends on, but two of
them are built against libraries of your system, which pip can't install:
PyGObject, the GTK bindings, and pygraphviz. You need, before running pip:

- a C compiler, pkg-config and the headers of Python;
- the development files of GObject Introspection and of cairo, for PyGObject;
- GTK 3 with its GObject Introspection data, which PyGObject loads at run time;
- Graphviz and its development files, for pygraphviz.

On Debian 13 (trixie) they are:

```sh
sudo apt install python3-venv python3-dev gcc pkg-config \
    libgirepository-2.0-dev libcairo2-dev gir1.2-gtk-3.0 \
    graphviz libgraphviz-dev
```

The names are those of Debian; other distributions have their equivalents.

To use Virtualbricks, and not only to install it, you need these programs too.
On Debian:

```sh
sudo apt install qemu-system-x86 qemu-system-gui qemu-utils vde2 \
    vde2-cryptcab xterm sudo
```

- `qemu-system-*` for each architecture of your VMs, and `qemu-img`;
  `qemu-system-gui` has the windows of the machines, SDL and GTK. QEMU 6.2
  and newer: before a machine starts, Virtualbricks asks its QEMU what it
  has, and a setting that this QEMU lacks is left out, with a warning in
  *File › Logs*. Ubuntu builds its QEMU without VDE, which a machine needs to
  plug into a switch: there, use a QEMU package built with it;
- VDE 2: `vde_switch`, `vde_plug`, `wirefilter`, `vde_plug2tap`,
  `vde_pcapplug`, `dpipe`, `vdeterm` and `unixterm`, and `vde_cryptcab`, in
  its own package; the router brick needs `vde_router`, which no distribution
  ships;
- a terminal, `xterm` by default, and `sudo`, which runs the bricks that need
  root, a tap and a capture (see [Configuration](#configuration)).

These are optional:

- `bsdtar` (`libarchive-tools`) or GNU `tar`, to export and import projects;
  without them Virtualbricks uses Python's `tarfile`;
- `gvfs`, so that removing a project can move it to the trash of your desktop;
  without a trash the window offers to delete it for good;
- an askpass helper for `sudo`, as `ssh-askpass`, to type the password of root
  in a window (see [Configuration](#configuration)).

## Installing

To install Virtualbricks for your user, once the libraries above are there:

```sh
pip install --user .
```

It installs the `virtualbricks` command, the `virtualbricks-migrate` window,
the manual pages of the configuration files and of the archives of the
projects, and the translations. To work on the code, follow
[Development](#development) instead.

## Running

```sh
virtualbricks
```

or `python -m virtualbricks`. The window opens with the project that was open
last in the workspace, and the terminal that started Virtualbricks reads the
commands of its console, unless you give `--noterm`; see
[The console](#the-console).


The options are:

- `-v`, `--verbose`, `-q`, `--quiet`: increase or decrease the log verbosity;
  they can be repeated.
- `--debug`: the most verbose output. With it, and with `-vv`, Ctrl+C and the
  `SIGUSR2` signal drop into the `pdb` debugger.
- `-l FILE`, `--logfile FILE`: write the log messages to a file.
- `--noterm`: don't read the console in the terminal.
- `--no-gui`: run without the windows, and without GTK: the console is the
  way in.
- `--run FILE`: run the commands of a file once the project is open, then
  read the console; with `--connect`, send them to the Virtualbricks that
  runs, and exit.
- `--workspace FOLDER`: use the projects of another folder, made if it isn't
  there, for this run only; see [Configuration](#configuration).
- `--lock MODE`: the single-instance mode, how many Virtualbricks can run at
  once; see below.
- `--command WORD...`: send a command of the console to the Virtualbricks
  that runs, and print its answer; see [The console](#the-console).
- `--socket [DESCRIPTION]`: listen on a control socket, `.control` in the
  runtime directory, or the one of a description, as
  `unix:~/labs/lab1.amp:protocol=amp`, `tcp:8765` or
  `ssl:8765:privateKey=FILE`; it can be given more than once.
- `--connect [DESCRIPTION]`: the Virtualbricks that runs that `--command`
  and `--run` talk to, the one of `.control` or of a description, as
  `tcp:lab.example:8765`.
- `--version`: print the version and exit.

`--lock` sets the single-instance mode, one of:

- `system`, the default: one Virtualbricks on the machine, whoever runs it
  and whatever its workspace. It holds the lock `/tmp/virtualbricks.lock`
  alone.
- `user`: one for each user, so the users of a shared machine don't stop each
  other. It holds the lock `.lock` of the runtime directory,
  `$XDG_RUNTIME_DIR/virtualbricks/`, and shares `/tmp/virtualbricks.lock`
  with the others in this mode: it doesn't start while one runs with
  `system`, nor one with `system` while it runs.
- `none`: no lock. It starts beside any other, and the others don't see it;
  two of yours share the settings, and nothing stops both from opening the
  same project.

The system releases the locks when Virtualbricks ends, even when it crashes,
so none is ever left behind. When a lock refuses a start, the message names
the processes that hold it and the users that started them.

### The console

A command of the console is a noun, a verb and its arguments:

```
brick new switch
brick new vm router
brick set router memory=512 use_kvm=true
brick card add router plug sw1
brick start router
event new down
event set down delay=600
event action add down stop router
event start down
```

The nouns are `brick`, `event`, `image`, `setting` and `project`; `help`
lists the commands, and Tab completes them, the names and the keys. A key
and its value are `KEY=VALUE`, with the names of the project file, and a
command changes all of them or none. The history is kept between runs, and
the line has the keys of readline: Ctrl+R searches the history, Alt+B and
Alt+F go by words, Ctrl+W, Ctrl+K and the others delete, Ctrl+Y puts back.
`python` opens a Python shell with the brick factory in it.

The same commands run from a file, with `source FILE` or `--run FILE`, from a
pipe, and in an event, as its actions. With `--no-gui --noterm --run FILE`,
Virtualbricks sets a lab up and runs it on a machine without a display.

A Virtualbricks started with `--socket`, with the windows or without,
listens on a control socket, `$XDG_RUNTIME_DIR/virtualbricks/.control`, and
`--command` sends it a command from any terminal or script, and
`--connect --run` the commands of a file:

```
virtualbricks --no-gui --socket
virtualbricks --command brick start router
virtualbricks --connect --run start-lab.vb
```

The answer goes to the standard output, an error to the standard error, and
the exit status is 0 when the command was done, 1 when it failed, and 2 when
no Virtualbricks answered. Only you can connect. The socket speaks JSON, a
line for each request and answer, so any program can use it.

A description after `--socket`, in the syntax of Twisted's endpoints, puts a
socket elsewhere, and `protocol=amp` makes it speak Twisted's AMP, for a
program written with Twisted: `--socket unix:~/labs/lab1.amp:protocol=amp`.
The program calls `Run` with a line of the console and gets a Deferred of
its answer; `virtualbricks/console/ampwire.py` has the commands. Once
`Hello` agrees on protocol 2, each command of the console is an AMP command
of its own, with typed arguments, as `BrickStart(name=["sw1", "vm1"])`:
`virtualbricks/console/ampcommands.py` has them. The option
can be given more than once, for a JSON socket and an AMP one at once.
`--command` talks to either: `--connect unix:~/labs/lab1.amp:protocol=amp
--command status`.

`--socket tcp:8765` listens on a port of this machine, and
`--socket ssl:8765:interface=0.0.0.0:privateKey=lab.pem` on a port open to
the network, with TLS. A client proves first that it knows the token of
`~/.config/virtualbricks/token`, which Virtualbricks makes; neither end
sends it. With `caCertsDir=FOLDER`, an ssl socket asks each client for a
certificate instead, and the log names it. `--command` talks to them as
`--connect tcp:8765` on this machine, or as
`--connect ssl:lab.example:8765:caCertsDir=FOLDER` from another.

Every option and command is in the manual page, which you can read from the
sources with `man ./docs/man/virtualbricks.1`, and in
[`docs/command-line.html`](docs/command-line.html).

## Configuration

Virtualbricks keeps its files in TOML, and writes them itself:

- `~/.config/virtualbricks/settings.toml`: your preferences, which aren't
  about a project, as the terminal. It is in `$XDG_CONFIG_HOME` if that is set.
- `~/.local/state/virtualbricks/state.toml`: what it remembers between runs,
  as the project that was open last in each workspace. It is in
  `$XDG_STATE_HOME` if that is set.
- `~/.virtualbricks/`: the workspace, a folder for each project, with its
  `project.toml`, its README and its private disks, and `vimages/`, the disk
  images its projects share. The `workspace` setting changes it, and
  `virtualbricks --workspace FOLDER` uses another one for a run, as a folder
  of projects for each course or each client; the setting stays as it is.

Each file says, in a comment above each key, what the key is for, and marks
with `# default` the values that are the defaults. Virtualbricks writes the
files again as it saves, so comments added by hand don't last.

Each project has its own settings, in its `project.toml`: the first time,
choose in *File › Settings*, on the page of the project, where
Virtualbricks finds the programs: `qemu_path` and `vde_path`, the folders of
the Qemu and VDE binaries. A new project starts with a copy of the settings of
the project that is open. The page of the application sets `terminal`, the
terminal of the consoles, and `audio_driver`, the audio driver of QEMU that
plays the sound cards of the machines: `alsa` by default, or `pa`,
`pipewire`, and the others your QEMU has.

A tap and a capture need root. Unless Virtualbricks runs as root, it runs them
with `sudo -A` when an askpass helper is configured, in `SUDO_ASKPASS` or
`/etc/sudo.conf`, and with `sudo -n` otherwise, which never asks for a password:
without a display, a `NOPASSWD` rule of sudoers lets them run. The PRIVILEGES
section of `man 5 virtualbricks-config` has the details.

The `~/.virtualbricks.conf` file and the `.project` files of Virtualbricks 2.1
and older are converted once, when the new version starts. The conversion is
also `virtualbricks-migrate`, a window, and `python -m virtualbricks.migrate`,
the command line.

The files are described in the manual page, which you can read from the
sources with `man ./docs/man/virtualbricks-config.5`, and in
[`docs/config-files.html`](docs/config-files.html); the archives that export
and import projects in `man ./docs/man/virtualbricks-archive.7` and
[`docs/archive-protocol.html`](docs/archive-protocol.html).

## Development

### Setting up

Once you have the libraries of [Requirements](#requirements):

```sh
git clone https://github.com/virtualsquare/virtualbricks.git
cd virtualbricks
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -e . --group dev
pre-commit install
```

The `dev` dependency group has the tools of the project: `coverage`, `black`,
`ruff`, `pyflakes`, `pre-commit`, `pypandoc-binary`, which brings pandoc for
the manual page, and `PyGObject-stubs`, the types of GTK. `--group` needs pip
25.1 or newer, and the pip of a new environment is often older, hence the
upgrade. The editable install (`-e`) makes the `virtualbricks` command run your
working copy.

The code has to run on Python 3.10, the oldest that is supported, so it is
best to work with that one.

To try your changes without touching your own settings and projects, give
Virtualbricks another home, as the tests do:

```sh
H=$(mktemp -d)
HOME=$H XDG_CONFIG_HOME=$H/.config XDG_STATE_HOME=$H/.local/state \
    virtualbricks
```

The locks are the same for every home: add `--lock none` to run that beside
your own Virtualbricks.

### Tests

The tests use Twisted's `trial`, and run from the root of the sources:

```sh
python -m twisted.trial virtualbricks                # all of them
python -m twisted.trial -j4 virtualbricks            # on four processes
python -m twisted.trial virtualbricks.tests.config.test_workspace
python -m twisted.trial virtualbricks.tests.config.test_workspace.TestNames.test_free_name
```

With the coverage of the code:

```sh
coverage run -m twisted.trial virtualbricks
coverage report
```

`trial` writes in `_trial_temp/`, which git ignores.

- The tests don't touch your settings, your projects or the locks: each one
  runs in a temporary home. They need neither root, nor Qemu, nor VDE, but
  one: `test_integration.py` makes the sample project of
  `virtualbricks/tests/sample.py`, a brick of each kind, and starts it with
  the programs installed here, the machine paused; it is skipped without
  `qemu-system-x86_64`, `qemu-img` and `vde_switch`.
- The command lines of the bricks are tested against what the QEMU and VDE of
  each supported distribution answer, recorded in
  `virtualbricks/tests/data/programs/<target>.json`. In the same folder,
  `record.py` records them again, for a new distribution or when one updates
  its QEMU, and `start.py` starts the sample project in a container of each
  distribution, as root: the check before a release. Both need `podman` and
  the network.
- The tests of the windows need a display, and are skipped without one. To run
  them on a machine without, install `xvfb` and run
  `xvfb-run -a python -m twisted.trial virtualbricks`.
- The tests of the archives and of the packing of the disks use `bsdtar`, GNU
  `tar`, `qemu-img` and `qemu-io`, and are skipped for the ones that aren't
  installed.
- `virtualbricks/tests/` has the layout of the package, a test module for each
  module: `virtualbricks/config/workspace.py` is tested by
  `virtualbricks/tests/config/test_workspace.py`. The helpers are in
  `virtualbricks/tests/__init__.py` (`isolate`, `reset_settings`,
  `make_factory`, `FakeLogger`, `use_workspace`, and `BrickTestCase` and
  `CommandTestCase` for the bricks) and, for the windows, in
  `virtualbricks/tests/gui/__init__.py` (`GuiTestCase`).
- `test_docs.py` checks that the manual page of the files documents every
  setting, key of the project file and kind of brick of the code, that the
  manual page of the command has every option and every command of the
  console as the table of the commands has them, and that the pages are up to
  date with their sources: when you change one of them, update
  `docs/man/virtualbricks-config.5.md` or `docs/man/virtualbricks.1.md`.

### Code style

The code is formatted with `black`, at 79 columns, and checked with `ruff`.
`pre-commit` runs them, and two more hooks, on every commit:

```sh
pre-commit run --all-files     # run them without committing
```

- **black** and **ruff**: format and check what you changed.
- **man pages**: `python docs/man/build.py` builds the pages of `docs/man/`
  from their Markdown sources with pandoc; the pages are committed. With
  `--check` it only tells whether one is out of date.
- **translations**: `./l10n.sh` extracts the messages of the sources into
  `locale/virtualbricks/virtualbricks.pot`, merges them into the `.po` file of
  each language and compiles the `.mo` catalogs, which are committed too. It
  needs the GNU gettext tools: `xgettext`, `msgmerge` and `msgfmt` (`gettext`
  in Debian).

When a hook changes files, as when you add a message the translations have to
know, the commit stops: stage what it changed and commit again.

The messages that the user reads go through `_()`, from `virtualbricks.i18n`.
To add a language, see the top of `l10n.sh`.

### Source layout

- `virtualbricks/`: `app.py` and `scripts/` start the application and read its
  command line; `brickfactory.py` is the model in memory, the bricks, the
  events and the images of the open project; `programs.py` finds the
  installed QEMU and VDE programs and asks them what they have; `vde.py`
  finds the VDE programs of the settings; `sudo.py` writes the `sudo`
  command of what needs root, and `ksm.py` turns Kernel Samepage Merging on
  and off; `markdown.py` reads the README of a project, and `topology.py`
  lays the lab out with Graphviz; `locations.py` has the paths of the files.
- `virtualbricks/bricks/`: `__init__.py` has what bricks and events share,
  and the base class of the bricks; a module for each kind of brick:
  virtual machine, switch, tap, wire, and so on; each writes its command
  line with `command.py`. `draft.py` is what the settings panels work on: a
  copy of a brick's settings, checked as it's set, given to the brick at
  OK; a brick with checks of its own has its draft in its module.
  `brickinfo.py` and `eventinfo.py` say in words what a brick or an event
  is and does, for the tabs of the main window and for the console.
- `virtualbricks/qemu/`: what Virtualbricks knows of QEMU itself.
  `imageformat.py` tells the format of a disk image, and its backing file,
  from the first bytes of the file; `run.py` finds the QEMU programs and
  runs `qemu-img`.
- `virtualbricks/console/`: the console. `command.py` declares each command
  with its arguments, `parser.py` reads and completes a line, `dispatch.py`
  runs it; a module for each noun, `bricks.py`, `events.py`, `images.py`,
  `settings.py` and `projects.py`, and `general.py` for `help`, `status`,
  `source` and `quit`. `terminal.py` reads the terminal, or a pipe, and
  `lineedit.py` has the keys of readline for its line. `control.py` listens
  on the control sockets, `client.py` is `--command` and `--connect --run`,
  with `ampbox.py`, the boxes of AMP read and written without Twisted, and
  `wire.py` has what both share: the text protocol, the descriptions of
  `--socket` and `--connect`, the checks of a socket's path, the token and
  its proof. `tls.py` has the certificates of the ssl sockets, and is the
  only module that needs pyOpenSSL.
  `ampwire.py` has the commands of the AMP socket, for the programs that use
  it. It imports no GTK, so that `--no-gui`
  doesn't load it, and `client.py` doesn't load Twisted's reactor either.
- `virtualbricks/config/`: the settings and the state, the schemas of their
  fields, the project file, and the projects: `workspace.py` lists, creates and
  opens them, `archive.py` and `importing.py` read, write and import their
  archives in a process of their own. The rest of the code imports what it
  needs from each module, as in `from virtualbricks.config.workspace import
  projects`; the package itself exports nothing.
  It imports no GTK or GLib, so that it works in a console or a script: what
  needs the desktop, as the trash, is given to it by the GUI.
- `virtualbricks/migrate/`: the only code that reads the files of Virtualbricks
  2.1 and older.
- `virtualbricks/gui/`: the windows, built in Python code. `mainwindow/` is
  the main window, with a module or a package for each tab: `bricks/`,
  `events/`, `images/`, `topology.py` and `readme.py`. The settings panel of
  each kind of brick is in `bricks/config/`: rows made by `form.py` from the
  schema, on the brick's draft, and the virtual machine's in `vm/`, a module
  for each section of its sidebar. The settings of an event and the details
  of an image are panels on drafts too, in `events/` and `images/`.
  `dialogs/` has the other windows and dialogs, and `messages.py` the
  messages of the Logs window.
- `virtualbricks/tests/`: the tests, in the layout of the package.
- `docs/`: the manual pages, in `man/`, and their web pages,
  `command-line.html`, `config-files.html` and `archive-protocol.html`; in
  `redesign/`, the designs of the parts that were rewritten, numbered in the
  order of the work, from the conversion of the Glade files to the console.
- `locale/`: the translations; `share/`: the desktop file and the icon.

## License

Virtualbricks is free software, under the GNU General Public License, version
2 or, at your option, any later version. See `COPYING`.
