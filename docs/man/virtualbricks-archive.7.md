---
title: VIRTUALBRICKS-ARCHIVE
section: 7
header: Virtualbricks Manual
footer: virtualbricks VERSION
date: DATE
---

# NAME

virtualbricks-archive - the process that reads and writes project archives

# SYNOPSIS

*project*.vbp

**python -m virtualbricks.config.archive** **<** *job.toml*

# DESCRIPTION

Virtualbricks exports a project to an archive, a *.vbp* file, and imports a
project from one, on the same computer or on another. The archive holds the
project file, its README, the private disks of the virtual machines and, if
you choose, the disk images they are based on: often gigabytes.

So the application never reads or writes an archive itself. For each job,
inspecting an archive, exporting a project or importing one, it starts a
process of its own, the *archive process*. It writes the job to the process's
standard input, as TOML, and follows the job on the process's standard output,
one JSON object a line, while the interface stays responsive. The process runs
one job and exits. It runs at a lower priority, **nice** 10, and it can be
stopped at any time with SIGTERM.

```
  application                         archive process
 +------------+                      +-------------+
 |            |-- stdin: the job --->|             |
 | ArchiveJob |   TOML, then EOF     |   main()    |-> bsdtar
 |            |                      |             |   or tar
 |            |<- stdout: messages --|             |
 |            |   JSON, one a line   |             |-> qemu-img
 |            |<- stderr ------------|             |
 |            |   kept for errors    |             |
 |            |-- SIGTERM: cancel -->|             |
 |            |<- exit status -------|             |
 +------------+                      +-------------+
```

This page sums up the archives (**THE ARCHIVE**), and describes the protocol
between the application and the process (**THE PROCESS**), the three jobs
(**JOBS**), the progress they report (**PROGRESS**), the tools they run
(**ARCHIVE TOOLS**) and how the application drives them (**THE APPLICATION'S
SIDE**). It's for whoever works on that code, and for anyone who wants to run
the process by hand, to look into an archive or to script an export.

# THE ARCHIVE

An archive, a *.vbp* file, is a tar file in the pax format, which
**virtualbricks-vbp**(5) describes in full. This page needs only what
follows.

Each member is a file of the project's folder, under its path in the folder,
or an image of the project, under *IMAGES/*, named after the image in the
project file. The name of a member gives its *kind*, the word that the
messages of the process use:

**contents**
:   **contents.toml**, the list of the other members.

**project**, **legacy project**
:   **project.toml**, the project file; **.project** or **.project~**, the
    project file of Virtualbricks 2.1 and older.

**readme**
:   **README.md**, or **README** before 3.0.

**disk**
:   *vm*\_*device*.cow, the private disk of a virtual machine.

**image**
:   IMAGES/*image*, a disk image; *.images/image* in older archives.

**other**
:   Any other file of the folder.

A new archive starts with its *head*: **contents.toml**, then the project
file and the README. An inspection reads the head and stops there. The
archives of older versions have no **contents.toml**, and an inspection
reads them to their end.

When **qemu-img** is installed, the export compresses each disk and each
image in the qcow2 format on its own, and **contents.toml** marks it
*packed*, with its size before, its *real_size*; the import turns them back
into normal qcow2 files. Without **qemu-img**, the export compresses the
whole archive with gzip instead.

Disks are sparse files, and the archive keeps their holes: a disk of 20 GB
can take 2 GB.

# THE PROCESS

## Starting

The application starts the process with its own Python interpreter and its own
environment:

```
python -m virtualbricks.config.archive
```

The process lowers its priority to **nice** 10, and
handles SIGTERM.

The process always comes from the same installation as the application, so
the protocol has no version: it changes with the code, and this page with
it.

## The job

The process reads its standard input to the end, then parses it as a TOML
table. The key **job** says which job it is, **inspect**, **export** or
**import**; the other keys depend on the job, and are described in **JOBS**.

```
job = "inspect"
archive = "/home/user/lab.vbp"
```

An unknown job is an error, as the other errors of the job. A missing key, or
one of the wrong type, is a bug of the caller: the process reports it with its
traceback.

## Messages

The process writes to its standard output one JSON object a line, and flushes
each one. Every object has one key, which says what it is:

**progress**
:   {\"step\": *step*, \"done\": *bytes*, \"total\": *bytes*}: how far a step
    of the job has gone; see **PROGRESS**.

**created**
:   *path*: the process created a file or a folder outside the job's folder,
    which it removes if the job doesn't end well; see **Cleaning up**.

**head**
:   *contents*: what an inspection knows of an older archive before reaching
    its end; see **inspect**.

**result**
:   *result*: the job is done. It depends on the job.

**error**
:   *message*: the job failed.

The messages come in this order:

```
messages = *( progress / created / head ) [ result / error ]
```

**result** or **error** is the last message; there is none when the job is
cancelled or the process dies. A reader ignores anything else: an empty line,
a line that isn't JSON, a value that isn't an object, an object with none of
these keys.

An import, for one, says:

```
 application                                  process
   |                                            |
   |  job = "import" ... EOF                    |
   |------------------------------------------->|
   |                                            | extract
   |  {"progress": {"step": "extract", ...}}    |
   |<-------------------------------------------|
   |  {"created": ".../debian.qcow2"}           | copy
   |<-------------------------------------------|
   |  {"progress": {"step": "unpack", ...}}     | unpack
   |<-------------------------------------------|
   |  {"result": {"name": "lab", ...}}          |
   |<-------------------------------------------|
   |  exit status 0                             |
   |<- - - - - - - - - - - - - - - - - - - - - -|
```

## Ending

The process exits when its job ends, with:

**0**
:   The job is done: the last message is **result**.

**1**
:   SIGTERM cancelled the job. The process removed what it wrote, and sent
    nothing more.

**2**
:   The job failed: the last message is **error**, with a message for the
    user, as \"the archive has no project file\" or the error of **bsdtar**
    or **qemu-img**.

**3**
:   A bug: the last message is **error**, with the Python traceback.

A process killed by another signal sends nothing more, and may leave files
behind: see **Cleaning up**. The messages tell the outcome, not the exit
status: a job is done when **result** came.

## Cancelling

SIGTERM stops the job wherever it is. The process stops its **tar** or
**qemu-img**, removes the files it wrote, and exits with 1:

- An export removes its unfinished archive and its folder. An archive that
  was already there under the same name is left as it was.
- An import removes its folder in the workspace and the images it copied to
  the shared images.
- An inspection writes nothing.

## Cleaning up

A job writes its files where they end up, under a temporary name, and renames
them at the end, so that a job that doesn't end leaves nothing behind. When
the job fails or is cancelled, the process removes them. When the process dies
before it can, the application removes them: the job's folder, when it made
it, and every path that the process sent with **created**.

.*name*.vbp.*XXXXXXXX*.part, .virtualbricks-export-*XXXXXXXX*/
:   The unfinished archive and its folder, next to the archive, which the
    export makes and sends with **created**.

*workspace*/.importing-*name*-*XXXXXXXX*/
:   The folder of an import, which the application makes before it starts
    the process.

*workspace*/shared_images/*file*
:   An image that the import copied to the shared images, and sent with
    **created**.

The application removes them only when the process ended without a
**result**.

# JOBS

## inspect

Read what an archive holds: its project file, its README and the list of its
members.

**archive** = *path*
:   The archive to read.

The result is an object:

**path** = *string*
:   The archive.

**data** = *object*
:   The project file, in the current format: converted from **.project**, or
    upgraded from an older **project.toml**.

**description** = *string*
:   The README, or \"\" when there is none. Bytes that aren't UTF-8 are
    replaced.

**members** = *array*
:   \[*name*, *size*, *kind*, *packed*, *real_size*\] for each member, in the
    order of the archive: from **contents.toml** when the archive has one,
    otherwise from the tar headers, with *packed* false and *real_size* 0.

**complete** = *boolean*
:   Whether **members** lists every member of the archive.

**report** = *array*
:   \[*level*, *text*, *where*\] for each problem found in the project file;
    *level* is **info**, **warning** or **error**, *where* the key it's
    about, or \"\".

**converted** = *boolean*
:   Whether **data** was converted from **.project**.

An inspection sends the progress of the step **read**. A new archive is read up
to the end of its head: the result comes with **complete** true, and the
progress stops early. An archive without **contents.toml** is read to its end;
as soon as its project file is read, the inspection sends a **head** message,
an object as the result with **complete** false and the members read so far.
The Import window shows its form from the head, and completes it with the
result.

```
  new archive, with contents.toml
  +----------+---------+--------+ - - - - - - - - - - - - +
  | contents | project | README |   disks, images...      |
  +----------+---------+--------+ - - - - - - - - - - - - +
  '------------ read -----------'  not read
                                '-> result, complete

  older archive, without contents.toml
  +---------+---------+------------------------------------+
  |   ...   | project |   README, disks, images...         |
  +---------+---------+------------------------------------+
  '------ read -------'-> head, not complete
  '------------------------- read -------------------------'
                                        result, complete <-'
```

The inspection fails when the archive has no project file, when the project
file can't be read or converted, or when **contents.toml** comes from a newer
Virtualbricks.

## export

Write an archive of a project:

```
job = "export"
project = "/home/user/.virtualbricks/lab"
output = "/home/user/lab.vbp"
files = ["project.toml", "README.md", "vm1_hda.cow"]
images = [["debian", "/srv/vm/debian-12.qcow2"]]
compression = "none"
qemu_img = "/usr/bin/qemu-img"
```

**project** = *path*
:   The folder of the project.

**output** = *path*
:   The archive to write. A file with that name is replaced when the export
    ends.

**files** = *array of strings*
:   The files of the project to store, relative to its folder. The Export
    window always stores **project.toml** and the README, **README.md** or,
    in a project not opened since 3.0, **README**, and lets you choose
    the private disks, the other files and the images; it never stores what
    older versions left in the folder: the *.images* folder and the
    *.project* files. The export leaves out a folder *IMAGES* of the
    project, as an import would take its files for images, and reports
    it.

**images** = *array* of \[*name*, *path*\]
:   The images to store, as *IMAGES/name*.

**compression** = **\"gzip\"** \| **\"none\"**, default **\"gzip\"**
:   Whether to compress the archive with gzip. The application asks for
    **\"none\"** when it gives **qemu_img**.

**qemu_img** = *path*, default **\"\"**
:   The **qemu-img** that packs the disks, or \"\" not to pack them.

The export takes these steps:

1. It creates the unfinished archive, .*name*.vbp.*XXXXXXXX*.part, and a
   folder, .virtualbricks-export-*XXXXXXXX*, both next to the archive because
   the packed disks can be large, and sends them with **created**.
2. It puts in the folder each member under its name in the archive: a qcow2
   disk or image packed by **qemu-img**, in the step **pack**, and any other
   file as a symbolic link to it.
3. It writes **contents.toml** in the folder.
4. It writes the folder into the unfinished archive with the archive tool,
   following the links, through gzip if asked, in the step **write**.
5. It renames the unfinished archive to *output*, and removes the folder.

```
 lab/project.toml  -- link -->  +---------------------------+
 lab/README.md     -- link -->  | .virtualbricks-export-*/  |
 lab/vm1_hda.cow   -- pack -->  |   contents.toml           |
 debian-12.qcow2   -- pack -->  |   project.toml  README.md |
                                |   vm1_hda.cow             |
                                |   IMAGES/debian           |
                                +---------------------------+
                                     | tar, in order
                                     v
                                .lab.vbp.XXXXXXXX.part
                                     | rename, at the end
                                     v
                                lab.vbp
```

The result is an object:

**output** = *string*
:   The archive.

**size** = *integer*
:   Its size, in bytes.

**report** = *array*
:   \[*level*, *text*, *where*\] for each problem, as a disk stored as it is.

## import

Make a project of an archive. The application reads the archive with
**inspect** first, and asks the user what to do with each image; this job does
the rest:

```
job = "import"
archive = "/home/user/lab.vbp"
staging = "/home/user/.virtualbricks/.importing-lab-k2x9q1ab"
destination = "/home/user/.virtualbricks/lab"
qemu_img = "/usr/bin/qemu-img"

[[images]]
name = "debian"
choice = "copy"
path = "/home/user/.virtualbricks/shared_images/debian-12.qcow2"
fallback = ""

[settings]
qemu_path = "/usr/bin"
```

**archive** = *path*
:   The archive to import.

**staging** = *path*
:   An empty folder of the workspace, .importing-*name*-*XXXXXXXX*, that the
    application creates and the list of projects ignores. The archive is
    extracted there.

**destination** = *path*
:   The folder of the new project, *workspace*/*name*. If a folder with that
    name appeared meanwhile, the import takes the next free name, *name*-2,
    *name*-3... and says so in its report. An import never replaces a
    project.

**images** = *array of tables*
:   What to do with each image of the project file:

    **name** = *string*
    :   The name of the image in the project file.

    **choice** = **\"copy\"** \| **\"use\"** \| **\"skip\"** \| **\"auto\"**
    :   **copy** moves the image from the archive to **path**, or to the
        next free name, *debian-12.1.qcow2*, *debian-12.2.qcow2*... **use**
        uses the file **path** of this computer. **skip** leaves the image
        unset: its disks get one in their settings later. **auto** copies the
        image if the archive has it, otherwise uses **fallback**, otherwise
        skips it; the application sends it for the images of an older archive
        that the inspection hadn't seen yet when the import started.

    **path** = *path*
    :   Where the copy goes, or the file used.

    **fallback** = *path*
    :   For **auto**: the file to use if the archive doesn't have the image,
        or \"\".

**settings** = *table*
:   The settings of the project to replace with this computer's:
    **qemu_path** and **vde_path**, the folders of QEMU and VDE.

**qemu_img** = *path*
:   The **qemu-img** that unpacks and rebases the disks, or \"\".

The application gives every image a default. An image that the archive has is
copied into the shared images, *workspace*/shared_images, unless they have a
file with the same file name and size, which is used. An image that the archive
doesn't have uses its file if this computer has it at the same path, or a file
of the shared images with its name, and is left unset otherwise. A setting is
replaced, unless you say otherwise, when its folder doesn't exist on this
computer.

The import takes these steps:

```
 workspace/
 |
 +-- .importing-lab-k2x9q1ab/   1  extract the archive here
 |     contents.toml            2  note what's packed, remove
 |     project.toml             3  read, or convert .project
 |     README.md
 |     IMAGES/debian  ----.     4  copy, use or skip images
 |     vm1_hda.cow        |     5  rewrite project.toml
 |                        |     6  rebase -u the private
 |                        |        disks on their images
 +-- shared_images/       |     7  unpack the packed disks
 |     debian-12.qcow2 <--'     8  turn zeros into holes
 |
 +-- lab/  <------------------  9  rename into place
```

1. Extract the archive into **staging**, in the step **extract**.
2. Read which members are packed from **contents.toml**, and remove it: it
   isn't a file of the project. Rename **README**, the README of before
   3.0, to **README.md**, unless there is one.
3. Read the project file and upgrade it, or convert **.project**.
4. Move each copied image to the shared images, sending it with
   **created**; then remove the *IMAGES* folder, or *.images* in an older
   archive, with the images that aren't copied.
5. Rewrite **project.toml** with the path of each image, \"\" for an image
   left unset, and with **settings**.
6. Point each private disk at its image, in the format of the image:
   **qemu-img rebase -u -b** *image* **-F** *format* *disk*.
7. Unpack the packed disks and images, in the step **unpack**.
8. After GNU **tar** or **tarfile**, turn the runs of zeros of the private
   disks and of the copied images into holes.
9. Rename **staging** to the project's folder, with the permissions of a
   normal folder.

The result is an object:

**name** = *string*
:   The name of the new project: the name of **destination**, or the next free
    one.

**report** = *array*
:   \[*level*, *text*, *where*\] for each problem: an image left unset, a
    disk left compressed or not rebased, what the conversion of **.project**
    found.

# PROGRESS

Each step counts bytes, *done* of *total*:

**read**, in **inspect**
:   The bytes of the archive read, of its size.

**pack**, in **export**
:   The bytes of the disks and images packed, of their data without holes.

**write**, in **export**
:   The bytes of the tar written, before gzip, of the data of the members
    without holes.

**extract**, in **import**
:   The bytes of the archive given to the archive tool, of its size.

**unpack**, in **import**
:   The bytes of the packed disks and images unpacked, of their size.

A step sends its progress at most ten times a second, and when it ends; a step
with nothing to do sends nothing. The steps of **pack** and **unpack** follow
the percentage that **qemu-img** prints. The *done* of a step can stay below
its *total*, as when an inspection stops at the head of an archive, or go past
it, as in **write**, which counts the tar headers too: a progress bar shows
the smaller of the two.

# ARCHIVE TOOLS

The process runs the first archive tool it finds: **bsdtar**; otherwise
**tar**, if the first line of **tar --version** says it's GNU tar, as the
**tar** of BusyBox doesn't keep holes; otherwise Python's **tarfile**.

Reading the head
:   Always with **tarfile**, reading the archive as a stream. If **tarfile**
    finds a member that it would read wrong (see **BUGS**), the process lists
    the archive with the tool instead, **bsdtar -t -v -f** *archive* or **tar
    -t -v --quoting-style=literal -f** *archive*, and extracts the files of
    the head with **-x -O -f** *archive* *member*.

Writing
:   **bsdtar -c -L --format pax -f - -C** *folder* **--** *members*, or
    **tar -c --sparse --dereference --format=posix -f - -C** *folder*
    **--** *members*, or **tarfile** with the sparse members written by
    Virtualbricks. The process compresses the output with gzip itself, so the
    archive is the same whatever the tool.

Extracting
:   The process feeds the archive to the tool through a pipe, so that the
    progress is the same with every tool: **bsdtar -x -S -f - -C** *folder*,
    or **tar -x -f - -C** *folder* with **--gzip**, **--bzip2**,
    **--xz** or **--zstd**, as GNU tar doesn't recognize the compression
    of a pipe. With **tarfile**, members with an absolute name, with *..* in
    their name, links and devices are skipped.

# THE APPLICATION'S SIDE

The module *virtualbricks/config/archive.py* has both sides of the protocol.
In the application, an **ArchiveJob** runs a job:

- **start**(*reactor*) starts the process with **reactor.spawnProcess**, writes
  the job as TOML and closes the standard input.
- A **progress** message calls *on_progress*(*step*, *done*, *total*), a
  **head** calls *on_head*(*table*), and a **created** adds its path to the
  leftovers.
- When the process ends, the Deferred **done** fires with the result, if one
  came, whatever the exit status. Otherwise the leftovers are removed, and
  **done** fails with **ArchiveCancelled** after **cancel**(), or else with
  **ArchiveError**, whose message is the **error** message, or the standard
  error of the process, or \"the process stopped\".
- **cancel**() sends SIGTERM to the process.

Three functions make the jobs, the first two in
**virtualbricks.config.archive** and the last in
**virtualbricks.config.importing**, and
**done** fires with what they make of the result:

**inspect_archive**(*path*, *on_head*, *on_progress*)
:   Fires with an **ArchiveContents**; *on_head* gets one too.

**export_project**(*project*, *output*, *files*, *images*, *on_progress*, *qemu_img*)
:   Fires with the result object. Asks for **\"none\"** compression when
    *qemu_img* is given.

**import_project**(*plan*, *workspace*, *on_progress*, *qemu_img*)
:   Creates the **staging** folder, a leftover from the start, and fires with
    an **ImportResult**, its name and its report. **plan_import** makes the
    *plan*, with the default of every choice, from an **ArchiveContents**;
    **update_plan** settles it with the result of the inspection when the
    head came first.

The Import window runs an inspection as soon as an archive is chosen, and
cancels it when another is chosen or when the import starts, which reads the
whole archive anyway. Closing the Import window cancels its inspection, but
closing either window lets an import or an export go on to its end, and the
application logs its result.

```
from virtualbricks.config.archive import inspect_archive

def show(contents):
    print(contents.description)
    for member in contents.members:
        print(member.kind, member.name, member.size)

job = inspect_archive(
    "/home/user/lab.vbp",
    on_progress=lambda step, done, total: print(step, done),
)
job.done.addCallback(show)
```

# FILES

*name*.vbp
:   An archive.

.*name*.vbp.*XXXXXXXX*.part
:   An archive being written, next to it.

.virtualbricks-export-*XXXXXXXX*/
:   The members of an archive being written, next to it.

*workspace*/.importing-*name*-*XXXXXXXX*/
:   A project being imported.

*workspace*/shared_images/
:   The shared images, where the import copies the images.

*workspace*/*name*/
:   An imported project.

# EXAMPLES

Run the process by hand. Inspect an archive:

```
$ printf 'job = "inspect"\narchive = "/home/user/lab.vbp"\n' |
>     python -m virtualbricks.config.archive
{"progress": {"step": "read", "done": 512, "total": 409600}}
{"result": {"path": "/home/user/lab.vbp", "data": ...}}
```

The result, laid out:

```
{
  "path": "/home/user/lab.vbp",
  "data": {
    "format": 1,
    "images": {
      "debian": {"path": "/srv/vm/debian-12.qcow2", ...}
    },
    "bricks": {"vm1": {"type": "qemu", ...}}
  },
  "description": "A two-host lab.\n",
  "members": [
    ["project.toml", 255, "project", false, 0],
    ["README.md", 16, "readme", false, 0],
    ["vm1_hda.cow", 197120, "disk", true, 196616],
    ["IMAGES/debian", 197120, "image", true, 196616]
  ],
  "complete": true,
  "report": [],
  "converted": false
}
```

Export a project, with the job of **export** in *export.toml*:

```
$ python -m virtualbricks.config.archive < export.toml
{"created": "/home/user/.lab.vbp.hsp68v_7.part"}
{"created": "/home/user/.virtualbricks-export-chcr2_tb"}
{"progress": {"step": "pack", "done": 0, "total": 393232}}
{"progress": {"step": "pack", "done": 393232, "total": 393232}}
{"progress": {"step": "write", "done": 409600, "total": 394772}}
{"progress": {"step": "write", "done": 394772, "total": 394772}}
{"result": {"output": "/home/user/lab.vbp", "size": 409600, ...}}
$ echo $?
0
```

Stop a long export: the process removes the unfinished archive and its folder.

```
$ python -m virtualbricks.config.archive \
>     < export.toml > messages &
$ sleep 2; kill $!; wait $!; echo $?
1
$ tail -n 1 messages
{"progress": {"step": "write", "done": 48234496, ...}}
```

A job that fails:

```
$ printf 'job = "inspect"\narchive = "notes.txt"\n' |
>     python -m virtualbricks.config.archive
{"progress": {"step": "read", "done": 512, "total": 5383}}
{"error": "notes.txt: invalid header"}
$ echo $?
2
```

# BUGS

An inspection that has to read the archive with the tool sends no progress,
and no head.

Python's **tarfile**, from 3.10 to 3.13, misreads a GNU sparse 1.0 member
whose size is in a pax record, as **bsdtar** and GNU **tar** write the members
larger than 8 GiB, and loses the member after it. The process then reads the
archive with the tool; without **bsdtar** or GNU **tar**, it can't read it,
and says \"install bsdtar or GNU tar to read this archive\".

# SEE ALSO

**virtualbricks-vbp**(5), **virtualbricks-config**(5), **bsdtar**(1),
**tar**(1), **tar**(5), **qemu-img**(1)

GNU tar, sparse formats:
<https://www.gnu.org/software/tar/manual/html_node/Sparse-Formats.html>

TOML 1.0: <https://toml.io/en/v1.0.0>
