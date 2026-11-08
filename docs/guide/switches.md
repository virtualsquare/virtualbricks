---
desc: Its ports, hub mode and fast spanning tree.
guide: "index#kinds"
seealso:
- kinds
- wires
- switch-wrappers
sort: 2
---

# Switches

A switch is a VDE switch, as an Ethernet switch: the other bricks plug into its
ports. A virtual machine plugs a network card into it, a wire joins it to
another switch, a tap joins this computer to it. A switch needs nothing else to
start. It runs `vde_switch`{.cmd}.

![The settings of sw1, with tap1 and vm1 plugged into it](figures/switch-ports.png){alt="The settings of sw1: Ports, 32, with the line Number of ports · at least 3: tap1, vm1 plug into sw1 under it; Hub mode and Fast spanning tree, off."}

## Ports {#ports}

**Ports**

:   How many plugs the switch takes, from 1 to 128; 32 by default. Each plug
    takes a port: a machine with two cards in the switch takes two. The switch
    can't have fewer ports than the plugs in it, and the line under
    **Ports** says how many it needs and which bricks plug into it.

**Hub mode**

:   Send every packet to every port, as a hub does, not only to the port of
    its destination. A program that captures packets on one port, as
    `tcpdump`{.cmd} in a machine, then sees the traffic of all of them. Off by
    default.

**Fast spanning tree**

:   Run the fast spanning tree protocol, which finds the loops between
    switches and turns off the ports that close them, so that a packet doesn't
    go round forever. Turn it on in the switches of a lab whose wires make a
    loop. Off by default.

## While it runs {#running}

The three settings change at once in a switch that runs: Virtualbricks gives
them to `vde_switch`{.cmd} through its console, without stopping it, and the
bar over the settings says so. The bricks plugged into the switch stay
plugged.

In the console of the switch, **Process › Open Control Monitor** in its menu,
`port/print`{.cmd} lists its ports and what is plugged into each; see
[](bricks#process).
