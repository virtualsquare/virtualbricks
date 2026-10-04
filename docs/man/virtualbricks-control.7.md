---
title: VIRTUALBRICKS-CONTROL
section: 7
header: Virtualbricks Manual
footer: virtualbricks VERSION
date: DATE
---

# NAME

virtualbricks-control - the protocols of the control sockets: text, AMP 1
and AMP 2

# SYNOPSIS

**virtualbricks** **--listen** **unix:***path***:protocol=text**

**virtualbricks** **--listen** [**unix:***path*]

**virtualbricks** **--listen** **tcp:***port*[**:protocol=text**]

# DESCRIPTION

A Virtualbricks started with **--listen** answers on control sockets: the
commands of its console, from **virtualbricks --command** or from any
program, and what the windows of another Virtualbricks ask. A socket
carries lines of JSON or the boxes of AMP, Twisted's Asynchronous Messaging
Protocol, and on them three protocols:

**text**
:   Lines of JSON, on a socket of **protocol=text**: a line of the console
    in each request, the lines it prints in each answer. Any language that
    reads and writes JSON speaks it, and a shell with **socat**(1).

**AMP 1**
:   On an AMP socket, as a socket is without **protocol=text**: **Hello**,
    who answers, and **Run**, a line of the console and its lines.
    **virtualbricks --command** speaks it, and so can a program written
    with Twisted.

**AMP 2**
:   On the same connection, once **Hello** agrees on it: a typed command
    for each command of the console, as **BrickStart** with its names, and
    the commands of the windows of **virtualbricks --connect**: **Follow**,
    which sends the project, then each change, and the others.

```
  +--------------+  +-------------+---------------------------+
  |     text     |  |    AMP 1    |           AMP 2           |
  |  line, cwd   |  | Hello, Run  | typed commands, Follow    |
  |  -> lines    |  |             | and its pushes, Attach    |
  +--------------+  +-------------+---------------------------+
  |  the token,  |  |  the token, if asked: Challenge and     |
  |  if asked    |  |  Authenticate                           |
  +--------------+  +-----------------------------------------+
  |  JSON lines  |  |  AMP boxes                              |
  +--------------+--+-----------------------------------------+
  |  a unix, tcp or ssl socket of --listen                    |
  +-----------------------------------------------------------+
     protocol=text      protocol=amp, the default
```

A **tcp** socket answers only a client that proves first that it knows the
token of Virtualbricks, in either format. This page describes the
protocols for whoever writes a client: the sockets (**THE SOCKETS**), the
proof of the token (**THE TOKEN**), the text protocol (**THE TEXT
PROTOCOL**), the boxes of AMP (**AMP**) and the commands of its two
protocols (**AMP PROTOCOL 1**, **AMP PROTOCOL 2**), how they change
(**VERSIONS**) and how much they carry (**LIMITS**). How to open the
sockets, and which, is in **THE CONTROL SOCKET** of **virtualbricks**(1).

# THE SOCKETS

The protocols are the same on each type of socket: **unix**, a path that
only its user can connect to; **tcp**, a port of this machine; and
**ssl**, a port inside TLS. Each **tcp** socket asks a client for the
token, and so may an **ssl** socket, see **virtualbricks**(1); a **unix**
socket never does. The first message tells the client which, see **THE
TOKEN**. The socket of **--listen** alone,
*\$XDG_RUNTIME_DIR*/virtualbricks/*key*/.control, speaks AMP.

Each connection runs its requests one after the other, in the order they
came: a client may send the next request before the answer to the one
before, and the answers come in the same order. Over AMP, the commands that
only read the machine answer at once, beside those that wait, see **AMP
PROTOCOL 2**. Connections don't wait for each other, nor for the terminal
or the events of Virtualbricks.

The paths of a command, as that of **source** *file*, are read from
**cwd**, an absolute path that a request may give, or else from the folder
where Virtualbricks runs. A client on another machine leaves **cwd** out:
its folders aren't those of Virtualbricks. Virtualbricks answers in its own
language, and logs each command it gets, with the address of the client on
a network socket.

When Virtualbricks quits, it closes each connection once the answers it
owes are written; a client that doesn't read them within 2 seconds is cut
off. **quit** answers too, and a connection that follows Virtualbricks gets
**Quitting** first.

# THE TOKEN

The token is a line of text of at least 16 characters, in a file:
*\$XDG_CONFIG_HOME*/virtualbricks/token, or the file of **tokenFile=** in
the description of the socket. The first start of a socket that needs it
makes the file, with 43 random characters. The file must be a regular file
of the user that nobody else can read or change, mode 0600; the spaces
around the line don't count. A client reads the same token: copy the file
to its machine.

Neither end sends the token. Each proves that it knows it, over two
nonces, a random number of each end in lowercase hex digits: Virtualbricks
sends one of 64 digits, and the client's has from 32 to 128. The proof of a
*side*, **client** or **server**, is the HMAC-SHA256, under the token in
UTF-8, of the text

```
virtualbricks side S C
```

where *S* is the nonce of Virtualbricks and *C* that of the client, one
space between the words, written in lowercase hex digits:

```
  client                               Virtualbricks
    |                                        |
    |<-- nonce S ----------------------------|
    |                                        |
    |    nonce C, HMAC(token,                |
    |    "virtualbricks client S C")         |
    |--------------------------------------->|  checks it: if
    |                                        |  wrong, closes
    |                                        |  the connection
    |<---------------------------------------|
    |    HMAC(token,                         |
    |    "virtualbricks server S C")         |
  checks it: if wrong,
  closes the connection
```

The client proves first, and Virtualbricks then proves it to the client: a
program that took the port in place of Virtualbricks doesn't know the
token, so it can't, and the client doesn't send it any command. With new
nonces each time, a proof is good for one connection only, and nobody who
reads it learns the token. A client has 10 seconds from connecting to give
a right proof; then the connection is closed.

In a shell, **openssl**(1) computes the proof of the client:

```
printf 'virtualbricks client %s %s' "$nonce" "$mine" |
    openssl dgst -sha256 -hmac "$token"
```

# THE TEXT PROTOCOL

## Lines

Each message is a JSON object on a line of its own, in UTF-8, ended by a
newline, LF. Virtualbricks skips the empty lines it gets, and closes the
connection on a line longer than 64 KiB, 65536 bytes. A key that a message
doesn't need is ignored: a client ignores the keys it doesn't know too, so
that a later version can add some.

## The greeting

Virtualbricks writes the first line as soon as a client connects:

```
{"protocol": 1, "version": "3.0.0", "pid": 4200,
 "project": "lab1"}
```

**protocol**
:   1, the version of the text protocol. A client that doesn't know it
    sends nothing, and closes the connection.

**version**
:   The version of Virtualbricks.

**pid**
:   Its process.

**project**
:   The name of the open project, or **null**.

## Requests and answers

A request has the command, **line**, a line of the console as it is typed,
and **cwd**, optional, the folder of its paths. Its answer has **ok**,
whether the command was done, **lines**, what it printed, a text for each
line, without newlines, and **error**, why it failed, when **ok** is
**false**; **lines** is then what it printed before it failed:

```
{"line": "brick start sw1", "cwd": "/home/alice/labs"}
{"ok": true, "lines": ["sw1 runs, process 4242"]}
{"line": "brick start vm9"}
{"ok": false, "lines": [], "error": "No brick named vm9"}
```

A line that isn't a request gets an answer with **ok** **false** and why,
as "Not a request: "cwd" is not an absolute path", and the connection goes
on.

## With the token

On a socket that asks for the token, the first line asks for the proof,
with the nonce of Virtualbricks, and the client answers with its own nonce
and its proof. The greeting follows a right proof, with the proof of
Virtualbricks:

```
{"protocol": 1, "auth": "token", "nonce": "3f9a..."}
{"nonce": "c41d...", "proof": "8e02..."}
{"protocol": 1, "version": "3.0.0", "pid": 4200,
 "project": "lab1", "proof": "51b7..."}
```

A wrong proof, a line that isn't one, or none in 10 seconds gets an answer
with **ok** **false** and why, as "Wrong token", and the connection
closes.

```
  client                               Virtualbricks
    |                                        |
    |<-- {"protocol": 1, "auth": "token", ---|  if it asks
    |    "nonce": S}                         |  for the token
    |--- {"nonce": C, "proof": ...} -------->|
    |                                        |
    |<-- {"protocol": 1, "version": ..., ----|  the greeting
    |    "pid": ..., "project": ...          |
    |    [, "proof": ...]}                   |
    |                                        |
    |--- {"line": "brick start sw1"} ------->|
    |--- {"line": "status"} ---------------->|
    |<-- {"ok": true, "lines": [...]} -------|  in the same
    |<-- {"ok": true, "lines": [...]} -------|  order
```

# AMP

## Boxes

AMP carries boxes: a key and its value, then another, and so on, up to a
key of no bytes. Each key and each value has its length first, in two
bytes, the high byte first: a key has from 1 to 255 bytes, a value from 0
to 65535. A request of **Hello**, and its answer:

```
   length  key         length  value
  +-------+-----------+-------+-----------------------+
  | 00 04 | _ask      | 00 01 | 1                     |
  | 00 08 | _command  | 00 05 | Hello                 |
  | 00 09 | protocols | 00 06 | 00 01 "1" 00 01 "2"   |
  | 00 00 |              the end of the box           |
  +-------+-----------+-------+-----------------------+
  | 00 07 | _answer   | 00 01 | 1                     |
  | 00 08 | protocol  | 00 01 | 2                     |
  | 00 07 | version   | 00 05 | 3.0.0                 |
  | 00 03 | pid       | 00 04 | 4200                  |
  | 00 07 | project   | 00 04 | lab1                  |
  | 00 00 |              the end of the box           |
  +-------+-----------+-------+-----------------------+
```

A request has **\_ask**, a tag that the program chooses, different from
those of its requests that wait, and **\_command**, the name of the
command; then its arguments, in any order. Its answer has **\_answer**, the
same tag, and the values of the answer; or, if the command failed,
**\_error**, the tag, **\_error_code** and **\_error_description**, why. The
tags pair the answers with the requests, which may be answered in another
order. A request without **\_ask** wants no answer: the pushes of **Follow**
are such. A program written with Twisted has all this in
**twisted.protocols.amp**; in Python without Twisted,
**virtualbricks.console.ampbox** reads and writes the boxes.

## Values

A value is bytes, read as the command says:

**str**
:   A text, in UTF-8.

**int**
:   An integer, in decimal digits, with **-** before it if negative.

**bool**
:   **True** or **False**.

**bytes**
:   Bytes, as they are.

**[str]**, **[int]**
:   A list: each item with its length in two bytes, one after the other.

**pairs**
:   A list of records, each with **key** and **value**, both **str**: each
    record a box, with its end, one after the other.

An optional argument, written **?** after its kind, is left out of the
box when it has no value, and so is an optional value of an answer.

## Errors

**\_error_code** is one of the codes of the command, which name what went
wrong; each protocol below lists its own. Twisted adds two: **UNHANDLED**,
there is no command of that name, as a command of a later version or of a
protocol that the connection doesn't speak, see **VERSIONS**; and
**UNKNOWN**, a failure that Virtualbricks didn't expect, after which the
connection closes. A box that isn't one closes the connection too.

# AMP PROTOCOL 1

The commands of protocol 1 are in the module
**virtualbricks.console.ampwire**, which loads nothing but Twisted's
**amp**: a program imports it, or copies it, as **THE CONTROL SOCKET** of
**virtualbricks**(1) does. They are written here as in
*tests/data/amp-protocol-2.txt* of the sources: each argument as
*name*:*kind*, then **->** and what the answer has:

```
Hello         protocols:[int]?
              -> protocol:int version:str pid:int project:str?
Run           line:str cwd:str? -> lines:[str]
Challenge     -> nonce:str
Authenticate  nonce:str proof:str -> proof:str
```

**Hello**
:   Who answers, and the protocol of the connection from then on.
    **protocols** are those the program speaks; **protocol** is the highest
    that Virtualbricks speaks too, 1 without them or when it speaks none of
    them. Then the **version** of Virtualbricks, its **pid**, and the open
    **project**, left out if none is. A connection that doesn't call
    **Hello** speaks protocol 1.

**Run**
:   A line of the console and its **cwd**, as in a request of the text
    protocol; the answer is the lines it printed. If the command fails,
    the error says why, and what it printed before is lost.

**Challenge**
:   The nonce of Virtualbricks, for the proof of the token.

**Authenticate**
:   The nonce of the program and its proof; the answer is the proof of
    Virtualbricks, which the program checks, see **THE TOKEN**.

Their errors:

**COMMAND_FAILED**
:   **Run**: the command failed, or its **cwd** isn't an absolute path.

**ANSWER_TOO_LONG**
:   **Run**: the command was done, but its lines are longer than the 65535
    bytes of a value; a text socket carries them.

**TOKEN_NEEDED**
:   **Hello**, **Run** and the commands of protocol 2: on a socket that
    asks for the token, each fails until the program proves that it knows
    it.

**WRONG_TOKEN**
:   **Challenge** and **Authenticate**: the socket takes no token, and the
    connection goes on; or the proof is wrong, or **Authenticate** came
    without a **Challenge** before it, and the connection closes.

```
  program                              Virtualbricks
    |                                        |
    |--- Challenge ------------------------->|  if it asks
    |<-- nonce S ----------------------------|  for the token
    |--- Authenticate nonce C, proof ------->|
    |<-- proof of Virtualbricks -------------|
    |                                        |
    |--- Hello protocols [1, 2] ------------>|
    |<-- protocol 2, version, pid, ... ------|
    |                                        |
    |--- Run line "brick start sw1" -------->|  protocol 1
    |<-- lines [...] ------------------------|
    |--- BrickStart name ["vm1"] ----------->|  protocol 2
    |<-- lines [...] ------------------------|
```

# AMP PROTOCOL 2

Once **Hello** has agreed on 2, a connection speaks the commands of
protocol 1 and those of protocol 2; before, these fail with
**PROTOCOL_NEEDED**. They are in two modules that load nothing else of
Virtualbricks but **ampwire**: **virtualbricks.console.ampcommands**, the
typed commands, and **virtualbricks.remote.commands**, those of the
windows; a program imports them, or copies them. Each command of protocol
2 has the same errors:

**NOT_FOUND**
:   A name of the command names nothing there: a brick, an event, an
    image, a project, a program or a file. Nothing was done.

**BAD_ARGUMENT**
:   An argument isn't one the command takes; or the box has a key that the
    command doesn't have, or lacks one it needs, which Twisted would drop,
    or close the connection on. Nothing was done.

**PROTOCOL_NEEDED**
:   **Hello** hasn't agreed on protocol 2.

**COMMAND_FAILED**
:   The command failed on the way: a program or a file said no. Part of it
    may be done.

**ANSWER_TOO_LONG**
:   The command was done, but its answer is longer than the 65535 bytes of
    a value.

**TOKEN_NEEDED**
:   As in protocol 1.

In the modules, **NotFound** and **BadArgument** are subclasses of
**CommandFailed**: a program that catches **CommandFailed** catches the
three.

## The typed commands

A typed command for each command of the console. Its name is the words of
the command, each with a capital letter: **brick card add** is
**BrickCardAdd**, **status** is **Status**. Its arguments are named after
those of the command in **COMMANDS** of **virtualbricks**(1), in lower
case, with **\_** for what isn't a letter or a digit: *NAME* is **name**,
*KEY*=*VALUE* is **key_value**, **--at** is **at**. A number is an
**int**, an argument that repeats a list, *KEY*=*VALUE*... a list of
**pairs**, an option without a value a **bool**, the rest a **str**; what
is optional in the console is optional here. Each takes **cwd** too, as
**Run** does, and answers **lines:[str]**, the lines of the console:

```
BrickTypes
BrickList
BrickNew           kind:str name:str?
BrickShow          name:str
BrickKeys          kind_name:str key:str?
BrickSet           name:str key_value:pairs
BrickUnset         name:str key:[str]
BrickStart         name:[str]
BrickStop          name:[str]
BrickKill          name:[str]
BrickRestart       name:[str]
BrickPause         name:[str]
BrickContinue      name:[str]
BrickSuspend       vm:str
BrickResume        vm:str
BrickReset         vm:str
BrickMonitor       name:str
BrickConnect       name:str target:[str]
BrickDisconnect    name:str end:str?
BrickCardAdd       vm:str kind:str options:[str]?
BrickCardSet       vm:str card:str key_value:pairs
BrickCardRemove    vm:str card:[str]
BrickRename        name:str new:str
BrickDuplicate     name:str new:str?
BrickDelete        name:[str]
EventList
EventNew           name:str?
EventShow          name:str
EventSet           name:str key_value:pairs
EventActionAdd     name:str what:str subject:str? at:int?
EventActionRemove  name:str n:[int]
EventActionMove    name:str n:int to:int
EventStart         name:[str]
EventStop          name:[str]
EventRun           name:[str]
EventRename        name:str new:str
EventDuplicate     name:str new:str?
EventDelete        name:[str]
ProjectList
ProjectShow
ProjectOpen        name:str
ProjectNew         name:str
ProjectSave
ProjectRename      name:str new:str
ProjectDuplicate   name:str new:str
ProjectDelete      name:str force:bool?
Help               topic:[str]?
Status
Quit
Source             file:str
ImageList
ImageAdd           name:str path:str key_value:pairs?
ImageShow          name:str
ImageSet           name:str key_value:pairs
ImageRename        name:str new:str
ImageDelete        name:str
SettingShow        key:str?
SettingSet         key_value:pairs
SettingUnset       key:[str]
```

What each does and prints is what **virtualbricks**(1) says of its command.
**BrickSet**(name="vm1", key_value=[{"key": "memory", "value": "1024"}]) is
**brick set vm1 memory=1024**; **BrickStart**(name=["sw1", "vm1"]) is
**brick start sw1 vm1**.

## The commands of the windows

What the windows of **virtualbricks --connect** need that the console has
no command for. A table, a state and the other JSON of this section are
JSON in a **str**, since AMP has no tables:

```
Follow             -> project:str? version:str
Apply              kind:str name:str changes:str links:str
                   extras:str ->
Connect            source:str target:str -> connected:bool
QemuFacts          program:str -> path:str version:str
                   options:str machines:str cpus:str devices:str
                   displays:str audio_drivers:str netdevs:str
                   accelerators:str
MachineProperties  program:str machine:str -> text:str
UsbDevices         -> devices:str
ImageFacts         path:str -> file:str info:str others:str
MakeImage          path:str format:str size:int ->
StartOver          vm:str device:str -> trashed:bool
TrashFile          path:str -> trashed:bool
Relink             name:str path:str ->
ProjectNames       -> names:[str]
ProjectSummary     name:str -> summary:str
DiskUsage          name:str -> private_disks:int other_files:int
Readme             -> text:str
SetReadme          text:str ->
ReadmePicture      name:str path:str offset:int
                   -> data:bytes size:int
SetKsm             enable:bool -> enabled:bool
Folder             path:str -> entries:[str] more:bool
Attach             brick:str console:str ->
```

**Follow**
:   Send the project, then each change, see **Follow and the pushes**; the
    answer is the open project, and the version of Virtualbricks.

**Apply**
:   The OK of the panel of a brick, an event or an image, *kind* **brick**,
    **event** or **image**: what the panel changed, all or nothing.
    **changes** is an object of the settings changed, by their names and
    with their values as the project file writes them, see
    **virtualbricks-config**(5); **links**, a list of the plugs moved, each
    [*index*, *target*], the target written as in the project
    file, **""** for none; **extras**, what a brick has beyond its
    settings, only when it changed: the **cards** of a machine, each
    {**kind**, **model**, **mac**, **connect**, **link**}, and the
    **states**, **transitions** and **period** of a Netemu. Only the keys
    given change: the last OK wins for them, and the rest keeps what
    another window set.

**Connect**
:   Connect brick *source* to brick *target*, as a drop does: a free plug,
    or a new card of a machine. Whether it could.

**QemuFacts**
:   What the QEMU program *program*, as **qemu-system-x86_64**, prints:
    its **path**, and for each question a JSON list [*out*, *err*,
    *status*], a value each, since all of them are more than
    a value carries.

**MachineProperties**
:   What **-machine** *type***,help** prints, for *machine*, or for the
    default type if it is **""**.

**UsbDevices**
:   The USB devices of the machine: a JSON list of {**id**,
    **description**}.

**ImageFacts**
:   What the file *path* is: **file**, {**size**, **mtime**, **taken**},
    the time in nanoseconds and the space it takes in bytes; **info**, what
    **qemu-img info --output=json** prints; **others**, a JSON list of
    [*project*, *image*], the images of the other projects of
    the workspace with that file.

**MakeImage**
:   Make the file of an empty disk, of *format* **qcow2** or **raw**, and
    of *size* bytes. **BAD_ARGUMENT** if the file is there already.

**StartOver**
:   The private copy of disk *device* of machine *vm* goes to the trash,
    or is deleted without one: whether it went to the trash.

**TrashFile**
:   A file of the workspace that no image uses goes to the trash, or is
    deleted without one: whether it went to the trash.

**Relink**
:   Give image *name* the file *path*, and the private copies made on the
    image with it.

**ProjectNames**
:   The names of the projects of the workspace, sorted.

**ProjectSummary**
:   What the list of the projects shows of one, as a JSON object:
    **name**, **path**, **description**, **modified**, **bricks** (a
    count for each type), **events** (a count), **images** (each {**name**,
    **path**, **found**}) and **problem**, **null** unless the project file
    can't be read.

**DiskUsage**
:   The space that a project takes, in bytes: its private disks, and the
    other files.

**Readme**, **SetReadme**
:   The README of the open project; the new one is written when the
    project is saved.

**ReadmePicture**
:   A picture of the README of project *name*, *path* relative to its
    folder, see **virtualbricks-config**(5): its **data** from byte
    *offset*, as much as a value carries, and the **size** of the file.
    A program asks again from the end of what came, until it has
    **size** bytes. **BAD_ARGUMENT** for a path that leads out of the
    folder, a file that isn't one or that is larger than 10 MB.

**SetKsm**
:   Turn KSM on or off; whether it runs afterwards.

**Folder**
:   What completes *path* as it is typed: the entries of its folder that
    start with its last part, a folder with a **/** after it, at most 200,
    and whether there are more.

**Attach**
:   Join the program to a console of a running brick, see **Attach**.

**QemuFacts**, **MachineProperties**, **UsbDevices**, **ImageFacts**,
**DiskUsage**, **ReadmePicture** and **Folder** change nothing: they answer as soon as they
can, beside the requests that wait. The others wait for their turn, as the
typed commands do, and Virtualbricks logs them.

## Follow and the pushes

**Follow** asks Virtualbricks for its project and its changes. It sends
them as *pushes*: commands that it calls on the program, without **\_ask**,
that want no answer. A program that follows declares the eight of them,
and has a responder for each: Twisted closes the connection on a command
it has no responder for.

```
Opened             project:str? settings:str machine:str
Changed            kind:str name:str table:str state:str
Renamed            kind:str old:str new:str
Removed            kind:str name:str
Synced
SettingsChanged    settings:str
Logged             message:str
Quitting
```

**Opened**
:   A project is open, and the copy starts over: its name, left out if
    none is; **settings**, a JSON object of the settings of Virtualbricks
    and of the project, by their names in **virtualbricks-config**(5); and
    **machine**, a JSON object of what the machine of Virtualbricks has:
    **version**, **workspace**, **project_folder**, **trash** (whether
    what is removed goes to a trash), **runtime_dir**,
    **workspace_runtime_dir**, **missing** (the programs it lacks),
    **qemu_programs** (the names of its QEMU programs), **lacks** (for
    each type of brick, **null** or the programs it lacks, {**line**,
    **text**}) and **ksm** (whether KSM runs).

**Changed**
:   An image, a brick or an event, *kind* **image**, **brick** or
    **event**, is new or changed: its **table**, as the project file
    writes it, and its **state**, what the project file doesn't write:
    {**file**}, the **size**, **mtime** and **taken** of the file of an
    image, **null** if it isn't there; {**pid**, **copies**}, the process
    of a brick, **null** if it doesn't run, and the private copies of a
    machine, as **file**, by device; {**left**}, the seconds that an event
    still waits, **null** if it doesn't.

**Renamed**
:   An image, a brick or an event has a new name.

**Removed**
:   A brick or an event is deleted, an image removed.

**Synced**
:   The whole project has been sent.

**SettingsChanged**
:   The settings changed: all of them, as in **Opened**.

**Logged**
:   A message of the log, info and above, as a JSON object: **time**, in
    seconds since 1970, **level**, **text**, **traceback** or **null**,
    **namespace**, **source** and **source_type**, the brick it is about
    or **null**, **pid**, and **stream**, **stdout** or **stderr** for
    what the process of a brick printed.

**Quitting**
:   Virtualbricks quits.

**Follow** sends **Opened**, a **Changed** for each image, brick and
event, then **Synced**: the images first, then the bricks, each after
those it plugs into, then the events. Then the last 500 messages of the
log, and the answer. After that, Virtualbricks gathers what changes and
sends it once a turn of its loop, each object once, as it is then: the
renames and the deletes first, in the order they came, then what changed,
in the order above, the settings, the messages of the log, and
**Quitting**. Before it answers a command of the connection, it sends what
waits: once a command is answered, the program has what it changed. When
another project opens, the copy starts over, with **Opened**; **Follow**
again does the same. A push longer than a value carries isn't sent, and
the log says so.

```
  program                              Virtualbricks
    |                                        |
    |--- Follow ---------------------------->|
    |<-- Opened project "lab1" --------------|  the project
    |<-- Changed image debian ---------------|
    |<-- Changed brick sw1 ------------------|
    |<-- Changed brick vm1 ------------------|
    |<-- Synced -----------------------------|
    |<-- Logged, the last 500 ---------------|
    |<-- project, version -------------------|  the answer
    |                                        |
    |--- BrickStart name ["vm1"] ----------->|
    |<-- Changed brick vm1 ------------------|  what it
    |<-- Changed image debian ---------------|  changed
    |<-- lines [...] ------------------------|  the answer
    |                                        |
    |<-- Changed brick vm1 ------------------|  once a turn
    |<-- Logged -----------------------------|
    |                                        |
    |<-- Quitting ---------------------------|  at the end
```

## Attach

**Attach** joins the program to a console of a running brick:
**monitor**, its control monitor, or **serial**, the serial socket of a
machine. Virtualbricks connects to the console, then answers; from then
on, the connection carries the bytes of the console both ways, and nothing
else: AMP's **ProtocolSwitchCommand**. When either end closes, so does the
other. So a program opens a new connection for each console, proves the
token if asked, agrees on protocol 2 with **Hello**, then calls
**Attach**. **NOT_FOUND** says there is no such brick, **BAD_ARGUMENT**
that it doesn't run or has no such console, **COMMAND_FAILED** that
Virtualbricks can't reach the console. The windows of **virtualbricks
--connect** join the connection to a terminal of their own, as
**vdeterm**(1):

```
  terminal     program            Virtualbricks     console
     |            |                     |              |
     |            |-- Attach brick vm1, |              |
     |            |   console monitor ->|-- connects ->|
     |            |<----------- answer -|              |
     |<= bytes ==>|<====== bytes ======>|<== bytes ===>|
```

# VERSIONS

The text protocol is 1, in the greeting; another would have another
number. Over AMP, **Hello** agrees on the protocol: the highest that both
ends speak. 1 is always one of them.

Protocol 2 keeps its commands as they are. A later Virtualbricks may add
commands to it, and optional arguments to its commands, and nothing else:
an older one answers a command it doesn't have with **UNHANDLED**, and an
argument it doesn't know with **BAD_ARGUMENT**, so a program that sends
them knows that they weren't done. A change of any other kind makes
protocol 3, which would take the place of 2: a program that speaks both
calls **Hello** with **protocols** [1, 2, 3]. The sources keep the commands
of protocol 2 in *tests/data/amp-protocol-2.txt*, which the tests compare
with the modules.

The windows of **virtualbricks --connect** also want the same version of
Virtualbricks at both ends: the **version** in the answer of **Hello**.

# LIMITS

A line of the text protocol
:   64 KiB, 65536 bytes; a longer one closes the connection.

A key of AMP
:   255 bytes.

A value of AMP
:   65535 bytes. A longer answer is **ANSWER_TOO_LONG**, after the command
    was done; a longer push isn't sent.

The proof of the token
:   10 seconds from connecting.

The last answers, at the end
:   2 seconds for the client to read them.

The log, for a program that follows
:   The last 500 messages, then each new one.

# EXAMPLES

A shell on a text socket, with **socat**(1); the lines it prints are the
greeting and the answers:

```
virtualbricks --no-gui --listen \
    unix:~/labs/lab1.text:protocol=text &
socat - UNIX-CONNECT:$HOME/labs/lab1.text
{"protocol": 1, "version": "3.0.0", "pid": 4200, ...}
{"line": "brick new switch sw1"}
{"ok": true, "lines": ["sw1"]}
{"line": "brick start sw1"}
{"ok": true, "lines": ["sw1 runs, process 4242"]}
```

A client of the text protocol in Python, without anything else, for a
Virtualbricks started with **--listen tcp:8765:protocol=text**:

```
import hmac, json, os, secrets, socket, sys


def proof(token, side, nonce, mine):
    text = f"virtualbricks {side} {nonce} {mine}"
    key = token.encode()
    return hmac.new(key, text.encode(), "sha256").hexdigest()


def send(lines, **message):
    lines.write(json.dumps(message).encode() + b"\n")
    lines.flush()


def receive(lines):
    return json.loads(lines.readline())


def connect(port, token):
    sock = socket.create_connection(("127.0.0.1", port))
    lines = sock.makefile("rwb")
    first = receive(lines)
    if first.get("auth") == "token":
        nonce, mine = first["nonce"], secrets.token_hex(32)
        send(lines, nonce=mine,
             proof=proof(token, "client", nonce, mine))
        first = receive(lines)
        expected = proof(token, "server", nonce, mine)
        given = first.get("proof", "")
        if not hmac.compare_digest(given, expected):
            sys.exit(first.get("error", "Wrong token"))
    if first.get("protocol") != 1:
        sys.exit("It doesn't speak the text protocol 1")
    return lines


def ask(lines, line):
    send(lines, line=line)
    answer = receive(lines)
    print("\n".join(answer["lines"]))
    if not answer["ok"]:
        sys.exit(answer["error"])


path = os.path.expanduser("~/.config/virtualbricks/token")
with open(path) as file:
    token = file.read().strip()
lines = connect(8765, token)
ask(lines, "status")
ask(lines, "brick list")
```

A program written with Twisted that speaks protocol 2, for a Virtualbricks
started with **--listen tcp:8765**: it starts **sw1**, and prints what
changes until Virtualbricks quits:

```
import json, os

from twisted.internet import defer, endpoints, task
from twisted.protocols import amp

from virtualbricks.console.ampcommands import BrickStart
from virtualbricks.console.ampwire import Hello, authenticate
from virtualbricks.remote import commands


class Follower(amp.AMP):
    """Prints what changes; a responder for each push."""

    def __init__(self):
        super().__init__()
        self.lost = defer.Deferred()

    def connectionLost(self, reason):
        super().connectionLost(reason)
        self.lost.callback(None)

    @commands.Opened.responder
    def opened(self, project, settings, machine):
        print("Project", project)
        return {}

    @commands.Changed.responder
    def changed(self, kind, name, table, state):
        print(kind, name, json.loads(state))
        return {}

    @commands.Renamed.responder
    def renamed(self, kind, old, new):
        print(kind, old, "is now", new)
        return {}

    @commands.Removed.responder
    def removed(self, kind, name):
        print(kind, name, "is gone")
        return {}

    @commands.Synced.responder
    def synced(self):
        return {}

    @commands.SettingsChanged.responder
    def settings_changed(self, settings):
        return {}

    @commands.Logged.responder
    def logged(self, message):
        print(json.loads(message)["text"])
        return {}

    @commands.Quitting.responder
    def quitting(self):
        print("Virtualbricks quits")
        return {}


async def main(reactor):
    endpoint = endpoints.TCP4ClientEndpoint(
        reactor, "127.0.0.1", 8765
    )
    vb = await endpoints.connectProtocol(endpoint, Follower())
    path = os.path.expanduser("~/.config/virtualbricks/token")
    with open(path) as file:
        await authenticate(vb, file.read().strip())
    hello = await vb.callRemote(Hello, protocols=[1, 2])
    if hello["protocol"] != 2:
        raise SystemExit("It doesn't speak protocol 2")
    await vb.callRemote(commands.Follow)
    await vb.callRemote(BrickStart, name=["sw1"])
    await vb.lost


task.react(lambda reactor: defer.ensureDeferred(main(reactor)))
```

# FILES

*\$XDG_CONFIG_HOME*/virtualbricks/token
:   The token of the **tcp** and **ssl** sockets, see **THE TOKEN**.

*\$XDG_RUNTIME_DIR*/virtualbricks/*key*/.control
:   The socket of **--listen** alone of the workspace of *key*, which
    speaks AMP.

# SEE ALSO

**virtualbricks**(1), **virtualbricks-config**(5),
**virtualbricks-archive**(7), **socat**(1), **openssl**(1)

AMP: <https://amp-protocol.net/>, and Twisted's howto:
<https://docs.twisted.org/en/stable/core/howto/amp.html>

JSON Lines: <https://jsonlines.org/>

HMAC: RFC 2104, <https://www.rfc-editor.org/rfc/rfc2104>
