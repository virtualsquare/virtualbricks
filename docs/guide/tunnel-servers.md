---
desc: The switch, port and password of the end of a tunnel that waits for the other.
guide: "index#kinds"
seealso:
- kinds
- tunnel-clients
sort: 6
---

# Tunnel servers

A tunnel joins a switch of this computer to a switch of another one, over the
network, through an encrypted link. It has two ends: a tunnel server, which
waits on a UDP port, and a tunnel client, on the other computer, which
connects to that port. Both run `vde_cryptcab`{.cmd}. See [](tunnel-clients)
for the other end.

## Connection {#connection}

**Plugged into**

:   The switch at this end of the tunnel. In **Nothing** the server is **Not
    connected**, and can't start.

## Tunnel {#tunnel}

**Port**

:   The UDP port where the server waits for the client, from 1 to 65535; 7667
    by default. It is the **Server port** of the client, and a firewall between
    the two computers must let UDP through to it.

**Password**

:   The password of the tunnel, which the client must have too; empty by
    default. The field hides it as you type it, but the project file keeps it
    as it is, in clear text. The key of the tunnel is made from it: choose one,
    since an empty password is a key that anyone can guess.

::: note
Virtualbricks makes the key as its older versions did, so that a tunnel works
with an end that runs one of them. A password with quotes, backslashes, a
dollar sign or two spaces in a row is the exception: then both ends need this
version.
:::

## While it runs {#running}

The settings take effect when the server starts again; **Restart**, under
**Process** in its menu, does it at once.
