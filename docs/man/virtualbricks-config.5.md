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
:   Your preferences, which aren't about a project: the workspace, the
    terminal, KSM and the tray icon.

**state.toml**
:   What Virtualbricks remembers between runs: the project that was open
    last in each workspace.

**project.toml**
:   One in each project: its bricks, events and disk images, how they are
    connected, and its settings, such as the folders of QEMU and VDE.

Virtualbricks writes these files itself. They can also be edited by hand, but
never while Virtualbricks is running: it rewrites **settings.toml** when it
quits and the open project's **project.toml** every three minutes, and your
changes would be lost.

The files of Virtualbricks 2.1 and older, *~/.virtualbricks.conf* and the
*.project* file of each project, are converted once by the migration (see
**MIGRATION**). Virtualbricks doesn't read them any more.

# COMMON RULES

## Format version

Every file starts with a **format** key, the version of its layout: **2**
for a project, **1** for the settings and the state. A project of format
**1** is read, and saved in format **2**: the commands of its events become
actions, see **Events**. A file written by a newer Virtualbricks, with a
higher **format**, is not read: its settings are not used and the file is never overwritten, and a
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

- A missing key takes its default value.
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
writes the whole file each time, with its own comments: the comments, key
order and formatting of a hand edit are not kept.

## Comments

Each file starts with a few lines of comments that say what it is, then a
blank line. Above each key, a comment says what the key is for, and ends in
parentheses with its range or its choices and its default. A value at its
default has **# default** beside it; a value without it was set:

```
# Number of ports (1-128; default 32)
ports = 16
# Send every packet to every port, as a hub (default false)
hub_mode = false  # default
```

The mark compares the value with the default when the file is written, so a
value you set to its default is marked too. A key that counts only while
another key has a given value says so last in the parentheses, as
**(0-500; default 1; used when use_vnc is true)**: otherwise the brick does
without it, and the key keeps its value. The keys that belong to the layout
of the file, as **format**, **type** and the connections, have a comment and
never the mark; tables have none. The comments are in English, and at most 79
columns wide.

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
quits. Two that run side by side, in two workspaces, each write all the
settings they have: the last one to write wins.

**workspace** = *path*, default `"~/.virtualbricks"`
:   The directory of the projects, *.virtualbricks* in your home directory
    by default. Write it as an absolute path: **~** is not expanded.
    **virtualbricks --workspace** *directory* uses another directory for
    one run, made if it isn't there, and leaves this setting as it is. Each
    workspace has its images, in its *vimages* directory, and the project
    that opens at start in it (see **STATE**). A Virtualbricks stays in the
    workspace it started in, whose lock it holds: a new value is for the
    next start.

**terminal** = *string*, default `"/usr/bin/xterm"`
:   The terminal that opens the console of a brick.

**kernel_samepage_merging** = *boolean*, default `false`
:   Enable Kernel Samepage Merging at start, so that virtual machines share
    identical memory pages.

**tray_icon** = *boolean*, default `true`
:   Show an icon in the system tray.

**warn_missing_programs** = *boolean*, default `true`
:   Warn at start about the programs that Virtualbricks needs and can't find,
    with the package that has each.

**audio_driver** = *string*, default `"alsa"`
:   The audio driver of QEMU that plays the sound cards of the virtual
    machines, as **"alsa"**, **"pa"** or **"pipewire"**. It's about this
    computer, not about a project. A driver that the installed QEMU doesn't
    have leaves the machines without a sound card, with a warning.

The **settings.toml** of an older version also has the settings of the
projects, described under **Project settings**: they're reported, ignored,
and dropped at the next save. Each project has its own.

# STATE

The file *\$XDG_STATE_HOME*/virtualbricks/state.toml, or
*~/.local/state/virtualbricks/state.toml* when **XDG_STATE_HOME** is not set.
Virtualbricks rewrites it whenever it opens a project; of two that run side
by side, the last one to write it wins.

**workspaces** = *array*, default `[]`
:   The workspaces used, the last used first: a table for each, with the
    keys of **Workspaces**. A workspace that isn't in the list opens its
    **new_project**.

## Workspaces

**path** = *path*
:   The directory of the workspace, as an absolute path. A table without
    it is reported and dropped.

**current_project** = *string*, default `"new_project"`
:   The project that opens at start in this workspace. A missing
    **new_project** is created. Any other project that can't be opened is
    reported, and Virtualbricks creates and opens **new_project_0**, or the
    next free number, instead.

# PROJECTS

A project is a directory of the workspace that contains a **project.toml**.
The name of the directory is the name of the project, so renaming a project
renames its directory. The directory also holds:

*README*
:   The description of the project: plain text, read as Markdown, see
    **README** below.

*vm*_*device*.cow
:   The private copy-on-write disk of a virtual machine, for example
    *router1_hda.cow* (see **disks** under **qemu**).

The file has these top-level keys:

**format** = *integer*
:   The version of the layout, see **COMMON RULES**.

**[settings]**
:   The settings of the project, see **Project settings**.

**[images.***name***]**
:   A disk image that virtual machines can use.

**[events.***name***]**
:   An event: commands to run, after a delay.

**[bricks.***name***]**
:   A brick. Its **type** key says which kind; the other keys depend on it.

## Project settings

The **[settings]** table. While the project is open, these are the settings
in effect, and the settings window changes them for this project only. A new
project starts with a copy of the settings of the project that is open, or
with the defaults when none is. An imported project brings the paths of the
machine it comes from; the import dialog offers to replace them with those of
the open project.

**cow_format** = *choice*, default `"qcow2"`
:   The format of the private copy-on-write disks of the virtual machines:
    **"cow"**, **"qcow"** or **"qcow2"**.

**log_link_loops** = *boolean*, default `false`
:   Log an error when starting a brick finds a loop in the links. The bricks
    on a loop don't start either way.

**allow_female_plugs** = *boolean*, default `false`
:   Allow plugs to connect to the socket cards of virtual machines, not only
    to switches.

**qemu_path** = *path*, default `"/usr/bin"`
:   The directory of the QEMU programs.

**vde_path** = *path*, default `"/usr/bin"`
:   The directory of the VDE programs, such as **vde_switch**(1).

## Images

**path** = *path*, default `""`
:   The image file. A relative path is relative to the project directory. An
    image without a path is dropped; an image whose file is missing is kept,
    and reported. Two images can't use the same file.

**description** = *string*, default `""`
:   A description, which can span several lines.

## Events

**icon** = *path*, default `""`
:   An image file to show instead of the icon of events. Nothing shows it
    yet.

**delay** = *integer*, default `0`
:   Seconds to wait before running the actions.

**actions** = *array*, default `[]`
:   What the event does after its delay, all at once: an action doesn't
    wait for the one before. Each is an inline table whose **kind** says
    what it does. **"start"** and **"stop"** start or stop their
    **target**, the name of a brick, with the bricks it plugs into, or of
    an event. **"console"** runs its **command** in the console, see
    **virtualbricks**(1), and **"shell"** runs it with **sh**(1). A brick
    or an event renamed is renamed in the targets, not in the commands.
    For example:

    ```
    actions = [
        {kind = "start", target = "sw1"},
        {kind = "console", command = "brick set vm1 memory=1024"},
        {kind = "shell", command = "logger lab started"},
    ]
    ```

    A project of format **1** had only **"vb"**, a command of the old
    console, and **"shell"**. Its commands are read as those of the new
    console, as **sw1 on** becomes **{kind = "start", target = "sw1"}** and
    **vm1 config memory=512** becomes **brick set vm1 memory=512**. A command
    the new console lacks stays as it was, and is reported.

## Bricks

Every brick table has a **type**, which is one of **qemu**, **switch**,
**switchwrapper**, **tap**, **capture**, **wire**, **netemu**,
**tunnellisten**, **tunnelconnect** and **router**, and these three keys:

**icon** = *path*, default `""`
:   An image file to show instead of the icon of the type. Only virtual
    machines show it, for now.

**on_start** = *event*, default `""`
:   The event that runs when the brick starts.

**on_stop** = *event*, default `""`
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

## README

The *README* of a project is plain text in UTF-8, which Virtualbricks
reads as Markdown. The Readme tab shows it rendered, and its pencil button
edits the text; the details of the Projects window show it rendered too.
The list of projects shows its first line, and the import window its first
paragraph that isn't a heading. The syntax is a subset of CommonMark, the
part that most editors and forges share:

**\# Title**, **\#\# Title**
:   A heading, with up to six **\#**. A line underlined with **===** or
    **\-\-\-** is a heading too.

*a new line*
:   A line break, so a README written as plain text keeps its lines. An
    empty line starts a new paragraph.

**\*italic\***, **\*\*bold\*\***, **\~\~struck\~\~**
:   Emphasis.

**\`code\`**
:   Code. A line of three backquotes, **\`\`\`**, above and below some
    lines makes a block of code.

**\- item**, **1. item**
:   An item of a list. An item indented under another is in a list inside
    it.

**\> text**
:   A quote.

**\[text\](https://\...)**, **\<https://\...\>**
:   A link. A URL written as it is, starting with **http://** or
    **https://**, is a link too. Only **http**, **https** and **mailto**
    links open, in the browser or the mail client.

**!\[text\](path)**
:   A picture: a file of the folder of the project, *path* relative to
    the folder, as **pictures/map.png**. The Readme tab and the Projects
    window show it, narrower if it's wider than they are. Any other
    picture shows as its text: a URL, an absolute path, a path or a link
    that leads out of the folder, a file larger than 10 MB or than 32
    million pixels, one that isn't a picture; and so do the pictures in
    the list of projects and in the import window. A picture is a PNG, a
    JPEG, a GIF, an SVG or another format that GdkPixbuf reads.

**\-\-\-**
:   A rule, between empty lines.

**\\**
:   A backslash before a mark keeps the mark: **\\\*** is a star.

Anything else shows as it's written: a table, HTML, a line indented by four
spaces.

# BRICK TYPES

## qemu

A QEMU virtual machine. Most keys become an option of the QEMU command line,
given in bold. Before a machine starts, Virtualbricks asks its QEMU program
what it has, and writes each option the way that version takes it. What the
program lacks is left out, and the machine starts with a warning that says so,
as a machine type or a CPU model that it doesn't know, which leaves QEMU's
default in its place.

**qemu_program** = *string*, default `"qemu-system-i386"`
:   The QEMU program, in the **qemu_path** directory, for example
    **"qemu-system-x86_64"**. It can't be empty.

**machine_type** = *string*, default `""`
:   The machine type, as in **-machine type=**. Empty means the default of
    QEMU.

**cpu_model** = *string*, default `""`
:   The CPU model: **-cpu**.

**use_kvm** = *boolean*, default `false`
:   Use KVM when the host supports it: **-accel kvm -accel tcg**.

**cpus** = *integer* 1-64, default `1`
:   The number of CPUs: **-smp**.

**memory** = *integer* 1-99999, default `64`
:   The memory, in MiB: **-m**.

**use_kvm_shadow_memory** = *boolean*, default `false`
:   Set the size of the KVM shadow memory to **kvm_shadow_memory**.

**kvm_shadow_memory** = *integer* 0-99999, default `1`
:   The size of the KVM shadow memory, in MiB: **-accel
    kvm,kvm-shadow-mem=**, which takes it in bytes.

**boot_order** = *string*, default `""`
:   The boot order: **-boot**, for example **"c"** for the first disk or
    **"d"** for the CD-ROM. Empty means the QEMU default.

**forget_disk_changes** = *boolean*, default `false`
:   Write to temporary files instead of the disk images, forgotten when the
    machine stops: **-snapshot**.

**virtio_disks** = *boolean*, default `false`
:   Attach the disks as virtio devices.

**cdrom** = *choice*, default `"none"`
:   The CD-ROM: **"none"**, **"image"** for the file **cdrom_image**, or
    **"device"** for the drive **cdrom_device** of the host: **-cdrom**.

**cdrom_image** = *path*, default `""`
:   An image file for the CD-ROM.

**cdrom_device** = *string*, default `""`
:   A CD-ROM drive of the host, for example **"/dev/cdrom"**.

**headless** = *boolean*, default `false`
:   No display: **-display none**. It leaves out **use_vnc** and
    **sdl_window**.

**standard_vga** = *boolean*, default `false`
:   A standard VGA card: **-vga std**.

**use_vnc** = *boolean*, default `false`
:   Show the display over VNC, on display **vnc_display**.

**vnc_display** = *integer* 0-500, default `1`
:   The VNC display: **-vnc :***N*.

**sdl_window** = *boolean*, default `false`
:   Show the display in an SDL window: **-display sdl**. QEMU has it with the
    package **qemu-system-gui**.

**sound_card** = *string*, default `""`
:   The sound card, as **"ac97"**, **"es1370"** or **"sb16"**: **-audiodev**,
    with the **audio_driver** setting, and **-device**. **"pcspk"** is the
    speaker of the PC: **-machine pcspk-audiodev=**.

**use_usb** = *boolean*, default `false`
:   Enable USB, **-usb**, and pass the devices of **usb_devices** to the
    guest.

**usb_devices** = *array*, default `[]`
:   USB devices of the host, each an inline table with an **id**, the
    vendor and product id as **"046d:c52b"**, and a **description**. Each
    device becomes **-device usb-host,vendorid=0x046d,productid=0xc52b**.

**keyboard_layout** = *string*, default `""`
:   The keyboard layout, a code of two letters such as **"it"**: **-k**.

**clock_local_time** = *boolean*, default `false`
:   Set the clock of the guest to the local time: **-rtc base=localtime**.

**clock_drift_fix** = *boolean*, default `false`
:   Correct the drift of the clock: **-rtc driftfix=slew**.

**serial_socket** = *boolean*, default `false`
:   Connect the serial port to a socket in the runtime directory:
    **-serial unix:**...**_serial**.

**use_kernel** = *boolean*, default `false`
:   Boot the kernel **kernel** directly.

**kernel** = *path*, default `""`
:   A kernel image: **-kernel**.

**use_initrd** = *boolean*, default `false`
:   Use the initial ramdisk **initrd**, with **use_kernel**.

**initrd** = *path*, default `""`
:   An initial ramdisk: **-initrd**.

**kernel_command_line** = *string*, default `""`
:   The kernel command line, with **use_kernel**: **-append**.

**use_gdb** = *boolean*, default `false`
:   Wait for a GDB connection on port **gdb_port**.

**gdb_port** = *integer* 1-65535, default `1234`
:   The port of the GDB server: **-gdb tcp::***port*.

**acpi** = *boolean*, default `true`
:   Give the machine ACPI. False turns it off: **-machine acpi=off**, or
    **-no-acpi** for a machine type without that property.

### Disks

The disks are in the subtables **disks.hda**, **disks.hdb**, **disks.hdc**,
**disks.hdd**, **disks.fda**, **disks.fdb** and **disks.mtdblock**, one for
each device, all of them always written:

**disks.***device***.image** = *image*, default `""`
:   The image of the device, by name.

**disks.***device***.private** = *boolean*, default `false`
:   Write to a private copy-on-write file, *vm*_*device*.cow in the project
    directory, instead of the image, which then stays unchanged. The format
    of the file is the project's **cow_format**.

### Network cards

**nics** is an array of tables, the network cards in the order the guest
sees them. Each card has these keys:

**kind** = *choice*
:   **"plug"** for a card plugged into a socket, **"socket"** for a card
    that other bricks plug into, or **"hostonly"** for a card on QEMU's user
    networking. A plug and a socket card need the **vde** network backend of
    QEMU, which Ubuntu builds its QEMU without: with a QEMU that lacks it, the
    card is there but unplugged, with a warning.

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
    **"virtio-net-pci"**. A model that the installed QEMU doesn't have
    becomes **"rtl8139"**, with a warning.

**mac** = *string*
:   The MAC address, as **"52:54:00:12:34:56"**. A missing or invalid
    address is replaced with a random one.

## switch

A VDE switch, **vde_switch**(1). Plugs connect to it by its name.

**ports** = *integer* 1-128, default `32`
:   The number of ports.

**hub_mode** = *boolean*, default `false`
:   Send every packet to every port, like a hub.

**fast_spanning_tree** = *boolean*, default `false`
:   Enable the fast spanning tree protocol.

## switchwrapper

A VDE switch that Virtualbricks doesn't start, run by another program. Plugs
connect to it by its name.

**socket_path** = *path*, default `""`
:   The control directory of the switch.

## tap

A tap interface of the host, plugged into a switch through
**vde_plug2tap**(1). It needs root, see **PRIVILEGES**. The interface
takes the name of the brick, which Linux limits to 15 characters: New
Brick, Rename and the console's **brick new** and **brick rename** refuse a
longer one.

**connect** = *string*, default `""`
:   The socket the tap is plugged into.

**address_mode** = *choice*, default `"off"`
:   How the interface gets its address: **"off"** for not at all,
    **"dhcp"**, or **"manual"** for **ip_address**, **netmask** and
    **gateway**.

**ip_address** = *address*, default `"10.0.0.1"`
:   The address of the interface.

**netmask** = *address*, default `"255.255.255.0"`
:   The netmask.

**gateway** = *address*, default `""`
:   The default gateway, or empty for none.

## capture

Captures the packets of an interface of the host into a switch, through
**vde_pcapplug**. It needs root, see **PRIVILEGES**.

**connect** = *string*, default `""`
:   The socket the capture is plugged into.

**interface** = *string*, default `""`
:   The interface of the host, for example **"eth0"**.

## wire

Connects two sockets, through **dpipe**(1) and **vde_plug**(1).

**endpoints** = *array*, default `["", ""]`
:   The two sockets, left and right.

## netemu

A wire that emulates a network link: bandwidth, delay, buffer and loss, which
can change over time between the states of a Markov chain. It runs
**vde-netemu**, or the **wirefilter**(1) of VDE, which it's a fork of, where
vde-netemu isn't installed.

**endpoints** = *array*, default `["", ""]`
:   The two sockets, left and right. The values of a state apply from left
    to right, the ones that end in **_right_to_left** from right to left. A
    socket card of a virtual machine can only be the right one.

**transition_period** = *integer* >= 1, default `100`
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
    right when **bandwidth_symmetric** is false.

**bandwidth_right_to_left** = *integer*, default `125000`
:   The bandwidth from right to left.

**bandwidth_symmetric** = *boolean*, default `true`
:   Use **bandwidth** in both directions.

**delay** = *integer*, default `0`
:   The propagation delay, one way, in milliseconds; from left to right when
    **delay_symmetric** is false.

**delay_right_to_left** = *integer*, default `0`
:   The delay from right to left.

**delay_symmetric** = *boolean*, default `true`
:   Use **delay** in both directions.

**buffer_size** = *integer*, default `75000`
:   The size of the channel buffer, in bytes, or 0 for no limit; from left
    to right when **buffer_size_symmetric** is false.

**buffer_size_right_to_left** = *integer*, default `75000`
:   The size of the channel buffer from right to left.

**buffer_size_symmetric** = *boolean*, default `true`
:   Use **buffer_size** in both directions.

**loss** = *number* 0-100, default `0.0`
:   The percentage of packets lost; from left to right when
    **loss_symmetric** is false.

**loss_right_to_left** = *number* 0-100, default `0.0`
:   The percentage of packets lost from right to left.

**loss_symmetric** = *boolean*, default `true`
:   Use **loss** in both directions.

## tunnellisten

The server end of an encrypted tunnel between two machines, through
**vde_cryptcab**(1).

**connect** = *string*, default `""`
:   The socket the tunnel is plugged into.

**listen_port** = *integer* 1-65535, default `7667`
:   The UDP port to listen on.

**password** = *string*, default `""`
:   The password of the tunnel. It's stored in clear text.

## tunnelconnect

The client end of an encrypted tunnel, through **vde_cryptcab**(1).

**connect** = *string*, default `""`
:   The socket the tunnel is plugged into.

**server_host** = *string*, default `""`
:   The host that runs the server end.

**server_port** = *integer* 1-65535, default `7667`
:   The UDP port of the server end.

**local_port** = *integer* 1-65535, default `10771`
:   The local UDP port.

**password** = *string*, default `""`
:   The password of the tunnel. It's stored in clear text.

## router

A router. It has only the two event keys.

# PRIVILEGES

A **tap** and a **capture** open interfaces of the host, and the
**kernel_samepage_merging** setting writes to */sys*: they need root. When
Virtualbricks doesn't run as root, it runs them with **sudo**(8), in one of
two ways:

**sudo -A**
:   When an askpass helper is configured: the program of **SUDO_ASKPASS**,
    or of a **Path askpass** line of */etc/sudo.conf*, as **ssh-askpass**(1).
    sudo runs it to ask for your password in a window, so it needs a
    display.

**sudo -n**
:   Otherwise. sudo never asks for a password: when it would have to, it
    fails at once, and the brick doesn't start. This is the way on a machine
    without a display, with a rule of **sudoers**(5) that lets you run the
    programs of the bricks, from the folder of the **vde_path** setting,
    without a password:

    ```
    alice ALL=(root) NOPASSWD: /usr/bin/vde_plug2tap, \
        /usr/bin/vde_pcapplug
    ```

The **kernel_samepage_merging** setting runs */bin/sh* as root to write its
value, and a rule that lets a shell run as root gives root to anyone who can
use it. Turn KSM on at boot instead, with a **tmpfiles.d**(5) line, and leave
**kernel_samepage_merging** false:

```
w /sys/kernel/mm/ksm/run - - - - 1
```

The settings of older versions have a **sudo** key, the program that did
this: it's reported, ignored, and dropped at the next save.

# MIGRATION

The first time Virtualbricks starts after an upgrade from 2.1 or older, it
converts *~/.virtualbricks.conf* into **settings.toml** and **state.toml**,
and the *.project* file of each project into a **project.toml** next to it,
and shows what it converted in a window. The settings of
*~/.virtualbricks.conf* that are now a project's, as **qemupath**, go into
each converted project. The keys get the names of this page, as **qemupath**
becomes **qemu_path** and **numports** becomes **ports**, and so do the
commands of the events become actions, as **sw1 config numports=16**
becomes **brick set sw1 ports=16**. The old files are left as they were.

The same conversion can be tried on copies, into a new folder laid out like
the XDG directories:

```
python -m virtualbricks.migrate --settings ~/.virtualbricks.conf \
    ~/vb-copy /tmp/vb-test
```

Started with **--workspace**, Virtualbricks converts the projects of
that directory in the same way.

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

*workspace*/.virtualbricks.lock
:   The lock of the workspace: the Virtualbricks that runs there holds it
    alone, in each single-instance mode but **none**, so two never share a
    workspace, even a directory that two users share.

*\$XDG_RUNTIME_DIR*/virtualbricks/*key*/
:   The runtime directory of a workspace, named by a key of eight letters
    and digits made from its path, so that two projects of the same name
    in two workspaces are apart. *.workspace* in it links to the
    workspace.

*\$XDG_RUNTIME_DIR*/virtualbricks/*key*/*project*/
:   The sockets and consoles of the running bricks, removed when you log out.

*/tmp/virtualbricks.lock*
:   The system lock. In the single-instance mode **system**, the default
    without **--workspace**, Virtualbricks holds it alone: one runs on the
    machine, whoever runs it and whatever its workspace. In the modes
    **user** and **workspace** it shares it with the others in those
    modes, so it doesn't start while one holds it alone. The mode is set by
    **virtualbricks --lock** *mode*.

*\$XDG_RUNTIME_DIR*/virtualbricks/.lock
:   The lock of your user, held alone in the single-instance mode **user**:
    one Virtualbricks for each user. In the mode **workspace**, the default
    with **--workspace**, the Virtualbricks of your workspaces share it: one
    for each workspace. The migration of your files holds it alone too. In
    the mode **none** Virtualbricks takes no lock, and the others don't see
    it. The system releases the locks when Virtualbricks ends, even on a
    crash.

*\$XDG_RUNTIME_DIR*/virtualbricks/*key*/.control
:   The control socket of a workspace, where a Virtualbricks started with
    **--listen** answers **virtualbricks --command** in Twisted's AMP;
    *.control.lock* beside it is held by the one that listens. A
    description after **--listen** puts a socket elsewhere, and with
    **protocol=text** it speaks the text protocol; see
    **virtualbricks**(1).

*\$XDG_RUNTIME_DIR*/virtualbricks/.connect-*pid*/
:   The sockets of the terminals of the consoles that the windows of
    another Virtualbricks, **virtualbricks --connect**, process *pid*,
    open; removed when they close. The folders without a dot are those of
    the workspaces.

*\$XDG_CONFIG_HOME*/virtualbricks/token
:   The token of the **tcp** and **ssl** control sockets: a client proves
    that it knows it before its first command. The first Virtualbricks
    started with such a socket makes it, readable by you alone; copy it to
    the machines of the clients. See **virtualbricks**(1).

*/etc/sudo.conf*
:   Its **Path askpass** line makes Virtualbricks run sudo with **-A**, as
    **SUDO_ASKPASS** does; see **PRIVILEGES**.

# ENVIRONMENT

**XDG_CONFIG_HOME**, **XDG_STATE_HOME**
:   Where the settings and the state are, *~/.config* and *~/.local/state*
    when they are not set. Relative paths are ignored, as the XDG Base
    Directory specification says.

**XDG_RUNTIME_DIR**
:   Where the sockets are. When it's not set, they are in a directory
    *virtualbricks-*uid of the temporary directory, readable only by you.

**SUDO_ASKPASS**
:   The askpass helper of **sudo**(8): when it's set, Virtualbricks runs
    sudo with **-A**; see **PRIVILEGES**.

# EXAMPLES

A **settings.toml** as Virtualbricks writes it at its first start, without
its comments:

```
format = 1
workspace = "/home/alice/.virtualbricks"
terminal = "/usr/bin/xterm"
kernel_samepage_merging = false
tray_icon = true
warn_missing_programs = true
audio_driver = "alsa"
```

A **state.toml** after projects were opened in two workspaces, the last
in *~/net101*, without its comments:

```
format = 1
workspaces = [
    {path = "/home/alice/net101", current_project = "ospf"},
    {path = "/srv/labs", current_project = "lab"},
]
```

A **project.toml** with a virtual machine, two switches connected by a
network emulator with two states, a tap and an event, without its comments.
The virtual machine is shortened: Virtualbricks writes all of its keys, and
the six empty disks.

```
format = 2

[settings]
cow_format = "qcow2"
log_link_loops = false
allow_female_plugs = false
qemu_path = "/usr/bin"
vde_path = "/usr/bin"

[images.debian]
path = "/home/alice/.virtualbricks/vimages/debian-12.qcow2"
description = "Debian 12\nbase image"

[events.start_lab]
icon = ""
delay = 5
actions = [
    {kind = "start", target = "router1"},
    {kind = "shell", command = "logger lab started"},
]

[bricks.sw1]
type = "switch"
icon = ""
on_start = "start_lab"
on_stop = ""
ports = 16
hub_mode = false
fast_spanning_tree = true

[bricks.sw2]
type = "switch"
icon = ""
on_start = ""
on_stop = ""
ports = 32
hub_mode = false
fast_spanning_tree = false

[bricks.router1]
type = "qemu"
icon = ""
on_start = ""
on_stop = ""
qemu_program = "qemu-system-x86_64"
machine_type = ""
cpu_model = ""
use_kvm = true
cpus = 2
memory = 1024
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
icon = ""
on_start = ""
on_stop = ""
address_mode = "manual"
ip_address = "10.0.0.1"
netmask = "255.255.255.0"
gateway = ""
connect = "sw2"

[bricks.wan]
type = "netemu"
icon = ""
on_start = ""
on_stop = ""
transition_period = 100
transitions = [[0.0, 0.2], [0.5, 0.0]]
endpoints = ["sw1", "sw2"]

[[bricks.wan.states]]
name = "good"
bandwidth = 125000
bandwidth_right_to_left = 125000
bandwidth_symmetric = true
delay = 10
delay_right_to_left = 0
delay_symmetric = true
buffer_size = 75000
buffer_size_right_to_left = 75000
buffer_size_symmetric = true
loss = 0.0
loss_right_to_left = 0.0
loss_symmetric = true

[[bricks.wan.states]]
name = "congested"
bandwidth = 125000
bandwidth_right_to_left = 125000
bandwidth_symmetric = true
delay = 200
delay_right_to_left = 50
delay_symmetric = false
buffer_size = 75000
buffer_size_right_to_left = 75000
buffer_size_symmetric = true
loss = 2.5
loss_right_to_left = 0.0
loss_symmetric = true
```

# BUGS

The **address_mode**, **ip_address**, **netmask** and **gateway** of a tap
are stored but not applied: the interface gets no address from Virtualbricks.

# SEE ALSO

**virtualbricks**(1), **virtualbricks-archive**(7), **qemu**(1),
**vde_switch**(1), **vde_plug2tap**(1), **vde_cryptcab**(1), **dpipe**(1),
**sudo**(8), **sudoers**(5), **sudo.conf**(5), **tmpfiles.d**(5)

TOML 1.0: <https://toml.io/en/v1.0.0>

XDG Base Directory Specification:
<https://specifications.freedesktop.org/basedir-spec/latest/>
