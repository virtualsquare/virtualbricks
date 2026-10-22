---
desc: Start, stop, configure, connect, rename and delete the bricks of a lab.
guide: "index#lab"
seealso:
- kinds
- events
sort: 1
---

# Bricks

The **Bricks** tab has a row for each brick of the project: its icon, grey
while it is stopped; its name; its kind and what matters about it, as
`Wire · sw1 ↔ sw2`{.sys}; its state; a button that starts or stops it; and the
button of its menu.

::: {.terms title="The states"}

**Running**, **Stopped**

:   Its program runs, or not.

**Starting**

:   Its program runs once the bricks it plugs into run, and a virtual machine
    has its disks ready. Meanwhile it counts as running: you can't rename it or
    delete it, nor quit Virtualbricks.

**Not connected**

:   A plug of the brick goes nowhere, as a wire with a free end: it can't start
    until you connect it.

**Not configured**

:   A setting that it needs is missing, as the host of a tunnel client: it
    can't start until you set it.
:::

## Above the list {#row}

**New Brick** adds a brick; see [](kinds). The search field finds a brick by
name or by kind: press [Ctrl+F]{.keyseq}, or start typing in the list. **All**
and **Running** switch between all the bricks and only those that run, which
then show the number of their process. **Start All** starts every brick that
can start, and **Stop All** stops them.

## Starting and stopping {#start}

The button of a row starts the brick, or stops it. Starting a brick starts
first the bricks it plugs into. Stopping a virtual machine asks its system to
shut down. Stopping a brick that is starting calls its start off: its program
doesn't run, and the bricks it plugs into start all the same.

## The settings of a brick {#settings}

Double-click a row, or select it and press [Enter]{.key}: the settings of the
brick show in place of the list, under a line that names it. **OK** applies
them, and is greyed while a setting is wrong, with the first problem beside it.
**Cancel** and [Esc]{.key} go back to the list without a change. While the
brick runs, a bar over its settings says which of them change at once.

![The settings of a
switch](figures/switch-settings.png){alt="The settings of sw1 in place of the list, under a line that names it: Ports, 32, and Hub mode and Fast spanning tree, off; Help, Cancel and OK at the bottom."}

## The menu of a brick {#menu}

The button at the end of the row, the right button of the mouse, the
[Menu]{.key} key and the picture of the **Topology** tab open the same menu:

**Start**, **Stop**

:   As the button of the row.

**Configure…**

:   The settings of the brick; [Enter]{.key} in the list.

**Rename…**, **Delete…**

:   Greyed while the brick runs or starts; [F2]{.key} and [Delete]{.key} in the
    list. Before a brick goes, the dialog says what goes with it: the bricks
    plugged into it are unplugged, the events no longer start or stop it, and
    the private copies of a machine go to the trash.

**Duplicate**

:   A copy of the brick, with its links, named after it with the next free
    number. The network cards of a machine get new MAC addresses.

**Connect To**

:   The bricks that this one can plug into.

**When It Starts**, **When It Stops**

:   An event to run when the brick starts or stops; see [](events).

**Resume**

:   For a virtual machine, start it from the state that **Suspend** saved in
    its first disk.

**Process**

:   For a running brick, what to do with its process: **Open Control Monitor**,
    which opens the console of the brick in a terminal; **Pause** and
    **Continue**; **Suspend** and **Reset** for a virtual machine; **Restart**;
    **Terminate** and **Kill**, when it doesn't stop.
