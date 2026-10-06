Virtualbricks 3.0: the console and the control protocols
########################################################

:date: 2026-10-06 12:00
:status: draft
:category: News
:tags: release, develop, console, control socket, amp, tls
:slug: the-console-and-the-control-protocols-of-virtualbricks-3-0
:author: Marco Giusti
:summary: How to drive Virtualbricks 3.0 without its windows: the console,
          the control sockets of --listen and --connect, on this machine or
          across the network, with a token or with certificates, and the
          three protocols they speak: lines of JSON, AMP 1 and AMP 2.
:lang: en

The `first post <{filename}/news/whats-coming-in-virtualbricks-3-0.rst>`_
of this series was a map of what changed in the ``develop`` branch. This one
is about how to drive Virtualbricks without its windows: from its console,
from a script, from another terminal, from a program in any language, and
from another machine. It starts with the console, then the control sockets
and how to describe them to ``--listen`` and ``--connect``, then each kind
of socket and how it keeps strangers out, and last the three protocols the
sockets speak, for whoever writes a client.

The examples are real: we ran each of them on Virtualbricks 3.0.0.dev3.
Only the names, the process numbers and the paths will differ on your
machine.


The console
===========

Virtualbricks 2.1 had a console too, with commands of its own, as
``sw1 on`` or ``sw1 config numports=16``. In 3.0 a command is a noun, a
verb, then its arguments. The nouns are ``brick``, ``event``, ``image``,
``setting`` and ``project``, and a few words stand alone: ``help``,
``status``, ``source``, ``python`` and ``quit``:

.. code-block:: text

   brick new switch
   brick new vm router
   brick set router memory=512 use_kvm=true
   brick card add router plug sw1 model=virtio-net-pci
   brick start router
   event new up
   event action add up start router
   event action add up shell "logger the lab is up"
   help brick set

- **Words as in a shell.** Quotes keep spaces, a backslash escapes, and
  ``#`` starts a comment. A name is always an argument, never a command, so
  a brick can be called ``list``.

- **Keys as in the project file.** ``KEY=VALUE``, as many as needed in one
  command, with the keys of ``project.toml``. They are all checked before
  any is set, so a command changes all of them or none. The disks of a
  machine are ``hda_image`` and ``hda_private``, and its network cards have
  commands of their own, ``brick card add``, ``set`` and ``remove``.
  ``brick keys switch`` lists the keys of a kind of brick, with their
  ranges and their defaults.

- **Answers.** A command prints something when there is something to say:
  the name given to a new brick, the process of a started one, a table.
  When it can't be done, it says why in one line that starts with
  ``Error:``, and changes nothing. ``start``, ``stop``, ``restart`` and
  ``suspend`` wait until they are done, or fail.

- **Typing.** On a terminal, Tab completes the nouns, the verbs, the names
  of the bricks, events, images and projects, the kinds of brick, the keys,
  and the values of a key that has a few. The prompt is the name of the
  open project. The history is kept between runs, the last 500 lines, in
  ``~/.local/state/virtualbricks/history``. The keys are those of readline:
  Up and Down, Ctrl+R and Ctrl+S to search, Ctrl+A and Ctrl+E, Alt+B and
  Alt+F, Ctrl+W, Ctrl+U, Ctrl+K and Ctrl+Y, Ctrl+T, Ctrl+L. Ctrl+C clears
  the line; while a command runs, it stops waiting for it, but not what it
  does. Ctrl+D on an empty line quits.

- **python** opens a Python shell, where ``factory`` is the factory of the
  bricks; Ctrl+D comes back to the console.

- **Pipes and scripts.** When the input isn't a terminal, each line is a
  command, and the end of the input quits. A file of commands runs with
  ``source FILE`` in the console, or with ``--run FILE`` at start. Empty
  lines and comments are skipped, and the first error stops the file,
  saying where, as ``lab.vb:4``.

- **Events.** The action of an event can be a command of the console, any
  of them; one that fails is logged with the event and the number of the
  action.

The console reads the terminal where Virtualbricks started, beside the
windows. ``--no-gui`` runs Virtualbricks without the windows, and without
loading GTK: the console is then the way in, and a lab can run on a server
without a display. ``--noterm`` doesn't read the terminal. With both,
nothing is read, and the lab runs until Virtualbricks gets ``SIGTERM`` or
``SIGINT``:

.. code-block:: sh

   virtualbricks --no-gui --noterm --listen --run ~/labs/ospf.vb

The ``--listen`` of that line is what lets you reach that lab afterwards.


The control socket
==================

A Virtualbricks started with ``--listen``, with its windows or without,
listens on control sockets once its project is open. Without
``--listen``, it listens on none. Then, from any terminal or script:

.. code-block:: sh

   virtualbricks --command brick start sw1 vm1
   virtualbricks --command brick set vm1 memory=1024
   virtualbricks --command status
   virtualbricks --connect --run ~/labs/traffic.vb

``--command`` sends the command of the words that follow and prints its
answer. The words reach the console quoted again, so a value with spaces is
quoted once, as in the console; the options of ``virtualbricks`` end at the
first word. Without words, ``--command`` sends the lines of its standard
input, each after the answer to the one before, up to the first error,
which names its line:

.. code-block:: text

   $ printf 'brick new switch sw2\nbrick set sw2 ports=16 stp=true\n' |
   >     virtualbricks --command
   sw2
   Error: line 2: sw2 has no key stp: brick keys sw2 lists them

``--connect --run FILE`` sends the lines of a file in the same way, and the
first error names the file and its line, as ``source`` does. Empty lines
aren't sent; comments are, and do nothing.

``--command`` loads neither GTK nor Twisted's reactor, opens no project and
takes no lock: it only talks to the socket. It takes no other option but
``--connect`` and ``--workspace``. The answer goes to the standard output,
an error to the standard error, and the exit status says how it went:

``0``
   The command was done, or every command of the file.

``1``
   The command failed, its answer was too long for AMP, an option is wrong,
   or the file of ``--run`` can't be read.

``2``
   No Virtualbricks answered: none listens there, several listen and none
   is named, it ended before it answered, it speaks another protocol, or it
   refused the token or the certificate. The message says which.

``130``
   Ctrl+C stopped the wait. The command goes on, there.

A relative path in a command, as that of ``source FILE``, is read from the
folder where you run ``virtualbricks --command``, on the same machine. To
another machine, ``--command`` doesn't send its folder, and the path is
read from the folder of that Virtualbricks.

Virtualbricks logs each command it gets, with the client that sent it, and
answers in its own language.


Describing a socket
===================

``--listen`` alone is the socket of the workspace. ``--listen`` followed by
a description is another socket, and ``--connect`` takes a description in
the same way. A description is written as Twisted's endpoints are: the type
of the socket, then its parts, separated by colons. A part is a value, or a
keyword and its value, ``key=value``, and a backslash makes the next
character plain, as the colons of an IPv6 address:

.. code-block:: text

   unix:~/labs/lab1.sock
   unix:address=~/labs/lab1.sock:protocol=text
   tcp:8765
   tcp:port=8765:interface=\:\:1
   ssl:8765:interface=0.0.0.0:privateKey=~/vb/lab-key.pem
   tcp:lab.example:8765                      (for --connect)
   ssl:host=lab.example:port=8765:caCertsDir=~/vb/lab

The three types are ``unix``, ``tcp`` and ``ssl``. Each takes
``protocol=amp``, the default, or ``protocol=text``. The keywords of each
type, for a socket that ``--listen`` opens and one that ``--connect``
reaches:

=============================  =======  =======  =======
Keyword                        unix     tcp      ssl
=============================  =======  =======  =======
*PATH*, address=               both
*PORT*, port=                           listen   listen
interface=                              listen   listen
*HOST*:*PORT*, host=, port=             connect  connect
protocol=                      both     both     both
tokenFile=                              both     both
privateKey=                                      both
certKey=                                         both
extraCertChain=                                  listen
caCertsDir=                                      both
=============================  =======  =======  =======

*listen* is for ``--listen``, *connect* for ``--connect``, and *both* for
either; a keyword can mean something else on each side, as ``caCertsDir=``
below. Each is described with its type. The file of a keyword can start
with ``~``, and a relative path is relative to the folder where you start
Virtualbricks.

**On the command line.** Both options take an optional value, which getopt
doesn't have, so the rule is this: the next word is the description when
it starts with a type and a colon, as ``unix:``, and the value after ``=``
always is, as ``--listen=tcp:8765``. A path alone is refused, so that it
isn't taken for a command:

.. code-block:: text

   $ virtualbricks --no-gui --listen ~/lab.sock
   --listen: /home/alice/lab.sock needs its type: unix:/home/alice/lab.sock

Quote a description that has a backslash, so that the shell leaves it.
``--listen`` can be given more than once, and Virtualbricks listens on each
socket, each with its protocol:

.. code-block:: sh

   virtualbricks --no-gui --noterm \
       --listen \
       --listen unix:~/labs/lab1.text:protocol=text \
       --listen tcp:8765 \
       --listen 'ssl:8768:privateKey=~/vb/lab-key.pem:caCertsDir=~/vb/clients'

A description is checked before anything starts: an unknown keyword, which
the message lists with those of the type; a keyword given twice; a port out
of 1–65535; a folder that isn't there; a tcp socket on the network; an ssl
socket without its key, or with a key that isn't that of its certificate;
a token file that others can read. Virtualbricks then exits with status 1
and says why.


Unix sockets
============

A unix socket is a file. Only you can connect to it: Virtualbricks makes it
with mode 0600, with a umask that leaves no moment between the bind and the
change of mode. So a unix socket asks for no token: the system knows who
connects.

**The socket of the workspace.** ``--listen`` alone listens on
``.control``, in a folder of the runtime folder that belongs to the
workspace:

.. code-block:: text

   /run/user/1000/virtualbricks/        $XDG_RUNTIME_DIR/virtualbricks
   └── qhz36ozg/                        the key of the workspace
       ├── .control                     the socket of --listen alone
       ├── .control.lock                its lock
       ├── .workspace -> ~/labs/a       the workspace
       └── lab/                         the sockets of the bricks of lab

The key is made from the path of the workspace, its first eight characters
of the SHA-256, in base32: the same folder has the same key, whatever path
names it. ``.workspace`` links back to the workspace, so ``--command`` can
say which Virtualbricks it found. Without ``XDG_RUNTIME_DIR``, the runtime
folder is ``/tmp/virtualbricks-UID``. Virtualbricks doesn't listen in a
runtime folder that isn't yours, or that others can write in.

**A socket of your own.** ``unix:PATH``, or ``unix:address=PATH``. The
folder must be there, and the path must fit in the 107 bytes that Linux
allows to the path of a socket; a deep scratch folder can be too long, and
Virtualbricks says so.

**One Virtualbricks for each socket.** The first to start takes the lock
*PATH*.lock, beside the socket, and listens; another one with the same
``--listen``, as with ``--lock none``, runs without that socket and says
who holds it. A socket left by a crash is removed at the next start, by
whoever takes the lock. Anything else at that path, a file or the socket of
another user, is left alone, and Virtualbricks listens without it.


Workspaces
==========

Each workspace has its own ``.control``, so two Virtualbricks that run side
by side, each in its workspace, both listen with ``--listen`` alone. On the
other end, ``--command``, ``--connect --run`` and ``--connect`` without a
description look for the Virtualbricks to talk to:

- with ``--workspace FOLDER``, the one that listens on the ``.control`` of
  that workspace;
- without it, the only Virtualbricks of yours that listens on the
  ``.control`` of its workspace; the locks, held, say which ones do;
- when several listen, none: it names them and sends nothing.

.. code-block:: text

   $ virtualbricks --no-gui --noterm --listen --workspace ~/labs/a &
   $ virtualbricks --no-gui --noterm --listen --workspace ~/labs/b &
   $ virtualbricks --command status
   Virtualbricks of yours listen in 2 workspaces: /home/alice/labs/b
   (process 430506) and /home/alice/labs/a (process 430482). Name one with
   --workspace, as virtualbricks --workspace /home/alice/labs/b --command
   status
   $ virtualbricks --workspace ~/labs/a --command status
   Nothing runs

``--connect`` with a description and ``--workspace`` are refused together:
each names a Virtualbricks, so give one of them.

When nobody listens, ``--command`` tells you whether a Virtualbricks of
yours runs without ``--listen``, or with another one, and how to start one
that listens.


TCP sockets
===========

``tcp:PORT``, or ``tcp:port=PORT``, listens on a port of this machine: on
``127.0.0.1``, or on another loopback address with ``interface=``, as
``'tcp:8765:interface=\:\:1'``, whose colons are escaped. What passes on
plain TCP can be read on the way, so a tcp socket refuses any address of the
network:

.. code-block:: text

   $ virtualbricks --no-gui --listen tcp:8765:interface=0.0.0.0
   --listen: tcp:8765:interface=0.0.0.0: tcp listens on this machine only,
   as interface=127.0.0.1 or ::1; across the network, ssl

A port is open to anyone on the machine, unlike a unix socket, and a
connection can do all that the console does, the shell commands in the
actions of an event included. So each client of a tcp socket proves first
that it knows the token, see below.

A port has no lock: the first Virtualbricks takes it, and another one logs
``Address already in use: no control socket`` and runs without it.

``--connect tcp:PORT`` reaches this machine; ``tcp:HOST:PORT``, or
``host=`` and ``port=``, another one, as an SSH tunnel would bring it
here. ``interface=`` is refused there, since it's where Virtualbricks
listens, not where to find it.

The log names each client by its address:

.. code-block:: text

   [virtualbricks.console.control#info] Listening on tcp 127.0.0.1 port
   8765, protocol amp, with the token of ~/.config/virtualbricks/token
   [virtualbricks.console.control#info] Command from 127.0.0.1 port 54560:
   status


The token
=========

The token is a line of text of at least 16 characters, in a file:
``~/.config/virtualbricks/token``, or the file of ``tokenFile=``. The first
socket that needs it makes it, with 43 random characters, and says so in
the log. You can also write your own:

.. code-block:: sh

   openssl rand -base64 32 > ~/.config/virtualbricks/token
   chmod 600 ~/.config/virtualbricks/token

The file must be a regular file of yours that nobody else can read or
change, mode 0600; the spaces around the line don't count. Virtualbricks
refuses to listen with another file, and ``--command`` refuses to use it:

.. code-block:: text

   Others can read or change /home/alice/vb/lab.token: chmod 600
   /home/alice/vb/lab.token: no command sent
   The token of /home/alice/vb/short.token has 5 characters; a token has
   at least 16: no command sent

A client reads the same token: copy the file to its machine, in the same
place, or name it with ``tokenFile=`` in the description of
``--connect``. Virtualbricks reads its token when it starts listening: a
new token counts from the next start.

**Neither end sends the token.** Each proves that it knows it, over two
nonces, a random number from each end: Virtualbricks sends one of 64 hex
digits, and the client chooses one of 32 to 128. The proof of a side,
``client`` or ``server``, is the HMAC-SHA256, under the token, of the text
``virtualbricks SIDE S C``, where ``S`` is the nonce of Virtualbricks and
``C`` that of the client, in lowercase hex digits:

.. code-block:: text

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

The client proves first, and Virtualbricks then proves it back. A program
that took the port before Virtualbricks doesn't know the token, so it
can't, and the client sends it no command. With new nonces each time, a
proof is good for one connection only, and nobody who reads it learns the
token. A client has 10 seconds from connecting to give a right proof; then
the connection is closed.

When the tokens differ, both ends say so:

.. code-block:: text

   $ virtualbricks --connect tcp:8765:tokenFile=~/vb/old.token --command status
   The Virtualbricks on 127.0.0.1 port 8765 has another token
   [virtualbricks.console.control#warn] 127.0.0.1 port 58750 on tcp port
   8765: wrong token

In a shell, ``openssl`` computes the proof of a client:

.. code-block:: sh

   printf 'virtualbricks client %s %s' "$nonce" "$mine" |
       openssl dgst -sha256 -hmac "$token"


SSL sockets
===========

``ssl:PORT`` listens inside TLS, so it can listen on the network: on
``127.0.0.1`` too, unless ``interface=`` names another address, as
``0.0.0.0`` for every IPv4 address of the machine. It needs the
certificate of Virtualbricks, in PEM:

``privateKey=FILE``
   The private key, which is required. The file can hold the certificate
   too.

``certKey=FILE``
   The certificate, when it's in a file of its own.

``extraCertChain=FILE``
   The certificates between it and the authority that issued it, when there
   are some.

The files are read, and checked, when Virtualbricks starts: a key that
isn't that of its certificate stops the start, with a message. An ssl
socket needs pyOpenSSL, ``python3-openssl``; a Virtualbricks without an
ssl socket doesn't load it.

A certificate for the lab machine, for its name and its address, made with
``openssl`` in ``~/vb``. ``lab-key.pem``, the key with the certificate,
stays there, for Virtualbricks; ``lab.pem``, the certificate alone, is for
the clients:

.. code-block:: sh

   openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 \
       -nodes -days 3650 -subj /CN=lab.example \
       -addext subjectAltName=DNS:lab.example,IP:192.0.2.7 \
       -keyout lab.key -out lab.pem
   cat lab.key lab.pem > lab-key.pem
   chmod 600 lab.key lab-key.pem

Then, on the lab machine, and from a desktop that has a copy of ``lab.pem``
in ``~/vb/lab``:

.. code-block:: sh

   virtualbricks --no-gui --noterm --listen \
       'ssl:8765:interface=0.0.0.0:privateKey=~/vb/lab-key.pem'
   virtualbricks --connect 'ssl:lab.example:8765:caCertsDir=~/vb/lab' \
       --command status

**The client checks Virtualbricks.** ``caCertsDir=DIR``, in the
description of ``--connect``, is a folder of ``.pem`` files: the
certificate of Virtualbricks itself, as ``lab.pem`` above, or that of the
authority that issued it. Without it, the authorities of the system are
trusted, as for a certificate of Let's Encrypt. The name in the
description must be one of the names of the certificate. Otherwise nothing
is sent:

.. code-block:: text

   The certificate of lab.example isn't one you trust: self-signed
   certificate. Name the folder of its certificate with caCertsDir=

**Virtualbricks checks the client** with the token, as on a tcp socket,
inside TLS: TLS hides the proof, and the token keeps strangers out. The log
says ``connected to ssl port 8765 with the token``.


Client certificates
===================

With ``caCertsDir=DIR`` in the description of ``--listen``, an ssl socket
asks each client for a certificate in place of the token: one that a
``.pem`` file of the folder issued, or is. So each client can have a
certificate of its own, self-signed, whose ``.pem`` goes in the folder:

.. code-block:: sh

   # on Alice's laptop, in ~/vb
   openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 \
       -nodes -days 3650 -subj /CN=alice-laptop \
       -keyout alice.key -out alice.pem
   cat alice.key alice.pem > alice-key.pem
   chmod 600 alice.key alice-key.pem
   # on the lab machine, with a copy of alice.pem, and only it, in ~/vb/clients
   virtualbricks --no-gui --noterm --listen \
       'ssl:8765:interface=0.0.0.0:privateKey=~/vb/lab-key.pem:caCertsDir=~/vb/clients'

The client shows its certificate with ``privateKey=``, a file with the key
and the certificate, or with ``privateKey=`` and ``certKey=``, a file for
each:

.. code-block:: sh

   virtualbricks --connect \
       'ssl:lab.example:8765:caCertsDir=~/vb/lab:privateKey=~/vb/alice-key.pem' \
       --command status

The log names the client by the name of its certificate, and so does each
of its commands:

.. code-block:: text

   127.0.0.1 port 48142 connected to ssl port 8765 as alice-laptop
   Command from alice-laptop at 127.0.0.1: status

A client without a certificate, or with one that the folder doesn't trust,
is refused by TLS, before any command, and both ends say why:

.. code-block:: text

   lab.example asks for your certificate: privateKey= and certKey=
   lab.example refused your certificate
   [...#warn] 127.0.0.1 port 48158 on ssl port 8765: the TLS handshake
   failed: peer did not return a certificate
   [...#warn] 127.0.0.1 port 48156 on ssl port 8765: the TLS handshake
   failed: certificate verify failed

The folder is read at start: to let a new client in, or to shut one out,
add or remove its ``.pem`` and start Virtualbricks again.


Three protocols
===============

A socket carries lines of JSON, with ``protocol=text``, or the boxes of
AMP, Twisted's Asynchronous Messaging Protocol, the default. On them,
Virtualbricks speaks three protocols:

.. code-block:: text

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

**text**
   A line of the console in each request, the lines it prints in each
   answer. Any language that reads and writes JSON speaks it, and so does a
   shell with ``socat``.

**AMP 1**
   ``Hello``, who answers, and ``Run``, a line of the console and its
   lines. ``virtualbricks --command`` speaks it, and so can a program
   written with Twisted.

**AMP 2**
   On the same connection, once ``Hello`` agrees on it: a typed command for
   each command of the console, and the commands of the windows of
   ``virtualbricks --connect``, as ``Follow``, which sends the project and
   then each change.

What they share:

- **One request after the other.** Each connection runs its requests in the
  order they came. A client may send the next request before the answer to
  the one before, and the answers come in the same order. Connections don't
  wait for each other, nor for the terminal or the events of Virtualbricks.

- **The folder of the paths.** The paths of a command, as that of
  ``source FILE``, are read from ``cwd``, an absolute path that a request
  may give, or else from the folder where Virtualbricks runs. A client on
  another machine leaves ``cwd`` out: its folders aren't those of
  Virtualbricks.

- **The end.** When Virtualbricks quits, it closes each connection once the
  answers it owes are written, ``quit`` included; a client that doesn't
  read them within 2 seconds is cut off.


The text protocol
=================

Each message is a JSON object on a line of its own, in UTF-8, ended by a
newline. Virtualbricks writes the first line, the greeting, as soon as a
client connects: the ``protocol``, 1; its ``version``; its process,
``pid``; and the open ``project``, or ``null``. A client that doesn't know
the protocol sends nothing and closes the connection.

A request has ``line``, a line of the console as it is typed, and
``cwd``, optional. Its answer has ``ok``, whether the command was done,
``lines``, what it printed, and ``error``, why it failed, when ``ok`` is
``false``; ``lines`` is then what it printed before it failed. A line that
isn't a request gets an answer with ``ok`` ``false`` and why, and the
connection goes on. With ``socat``, on a text socket:

.. code-block:: text

   $ virtualbricks --no-gui --listen unix:~/labs/lab1.text:protocol=text &
   $ socat - UNIX-CONNECT:$HOME/labs/lab1.text
   {"protocol": 1, "version": "3.0.0.dev3", "pid": 430482, "project": "lab1"}
   {"line": "brick start sw2", "cwd": "/home/alice/labs"}
   {"ok": true, "lines": ["sw2 runs, process 430557"]}
   {"line": "status"}
   {"ok": true, "lines": ["BRICK  KIND    PROCESS", "sw1    Switch  430548", "sw2    Switch  430557"]}
   {"line": "brick start vm9"}
   {"ok": false, "lines": [], "error": "No brick named vm9"}
   {"cwd": "labs", "line": "status"}
   {"ok": false, "lines": [], "error": "Not a request: \"cwd\" is not an absolute path"}
   hello
   {"ok": false, "lines": [], "error": "Not a request: a line of JSON, as {\"line\": \"brick list\"}"}

Virtualbricks skips the empty lines, and closes the connection on a line
longer than 64 KiB. A key that a message doesn't need is ignored, and a
client should ignore the keys it doesn't know, so that a later version can
add some. Over text, an answer can be as long as it needs, and what a
command printed before it failed comes with its error:
``virtualbricks --command`` prints it, on a text socket, before the error.

**With the token.** On a tcp or ssl socket that asks for the token, the
first line asks for the proof, with the nonce of Virtualbricks; the client
answers with its own nonce and its proof, and the greeting follows, with
the proof of Virtualbricks:

.. code-block:: text

   {"protocol": 1, "auth": "token", "nonce": "a12ba50c...0080720"}
   {"nonce": "c41d...", "proof": "8e02..."}
   {"protocol": 1, "version": "3.0.0.dev3", "pid": 4200, "project": "lab1", "proof": "51b7..."}

A wrong proof, a line that isn't one, or none in 10 seconds gets an answer
with ``ok`` ``false`` and why, as ``Wrong token``, and the connection
closes. A whole client, in Python and nothing else, for a Virtualbricks
started with ``--listen tcp:8766:protocol=text``:

.. code-block:: python

   import hmac, json, os, secrets, socket, sys


   def proof(token, side, nonce, mine):
       text = f"virtualbricks {side} {nonce} {mine}"
       return hmac.new(token.encode(), text.encode(), "sha256").hexdigest()


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
           send(lines, nonce=mine, proof=proof(token, "client", nonce, mine))
           first = receive(lines)
           expected = proof(token, "server", nonce, mine)
           if not hmac.compare_digest(first.get("proof", ""), expected):
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


   config = os.path.expanduser("~/.config")
   config = os.environ.get("XDG_CONFIG_HOME") or config
   with open(os.path.join(config, "virtualbricks", "token")) as file:
       token = file.read().strip()
   lines = connect(8766, token)
   ask(lines, "status")
   ask(lines, "brick list")

It prints:

.. code-block:: text

   BRICK  KIND    PROCESS
   sw1    Switch  430548
   sw2    Switch  430557
   NAME  KIND    STATE    SUMMARY
   sw1   Switch  Running  32 ports
   sw2   Switch  Running  32 ports


AMP
===

AMP carries boxes: a key and its value, then another, and so on, up to a
key of no bytes. Each key and each value has its length first, in two
bytes: a key has from 1 to 255 bytes, a value from 0 to 65535. A request of
``Hello``, and its answer:

.. code-block:: text

      length  key         length  value
     +-------+-----------+-------+-----------------------+
     | 00 04 | _ask      | 00 01 | 1                     |
     | 00 08 | _command  | 00 05 | Hello                 |
     | 00 09 | protocols | 00 06 | 00 01 "1" 00 01 "2"   |
     | 00 00 |              the end of the box           |
     +-------+-----------+-------+-----------------------+
     | 00 07 | _answer   | 00 01 | 1                     |
     | 00 08 | protocol  | 00 01 | 2                     |
     | 00 07 | version   | 00 0a | 3.0.0.dev3            |
     | 00 03 | pid       | 00 06 | 430482                |
     | 00 07 | project   | 00 04 | lab1                  |
     | 00 00 |              the end of the box           |
     +-------+-----------+-------+-----------------------+

A request has ``_ask``, a tag that the client chooses, and ``_command``,
the name of the command, then its arguments. Its answer has ``_answer``,
the same tag, and the values; or, if the command failed, ``_error``, the
tag, ``_error_code`` and ``_error_description``. A request without
``_ask`` wants no answer. A value is text in UTF-8, an integer in decimal
digits, ``True`` or ``False``, bytes, or a list, each item with its length
first. An optional argument is left out of the box when it has no value.

Twisted adds two error codes to those of each command: ``UNHANDLED``, there
is no command of that name, and ``UNKNOWN``, a failure that Virtualbricks
didn't expect, after which the connection closes. A box that isn't one
closes the connection too.

A program written with Twisted has all this in
``twisted.protocols.amp``. In Python without Twisted,
``virtualbricks.console.ampbox`` reads and writes the boxes: it's what
``virtualbricks --command`` uses, so that it starts without the reactor. In
another language, a box is a few lines of code.


AMP protocol 1
==============

Four commands, in the module ``virtualbricks.console.ampwire``, which loads
nothing but Twisted's ``amp``. A program imports it, or copies it: the
manual page ``virtualbricks(1)`` has them as a program declares them.

.. code-block:: text

   Hello         protocols:[int]?
                 -> protocol:int version:str pid:int project:str?
   Run           line:str cwd:str? -> lines:[str]
   Challenge     -> nonce:str
   Authenticate  nonce:str proof:str -> proof:str

``Hello``
   Who answers, and the protocol of the connection from then on.
   ``protocols`` are those the program speaks; ``protocol`` is the highest
   that Virtualbricks speaks too, 1 without them. A connection that doesn't
   call ``Hello`` speaks protocol 1.

``Run``
   A line of the console and its ``cwd``; the answer is the lines it
   printed. If the command fails, the error says why, and what it printed
   before is lost.

``Challenge``, ``Authenticate``
   The proof of the token: ``Challenge`` answers the nonce of
   Virtualbricks, ``Authenticate`` takes the nonce of the program and its
   proof, and answers the proof of Virtualbricks, which the program checks.
   ``authenticate(vb, token)``, in ``ampwire``, does both and the check.

Their errors:

``COMMAND_FAILED``
   ``Run``: the command failed, or its ``cwd`` isn't an absolute path.

``ANSWER_TOO_LONG``
   ``Run``: the command was done, but its lines are longer than the 65535
   bytes of a value. A text socket carries them.

``TOKEN_NEEDED``
   On a socket that asks for the token, every command but ``Challenge`` and
   ``Authenticate`` fails until the program proves that it knows it.

``WRONG_TOKEN``
   The socket takes no token, and the connection goes on; or the proof is
   wrong, or ``Authenticate`` came without a ``Challenge``, and the
   connection closes.

``virtualbricks --command`` calls ``Hello``, proves the token if the answer
is ``TOKEN_NEEDED``, then sends each line with ``Run``. A program with
Twisted, on a unix socket:

.. code-block:: python

   import os

   from twisted.internet import endpoints, task
   from twisted.internet.defer import ensureDeferred
   from twisted.protocols import amp

   from virtualbricks.console.ampwire import Run


   async def main(reactor):
       path = os.path.expanduser("~/labs/lab1.sock")
       endpoint = endpoints.UNIXClientEndpoint(reactor, path)
       vb = await endpoints.connectProtocol(endpoint, amp.AMP())
       answer = await vb.callRemote(Run, line="brick start sw1")
       print("\n".join(answer["lines"]))


   task.react(lambda reactor: ensureDeferred(main(reactor)))

Over tcp, the endpoint is ``TCP4ClientEndpoint(reactor, "127.0.0.1",
PORT)``, and the program awaits ``authenticate(vb, token)`` before the
other commands. Over ssl, Twisted's ``tls:HOST:PORT:trustRoots=DIR``
checks the certificate of Virtualbricks and its name, and
``certificate=`` and ``privateKey=`` add the program's own.


AMP protocol 2
==============

A connection speaks protocol 2 once ``Hello`` has agreed on it: the
program calls ``Hello`` with ``protocols=[1, 2]``, and the answer has
``protocol`` 2. From then on, it speaks the commands of both protocols;
before, those of protocol 2 fail with ``PROTOCOL_NEEDED``.

The typed commands
------------------

A typed command for each command of the console, in the module
``virtualbricks.console.ampcommands``, which loads nothing else of
Virtualbricks but ``ampwire``. The name is the words of the command, each
with a capital letter: ``brick card add`` is ``BrickCardAdd``, ``status``
is ``Status``. The arguments are named after those of the console, in lower
case, with ``_`` for what isn't a letter or a digit: ``NAME`` is ``name``,
``KEY=VALUE`` is ``key_value``, ``--at`` is ``at``. A number is an
integer; an argument that repeats, a list; ``KEY=VALUE...``, a list of
records of ``key`` and ``value``; an option without a value, a boolean;
the rest, text; and what is optional in the console is optional here. Each
takes ``cwd`` too, as ``Run`` does, and answers ``lines``, what the console
prints:

.. code-block:: text

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
   ImageList
   ImageAdd           name:str path:str key_value:pairs?
   ImageShow          name:str
   ImageSet           name:str key_value:pairs
   ImageRename        name:str new:str
   ImageDelete        name:str
   SettingShow        key:str?
   SettingSet         key_value:pairs
   SettingUnset       key:[str]
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

``BrickSet(name="vm1", key_value=[{"key": "memory", "value": "1024"}])`` is
``brick set vm1 memory=1024``, and ``BrickStart(name=["sw1", "vm1"])`` is
``brick start sw1 vm1``. Where ``Run`` fails with ``COMMAND_FAILED``
whatever went wrong, the typed commands say what it was:

``NOT_FOUND``
   A name of the command names nothing there: a brick, an event, an image,
   a project, a program or a file. Nothing was done.

``BAD_ARGUMENT``
   An argument isn't one the command takes; or the box has a key that the
   command doesn't have, or lacks one it needs, which Twisted would drop or
   close the connection on. Nothing was done.

``COMMAND_FAILED``
   The command failed on the way: a program or a file said no. Part of it
   may be done.

``PROTOCOL_NEEDED``, ``ANSWER_TOO_LONG``, ``TOKEN_NEEDED``
   As above.

In the modules, ``NotFound`` and ``BadArgument`` are subclasses of
``CommandFailed``: a program that catches ``CommandFailed`` catches the
three.

The commands of the windows
---------------------------

What the windows of ``virtualbricks --connect`` need that the console has
no command for, in the module ``virtualbricks.remote.commands``. A table, a
state and the other structured values are JSON in a text, since AMP has no
tables:

.. code-block:: text

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
   ProgramsFound      vde_path:str qemu_path:str
                      -> vde:str qemu:str
   Attach             brick:str console:str ->

- ``Apply`` is the OK of the panel of a brick, an event or an image: the
  settings it changed, the plugs it moved, and, when they changed, the cards
  of a machine or the states of a Netemu. Only the keys given change, so
  two windows that change different keys of a brick keep both.
- ``Connect`` is a drop in the Topology: a free plug, or a new card of a
  machine.
- ``MakeImage``, ``StartOver``, ``TrashFile`` and ``Relink`` work on the
  files of the images and of the private copies.
- ``ProjectNames``, ``ProjectSummary``, ``DiskUsage``, ``Readme`` and
  ``SetReadme`` fill the Projects window and the Readme tab.
  ``ReadmePicture`` sends a picture of a README in pieces, from
  ``offset``, until the program has ``size`` bytes, up to 10 MB.
- ``QemuFacts``, ``MachineProperties`` and ``UsbDevices`` are what the QEMU
  and the USB devices of the lab machine have, for the panel of a virtual
  machine; ``ImageFacts`` is what a disk image is; ``Folder`` completes a
  path as it is typed, at most 200 entries; ``ProgramsFound`` says what the
  folders of QEMU and VDE hold, for the Settings window.

The commands that only read the machine, ``QemuFacts``,
``MachineProperties``, ``UsbDevices``, ``ImageFacts``, ``DiskUsage``,
``ReadmePicture``, ``Folder`` and ``ProgramsFound``, answer as soon as they
can, beside the requests that wait. The others wait for their turn, as the
typed commands do, and Virtualbricks logs them.

Follow and the pushes
---------------------

``Follow`` asks for the project and for its changes. Virtualbricks sends
them as pushes, commands that it calls on the program without ``_ask``,
which want no answer:

.. code-block:: text

   Opened             project:str? settings:str machine:str
   Changed            kind:str name:str table:str state:str
   Renamed            kind:str old:str new:str
   Removed            kind:str name:str
   Synced
   SettingsChanged    settings:str
   Logged             message:str
   Quitting

First ``Opened``, with the settings and what the lab machine has: its
version, its workspace, its folders, whether it has a trash, its QEMU
programs, the programs it lacks for each kind of brick, and whether KSM
runs. Then a ``Changed`` for each image, brick and event, each brick after
those it plugs into, with its ``table``, as the project file writes it, and
its ``state``, what the file doesn't: the process of a brick, the private
copies of a machine, the file of an image, the seconds an event still
waits. Then ``Synced``, the last 500 messages of the log, and the answer.
From then on, Virtualbricks gathers what changes and sends it once a turn
of its loop, each object once, as it is then. When another project opens,
the copy starts over with ``Opened``.

A program that follows declares the eight pushes, and has a responder for
each: Twisted closes the connection on a command it has no responder for.
A program that follows the project and drives it with typed commands:

.. code-block:: python

   import json, os

   from twisted.internet import defer, endpoints, task
   from twisted.protocols import amp

   from virtualbricks.console.ampcommands import BrickSet, BrickStop, NotFound
   from virtualbricks.console.ampwire import Hello, authenticate
   from virtualbricks.remote import commands


   class Follower(amp.AMP):
       """Prints what changes: a responder for each of the eight pushes."""

       @commands.Opened.responder
       def opened(self, project, settings, machine):
           print("Opened", project)
           return {}

       @commands.Changed.responder
       def changed(self, kind, name, table, state):
           print("Changed", kind, name, json.loads(state))
           return {}

       @commands.Renamed.responder
       def renamed(self, kind, old, new):
           return {}

       @commands.Removed.responder
       def removed(self, kind, name):
           return {}

       @commands.Synced.responder
       def synced(self):
           print("Synced")
           return {}

       @commands.SettingsChanged.responder
       def settings_changed(self, settings):
           return {}

       @commands.Logged.responder
       def logged(self, message):
           return {}

       @commands.Quitting.responder
       def quitting(self):
           return {}


   async def main(reactor):
       endpoint = endpoints.TCP4ClientEndpoint(reactor, "127.0.0.1", 8765)
       vb = await endpoints.connectProtocol(endpoint, Follower())
       config = os.path.expanduser("~/.config")
       config = os.environ.get("XDG_CONFIG_HOME") or config
       with open(os.path.join(config, "virtualbricks", "token")) as file:
           await authenticate(vb, file.read().strip())
       hello = await vb.callRemote(Hello, protocols=[1, 2])
       if hello["protocol"] != 2:
           raise SystemExit("It doesn't speak protocol 2")
       await vb.callRemote(commands.Follow)
       print(await vb.callRemote(BrickStop, name=["sw2"]))
       ports = {"key": "ports", "value": "16"}
       print(await vb.callRemote(BrickSet, name="sw2", key_value=[ports]))
       try:
           await vb.callRemote(BrickStop, name=["sw9"])
       except NotFound as exc:
           print("NotFound:", exc)


   task.react(lambda reactor: defer.ensureDeferred(main(reactor)))

It prints:

.. code-block:: text

   Opened lab1
   Changed brick sw1 {'pid': 430548}
   Changed brick sw2 {'pid': 430557}
   Synced
   {'lines': ['sw2 stopped']}
   Changed brick sw2 {'pid': None}
   Changed brick sw2 {'pid': None}
   {'lines': []}
   NotFound: No brick named sw9

Attach
------

``Attach`` joins the program to a console of a running brick: ``monitor``,
its control monitor, or ``serial``, the serial socket of a machine.
Virtualbricks connects to the console, then answers, and from then on the
connection carries the bytes of the console both ways, and nothing else:
it's AMP's ``ProtocolSwitchCommand``. When either end closes, so does the
other. So a program opens a new connection for each console, proves the
token if asked, agrees on protocol 2, then calls ``Attach``. The windows of
``virtualbricks --connect`` join that connection to a terminal of their
own, with ``vdeterm`` or ``unixterm``.

.. code-block:: text

     terminal     program            Virtualbricks     console
        |            |                     |              |
        |            |-- Attach brick vm1, |              |
        |            |   console monitor ->|-- connects ->|
        |            |<----------- answer -|              |
        |<= bytes ==>|<====== bytes ======>|<== bytes ===>|

Versions
--------

Protocol 2 keeps its commands as they are. A later Virtualbricks may add
commands to it, and optional arguments to its commands, and nothing else:
an older one answers a command it doesn't have with ``UNHANDLED``, and an
argument it doesn't know with ``BAD_ARGUMENT``, so a program knows that
they weren't done. A change of any other kind makes protocol 3, which would
take the place of 2: a program that speaks both calls ``Hello`` with
``protocols=[1, 2, 3]``. The sources keep the commands of protocol 2 in
``tests/data/amp-protocol-2.txt``, and the tests compare it with the
modules, so that no change slips in.


The windows of another Virtualbricks
====================================

``--connect`` without ``--command`` or ``--run`` opens the windows of the
Virtualbricks it names: the bricks run there, on the lab machine, and the
windows here. That Virtualbricks listens on an AMP socket, with its own
windows or with ``--no-gui``, and both ends run the same version:

.. code-block:: sh

   # on the lab machine
   virtualbricks --no-gui --noterm --listen \
       'ssl:8765:interface=0.0.0.0:privateKey=~/vb/lab-key.pem'
   # on your desktop
   virtualbricks --connect 'ssl:lab.example:8765:caCertsDir=~/vb/lab'

``virtualbricks --connect`` alone opens the windows of a Virtualbricks of
yours on this machine, found as ``--command`` finds it: that of
``--workspace``, or the only one that listens. The windows call it *this
computer*.

The windows speak protocol 2, so ``--connect`` takes no ``protocol=text``
here; nor ``--no-gui``, ``--lock`` or ``--listen``, which are for the
Virtualbricks that runs the bricks. They prove the token, or show their
certificate, as ``--command`` does.

- **They follow the project there**: its bricks, events and images, their
  processes, the settings and the log. What the console or other windows
  change there shows at once, and the title names the project and where it
  runs.
- **What they do goes there**: a start, a new brick, the OK of a panel,
  which sends only the keys it changed.
- **What they show is the lab machine's**: its QEMU programs and what they
  can do, its USB devices, the files of its images, its projects. A path is
  a path there, typed in an entry that completes from the folders there.
  Settings has three pages: this computer, as the terminal; the lab
  machine, its KSM and the audio driver of QEMU; and the project.
- **Consoles open here.** *Open Control Monitor* starts a terminal on this
  computer, joined to the console there with ``Attach``.
- **When the connection is lost**, a bar says why, and *Reconnect* starts
  the copy over. *Quit* closes the windows; the Virtualbricks there goes
  on.

Some items wait for a later version, greyed: Import and Export, saving or
merging the private copy of a disk, copying an image to the image folder,
*Show in Files*, and *Terminate*.


Limits
======

A line of the text protocol
   64 KiB; a longer one closes the connection.

A key of AMP
   255 bytes.

A value of AMP
   65535 bytes. A longer answer is ``ANSWER_TOO_LONG``, after the command
   was done; a longer push isn't sent, and the log says so.

The path of a unix socket
   107 bytes.

The token
   At least 16 characters; Virtualbricks makes them of 43.

The proof of the token
   10 seconds from connecting.

The last answers, at the end
   2 seconds for the client to read them.

The log, for a program that follows
   The last 500 messages, then each new one.


Try it
======

All of this is in the ``develop`` branch: the `first post
<{filename}/news/whats-coming-in-virtualbricks-3-0.rst>`_ says how to
install it. The manual pages go further: ``virtualbricks(1)`` for the
options, the console and its commands, and ``virtualbricks-control(7)`` for
the protocols, for whoever writes a client. Start a lab with ``--listen``,
drive it from another terminal, write a client in your language, and tell
us what breaks on `GitHub
<https://github.com/virtualsquare/virtualbricks/issues>`_.
