---
desc: The switch and the interface of this computer that a capture interface joins.
guide: "index#kinds"
seealso:
- kinds
- taps
- problems#sudo
sort: 9
---

# Capture interfaces

A capture interface joins a switch of the lab to a network interface that this
computer has already, as its Ethernet card: the packets of that interface go
into the switch, and those of the switch go out of the interface. It runs
`vde_pcapplug`{.cmd} as root, through `sudo`{.cmd}; see [](problems#sudo).

## Connection {#connection}

**Plugged into**

:   The switch that gets the packets. In **Nothing** the capture interface is
    **Not connected**, and can't start.

## Capture {#capture}

**Interface**

:   The interface of this computer, as `eth0`{.sys}; **None** by default. The
    menu lists the interfaces of this computer when the settings open, but the
    loopback, `lo`{.sys}. Without one the capture interface is **Not
    configured**, and can't start. An interface that this computer doesn't
    have, as in a project made on another computer, shows as
    `eth1, not on this host`, with a warning: choose one of this computer.

## While it runs {#running}

The settings take effect when the capture interface starts again;
**Restart**, under **Process** in its menu, does it at once.
