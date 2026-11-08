---
desc: The control folder of a switch that another program runs.
guide: "index#kinds"
seealso:
- kinds
- switches
sort: 3
---

# Switch wrappers

A switch wrapper is a switch that another program runs: a `vde_switch`{.cmd}
started by hand, by a script or by another project. The bricks of this project
plug into it as into a switch of their own. Virtualbricks doesn't start it or
stop it: the wrapper runs while a switch listens in its folder.

## Switch {#switch}

**Control folder**

:   The control folder of the switch: the folder that `vde_switch`{.cmd} makes
    for its sockets, the one its option `-s` names, with the socket
    `ctl`{.file} in it. Type it, or choose it with the button beside it.
    Without a folder the wrapper is **Not configured**.

For a switch started as

```
vde_switch -d -s /tmp/lab-switch
```

the control folder is `/tmp/lab-switch`{.file}.

The ports of the switch, its hub mode and its spanning tree are the other
program's: the wrapper has no settings of them.

## Its state {#state}

Virtualbricks looks at the folder every second:

**Running**

:   A switch listens in the folder.

**Stopped**

:   The folder isn't there, as when the switch has quit and removed it.

**Error**

:   The folder is there, but no switch listens: it has no socket
    `ctl`{.file}, or the one that a killed switch leaves. The tooltip of the
    state says which, and so does the **Logs** window.

**Start** only looks at the folder, and fails, saying why, when no switch
listens there. **Stop** is refused while a switch listens: the program that
runs it stops it. A brick that plugs into the wrapper starts only while its
switch listens.

## While it runs {#running}

A new control folder takes effect at once: Virtualbricks looks at the new
folder, and the bricks plugged into the wrapper join that switch the next time
they start.
