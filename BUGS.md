# Bugs

Bugs found and not fixed yet, by area, each with how it was seen. A fixed
one leaves the list.

## Control socket

- [ ] **`Changed` comes after the answer of `BrickStop`.** Over AMP 2, with
  `Follow`, the `Changed` push of a brick that stops (`pid` None) comes
  after the answer of `BrickStop`, every time. `virtualbricks-control`(7)
  promises that "once a command is answered, the program has what it
  changed", and `BrickStart` keeps the promise. Seen on 3.0.0.dev3, on 6
  October 2026, with a switch:

  ```
  ask BrickStart
  Changed brick sw2 {'pid': 430716}
  answer {'lines': ['sw2 runs, process 430716']}
  ask BrickStop
  answer {'lines': ['sw2 stopped']}
  Changed brick sw2 {'pid': None}
  ```

  In one run, two `Changed brick sw2 {'pid': None}` came after the answer.
  The answer of a typed command waits for `pushes_first()`
  (`virtualbricks/remote/follower.py`), from `_responder()` in
  `virtualbricks/console/control.py`.

## Signals

- [ ] **Two SIGTERMs in a row hang `--no-gui -l FILE`.** The second SIGTERM
  arrived while the handler of the first was writing "Received SIGTERM,
  shutting down." to the log file: the process stays, ignores further
  SIGTERMs, and its socket doesn't answer. Seen on 6 October 2026 with
  `pkill` matching both `timeout` and the `python` it ran, so each sent one;
  Python 3.10, Twisted 26.4.0. The Python stack, from `py-bt` in gdb, has
  Twisted's `sigTerm()` in `sigTerm()`, both at the `self._block.acquire()`
  of `threading._RLock`, through `LogFile.write()`, which
  `twisted.python.threadable` synchronizes. That lock is the pure Python
  `RLock`: the signal came after the first `_block.acquire()` returned and
  before `_owner` was set, so the second handler waits for a lock that its
  own thread holds. The log file of `-l` is a `LogFile` (`_log_file` in
  `virtualbricks/cli.py`); the standard output takes no such lock.
  `sigInt()` logs the same way, so two Ctrl+C might hang it too (not
  tried).

## Archives

- [ ] **An exported archive is readable only by its owner.** The export
  writes the archive to a temporary file made by `tempfile.mkstemp()`,
  which creates it with mode 0600 whatever the umask, and renames it to the
  `.vbp` at the end, so the archive keeps 0600 (`write_archive()` in
  `virtualbricks/config/archive.py`). The import, instead, gives the folder
  it makes the permissions of a normal folder ("mkdtemp made the folder
  private; a project folder isn't", in `move_into_place()` of
  `virtualbricks/config/importing.py`). Seen on 3.0.0.dev3, on 7 October
  2026, writing `virtualbricks-vbp`(5): an export with the umask 022 gave
  `-rw-------` for the archive, also with `compression = "gzip"`, as the
  same file is written either way.
- [ ] **A gzip archive names the temporary file in its header.** Without
  `qemu-img`, the export compresses the archive with
  `gzip.GzipFile(fileobj=..., mtime=0)` (`_Output` in
  `virtualbricks/config/archive.py`), which takes the name of the file
  from `fileobj.name`: the header of the archive holds the name of the
  unfinished archive, `.lab.vbp.XXXXXXXX.part`, with the flag FNAME.
  `gunzip -N` restores the tar under that hidden name, and `gzip -lN`
  lists it. Seen on 3.0.0.dev3, on 7 October 2026, writing
  `virtualbricks-vbp`(5):

  ```
  $ gzip -lN < lab.vbp
           compressed        uncompressed  ratio uncompressed_name
                  617               10240  94.4% .gz.vbp.2or1v0ic.part
  ```

## Manual pages

- [ ] **virtualbricks(1): the ssl examples pass the certificate as the
  key.** They pass `privateKey=~/vb/lab.pem`, but the `openssl` command of
  the same page writes the key to `lab.key` and the certificate to
  `lab.pem`. Either the examples pass
  `privateKey=~/vb/lab.key:certKey=~/vb/lab.pem`, or the command writes
  both into one file. Four examples in `docs/man/virtualbricks.1.md`, the
  same in `docs/command-line.html` and in `docs/man/virtualbricks.1`.
- [ ] **virtualbricks(1): the JSON protocol greets with version
  `"2.1.0"`.** The example of the token's proof, in "The JSON protocol",
  greets with `"version": "2.1.0"`; Virtualbricks 3 greets with its own,
  as `virtualbricks-control`(7) shows with `"3.0.0"`. Same three files.
