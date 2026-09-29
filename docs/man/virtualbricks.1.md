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

**virtualbricks** [**--socket** [*description*]] **--command** [*word*...]

# DESCRIPTION

Virtualbricks makes and runs labs of virtual machines, run by QEMU, and of
the VDE switches, cables, taps and tunnels between them. It opens the
project that was open last in its workspace, a folder of projects; see
**virtualbricks-config**(5).

Started from a terminal, it reads the commands of its console there, beside
the windows. With **--no-gui** it runs without them, and the console is the
way in: a lab on a machine without a display.

Started with **--socket**, it listens on control sockets, on this machine
or across the network: **virtualbricks --command** sends it a command of
the console from any terminal or script, and prints its answer, and a
program written with Twisted can drive it through AMP. See **THE CONTROL
SOCKET**.

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
    runs, and print its answer; without words, send the lines of the
    standard input. It takes no lock, and no other option but one
    **--socket**, text or AMP. See **THE CONTROL SOCKET**.

**--socket** [*description*]
:   Listen on a control socket: alone, the text socket *.control* in the
    runtime folder; with a *description*, as
    **unix:~/labs/lab1.amp:protocol=amp** or **tcp:8765**, the socket it
    describes. It can be given more than once. The next word is the
    description when it starts with a type and a colon, as **unix:**;
    after **=** it is too. With **--command**, the socket to talk to, as
    **tcp:lab.example:8765**. See **THE CONTROL SOCKET**.

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

# THE CONTROL SOCKET

A Virtualbricks started with **--socket**, with the windows or without,
listens on control sockets once its project is open; without it, on none.
**--socket** alone is the text socket
*\$XDG_RUNTIME_DIR*/virtualbricks/.control. A description, in the syntax
of Twisted's endpoints, names another: its type, **unix**, **tcp** or
**ssl**; the path of a **unix** socket, or **address=***path*; the port of
the others, or **port=***port*; and **protocol=text**, the default, or
**protocol=amp**. **:** separates the parts, and a backslash makes the
next character plain. The option can be given more than once:

```
virtualbricks --no-gui --socket
virtualbricks --no-gui --socket unix:~/labs/lab1.sock
virtualbricks --no-gui --socket \
    --socket unix:~/labs/lab1.amp:protocol=amp
virtualbricks --no-gui --socket tcp:8765
```

**--command** sends a command to a socket, as typed in the console, in
the protocol of its description:

```
virtualbricks --command brick start sw1 vm1
virtualbricks --command brick set vm1 memory=1024
virtualbricks --socket unix:~/labs/lab1.sock --command status
virtualbricks --socket tcp:8765 --command status
virtualbricks --socket unix:~/labs/lab1.amp:protocol=amp \
    --command status
```

The words after **--command** are those of the command, as the shell split
them; they reach the console quoted again, so a value with spaces is quoted
once, as in the console. The options of **virtualbricks** end at the first
word. Without words, the lines of the standard input are the commands, each
sent after the answer to the one before, up to the first error, which names
its line.

The answer goes to the standard output. When a command fails, what it did
first goes there too, and the error, **Error:** and why, to the standard
error; see **EXIT STATUS**. A relative path, as that of **source** *file*,
is read from the folder where **--command** runs. Ctrl+C stops waiting, not
the command. Virtualbricks logs each command it gets, and answers in its
own language. Over AMP, what a command did before it failed doesn't come,
and an answer longer than 65535 bytes is an error; a text socket carries
both.

Only you can connect to a **unix** socket: each is yours alone, and
Virtualbricks doesn't listen in a runtime folder that isn't yours, or that
others can write in. One Virtualbricks has each socket: the first to
start, which holds the lock *path*.lock beside it; with **--lock none**,
another one with the same **--socket** runs without that socket. A socket
left by a crash is removed at the next start; nothing else at the path is.

## Sockets on the network

A **tcp** socket listens on this machine: on **127.0.0.1**, or on another
loopback address of **interface=**, as **'interface=\\:\\:1'**, whose
colons are escaped. Across the network, what passes on **tcp** could be
read, so it is refused there. An **ssl** socket encrypts, and listens on
**127.0.0.1** too, or on the address of **interface=**, as **0.0.0.0** for
every IPv4 address of the machine. It needs the certificate of
Virtualbricks: **privateKey=***file*, its key, and **certKey=***file*, the
certificate, unless the key's file holds it too, both in PEM;
**extraCertChain=***file* holds the certificates between it and the
authority that issued it. A port has no lock: the first Virtualbricks
takes it, and another one runs without that socket.

Whoever reaches a port can connect, and a connection can do all that the
console does, the shell commands of an event's actions included. So each
client proves first that it knows the token of Virtualbricks: the line of
*\$XDG_CONFIG_HOME*/virtualbricks/token, which the first start with such a
socket makes, or of the file of **tokenFile=**. Neither end sends it: each
proves that it knows it, and a client without a proof in 10 seconds is cut
off. The file must be yours, and nobody else may read it; copy it to the
machines of the clients. With **caCertsDir=***directory*, an **ssl**
socket asks each client for a certificate in place of the token: one that
a .pem file of *directory* issued, or is. The files are read at start. The
log names each client, by its address or by its certificate:

```
virtualbricks --no-gui --socket \
    'ssl:8765:interface=0.0.0.0:privateKey=~/vb/lab.pem'
virtualbricks --no-gui --socket \
    'ssl:8765:privateKey=~/vb/lab.pem:caCertsDir=~/vb/clients'
```

**--command** names the machine as **tcp:***host***:***port*, or with
**host=** and **port=**; **tcp:***port* alone is this machine. Over
**ssl**, **caCertsDir=***directory* holds the certificate of Virtualbricks,
or that of its authority; without it, the authorities of the system are
trusted. **privateKey=** and **certKey=** are the certificate of the
client, for a Virtualbricks that asks for one. The token is that of
**tokenFile=**, or the default one. To another machine, **--command**
doesn't send its folder: a relative path is read from the folder of that
Virtualbricks.

```
virtualbricks \
    --socket 'ssl:lab.example:8765:caCertsDir=~/vb/lab' \
    --command status
```

The certificates, made with **openssl**(1): that of the machine of
Virtualbricks, for its name and address, and that of a client, whose .pem
goes into the directory of **caCertsDir=**:

```
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 \
    -nodes -days 3650 -subj /CN=lab.example \
    -addext subjectAltName=DNS:lab.example,IP:192.0.2.7 \
    -keyout lab.key -out lab.pem
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 \
    -nodes -days 3650 -subj /CN=alice-laptop \
    -keyout alice.key -out alice.pem
```

## The text protocol

Any program can talk to a text socket: UTF-8 JSON, an object on each line.
Virtualbricks greets with the **protocol**, 1, its **version**, its
**pid** and the open **project**; then it answers each request in turn.
A request's **cwd**, the folder of its paths, is optional:

```
{"line": "brick start sw1", "cwd": "/home/alice/labs"}
{"ok": true, "lines": ["sw1 runs, process 4242"]}
{"line": "brick start vm9"}
{"ok": false, "lines": [], "error": "No brick named vm9"}
```

On a socket that asks for the token, the first line asks for the proof,
with a **nonce** of 64 hex digits. The client answers with a nonce of its
own and its **proof**: the HMAC-SHA256 under the token of
**virtualbricks client** *nonce* *its-nonce*, in hex. The greeting follows,
with the proof of Virtualbricks, that of **virtualbricks server** *nonce*
*its-nonce*, which the client checks. A wrong proof is refused, and the
connection closed:

```
{"protocol": 1, "auth": "token", "nonce": "3f9a..."}
{"nonce": "c41d...", "proof": "8e02..."}
{"protocol": 1, "version": "2.1.0", "pid": 4200,
 "project": "lab1", "proof": "51b7..."}
```

In a shell, **openssl** computes a proof:

```
printf 'virtualbricks client %s %s' "$nonce" "$mine" |
    openssl dgst -sha256 -hmac "$token"
```

## The AMP protocol

A program written with Twisted drives an AMP socket with two commands.
**Hello** answers the **protocol**, 1, the **version**, the **pid** and
the **project**. **Run** takes a **line** of the console and its **cwd**,
optional, and answers its **lines**. A command that fails raises
**CommandFailed**, with its error; **AnswerTooLong** says that a command
was done, but its answer is longer than the 65535 bytes of an AMP value.
The requests of a connection run in turn. On a socket that asks for the
token, **Hello** and **Run** fail with **TokenNeeded** until the program
proves it: **authenticate**(*vb*, *token*) calls **Challenge**, then
**Authenticate**, and raises **WrongToken** if either end doesn't know the
token. The module **virtualbricks.console.ampwire** has the commands; a
program that can't import it declares them:

```
class CommandFailed(Exception):
    pass

class AnswerTooLong(Exception):
    pass

class TokenNeeded(Exception):
    pass

class WrongToken(Exception):
    pass

class Hello(amp.Command):
    response = [
        (b"protocol", amp.Integer()),
        (b"version", amp.Unicode()),
        (b"pid", amp.Integer()),
        (b"project", amp.Unicode(optional=True)),
    ]
    errors = {TokenNeeded: b"TOKEN_NEEDED"}

class Run(amp.Command):
    arguments = [
        (b"line", amp.Unicode()),
        (b"cwd", amp.Unicode(optional=True)),
    ]
    response = [(b"lines", amp.ListOf(amp.Unicode()))]
    errors = {
        CommandFailed: b"COMMAND_FAILED",
        AnswerTooLong: b"ANSWER_TOO_LONG",
        TokenNeeded: b"TOKEN_NEEDED",
    }

class Challenge(amp.Command):
    response = [(b"nonce", amp.Unicode())]
    errors = {WrongToken: b"WRONG_TOKEN"}

class Authenticate(amp.Command):
    arguments = [
        (b"nonce", amp.Unicode()),
        (b"proof", amp.Unicode()),
    ]
    response = [(b"proof", amp.Unicode())]
    errors = {WrongToken: b"WRONG_TOKEN"}

def proof(token, side, nonce, mine):
    text = f"virtualbricks {side} {nonce} {mine}"
    key = token.encode()
    return hmac.new(key, text.encode(), "sha256").hexdigest()

async def authenticate(vb, token):
    mine = secrets.token_hex(32)
    nonce = (await vb.callRemote(Challenge))["nonce"]
    answer = await vb.callRemote(
        Authenticate,
        nonce=mine,
        proof=proof(token, "client", nonce, mine),
    )
    expected = proof(token, "server", nonce, mine)
    if not hmac.compare_digest(answer["proof"], expected):
        raise WrongToken("The other end doesn't know the token")
```

Then a program, for the AMP socket of the third example above:

```
async def main(reactor):
    path = os.path.expanduser("~/labs/lab1.amp")
    endpoint = endpoints.UNIXClientEndpoint(reactor, path)
    vb = await endpoints.connectProtocol(endpoint, amp.AMP())
    answer = await vb.callRemote(Run, line="brick start sw1")
    print("\n".join(answer["lines"]))

task.react(lambda reactor: ensureDeferred(main(reactor)))
```

Over **tcp**, the endpoint is **tcp:127.0.0.1:***port*, and the program
calls **authenticate**() before the other commands. Over **ssl**, Twisted's
**tls:***host***:***port***:trustRoots=***directory* checks the certificate
of Virtualbricks and its name; **certificate=** and **privateKey=** add
the program's own.

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

# EXIT STATUS

With **--command**:

**0**
:   The command was done.

**1**
:   The command failed, its answer was too long for AMP, or an option is
    wrong.

**2**
:   No Virtualbricks answered: none listens there, it ended before it
    answered, it speaks another protocol, or it refused the token or the
    certificate. The error says which.

**130**
:   Ctrl+C stopped the wait.

# FILES

*\$XDG_STATE_HOME*/virtualbricks/history
:   The history of the console, the last 500 lines.

*/tmp/virtualbricks.lock*, *\$XDG_RUNTIME_DIR*/virtualbricks/.lock
:   The locks of the single-instance mode, see **--lock**.

*\$XDG_RUNTIME_DIR*/virtualbricks/.control, .control.lock
:   The text socket of **--socket** alone and its lock, see **THE CONTROL
    SOCKET**.

*\$XDG_CONFIG_HOME*/virtualbricks/token
:   The token of the **tcp** and **ssl** sockets, see **THE CONTROL
    SOCKET**.

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

A lab on a server, from a file, without windows or console, with the
text socket:

```
virtualbricks --no-gui --noterm --socket --run ~/labs/ospf.vb
```

The machine of that lab, from another terminal, and the commands of a
file, sent to it one after the other:

```
virtualbricks --command brick start router
virtualbricks --command < ~/labs/traffic.vb
```

The same lab, open to the network over **ssl**, and its machine, started
from a laptop that has a copy of the token and of **lab.pem**, in
*~/vb/lab*:

```
virtualbricks --no-gui --noterm --run ~/labs/ospf.vb --socket \
    'ssl:8765:interface=0.0.0.0:privateKey=~/vb/lab.pem'
virtualbricks \
    --socket 'ssl:lab.example:8765:caCertsDir=~/vb/lab' \
    --command brick start router
```

# SEE ALSO

**virtualbricks-config**(5), **virtualbricks-archive**(7), **qemu**(1),
**vde_switch**(1), **openssl**(1)
