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

**virtualbricks --connect** *description* [*options*]

**virtualbricks** [**--connect** [*description*]] [**--workspace**
*directory*] **--command** [*word*...]

**virtualbricks --connect** [*description*] [**--workspace** *directory*]
**--run** *file*

# DESCRIPTION

Virtualbricks makes and runs labs of virtual machines, run by QEMU, and of
the VDE switches, cables, taps and tunnels between them. It opens the
project that was open last in its workspace, a folder of projects; see
**virtualbricks-config**(5). Started with **--workspace**, one runs in each
workspace, side by side.

Started from a terminal, it reads the commands of its console there, beside
the windows. With **--no-gui** it runs without them, and the console is the
way in: a lab on a machine without a display.

Started with **--listen**, it listens on control sockets, on this machine
or across the network: **virtualbricks --command** sends it a command of
the console from any terminal or script, and prints its answer,
**virtualbricks --connect --run** sends it the commands of a file, and a
program written with Twisted can drive it through AMP. See **THE CONTROL
SOCKET**.

Started with **--connect** and the description of a socket alone,
it opens the windows of the Virtualbricks that listens there, on this
machine or another: the bricks run there, the windows here. See **THE
WINDOWS OF ANOTHER VIRTUALBRICKS**.

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
    does, then read the console. With **--connect**, send them to the
    Virtualbricks that runs instead, up to the first error, and exit. See
    **THE CONTROL SOCKET**.

**--workspace** *directory*
:   Use the projects of *directory* for this run, instead of the
    **workspace** setting; it's made if it isn't there. Without **--lock**,
    the single-instance mode is then **workspace**. With **--command** or
    **--connect --run**, the Virtualbricks that runs in *directory*.

**--lock** *mode*
:   The single-instance mode: **system**, one Virtualbricks on the
    machine, the default without **--workspace**; **user**, one for each
    user; **workspace**, one for each workspace, the default with
    **--workspace**; **none**, no limit. Each mode but **none** holds the
    lock of its workspace too, so two never share one. See **FILES**.

**--command** [*word*...]
:   Send the command of the words that follow to the Virtualbricks that
    runs, and print its answer; without words, send the lines of the
    standard input. It takes no lock, and no other option but
    **--connect** or **--workspace**. See **THE CONTROL SOCKET**.

**--listen** [*description*]
:   Listen on a control socket: alone, the socket *.control* in the
    runtime folder of the workspace; with a *description*, as
    **unix:~/labs/lab1.sock** or **tcp:8765**, the socket it describes.
    It speaks AMP, or the text protocol with **protocol=text**. It can be
    given more than once. The next word is the description when it starts
    with a type and a colon, as **unix:**; after **=** it is too. See
    **THE CONTROL SOCKET**.

**--connect** [*description*]
:   The Virtualbricks that runs that **--command** and **--run** talk
    to: alone, the one of the socket *.control* of its workspace, that of
    **--workspace** or the only one that listens; with a *description*,
    the one of the socket it describes, as **unix:~/labs/lab1.sock** or
    **tcp:lab.example:8765**. It speaks AMP, or the text protocol with
    **protocol=text**. The next word is its description as for
    **--listen**. With **--command** or **--run**, it takes no
    **--listen**, no other option of a start, and no **--workspace** with
    a description. See **THE CONTROL SOCKET**.

    Without them, it opens the windows of the Virtualbricks of the socket
    of *description*, which speak AMP, so it takes no **protocol=text**;
    nor **--no-gui**, **--lock**, **--workspace** or **--listen**, which
    are for the Virtualbricks that runs the bricks. See **THE WINDOWS OF
    ANOTHER VIRTUALBRICKS**.

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

A Virtualbricks started with **--listen**, with the windows or without,
listens on control sockets once its project is open; without it, on none.
**--listen** alone is the socket of the workspace,
*\$XDG_RUNTIME_DIR*/virtualbricks/*key*/.control, where *key* is named
after the path of the workspace, and *.workspace* beside it links to the
workspace. A description, in the syntax
of Twisted's endpoints, names another: its type, **unix**, **tcp** or
**ssl**; the path of a **unix** socket, or **address=***path*; the port of
the others, or **port=***port*; and **protocol=amp**, the default, or
**protocol=text**. **:** separates the parts, and a backslash makes the
next character plain. The option can be given more than once:

```
virtualbricks --no-gui --listen
virtualbricks --no-gui --listen unix:~/labs/lab1.sock
virtualbricks --no-gui --listen \
    --listen unix:~/labs/lab1.text:protocol=text
virtualbricks --no-gui --listen tcp:8765
```

**--command** sends a command, as typed in the console, to the socket of
**--connect**, in the protocol of its description. Without it, it sends
it to the socket *.control* of the workspace of **--workspace**, or else
of the only Virtualbricks of yours that listens on one; when several do,
it names them and sends nothing:

```
virtualbricks --command brick start sw1 vm1
virtualbricks --command brick set vm1 memory=1024
virtualbricks --workspace ~/labs/bgp --command status
virtualbricks --connect unix:~/labs/lab1.sock --command status
virtualbricks --connect tcp:8765 --command status
virtualbricks --connect unix:~/labs/lab1.text:protocol=text \
    --command status
```

The words after **--command** are those of the command, as the shell split
them; they reach the console quoted again, so a value with spaces is quoted
once, as in the console. The options of **virtualbricks** end at the first
word. Without words, the lines of the standard input are the commands, each
sent after the answer to the one before, up to the first error, which names
its line.

**--connect --run** *file* sends the lines of *file* in the same way, and
the first error names the file and its line, as *lab.vb*:7, as **source**
says it. Empty lines aren't sent; comments are, and do nothing.

```
virtualbricks --connect --run ~/labs/traffic.vb
virtualbricks --connect tcp:lab.example:8765 --run traffic.vb
```

The answer goes to the standard output. When a command fails, the
error, **Error:** and why, goes to the standard error; see **EXIT
STATUS**. A relative path, as that of **source** *file*, is read from the
folder where **virtualbricks** runs. Ctrl+C stops waiting, not the
command. Virtualbricks logs each command it gets, and answers in its own
language. Over AMP, what a command did before it failed doesn't come, and
an answer longer than 65535 bytes is an error; a text socket carries
both, and what a command did first goes to the standard output before
its error.

Only you can connect to a **unix** socket: each is yours alone, and
Virtualbricks doesn't listen in a runtime folder that isn't yours, or that
others can write in. One Virtualbricks has each socket: the first to
start, which holds the lock *path*.lock beside it; with **--lock none**,
another one with the same **--listen** runs without that socket. Each
workspace has its own socket *.control*, so two Virtualbricks side by side
both listen with **--listen** alone. A socket
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
virtualbricks --no-gui --listen \
    'ssl:8765:interface=0.0.0.0:privateKey=~/vb/lab.pem'
virtualbricks --no-gui --listen \
    'ssl:8765:privateKey=~/vb/lab.pem:caCertsDir=~/vb/clients'
```

**--connect** names the machine as **tcp:***host***:***port*, or with
**host=** and **port=**; **tcp:***port* alone is this machine. Over
**ssl**, **caCertsDir=***directory* holds the certificate of Virtualbricks,
or that of its authority; without it, the authorities of the system are
trusted. **privateKey=** and **certKey=** are the certificate of the
client, for a Virtualbricks that asks for one. The token is that of
**tokenFile=**, or the default one. To another machine, **virtualbricks**
doesn't send its folder: a relative path is read from the folder of that
Virtualbricks.

```
virtualbricks \
    --connect 'ssl:lab.example:8765:caCertsDir=~/vb/lab' \
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

Any program can talk to a text socket, one of **protocol=text**: UTF-8
JSON, an object on each line.
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

A program written with Twisted drives an AMP socket, as one is without
**protocol=text**, with the commands of protocol 1, and with the typed
commands of protocol 2 too. **Hello** agrees on the protocol of the
connection: it takes **protocols**, those the program speaks, optional,
and answers in **protocol** the highest that Virtualbricks speaks too, 1
without them; and the **version**, the **pid** and the **project**.
**Run** takes a **line** of the console and its **cwd**, optional, and
answers its **lines**. A command that fails raises
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
    arguments = [
        (
            b"protocols",
            amp.ListOf(amp.Integer(), optional=True),
        ),
    ]
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

Then a program, for the socket of the second example above:

```
async def main(reactor):
    path = os.path.expanduser("~/labs/lab1.sock")
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

## The typed commands

Protocol 2 adds a typed AMP command for each command of the console, in
the module **virtualbricks.console.ampcommands**, which loads nothing else
of Virtualbricks but **ampwire**; a program imports it, or copies it. A
connection speaks them once **Hello** has agreed on 2; before, they fail
with **ProtocolNeeded**. The name of a command is its words, each with a
capital: **brick card add** is **BrickCardAdd**, **status** is **Status**.
Its arguments are named after those of **COMMANDS**, in lower case, with
**_** for what isn't a letter or a digit: **NAME** is **name**,
**KEY=VALUE** is **key_value**, **--at** is **at**. A number is an
**Integer**, an argument that repeats a **ListOf**, **KEY=VALUE** a list of
records of **key** and **value**, both text, an option without a value a
**Boolean**; the rest is text, and what is in brackets is optional. Each
command takes **cwd** too, as **Run** does, and answers the **lines** of
the console.

**NotFound** says that a name of the command names nothing of the
project, **BadArgument** that an argument isn't one the command takes, or
that the program sent a key the command doesn't have, or left out one it
needs: nothing was done. Both are kinds of **CommandFailed**, which says
that the command failed on the way. The typed commands run in turn with
**Run**, and on a socket that asks for the token they wait for the proof
too.

```
async def main(reactor):
    path = os.path.expanduser("~/labs/lab1.sock")
    endpoint = endpoints.UNIXClientEndpoint(reactor, path)
    vb = await endpoints.connectProtocol(endpoint, amp.AMP())
    hello = await vb.callRemote(Hello, protocols=[2])
    if hello["protocol"] != 2:
        raise SystemExit("It knows protocol 1 only")
    memory = {"key": "memory", "value": "1024"}
    await vb.callRemote(
        BrickSet, name="vm1", key_value=[memory]
    )
    try:
        await vb.callRemote(BrickStart, name=["sw1", "vm1"])
    except NotFound as exc:
        print(exc)
```

Protocol 2 keeps its commands. A later Virtualbricks may add commands to
it, or optional arguments, which an older one refuses with
**UnhandledCommand** or **BadArgument**; a change of any other kind is
protocol 3, and a program that asks for 2 then gets 1, with **Run**.

## The commands of the windows

Protocol 2 has the commands of the windows of another Virtualbricks too,
in the module **virtualbricks.remote.commands**, which a program may
import as **ampcommands**. They pass the checks of the typed commands.
**Follow** asks for the project and its changes: Virtualbricks then
calls on the program, without waiting for an answer, **Opened** when a
project opens, **Changed** for each image, brick and event, then
**Synced**; after that, **Changed**, **Renamed** and **Removed** for each
change, gathered once a turn, **SettingsChanged**, **Logged** for each
message of its log, the last 500 first, and **Quitting**. A table, a
state, the settings and a message are JSON in a text. What waits for the
program goes before the answer of each of its commands, so that once a
command is answered the program has what it changed.

The others are what the windows do that the console has no command for:
**Apply**, the OK of a panel, the keys it changed only; **Connect**, a
drop; **MakeImage**, **StartOver**, **TrashFile** and **Relink**, the
files of the images; **ProjectNames**, **ProjectSummary**, **Readme**,
**SetReadme** and **SetKsm**. The facts of the machine answer beside the
requests that wait: **QemuFacts**, the texts that a QEMU program prints;
**MachineProperties**, **UsbDevices**, **ImageFacts**, **DiskUsage** and
**Folder**, the entries of a folder, for a path being typed. **Attach**
switches the connection to the bytes of the console of a brick, AMP's
**ProtocolSwitchCommand**.

# THE WINDOWS OF ANOTHER VIRTUALBRICKS

**virtualbricks --connect** *description* opens the windows of the
Virtualbricks of the socket of *description*: the lab machine, which
runs the bricks, this machine or another, and the desktop, which shows
them. The Virtualbricks there listens with **--listen**, on a socket that
speaks AMP, as one does without **protocol=text**, with its own windows
or with **--no-gui**, and both run the same version:

```
virtualbricks --no-gui --noterm --listen \
    'ssl:8765:interface=0.0.0.0:privateKey=~/vb/lab.pem'
virtualbricks --connect \
    'ssl:lab.example:8765:caCertsDir=~/vb/lab'
```

The windows follow the project open there: its bricks, events and
images, their processes, the settings and the messages of its log; what
the console or other windows change there shows at once. What the windows
do goes there: a start, a new brick, the OK of a panel, which sends only
the keys that the panel changed, so that two windows that change
different keys of a brick keep both. The title names the project and
where it runs.

What they show of the lab machine is its own: its QEMU programs and what
they can do, its USB devices, the files of its images and of the private
copies, its projects and the README of the open one. A path is a path
there: the windows have no file chooser for it, but an entry that
completes from the folders there. Settings has three pages: *This
computer*, the settings of the windows, as the terminal; the lab machine,
its KSM and the audio driver of QEMU, with its workspace shown; and the
project's. **Open Control Monitor** starts the terminal of this computer,
with **vdeterm** or **unixterm** of VDE, on a socket of its own, and the
windows join it to the console there over another connection.

The windows start no program of a brick here, and the files they work
on are those of the lab machine. Some items wait for a later version,
greyed: **Import** and **Export**, saving or merging the private copy of
a disk, copying an image to the image folder, **Show in Files**, and
**Terminate**, which stops a machine with **SIGTERM**.

When the connection is lost, a bar says why, and the windows wait:
**Reconnect** connects again, and the copy starts over. When the
Virtualbricks there quits, the bar says so. **Quit** closes the windows;
the Virtualbricks there goes on.

A **tcp** or **ssl** socket asks for the token, as for **--command**:
that of **tokenFile=**, or the default one. Over **ssl**,
**caCertsDir=** holds the certificate of the lab machine, or that of its
authority, and **privateKey=** and **certKey=** are the windows' own,
for a Virtualbricks that asks for one. See **Sockets on the network**.

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

With **--command**, and with **--connect --run**:

**0**
:   The command was done, or every command of the file.

**1**
:   The command failed, its answer was too long for AMP, an option is
    wrong, or the file of **--run** can't be read.

**2**
:   No Virtualbricks answered: none listens there, several listen and
    none is named, it ended before it answered, it speaks another
    protocol, or it refused the token or the certificate. The error says
    which.

**130**
:   Ctrl+C stopped the wait.

With the windows of **--connect**, **1**: they couldn't reach the
Virtualbricks there, it refused them, or it runs another version.

# FILES

*\$XDG_STATE_HOME*/virtualbricks/history
:   The history of the console, the last 500 lines.

*/tmp/virtualbricks.lock*, *\$XDG_RUNTIME_DIR*/virtualbricks/.lock
:   The locks of the single-instance mode, see **--lock**.

*workspace*/.virtualbricks.lock
:   The lock of a workspace, held by the Virtualbricks that runs there in
    each mode but **none**, see **--lock**.

*\$XDG_RUNTIME_DIR*/virtualbricks/*key*/.control, .control.lock
:   The socket of **--listen** alone of the workspace of *key* and its
    lock, see **THE CONTROL SOCKET**.

*\$XDG_CONFIG_HOME*/virtualbricks/token
:   The token of the **tcp** and **ssl** sockets, see **THE CONTROL
    SOCKET**.

*\$XDG_RUNTIME_DIR*/virtualbricks/.connect-*pid*
:   The sockets of the terminals of the consoles that the windows of
    **--connect** open, see **THE WINDOWS OF ANOTHER VIRTUALBRICKS**.

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
socket of its workspace:

```
virtualbricks --no-gui --noterm --listen --run ~/labs/ospf.vb
```

The machine of that lab, from another terminal, and the commands of a
file, sent to it one after the other:

```
virtualbricks --command brick start router
virtualbricks --connect --run ~/labs/traffic.vb
```

The same lab, open to the network over **ssl**, and its machine, started
from a laptop that has a copy of the token and of **lab.pem**, in
*~/vb/lab*:

```
virtualbricks --no-gui --noterm --run ~/labs/ospf.vb --listen \
    'ssl:8765:interface=0.0.0.0:privateKey=~/vb/lab.pem'
virtualbricks \
    --connect 'ssl:lab.example:8765:caCertsDir=~/vb/lab' \
    --command brick start router
```

The windows of that lab, on the same laptop:

```
virtualbricks --connect \
    'ssl:lab.example:8765:caCertsDir=~/vb/lab'
```

Two labs side by side, each in its workspace, both listening, and a
command to one of them:

```
virtualbricks --no-gui --noterm --listen --workspace ~/labs/a &
virtualbricks --no-gui --noterm --listen --workspace ~/labs/b &
virtualbricks --workspace ~/labs/b --command status
```

# SEE ALSO

**virtualbricks-config**(5), **virtualbricks-archive**(7), **qemu**(1),
**vde_switch**(1), **openssl**(1)
