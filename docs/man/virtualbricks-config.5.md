---
title: VIRTUALBRICKS-CONFIG
section: 5
header: Virtualbricks Manual
footer: virtualbricks VERSION
date: DATE
---

# NAME

virtualbricks-config - settings, state and project files of Virtualbricks

# SYNOPSIS

*\$XDG_CONFIG_HOME*/virtualbricks/settings.toml\
*\$XDG_STATE_HOME*/virtualbricks/state.toml\
*workspace*/*project*/project.toml

# DESCRIPTION

Virtualbricks keeps its configuration in three kinds of file, all written in
TOML 1.0:

**settings.toml**
:   Your preferences: the programs to run, the workspace, and the values that
    new projects start with.

**state.toml**
:   What Virtualbricks remembers between runs: the project that was open.

**project.toml**
:   One in each project: its bricks, events and disk images, how they are
    connected, and the project's own copy of some settings.

Virtualbricks writes these files itself. They can also be edited by hand, but
never while Virtualbricks is running: it rewrites **settings.toml** when it
quits and the open project's **project.toml** every three minutes, and your
changes would be lost.

The files of Virtualbricks 2.1 and older, *~/.virtualbricks.conf* and the
*.project* file of each project, are converted once by the migration (see
**MIGRATION**). Virtualbricks doesn't read them any more.

# COMMON RULES

## Format version

Every file starts with a **format** key, the version of its layout, currently
**1**. A file written by a newer Virtualbricks, with a higher **format**, is
not read: its settings are not used and the file is never overwritten, and a
project in that format doesn't open. A missing or invalid **format** is
reported, and the file is read as the current version.

## Every value is written

Virtualbricks writes every key, including the ones at their default value, so
a file shows the whole configuration. When a default changes in a new version
of Virtualbricks, existing files keep their value.

## Reading is lenient

A file edited by hand doesn't have to be complete or tidy. Each problem is
reported in the messages window and in the log, with the key it's about, and
Virtualbricks carries on:

- A missing key takes its default value. In a project, a missing setting
  takes the value of the application settings.
- A key with a value of the wrong type or out of range takes its default
  value.
- An unknown key is ignored, and dropped at the next save.
- A brick of an unknown type, or with an invalid name, is dropped.
- A connection to a socket that doesn't exist is left unconnected.

A file that isn't valid TOML is not read at all: Virtualbricks uses the
default settings and doesn't overwrite the file, and a project in that state
doesn't open.

## Writing

Virtualbricks writes a new file next to the old one and renames it over the
old one once it's complete, so a crash never leaves a half-written file. It
writes the whole file each time: comments, key order and formatting of a hand
edit are not kept.

## Names

Images, events and bricks are tables keyed by their name. A name starts with
a letter and contains only letters, digits, underscores, hyphens and dots, and
no two of them can share a name, even of different kinds. A name with a dot
must be quoted in TOML, as in **[bricks."vm.1"]**.

## Types

The values have these types:

*boolean*
:   **true** or **false**.

*integer*, *number*
:   A whole number, or any number. Some have a range, given as *min*-*max*.

*string*, *path*
:   A string. A path is the path of a file or a directory; an empty string
    means none.

*event*, *image*
:   The name of an event or of a disk image of the project, or an empty
    string for none.

*address*
:   An IPv4 address, as **"10.0.0.1"**.

*choice*
:   One of the strings listed with the key.

# SETTINGS

The file *\$XDG_CONFIG_HOME*/virtualbricks/settings.toml, or
*~/.config/virtualbricks/settings.toml* when **XDG_CONFIG_HOME** is not set.
Virtualbricks creates it with the default values at its first start, and
rewrites it when the settings window is closed with OK and when Virtualbricks
quits.

## Application settings

**workspace** = *path*, default `"~/.virtualbricks"`
:   The directory of the projects, *.virtualbricks* in your home directory
    by default. Write it as an absolute path: **~** is not expanded.

**term** = *string*, default `"/usr/bin/xterm"`
:   The terminal that opens the console of a brick.

**sudo** = *string*, default `"/usr/bin/gksu"`
:   The program that runs the bricks that need privileges, such as a tap.
    It's given **--** and the command line of the brick. Virtualbricks
    doesn't use it when it runs as root.

**ksm** = *boolean*, default `false`
:   Enable Kernel Samepage Merging at start, so that virtual machines share
    identical memory pages.

**systray** = *boolean*, default `true`
:   Show an icon in the system tray.

**show_missing** = *boolean*, default `true`
:   Warn at start about the programs that Virtualbricks needs and can't find.

## Settings of new projects

These settings also exist in each project, in its **[settings]** table (see
**PROJECTS**). Here they are the values that a new project starts with; while
a project is open, its own values are used instead.

**cowfmt** = *choice*, default `"qcow2"`
:   The format of the private copy-on-write disks of the virtual machines:
    **"cow"**, **"qcow"** or **"qcow2"**.

**erroronloop** = *boolean*, default `false`
:   Log an error when starting a brick finds a loop in the network.

**femaleplugs** = *boolean*, default `false`
:   Allow plugs to connect to the socket cards of virtual machines, not only
    to switches.

**qemupath** = *path*, default `"/usr/bin"`
:   The directory of the QEMU programs.

**vdepath** = *path*, default `"/usr/bin"`
:   The directory of the VDE programs, such as **vde_switch**(1).

# STATE

The file *\$XDG_STATE_HOME*/virtualbricks/state.toml, or
*~/.local/state/virtualbricks/state.toml* when **XDG_STATE_HOME** is not set.
Virtualbricks rewrites it whenever it opens a project.

**current_project** = *string*, default `"new_project"`
:   The project that opens at start. A missing **new_project** is created.
    Any other project that can't be opened is reported, and Virtualbricks
    creates and opens **new_project_0**, or the next free number, instead.

# PROJECTS

A project is a directory of the workspace that contains a **project.toml**.
The name of the directory is the name of the project, so renaming a project
renames its directory. The directory also holds:

*README*
:   The description of the project, in plain text.

*vm*_*device*.cow
:   The private copy-on-write disk of a virtual machine, for example
    *router1_hda.cow* (see **disks** under **qemu**).

The file has these top-level keys:

**format** = *integer*
:   The version of the layout, see **COMMON RULES**.

**[settings]**
:   The project's own values of **cowfmt**, **erroronloop**, **femaleplugs**,
    **qemupath** and **vdepath**, described under **SETTINGS**. A new project
    copies them from the application settings. An imported project brings
    the paths of the machine it comes from; the import dialog offers to
    replace them with the paths of this machine.

**[images.***name***]**
:   A disk image that virtual machines can use.

**[events.***name***]**
:   An event: commands to run, after a delay.

**[bricks.***name***]**
:   A brick. Its **type** key says which kind; the other keys depend on it.

## Images

**path** = *path*, default `""`
:   The image file. A relative path is relative to the project directory. An
    image without a path is dropped; an image whose file is missing is kept,
    and reported. Two images can't use the same file.

**description** = *string*, default `""`
:   A description, which can span several lines.

## Events

**delay** = *integer*, default `0`
:   Seconds to wait before running the actions.

**actions** = *array*, default `[]`
:   The commands to run, in order. Each one is an inline table with two keys:
    **kind**, which is **"vb"** for a command of the Virtualbricks console or
    **"shell"** for a command run by **sh**(1), and **command**, the command
    itself. For example:

    ```
    actions = [
        {kind = "vb", command = "sw1 on"},
        {kind = "shell", command = "logger lab started"},
    ]
    ```

## Bricks

Every brick table has a **type**, which is one of **qemu**, **switch**,
**switchwrapper**, **tap**, **capture**, **wire**, **netemu**,
**tunnellisten**, **tunnelconnect** and **router**, and these two keys:

**pon_vbevent** = *event*, default `""`
:   The event that runs when the brick starts.

**poff_vbevent** = *event*, default `""`
:   The event that runs when the brick stops.

The other keys are described below for each type.

## Connections

A connection goes from a plug of a brick to a socket of another. It's
written in the brick that owns the plug, as a string that names the socket:

*brick*
:   The only socket of a switch or a switch wrapper, for example **"sw1"**.

*vm*:*card*
:   A socket card of a virtual machine, for example **"router1:lan"**.

An empty string leaves the plug unconnected. Depending on its type, a brick
has one plug in **connect**, two in **endpoints**, or network cards in
**nics**.

# BRICK TYPES

## qemu

A QEMU virtual machine. Most keys become an option of the QEMU command line,
given in bold.

**argv0** = *string*, default `"qemu-system-i386"`
:   The QEMU program, in the **qemupath** directory, for example
    **"qemu-system-x86_64"**. Empty means **qemu-system-x86_64**.

**machine** = *string*, default `""`
:   The machine type, as in **-machine type=**.

**cpu** = *string*, default `""`
:   The CPU model: **-cpu**.

**kvm** = *boolean*, default `false`
:   Use KVM when the host supports it: **-machine accel=kvm:tcg**.

**smp** = *integer* 1-64, default `1`
:   The number of CPUs: **-smp**.

**ram** = *integer* 1-99999, default `64`
:   The memory, in MiB: **-m**.

**kvmsm** = *boolean*, default `false`
:   Set the size of the KVM shadow memory to **kvmsmem**.

**kvmsmem** = *integer* 0-99999, default `1`
:   The size of the KVM shadow memory: **-machine kvm_shadow_mem=**.

**boot** = *string*, default `""`
:   The boot order: **-boot**, for example **"c"** for the first disk or
    **"d"** for the CD-ROM. Empty means the QEMU default.

**snapshot** = *boolean*, default `false`
:   Write to temporary files instead of the disk images: **-snapshot**.

**use_virtio** = *boolean*, default `false`
:   Attach the disks as virtio devices.

**cdromen** = *boolean*, default `false`
:   Use the image **cdrom** as the CD-ROM.

**cdrom** = *path*, default `""`
:   An image file for the CD-ROM: **-cdrom**.

**deviceen** = *boolean*, default `false`
:   Use the host device **device** as the CD-ROM, unless **cdromen** is set.

**device** = *string*, default `""`
:   A CD-ROM device of the host, for example **"/dev/cdrom"**.

**novga** = *boolean*, default `false`
:   No display: **-display none**.

**vga** = *boolean*, default `false`
:   A standard VGA card: **-vga std**.

**vnc** = *boolean*, default `false`
:   Show the display over VNC, on display **vncN**.

**vncN** = *integer* 0-500, default `1`
:   The VNC display: **-vnc :***N*.

**sdl** = *boolean*, default `false`
:   Show the display in an SDL window: **-sdl**.

**portrait** = *boolean*, default `false`
:   Rotate the display: **-portrait**.

**soundhw** = *string*, default `""`
:   The sound card: **-soundhw**.

**usbmode** = *boolean*, default `false`
:   Enable USB, **-usb**, and pass the devices of **usbdevlist** to the
    guest.

**usbdevlist** = *array*, default `[]`
:   USB devices of the host, each an inline table with an **id**, the
    vendor and product id as **"046d:c52b"**, and a **description**. Each
    device becomes **-usbdevice host:***id*.

**keyboard** = *string*, default `""`
:   The keyboard layout, a code of two letters such as **"it"**: **-k**.

**rtc** = *boolean*, default `false`
:   Set the clock of the guest to the local time: **-rtc base=localtime**.

**tdf** = *boolean*, default `false`
:   Correct the drift of the clock: **-rtc driftfix=slew**.

**serial** = *boolean*, default `false`
:   Connect the serial port to a socket in the runtime directory:
    **-serial unix:**...**_serial**.

**kernelenbl** = *boolean*, default `false`
:   Boot the kernel **kernel** directly.

**kernel** = *path*, default `""`
:   A kernel image: **-kernel**.

**initrdenbl** = *boolean*, default `false`
:   Use the initial ramdisk **initrd**.

**initrd** = *path*, default `""`
:   An initial ramdisk: **-initrd**.

**kopt** = *string*, default `""`
:   The kernel command line, with **kernelenbl**: **-append**.

**gdb** = *boolean*, default `false`
:   Wait for a GDB connection on port **gdbport**.

**gdbport** = *integer* 1-65535, default `1234`
:   The port of the GDB server: **-gdb tcp::***port*.

**noacpi** = *string*, default `""`
:   **"\*"** disables ACPI: **-no-acpi**.

**loadvm** = *string*, default `""`
:   A saved state to resume the machine from: **-loadvm**. Virtualbricks sets
    it while it resumes a machine; leave it empty.

**icon** = *path*, default `""`
:   An image file that shows the machine in the main window.

**stdout** = *string*, default `""`
:   Not used.

### Disks

The disks are in the subtables **disks.hda**, **disks.hdb**, **disks.hdc**,
**disks.hdd**, **disks.fda**, **disks.fdb** and **disks.mtdblock**, one for
each device, all of them always written:

**disks.***device***.image** = *image*, default `""`
:   The image of the device, by name.

**disks.***device***.private** = *boolean*, default `false`
:   Write to a private copy-on-write file, *vm*_*device*.cow in the project
    directory, instead of the image, which then stays unchanged. The format
    of the file is the project's **cowfmt**.

### Network cards

**nics** is an array of tables, the network cards in the order the guest
sees them. Each card has these keys:

**kind** = *choice*
:   **"plug"** for a card plugged into a socket, **"socket"** for a card
    that other bricks plug into, or **"hostonly"** for a card on QEMU's user
    networking.

**connect** = *string*
:   With **"plug"**, the socket the card is plugged into; see
    **Connections**.

**name** = *string*
:   With **"socket"**, the name of the socket card, made of letters, digits,
    underscores, hyphens and dots. Other bricks connect to it as
    *vm*:*name*. When it's missing, the card is named **sock_eth***N* after
    its position.

**model** = *string*, default `"rtl8139"`
:   The model of the card, for example **"e1000"** or
    **"virtio-net-pci"**.

**mac** = *string*
:   The MAC address, as **"52:54:00:12:34:56"**. A missing or invalid
    address is replaced with a random one.

## switch

A VDE switch, **vde_switch**(1). Plugs connect to it by its name.

**numports** = *integer* 1-128, default `32`
:   The number of ports.

**hub** = *boolean*, default `false`
:   Send every packet to every port, like a hub.

**fstp** = *boolean*, default `false`
:   Enable the fast spanning tree protocol.

## switchwrapper

A VDE switch that Virtualbricks doesn't start, run by another program. Plugs
connect to it by its name.

**path** = *path*, default `""`
:   The control directory of the switch.

## tap

A tap interface of the host, plugged into a switch through
**vde_plug2tap**(1). It needs privileges, see **sudo**.

**connect** = *string*, default `""`
:   The socket the tap is plugged into.

**mode** = *choice*, default `"off"`
:   How the interface gets its address: **"off"** for not at all,
    **"dhcp"**, or **"manual"** for **ip**, **nm** and **gw**.

**ip** = *address*, default `"10.0.0.1"`
:   The address of the interface.

**nm** = *address*, default `"255.255.255.0"`
:   The netmask.

**gw** = *address*, default `""`
:   The default gateway, or empty for none.

## capture

Captures the packets of an interface of the host into a switch, through
**vde_pcapplug**. It needs privileges, see **sudo**.

**connect** = *string*, default `""`
:   The socket the capture is plugged into.

**iface** = *string*, default `""`
:   The interface of the host, for example **"eth0"**.

## wire

Connects two sockets, through **dpipe**(1) and **vde_plug**(1).

**endpoints** = *array*, default `["", ""]`
:   The two sockets, left and right.

## netemu

A wire that emulates a network link: bandwidth, delay, buffer and loss, which
can change over time between the states of a Markov chain.

**endpoints** = *array*, default `["", ""]`
:   The two sockets, left and right. LR values apply from left to right, RL
    values from right to left.

**transperiod** = *integer* >= 1, default `100`
:   How often the emulator may change state, in milliseconds.

**transitions** = *array*, default `[[0.0]]`
:   The transition matrix: the number in row *i* and column *j* is the
    probability of going from state *i* to state *j* at each period. It has a
    row and a column for each state.

**states** is an array of tables, at least one, and the first one is the state
the emulator starts in. Each state has these keys:

**name** = *string*, default `"default name"`
:   The name of the state.

**bandwidth** = *integer*, default `125000`
:   The bandwidth, in bytes per second, or 0 for no limit; from left to
    right when **bandwidthsymm** is false.

**bandwidthr** = *integer*, default `125000`
:   The bandwidth from right to left.

**bandwidthsymm** = *boolean*, default `true`
:   Use **bandwidth** in both directions.

**delay** = *integer*, default `0`
:   The propagation delay, one way, in milliseconds; from left to right when
    **delaysymm** is false.

**delayr** = *integer*, default `0`
:   The delay from right to left.

**delaysymm** = *boolean*, default `true`
:   Use **delay** in both directions.

**chanbufsize** = *integer*, default `75000`
:   The size of the channel buffer, in bytes, or 0 for no limit; from left
    to right when **chanbufsizesymm** is false.

**chanbufsizer** = *integer*, default `75000`
:   The size of the channel buffer from right to left.

**chanbufsizesymm** = *boolean*, default `true`
:   Use **chanbufsize** in both directions.

**loss** = *number* 0-100, default `0.0`
:   The percentage of packets lost; from left to right when **losssymm** is
    false.

**lossr** = *number* 0-100, default `0.0`
:   The percentage of packets lost from right to left.

**losssymm** = *boolean*, default `true`
:   Use **loss** in both directions.

## tunnellisten

The server end of an encrypted tunnel between two machines, through
**vde_cryptcab**(1).

**connect** = *string*, default `""`
:   The socket the tunnel is plugged into.

**port** = *integer* 1-65535, default `7667`
:   The UDP port to listen on.

**password** = *string*, default `""`
:   The password of the tunnel. It's stored in clear text.

## tunnelconnect

The client end of an encrypted tunnel, through **vde_cryptcab**(1).

**connect** = *string*, default `""`
:   The socket the tunnel is plugged into.

**host** = *string*, default `""`
:   The host that runs the server end.

**port** = *integer* 1-65535, default `7667`
:   The UDP port of the server end.

**localport** = *integer* 1-65535, default `10771`
:   The local UDP port.

**password** = *string*, default `""`
:   The password of the tunnel. It's stored in clear text.

## router

A router. It has only the two event keys.

# MIGRATION

The first time Virtualbricks starts after an upgrade from 2.1 or older, it
converts *~/.virtualbricks.conf* into **settings.toml** and **state.toml**,
and the *.project* file of each project into a **project.toml** next to it,
and shows what it converted in a window. The old files are left as they
were.

The same conversion can be tried on copies, into a new folder laid out like
the XDG directories:

```
python -m virtualbricks.migrate --settings ~/.virtualbricks.conf \
    ~/vb-copy /tmp/vb-test
```

**virtualbricks-migrate** opens the same conversion in a window, and
**python -m virtualbricks.migrate --help** lists every option. An archive of
an old project is converted when it's imported.

# FILES

*\$XDG_CONFIG_HOME*/virtualbricks/settings.toml
:   The settings.

*\$XDG_STATE_HOME*/virtualbricks/state.toml
:   The state.

*\$XDG_STATE_HOME*/virtualbricks/migration-report.txt
:   The report of the last migration.

*workspace*/*project*/project.toml
:   A project.

*workspace*/vimages/
:   The images saved when a project is imported.

*\$XDG_RUNTIME_DIR*/virtualbricks/*project*/
:   The sockets and consoles of the running bricks, removed when you log out.

*/tmp/vb.lock*
:   The lock that lets only one Virtualbricks run on the machine.

# ENVIRONMENT

**XDG_CONFIG_HOME**, **XDG_STATE_HOME**
:   Where the settings and the state are, *~/.config* and *~/.local/state*
    when they are not set. Relative paths are ignored, as the XDG Base
    Directory specification says.

**XDG_RUNTIME_DIR**
:   Where the sockets are. When it's not set, they are in a directory
    *virtualbricks-*uid of the temporary directory, readable only by you.

# EXAMPLES

A **settings.toml** as Virtualbricks writes it at its first start:

```
format = 1
cowfmt = "qcow2"
erroronloop = false
femaleplugs = false
qemupath = "/usr/bin"
vdepath = "/usr/bin"
workspace = "/home/alice/.virtualbricks"
term = "/usr/bin/xterm"
sudo = "/usr/bin/gksu"
ksm = false
systray = true
show_missing = true
```

A **project.toml** with a virtual machine, two switches connected by a
network emulator with two states, a tap and an event. The virtual machine is
shortened: Virtualbricks writes all of its keys, and the six empty disks.

```
format = 1

[settings]
cowfmt = "qcow2"
erroronloop = false
femaleplugs = false
qemupath = "/usr/bin"
vdepath = "/usr/bin"

[images.debian]
path = "/home/alice/.virtualbricks/vimages/debian-12.qcow2"
description = "Debian 12\nbase image"

[events.start_lab]
actions = [
    {kind = "vb", command = "sw1 on"},
    {kind = "shell", command = "logger lab started"},
]
delay = 5

[bricks.sw1]
type = "switch"
pon_vbevent = "start_lab"
poff_vbevent = ""
numports = 16
hub = false
fstp = true

[bricks.sw2]
type = "switch"
pon_vbevent = ""
poff_vbevent = ""
numports = 32
hub = false
fstp = false

[bricks.router1]
type = "qemu"
pon_vbevent = ""
poff_vbevent = ""
argv0 = "qemu-system-x86_64"
kvm = true
smp = 2
ram = 1024
# ... and the other keys of a qemu brick

[bricks.router1.disks.hda]
image = "debian"
private = true

# ... and hdb to mtdblock, with image = "" and private = false

[[bricks.router1.nics]]
kind = "plug"
connect = "sw1"
model = "e1000"
mac = "52:54:00:12:34:01"

[[bricks.router1.nics]]
kind = "hostonly"
model = "virtio-net-pci"
mac = "52:54:00:12:34:02"

[[bricks.router1.nics]]
kind = "socket"
name = "lan"
model = "e1000"
mac = "52:54:00:12:34:03"

[bricks.tap0]
type = "tap"
pon_vbevent = ""
poff_vbevent = ""
ip = "10.0.0.1"
nm = "255.255.255.0"
gw = ""
mode = "manual"
connect = "sw2"

[bricks.wan]
type = "netemu"
pon_vbevent = ""
poff_vbevent = ""
transperiod = 100
transitions = [[0.0, 0.2], [0.5, 0.0]]
endpoints = ["sw1", "sw2"]

[[bricks.wan.states]]
name = "good"
bandwidth = 125000
bandwidthr = 125000
bandwidthsymm = true
delay = 10
delayr = 0
delaysymm = true
chanbufsize = 75000
chanbufsizer = 75000
chanbufsizesymm = true
loss = 0.0
lossr = 0.0
losssymm = true

[[bricks.wan.states]]
name = "congested"
bandwidth = 125000
bandwidthr = 125000
bandwidthsymm = true
delay = 200
delayr = 50
delaysymm = false
chanbufsize = 75000
chanbufsizer = 75000
chanbufsizesymm = true
loss = 2.5
lossr = 0.0
losssymm = true
```

# BUGS

The **mode**, **ip**, **nm** and **gw** of a tap are stored but not applied:
the interface gets no address from Virtualbricks.

# SEE ALSO

**qemu**(1), **vde_switch**(1), **vde_plug2tap**(1), **vde_cryptcab**(1),
**dpipe**(1)

TOML 1.0: <https://toml.io/en/v1.0.0>

XDG Base Directory Specification:
<https://specifications.freedesktop.org/basedir-spec/latest/>
