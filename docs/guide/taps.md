---
desc: The switch that a network interface of this computer joins, and its address.
guide: "index#kinds"
seealso:
- kinds
- events#tap
- problems#sudo
sort: 8
---

# Taps

A tap is a network interface of this computer, plugged into a switch of the
lab: through it this computer joins the lab, as one more machine on that
switch. The interface takes the name of the brick, as `tap1`{.sys}, so the name
of a tap has 15 characters at most. It runs `vde_plug2tap`{.cmd} as root,
through `sudo`{.cmd}; see [](problems#sudo).

## Connection {#connection}

**Plugged into**

:   The switch that the interface joins. In **Nothing** the tap is **Not
    connected**, and can't start.

## Address {#address}

**Address**

:   How the interface gets its address: **Off**, the default, **DHCP** or
    **Manual**.

**IP address**, **Netmask**, **Gateway**

:   With **Manual**: the address of the interface, 10.0.0.1 by default; its
    netmask, 255.255.255.0 by default; and the default gateway, empty for
    none. They are greyed otherwise.

::: {.note .warning}
Virtualbricks doesn't give the interface its address yet: with **DHCP** or
**Manual**, the settings keep your choice, and the line under **Address** says
so. The interface comes up without an address. An event of the start of the
tap can give it one; see [](events#tap).
:::

## While it runs {#running}

A new switch takes effect when the tap starts again; **Restart**, under
**Process** in its menu, does it at once.
