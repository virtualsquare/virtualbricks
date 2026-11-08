---
desc: The switch, server, ports and password of the end of a tunnel that connects to the other.
guide: "index#kinds"
seealso:
- kinds
- tunnel-servers
sort: 7
---

# Tunnel clients

A tunnel joins a switch of this computer to a switch of another one, over the
network, through an encrypted link. The tunnel client is the end that connects
to a tunnel server on the other computer. Both run `vde_cryptcab`{.cmd}. See
[](tunnel-servers) for the other end.

## Connection {#connection}

**Plugged into**

:   The switch at this end of the tunnel. In **Nothing** the client is **Not
    connected**, and can't start.

## Tunnel {#tunnel}

**Server**

:   The computer that runs the tunnel server: its name, or its address, as
    the network of this computer reaches it. Without one the client is **Not
    configured**, and can't start.

**Server port**

:   The UDP port of the server, its **Port**, from 1 to 65535; 7667 by
    default.

**Local port**

:   The UDP port of this end, from 1 to 65535; 10771 by default. Two tunnel
    clients of this computer that run together need two ports.

**Password**

:   The password of the tunnel, the same as the server's; empty by default.
    The field hides it as you type it, but the project file keeps it as it is,
    in clear text. Older versions of Virtualbricks agree on the key of the
    tunnel, unless the password has quotes, backslashes, a dollar sign or two
    spaces in a row; see [](tunnel-servers#tunnel).

## While it runs {#running}

The settings take effect when the client starts again; **Restart**, under
**Process** in its menu, does it at once.
