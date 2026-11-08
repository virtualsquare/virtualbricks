---
desc: The two switches a wire joins.
guide: "index#kinds"
seealso:
- kinds
- netemu
- topology#connect
sort: 4
---

# Wires

A wire is a cable between two switches: what one of them sends to the other,
the wire passes on, both ways. It runs `dpipe`{.cmd}, which joins two
`vde_plug`{.cmd}, one in each switch.

## Ends {#ends}

**Left end**, **Right end**

:   The switches at the two ends of the wire. Each list has **Nothing**, then
    the switches and the switch wrappers of the project, by their name. With
    **Plugs into machines**, in the settings of the project, it has the socket
    cards of the virtual machines too, by the name of their socket: see
    [](machines#network) and [](settings#project).

An end in **Nothing** keeps the wire from starting: it is **Not connected**,
and the end says so under it, in the colour of warnings. **Connect To**, in the
menu of the wire, and the picture of the **Topology** tab connect its ends too;
see [](bricks#menu) and [](topology#connect).

## While it runs {#running}

New ends take effect when the wire starts again. **Restart**, under
**Process** in its menu, does it at once; see [](bricks#process).

Stopping the wire cuts the link between its switches, and starting it again
mends it: [](events#flap) does it over and over.
