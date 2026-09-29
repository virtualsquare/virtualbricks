---
title: VIRTUALBRICKS
section: 1
header: Virtualbricks Manual
footer: virtualbricks VERSION
date: DATE
---

# NAME

virtualbricks - labs of QEMU machines and VDE networks, and their console

# SYNOPSIS

**virtualbricks** [*options*]

**virtualbricks --no-gui** [*options*]

# DESCRIPTION

Virtualbricks makes and runs labs of virtual machines, run by QEMU, and of
the VDE switches, cables, taps and tunnels between them. It opens the
project that was open last in its workspace, a folder of projects; see
**virtualbricks-config**(5).

Started from a terminal, it reads the commands of its console there, beside
the windows. With **--no-gui** it runs without them, and the console is the
way in: a lab on a machine without a display.

# OPTIONS

**-v**, **--verbose**
:   Log more; it can be repeated.

**-q**, **--quiet**
:   Log less; it can be repeated.

**-b**, **--debug**
:   Log everything. With it, and with **-vv**, Ctrl+C and the **SIGUSR2**
    signal drop into the **pdb** debugger, unless **--noterm** is given.

**-l** *file*, **--logfile** *file*
:   Write the log messages to *file*; **-** for the standard output.

**--logger** *name*
:   The fully qualified name of a factory of the log observer, instead of
    **--logfile**.

**--noterm**
:   Don't read the console in the terminal.

**--no-gui**
:   Run without the windows: no GTK is loaded, and the console is the way
    in. With **--noterm** too, nothing is read: the lab runs until
    Virtualbricks gets **SIGTERM** or **SIGINT**.

**--run** *file*
:   Run the commands of *file* once the project is open, as **source**
    does, then read the console.

**--workspace** *directory*
:   Use the projects of *directory* for this run, instead of the
    **workspace** setting; it's made if it isn't there.

**--lock** *mode*
:   The single-instance mode: **system**, the default, one Virtualbricks
    on the machine; **user**, one for each user; **none**, no limit. See
    **FILES**.

**--command** [*word*...]
:   Send the command of the words that follow to the Virtualbricks that
    runs, through its control socket, and print its answer; without
    words, the lines of the standard input.

**--socket** *path*
:   Listen on the control socket *path*, instead of *.control* in the
    runtime folder; see **FILES**. Its folder must exist.

**--version**
:   Print the version and exit.

**--help**
:   Print the options and exit.

# THE CONSOLE

## Commands

A command is a noun, a verb, then its arguments: **brick start sw1**. The
nouns are **brick**, **event**, **image**, **setting** and **project**, and a
few words stand alone: **help**, **status**, **source**, **python** and
**quit**. A name is always an argument, never a command, so a brick can be
called **list**.

The words are split as the shell splits them: quotes keep spaces, a
backslash escapes, and **#** starts a comment. A key and its value are
*KEY*=*VALUE*, as many as needed in one command; they are all checked
before any is set, so a command changes all of them or none:

```
brick set vm1 memory=1024 "kernel_command_line=quiet ro"
```

The keys are those of the project file, see **virtualbricks-config**(5),
but for the disks, whose keys are *device*_**image** and
*device*_**private**, as **hda_image**, and the network cards, which have
commands of their own. Options, as **--force**, go anywhere after the verb.

## Answers

A command answers when there is something to say: the name given to a new
brick, the process of a started one, a table. When it can't be done, it
says why in one line, which starts with **Error:**, and changes nothing;
a command that starts several bricks says which started before the one that
failed. **start**, **stop**, **restart** and **suspend** wait until they are
done, or fail.

## Typing

On a terminal the line can be edited, and Tab completes the nouns, the
verbs, the names of the bricks, events, images and projects, the kinds of
brick, the keys, and the values of a key that has a few. The prompt is the
name of the open project.

Up and Down
:   Go through the history, which is kept between runs.

Ctrl+R, Ctrl+S
:   Search the history backwards or forwards as you type. Ctrl+R or
    Ctrl+S again finds the next match, Backspace takes back a
    character, Ctrl+G gives the line back as it was, and any other key
    keeps the line found: Enter runs it.

Ctrl+A, Ctrl+E
:   Go to the start or the end of the line.

Ctrl+B, Ctrl+F
:   Go back or forward a character.

Alt+B, Alt+F, Ctrl+Left, Ctrl+Right
:   Go back or forward a word. Here a word is letters and digits, so
    **memory=512** is two.

Ctrl+D
:   Delete the character under the cursor; on an empty line, quit, as
    **quit** does.

Ctrl+W
:   Delete the word before the cursor, up to a space.

Alt+Backspace, Alt+D
:   Delete the word before or after the cursor, letters and digits.

Ctrl+U, Ctrl+K
:   Delete the line before or after the cursor.

Ctrl+Y
:   Put back what was deleted last; what keys deleted one after the
    other comes back together.

Ctrl+T, Alt+T
:   Swap the character before the cursor with the one under it, or the
    word before it with the word after it; at the end of the line, the
    last two.

Ctrl+C
:   Clear the line; while a command runs, stop waiting for it, but not
    what it does: its answer comes when it's done.

Ctrl+L
:   Clear the screen.

The Alt keys need a terminal that sends Escape before the key, as most do;
xterm does with its **metaSendsEscape** resource. Escape and then the key
works everywhere.

**python** opens a Python shell, where **factory** is the factory of the
bricks and the line has the same keys, but for Tab, which indents; Ctrl+D
on an empty line comes back to the console.

When the input isn't a terminal, as a pipe, each line is a command, run
after the one before, and the end of the input quits.

## Scripts

A file of commands, one a line, runs with **source** *file* in the console
or **--run** *file* at start. Empty lines and comments are skipped, and the
first error stops the file, saying where, as *lab.vb*:7.

# COMMANDS

## Bricks

**brick types**
:   The kinds of brick, and what this computer lacks for each.

**brick list**
:   The bricks, their state and settings.

**brick new** *KIND* [*NAME*]
:   Make a brick; without a name, the kind's and the first free number.
    For example, **brick new switch**.

**brick show** *NAME*
:   A brick's state, links and keys.

**brick keys** *KIND*|*NAME* [*KEY*]
:   The keys of a kind of brick or of a brick, or one, with what each is for.
    For example, **brick keys vm memory**.

**brick set** *NAME* *KEY*=*VALUE*...
:   Change keys of a brick, all or none.
    For example, **brick set sw1 ports=16 hub_mode=true**.

**brick unset** *NAME* *KEY*...
:   Put keys of a brick back to their defaults.
    For example, **brick unset sw1 ports**.

**brick start** *NAME*...
:   Start bricks, after those they plug into, and wait for them.
    For example, **brick start router**.

**brick stop** *NAME*...
:   Stop bricks, and wait until their programs end.

**brick kill** *NAME*...
:   Kill the programs of bricks.

**brick restart** *NAME*...
:   Stop bricks, killing them after two seconds, and start them.

**brick pause** *NAME*...
:   Pause the programs of bricks.

**brick continue** *NAME*...
:   Let paused bricks go on.

**brick suspend** *VM*
:   Save a machine's state in its first disk, and stop it.

**brick resume** *VM*
:   Start a machine from the state that suspend saved.

**brick reset** *VM*
:   Reset a running machine, as its reset button.

**brick monitor** *NAME*
:   Open the control monitor of a running brick in a terminal.

**brick connect** *NAME* *TARGET*...
:   Plug a brick into switches: a wire or a Netemu's ends, left then right.
    For example, **brick connect w1 sw1 sw2**.

**brick disconnect** *NAME* [*END*]
:   Unplug a brick, or one end of a wire or a Netemu.

**brick card add** *VM* *KIND* [*OPTIONS*...]
:   Add a network card: plug and its target, socket, or hostonly; model= and mac= are its own.
    For example, **brick card add vm1 plug sw1 model=virtio-net-pci**.

**brick card set** *VM* *CARD* *KEY*=*VALUE*...
:   Change a card's model, mac, or target: a switch, hostonly, or nothing.
    For example, **brick card set vm1 eth0 model=e1000 target=sw2**.

**brick card remove** *VM* *CARD*...
:   Take network cards out of a machine.

**brick rename** *NAME* *NEW*
:   Rename a brick.

**brick duplicate** *NAME* [*NEW*]
:   Copy a brick, with its links.

**brick delete** *NAME*...
:   Delete bricks that don't run.

## Events

**event list**
:   The events, their state and actions.

**event new** [*NAME*]
:   Make an event; without a name, new_event or the next free one.

**event show** *NAME*
:   An event's delay, its actions numbered, what starts it.

**event set** *NAME* *KEY*=*VALUE*...
:   Change an event's delay or icon.
    For example, **event set boot delay=10**.

**event action add** *NAME* *WHAT* [*SUBJECT*] [**--at** *N*]
:   Add an action: start or stop a brick or an event, or a command of the console or the shell.
    For example, **event action add boot console "brick set vm1 memory=1024"**.

**event action remove** *NAME* *N*...
:   Remove actions of an event, by their numbers.

**event action move** *NAME* *N* *TO*
:   Move an action of an event to another place.

**event start** *NAME*...
:   Start events: each waits its delay, then runs its actions.

**event stop** *NAME*...
:   Stop events that wait.

**event run** *NAME*...
:   Run the actions of events now, and wait for them.

**event rename** *NAME* *NEW*
:   Rename an event, and every brick and action that names it.

**event duplicate** *NAME* [*NEW*]
:   Copy an event.

**event delete** *NAME*...
:   Delete events.

## Images

**image list**
:   The disk images and their users.

**image add** *NAME* *PATH* [*KEY*=*VALUE*...]
:   Add an image file to the project; description= says what it is.
    For example, **image add debian ~/images/debian.qcow2 description="Debian 13"**.

**image show** *NAME*
:   An image's file, description and users.

**image set** *NAME* *KEY*=*VALUE*...
:   Change the description of an image.

**image rename** *NAME* *NEW*
:   Rename an image, in the disks that use it too.

**image delete** *NAME*
:   Remove an image from the project; its file and the private copies stay.

## Settings

**setting show** [*KEY*]
:   The settings of Virtualbricks and of the open project.

**setting set** *KEY*=*VALUE*...
:   Change settings, all or none.
    For example, **setting set terminal=/usr/bin/gnome-terminal**.

**setting unset** *KEY*...
:   Put settings back to their defaults.

## Projects

**project list**
:   The projects of the workspace.

**project show**
:   The open project.

**project open** *NAME*
:   Save the open project and open another.

**project new** *NAME*
:   Save the open project, make a new one and open it.

**project save**
:   Save the open project now.

**project rename** *NAME* *NEW*
:   Rename a project.

**project duplicate** *NAME* *NEW*
:   Copy a project, its disks included.

**project delete** *NAME* [**--force**]
:   Move a project to the trash; without one, --force deletes it for good.

## Other commands

**help** [*TOPIC*...]
:   The commands, a noun's verbs, or one command.
    For example, **help brick set**.

**status**
:   What runs: the bricks with their processes, the events that wait.

**quit**
:   Quit Virtualbricks; refused while bricks run.

**source** *FILE*
:   Run the commands of a file, one a line, up to the first error.
    For example, **source ~/labs/start.vb**.

# EVENTS

An event, started, waits its delay, then runs its actions, all at once:
an action doesn't wait for the one before. An action starts or stops a
brick, with the bricks it plugs into, or an event, or runs a command of the
console or of the shell, as **event action add** makes them. A command of the console in an event is
any command of this page, and one that fails is logged with the event, the
number of the action and the reason. The project file keeps the actions as
**virtualbricks-config**(5) says.

# FILES

*\$XDG_STATE_HOME*/virtualbricks/history
:   The history of the console, the last 500 lines.

*/tmp/virtualbricks.lock*, *\$XDG_RUNTIME_DIR*/virtualbricks/.lock
:   The locks of the single-instance mode, see **--lock**.

The settings, the state and the projects are described in
**virtualbricks-config**(5).

# EXAMPLES

A switch and a machine plugged into it, started:

```
brick new switch
brick new vm router
brick set router memory=512 use_kvm=true
brick card add router plug sw1 model=virtio-net-pci
brick start router
```

The machine, with its switch, for ten minutes, and a line in the
system log:

```
event new up
event action add up start router
event action add up shell "logger the lab is up"
event new down
event set down delay=600
event action add down stop router
event start up down
```

A lab on a server, from a file, without windows or console:

```
virtualbricks --no-gui --noterm --run ~/labs/ospf.vb
```

# SEE ALSO

**virtualbricks-config**(5), **virtualbricks-archive**(7), **qemu**(1),
**vde_switch**(1)
