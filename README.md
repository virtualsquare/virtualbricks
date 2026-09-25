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
sudo apt install qemu-system-x86 qemu-utils vde2 xterm sudo
```

- `qemu-system-*` for each architecture of your VMs, and `qemu-img`;
- VDE 2: `vde_switch`, `vde_plug`, `wirefilter`, `vde_plug2tap`, `dpipe`,
  `vdeterm`, `vde_router` and `vde_cryptcab`;
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

It installs the `virtualbricks` command, the manual page of the configuration
files and the translations. To work on the code, follow
[Development](#development) instead.

## Running

```sh
virtualbricks
```

or `python -m virtualbricks`. The window opens with the project that was open
last. The terminal that started Virtualbricks runs a Python console with the
brick factory in it, unless you give `--noterm`.

The options are:

- `-v`, `--verbose`, `-q`, `--quiet`: increase or decrease the log verbosity;
  they can be repeated.
- `--debug`: the most verbose output. With it, and with `-vv`, Ctrl+C and the
  `SIGUSR2` signal drop into the `pdb` debugger.
- `-l FILE`, `--logfile FILE`: write the log messages to a file.
- `--noterm`: don't show the console in the terminal.
- `--version`: print the version and exit.

Only one Virtualbricks can run at a time. It holds the lock `/tmp/vb.lock`,
and if a crash leaves it behind, the message that refuses to start says to
delete it.

## Configuration

Virtualbricks keeps its files in TOML, and writes them itself:

- `~/.config/virtualbricks/settings.toml`: your preferences, which aren't
  about a project, as the terminal. It is in `$XDG_CONFIG_HOME` if that is set.
- `~/.local/state/virtualbricks/state.toml`: what it remembers between runs,
  as the project that was open. It is in `$XDG_STATE_HOME` if that is set.
- `~/.virtualbricks/`: the workspace, a folder for each project, with its
  `project.toml`, its README and its private disks. The `workspace` setting
  changes it.

Each project has its own settings, in its `project.toml`: the first time,
choose in *Settings › Preferences*, on the page of the project, where
Virtualbricks finds the programs: `qemupath` and `vdepath`, the folders of the
Qemu and VDE binaries. A new project starts with a copy of the settings of the
project that is open. The page of the application sets `term`, the terminal of
the consoles.

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
[`docs/config-files.html`](docs/config-files.html).

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

The lock `/tmp/vb.lock` is the same for every home: you can't run that while
another Virtualbricks is running.

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

- The tests don't touch your settings, your projects or the lock: each one
  runs in a temporary home. They need neither root, nor Qemu, nor VDE.
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
  `make_factory`, `FakeLogger`, `use_workspace`) and, for the windows, in
  `virtualbricks/tests/gui/__init__.py` (`GuiTestCase`).
- `test_docs.py` checks that the manual page documents every setting, key of
  the project file and kind of brick of the code, and that the page is up to
  date with its source: when you change one of them, update
  `docs/man/virtualbricks-config.5.md`.

### Code style

The code is formatted with `black`, at 79 columns, and checked with `ruff`.
`pre-commit` runs them, and two more hooks, on every commit:

```sh
pre-commit run --all-files     # run them without committing
```

- **black** and **ruff**: format and check what you changed.
- **man pages**: `python docs/man/build.py` builds
  `docs/man/virtualbricks-config.5` from its Markdown source with pandoc; the
  page is committed. With `--check` it only tells whether the page is out of
  date.
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
  events and the images of the open project; `console.py` is the console of
  the terminal; `tools.py` and `spawn.py` run the Qemu and VDE programs;
  `locations.py` has the paths of the files.
- `virtualbricks/bricks/`: a module for each kind of brick: virtual machine,
  switch, tap, wire, and so on.
- `virtualbricks/config/`: the settings and the state, the schemas of their
  fields, the project file, and the projects: `workspace.py` lists, creates and
  opens them, `archive.py` and `importing.py` read, write and import their
  archives in a process of their own. The rest of the code takes what it needs
  from the package by name, as in `from virtualbricks.config import projects`.
  It imports no GTK or GLib, so that it works in a console or a script: what
  needs the desktop, as the trash, is given to it by the GUI.
- `virtualbricks/migrate/`: the only code that reads the files of Virtualbricks
  2.1 and older.
- `virtualbricks/gui/`: the application window and the messages log;
  `windows/` has a module for each window, built in Python code.
- `virtualbricks/tests/`: the tests, in the layout of the package.
- `docs/`: the manual page, in `man/`, and the designs of the parts that were
  rewritten: `config-redesign.html` and `config-files.html` for the files,
  `messages-window.html` for the messages window and `projects-redesign.html`
  for the projects, their import and their export.
- `locale/`: the translations; `share/`: the desktop file and the icon.

## License

Virtualbricks is free software, under the GNU General Public License, version
2 or, at your option, any later version. See `COPYING`.
