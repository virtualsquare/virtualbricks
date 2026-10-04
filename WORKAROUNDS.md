# Workarounds

The places where Virtualbricks works around a limit or a bug of a library,
or of a program that it runs, with the versions that need them. When a
distribution is no longer supported, the workarounds that only its versions
need can go: find its column in [Versions](#versions), then its section
below.

Each workaround is found by its file and its name, not by a line; the words
in quotes find it with `grep -rn`.

## Versions

The versions of the supported distributions, from `apt-cache policy` in a
container of each, on 4 October 2026:

| | Ubuntu 22.04 | Debian 12 | Ubuntu 24.04 | Debian 13 | Ubuntu 26.04 | Debian testing, sid |
|---|---|---|---|---|---|---|
| Python | 3.10.6 | 3.11.2 | 3.12.3 | 3.13.5 | 3.14.3 | 3.14.7 |
| GTK 3 | 3.24.33 | 3.24.38 | 3.24.41 | 3.24.49 | 3.24.52 | 3.24.52 |
| GLib | 2.72.4 | 2.74.6 | 2.80.0 | 2.84.4 | 2.88.0 | 2.90.0 |
| Pango | 1.50.6 | 1.50.12 | 1.52.1 | 1.56.3 | 1.57.0 | 1.58.0, 1.58.2 |
| AT-SPI (at-spi2-core) | 2.44.0 | 2.46.0 | 2.52.0 | 2.56.2 | 2.60.4 | 2.62.0 |
| PyGObject | 3.42.1 | 3.42.2 | 3.48.2 | 3.50.0 | 3.56.2 | 3.58.0 |
| Twisted | 22.1.0 | 22.4.0 | 24.3.0 | 24.11.0 | 25.5.0 | 26.4.0 |
| attrs | 21.2.0 | 22.2.0 | 23.2.0 | 25.3.0 | 25.4.0 | 26.1.0 |
| tomli | 1.2.2 | 2.0.1 | 2.0.1 | 2.2.1 | 2.4.0 | 2.4.1 |
| tomlkit | 0.9.2 | 0.11.7 | 0.12.4 | 0.13.2 | 0.13.3 | 0.13.3 |
| markdown-it-py | 1.1.0 | 2.1.0 | 3.0.0 | 3.0.0 | 3.0.0 | 4.2.0 |
| pygraphviz | 1.7 | 1.7 | 1.7 | 1.14 | 1.14 | 1.14 |
| zope.interface | 5.4.0 | 5.5.2 | 6.1 | 7.2 | 8.2 | 8.6 |
| pyOpenSSL | 21.0.0 | 23.0.0 | 23.2.0 | 25.0.0 | 25.3.0 | 26.4.0 |
| OpenSSL | 3.0.2 | 3.0.22 | 3.0.13 | 3.5.7 | 3.5.5 | 3.6.4, 3.6.5 |
| QEMU | 6.2 | 7.2 | 8.2.2 | 10.0.13 | 10.2.1 | 11.1.1, 11.1.2 |
| vde2-cryptcab | 2.3.2+r586 | 2.3.2+r586 | 2.3.2+r586 | 2.3.2+r586 | 2.3.2+r586 | 2.3.2+r586 |

The versions are those of the packages, without the revision of the
distribution.

## Gone with Ubuntu 22.04

Ubuntu 22.04 is the only target with Python 3.10, attrs 21 and QEMU 6.2.

### W1. tomllib, else tomli

- **Why:** Python 3.10 has no `tomllib`; it came in 3.11.
- **Needed on:** Ubuntu 22.04 (3.10.6). Debian 12 (3.11.2) and later have it.
- **Where:** `virtualbricks/config/tomlfile.py` and `e2e/steps.py`, "import
  tomli as tomllib"; `pyproject.toml`, the dependency `tomli>=1.2;
  python_version < '3.11'`.
- **Removing it:** `import tomllib` alone, and the dependency goes.

### W2. attr.define, not attrs.define

- **Why:** attrs 21.2.0 has no `attrs` namespace; it came in 21.3.0.
- **Needed on:** Ubuntu 22.04 (21.2.0). Debian 12 (22.2.0) and later have it.
- **Where:** `virtualbricks/config/schema.py`, "define = attr.define".
- **Removing it:** optional: attrs keeps `attr` too. `from attrs import define`
  if the new names are wanted.

### W3. Unpack from typing_extensions

- **Why:** Python 3.10 has no `typing.Unpack`; it came in 3.11.
- **Needed on:** Ubuntu 22.04 (3.10.6), for the type checker only: the import
  is under `TYPE_CHECKING`, and typing_extensions isn't a dependency.
- **Where:** `virtualbricks/migrate/gui.py` and `virtualbricks/migrate/cli.py`,
  "from typing_extensions import Unpack".
- **Removing it:** `from typing import Unpack`.

### W4. The audio drivers of QEMU 6.2, taken on trust

- **Why:** QEMU 6.2 can't list its audio drivers (`-audiodev help` fails), so
  a sound card's driver can't be checked before the machine starts.
- **Needed on:** Ubuntu 22.04 (QEMU 6.2).
- **Where:** `virtualbricks/programs.py`, `QemuInfo.audio_drivers` ("None when
  the program can't list them") and `qemu_info()`, "if audio.status == 0
  else None"; `virtualbricks/bricks/virtualmachine.py`,
  `VirtualMachineDraft.note()` ("doesn't list its drivers") and `lacks()`
  ("QEMU 6.2 doesn't list its drivers").
- **Removing it:** `audio_drivers` is always a set; the note and the `None`
  checks go.

### W5. The "qemu:" lines in the help of QEMU 6.2

- **Why:** QEMU 6.2 writes a message for each module it leaves out among the
  lines of a `help` list.
- **Needed on:** Ubuntu 22.04 (QEMU 6.2). Whether later QEMU write them wasn't
  checked: check on the oldest QEMU left before removing it.
- **Where:** `virtualbricks/programs.py`, `_items()`, "as QEMU 6.2 writes
  them".

QEMU 6.2 is also the oldest QEMU supported on its own terms (every major
version from 6.2): W4 and W5 go when that promise changes, which may be later
than Ubuntu 22.04.

### The floors that follow Ubuntu 22.04

The oldest versions that Virtualbricks asks for are those of Ubuntu 22.04.
With it gone, raise them to those of Debian 12:

| Where | Now | Debian 12 |
|---|---|---|
| `pyproject.toml`, `requires-python` | `>=3.10` | `>=3.11` |
| `pyproject.toml`, `[tool.black]` and `[tool.ruff]` | `py310` | `py311` |
| `pyproject.toml`, `Twisted[tls]` | `>=22.1` | `>=22.4` |
| `pyproject.toml`, `attrs` | `>=20.1` | `>=22.2` |
| `pyproject.toml`, `markdown-it-py` | `>=1.1` | `>=2.1` |
| `pyproject.toml`, `zope.interface` | `>=5.4` | `>=5.5` |
| `pyproject.toml`, `tomlkit` | `>=0.9` | `>=0.11` |
| `pyproject.toml`, `tomli` | `>=1.2` | gone (W1) |
| `README.md`, Requirements | "Python 3.10 or newer" | 3.11 |
| `README.md`, Development | "has to run on Python 3.10" | 3.11 |

PyGObject (`>=3.42`) and pygraphviz (`>=1.7`) stay: Debian 12 has 3.42.2
and 1.7.

## Gone with Debian 12 and Ubuntu 24.04

### W6. The CPU models of QEMU 8 and older

- **Why:** up to QEMU 8, a line of `-cpu help` starts with the architecture,
  as "x86 486"; from QEMU 9 it's indented instead.
- **Needed on:** Ubuntu 22.04 (6.2), Debian 12 (7.2), Ubuntu 24.04 (8.2.2).
  No target has QEMU 9; Debian 13 has 10.0.
- **Where:** `virtualbricks/programs.py`, `parse_cpus()`, "Up to QEMU 8".
- **Removing it:** only the indented lines; when the oldest QEMU supported is
  9 or later.

## Needed on every target

These are limits of GTK 3, Pango and OpenSSL that every target has: they go
with a library that changes them, not with a distribution. Each needs a check
in the move to GTK 4 (`docs/redesign/18 - gtk4-migration.html`).

### W7. A resize asked while GTK gives the sizes is lost

- **Why:** GTK 3 drops a resize that a widget queues while it is being
  allocated: `gtk_widget_size_allocate()` clears it afterwards ("Size
  allocation is god" in `gtkwidget.c`). Whatever changes a size on
  `size-allocate` does it in an idle call.
- **Needed on:** every target (GTK 3.24.33 to 3.24.52).
- **Where:** "GTK would lose" and "GTK forgets":
  - `virtualbricks/gui/mainwindow/topologyview.py`,
    `TopologyView.on_allocated()` → `_fit_later()`;
  - `virtualbricks/gui/mainwindow/topology.py`,
    `TopologyTab.on_bar_allocated()` → `_measure()`;
  - `virtualbricks/gui/mainwindow/readme.py`, `ReadmeTab.on_size_allocate()`
    → `_set_margin_later()`;
  - `virtualbricks/gui/markdownview.py`, `MarkdownLabel.on_size_allocate()`
    and `MarkdownView.on_size_allocate()` → `_fit_later()`.

### W8. A popover is destroyed once idle, after "closed"

- **Why:** GTK 3 emits "closed" in the middle of a click on an item of a
  popover, and goes on using the popover; the item runs its action last.
  Destroyed in "closed", the popover was freed under GTK (a segmentation
  fault) and the action lost.
- **Needed on:** every target (GTK 3.24).
- **Where:** `virtualbricks/gui/mainwindow/rowtab.py`, `Row.on_menu_closed()`,
  "GLib.idle_add(popover.destroy)". Commit c1deff3.

### W9. The picture of the Topology tab has a viewport of its own

- **Why:** the viewport that `GtkScrolledWindow` adds around a widget that
  can't scroll follows the focus: a press on the picture gave it the focus,
  and the view scrolled back to its corner. A viewport made by hand has no
  focus adjustments.
- **Needed on:** every target (GTK 3.24).
- **Where:** `virtualbricks/gui/mainwindow/topologyview.py`,
  `TopologyView.__init__()`, "a viewport of its own". Commit e8bc37b.

### W10. Add Image opens a popover, not a Gtk.Menu

- **Why:** a `Gtk.Menu` shows on the screen but out of the widgets of the
  window that AT-SPI lists: a screen reader that walks them, and the
  end-to-end tests, can't find its items.
- **Needed on:** every target (GTK 3.24). Keep it anyway: the menus of the
  rows and New Brick are popovers too, and GTK 4 has no `Gtk.Menu`.
- **Where:** `virtualbricks/gui/mainwindow/images/tab.py`,
  `ImagesTab._make_add_menu()`, "where a Gtk.Menu isn't". Commit dd20fd7.

### W11. A context menu is kept while it shows

- **Why:** a `Gtk.Menu` popped up from Python is released once Python drops
  it, so `popup()` asks its callers to keep it, and the tabs do. Not checked
  again since: the widget that the menu is attached to may hold it too.
- **Needed on:** every target (GTK 3.24, PyGObject 3.42 to 3.58). It goes with
  `Gtk.Menu`, in GTK 4.
- **Where:** `virtualbricks/gui/mainwindow/tab.py`, `popup()`, "Keep the menu
  that it returns while it shows"; `virtualbricks/gui/mainwindow/topology.py`
  and `virtualbricks/gui/mainwindow/rowtab.py`, "kept while it shows".

### W12. A README in a label: one Pango paragraph, the lines that fit

- **Why:** a `GtkLabel` limits the lines of each Pango paragraph, not of the
  label, and Pango joins to the last line that it trims the lines after it,
  without their breaks. `MarkdownLabel` joins the lines of the README with a
  line separator, which doesn't end the paragraph, and keeps only the lines
  that fit.
- **Needed on:** every target (Pango 1.50.6 to 1.58.2); GTK 4 lays out its
  labels with Pango too.
- **Where:** `virtualbricks/gui/markdownview.py`, `MarkdownLabel` and its
  `fit()`, `LINE_SEPARATOR`.

### W13. OpenSSL loads its legacy provider for vde_cryptcab

- **Why:** vde_cryptcab encrypts with Blowfish, which OpenSSL 3 has only in
  its legacy provider, and loads only when told. Each end of a tunnel writes
  an OpenSSL configuration that loads it, and starts vde_cryptcab with
  `OPENSSL_CONF` naming it.
- **Needed on:** every target (OpenSSL 3.0.2 to 3.6.5, vde2-cryptcab
  2.3.2+r586 everywhere). It goes only if vde_cryptcab changes its cipher. An
  OpenSSL without the legacy provider would stop the tunnels altogether.
- **Where:** `virtualbricks/bricks/tunnellisten.py`, `OPENSSL_CONFIG`,
  `write_openssl_config()` and `cryptcab()`, "OPENSSL_CONF". Commit b6c2e05.

## The end-to-end tests

The tests in `e2e/` run Virtualbricks on `broadwayd`, GTK 3's HTML5 backend,
and find its widgets through AT-SPI. These workarounds are for limits of GTK
3 on Broadway and of what GTK 3 tells AT-SPI, on every target (GTK 3.24.33 to
3.24.52): they go, or change, with GTK 4. `e2e/README.md` (What it can't do
yet) and `e2e/TODO.md` (Out of reach on Broadway) have the limits that have
no workaround, such as drag and drop.

### E1. Text is written through AT-SPI, not typed as keys

- **Why:** GTK 3's Broadway backend leaves unset the modifiers that a key
  consumes, which GTK reads anyway (`_gtk_key_hash_lookup`): a key then
  sometimes matches an accelerator or a mnemonic, as a "p" Ctrl+P.
- **Where:** `e2e/harness.py`, `Virtualbricks.type()`; `e2e/a11y.py`,
  `write()` and `erase()`. `Virtualbricks.key()` sends only keys that the
  window has with no other modifier.

### E2. A key waits for its window to be active

- **Why:** broadwayd gives a key to the window that has the focus when the
  key comes, and focuses the window pressed only once it has handled the
  press: a key right after a click went to the window before.
- **Where:** `e2e/harness.py`, `Virtualbricks.key()`, "a11y.active(window)".

### E3. A broadwayd for each Virtualbricks

- **Why:** broadwayd aborts when a program that it shows quits ("can't write
  to client").
- **Where:** `e2e/harness.py`, `Desktop.screen()`.

### E4. The offsets of the text of a text view

- **Why:** a `GtkTextView` of GTK 3 leaves its images out of the text that it
  tells AT-SPI, but counts them in the offsets of its characters.
- **Where:** `e2e/a11y.py`, `offset()`.

### E5. The event chosen in a brick's menu is read on its row

- **Why:** the radio choices of a menu of GTK 3, model buttons in a popover,
  don't tell AT-SPI which one is on.
- **Where:** `e2e/steps.py`, `choose_event()`, "don't tell AT-SPI which is
  on".

### E6. The + and − of a spin button are clicked where GTK 3 draws them

- **Why:** AT-SPI shows a spin button as one widget, without its two buttons;
  GTK 3 draws − and + at its right end, + last, each about as wide as the
  spin button is high.
- **Where:** `e2e/harness.py`, `Virtualbricks.spin()`, and `type()` for a
  spin button.

### E7. The browser speaks the Broadway of GTK 3

- **Why:** `e2e/broadway.py` speaks the protocol of `broadway.js` of GTK
  3.24; that of GTK 4 differs. On Ubuntu 22.04, `gtk4-broadwayd` (GTK 4.6.9)
  crashes with any window: with GTK 4 there, the tests would need Xvfb.
- **Where:** `e2e/broadway.py`, `e2e/recording.py`.

## Can go now

### D2. The comments about a bug of GTK 2

- **Why kept:** none: two lines of PyGTK commented out, `gtk.set_interactive`
  and `gtk.link_button_set_uri_hook`.
- **Where:** `virtualbricks/gui/gui.py`, `Application._run()`, "a bug in gtk2".

## Keeping this list

- A new workaround comes here with its versions: those that need it, the
  first that doesn't, and the distributions that have them.
- When a distribution goes: check its column in [Versions](#versions) again,
  remove the workarounds of its section and raise the floors, then move what
  the next oldest distribution still needs into a section of its own.
- When the move to GTK 4 starts, check W7 to W12 and E1 to E7 again.
