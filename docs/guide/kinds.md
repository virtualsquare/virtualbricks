---
desc: What each brick is for, and the program that runs it.
guide: "index#start"
seealso:
- programs
- bricks
sort: 2
---

# The kinds of brick

**New Brick**, in the **Bricks** tab, lists the kinds of brick in three groups.
A new brick is named after its kind and the first free number, as `sw1`{.sys}
or `tap1`{.sys}, and its settings show at once.

![New
Brick](figures/new-brick.png){alt="New Brick open over the Bricks tab: the kinds of brick in three groups, Machines and switches, Links and This computer, each with a line that says what it is; the row Router says that vde_router isn't installed."}

When this computer lacks the program of a kind, its row says so after a warning
sign. You can still make the brick: it starts once the program is installed.
See [](programs).

## Machines and switches {#machines}

**Virtual machine**

:   A computer that QEMU runs, with its disks, its memory, and a network card
    for each switch it plugs into. See [](machines).

**Switch**

:   A VDE switch: the other bricks plug into its ports, as into an Ethernet
    switch. It can start as it is. It runs `vde_switch`{.cmd}.

**Switch wrapper**

:   A switch that another program runs. The bricks of this project plug into
    its socket, whose path its settings give. You don't start or stop it: it
    runs while that socket is there.

**Router**

:   A VDE router between switches. It has no settings yet: its console
    configures it. It runs `vde_router`{.cmd}.

## Links {#links}

**Wire**

:   A cable between two switches, which its settings choose. It runs
    `dpipe`{.cmd} and `vde_plug`{.cmd}.

**Netemu**

:   A cable between two switches that emulates a network link: its bandwidth,
    delay, loss and more, in states that change over time. It runs
    `vde-netemu`{.cmd}.

**Tunnel server**

:   One end of an encrypted tunnel: it joins a switch here to a tunnel client
    on another computer, which connects to it. It runs `vde_cryptcab`{.cmd}.

**Tunnel client**

:   The other end of an encrypted tunnel: it joins a switch here to a tunnel
    server on another computer, whose address its settings give. It runs
    `vde_cryptcab`{.cmd}.

## This computer {#host}

**Tap**

:   A network interface of this computer, plugged into a switch: this computer
    joins the lab through it. It runs `vde_plug2tap`{.cmd} as root, through
    `sudo`{.cmd}.

**Capture interface**

:   An interface of this computer, whose packets go to a switch. It runs
    `vde_pcapplug`{.cmd} as root, through `sudo`{.cmd}.

For what `sudo`{.cmd} needs, see [](problems#sudo).
