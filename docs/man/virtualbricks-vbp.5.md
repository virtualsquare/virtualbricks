---
title: VIRTUALBRICKS-VBP
section: 5
header: Virtualbricks Manual
footer: virtualbricks VERSION
date: DATE
---

# NAME

virtualbricks-vbp - the archive of a Virtualbricks project

# SYNOPSIS

*project*.vbp

# DESCRIPTION

A *.vbp* file is a project of Virtualbricks in one file, to move it to
another computer, to keep it or to share it. The Export window writes it,
and the Import window makes a new project of it; both leave the work to the
archive process, described in **virtualbricks-archive**(7).

It is a tar archive of the project's folder: the project file, its README,
the private disks of the virtual machines, the other files of the folder
that you chose and, if you chose them too, the disk images that the disks
use, under *IMAGES/*. Its first member, **contents.toml**, lists the
others.

The format follows from four aims:

- Any **tar**(1) reads and writes it: an archive can be looked into, or
  made, without Virtualbricks.
- An archive can take gigabytes, but its first kilobytes say what it holds:
  the list and the project file come first.
- The disks keep their holes, and are compressed one by one, in a format
  that QEMU runs as it is.
- The project names its images, and the archive stores each one under its
  name, not under its file: the computer that imports the archive chooses
  where each image goes.

The archive of a project with one virtual machine, whose disk **hda** is a
private disk on top of the image **debian**, and whose disk **hdb** is the
image **scratch**:

```
$ tar -tvf lab.vbp
-rw-r--r-- alice/alice     318 2026-10-07 22:57 contents.toml
-rw------- alice/alice    6247 2026-10-07 21:19 project.toml
-rw-r--r-- alice/alice      31 2026-10-07 21:19 README.md
-rw-r--r-- alice/alice  328192 2026-10-07 22:57 vm1_hda.cow
-rw-r--r-- alice/alice  328192 2026-10-07 22:57 IMAGES/debian
-rw-r--r-- alice/alice 33554432 2026-10-07 21:19 IMAGES/scratch
```

The examples of this page come from that archive.

# THE CONTAINER

## Tar

An archive is a tar file in the POSIX.1-2001 format, *pax*: a sequence of
512-byte blocks. Each member is a header block followed by its data, padded
with zeros to a whole block. Before a member whose attributes don't fit its
header, as times with fractions of a second or the records of a sparse file,
comes a pax extended header: a member of type **x** whose data are records
of the form *length* *key*=*value*, each ending with a newline. Two blocks
of zeros end the archive, which is then padded with zeros to a multiple of
10240 bytes, the record of tar.

The blocks of the example:

```
 offset  type  header name                       size
      0  x     PaxHeader/contents.toml             90
   1024  0     contents.toml                      318
   2048  x     PaxHeader/project.toml              90
   3072  0     project.toml                      6247
  10240  x     PaxHeader/README.md                 90
  11264  0     README.md                           31
  12288  x     PaxHeader/vm1_hda.cow              195
  13312  0     GNUSparseFile.0/vm1_hda.cow     267264
 281088  x     IMAGES/PaxHeader/debian            197
 282112  0     IMAGES/GNUSparseFile.0/debian   267264
 549888  x     IMAGES/PaxHeader/scratch           200
 550912  0     IMAGES/GNUSparseFile.0/scratch    4608
 556032        14 blocks of zeros, to 563200
```

The members with holes are GNU sparse members, whose header name is a
placeholder; see **HOLES**.

## Compression

When **qemu-img** is installed, the archive is not compressed as a whole:
its disks are compressed one by one inside it (see **PACKED DISKS**), and
the rest is a few kilobytes. Without **qemu-img**, the whole archive is
compressed with gzip, whose header then has no time.

Virtualbricks reads an archive that is not compressed or compressed with
gzip, bzip2 or xz, which it recognizes by its first bytes, whatever its
extension.

## The name of the file

An archive has the extension *.vbp*, compressed or not. The Import window
offers the files *\*.vbp*, *\*.tar.gz*, *\*.tgz* and *\*.tar*. The name of
the file suggests the name of the project: without *.vbp*, *.tar.gz*,
*.tgz*, *.tar.xz*, *.tar.bz2* or its last extension, at most 38 bytes,
without leading dots, and the next free name, *lab-2*, *lab-3*\... when
the workspace has a project with that name. The archive itself doesn't
name the project.

## Names and attributes

Every member is a regular file, named by its path relative to the
project's folder, with */* between folders. A name has no leading */* and
no *..*; a reader drops a leading *./* and a trailing */*, so that an
archive made with **tar -C** *folder* **.** works too. The members that
aren't regular files, such as the folders of such an archive, are skipped
by an inspection; links and devices are never written, and the import
skips them when it extracts the archive with Python's **tarfile**.

The owner, the group, the permissions and the times of the members are
those that the writer found; Virtualbricks gives them no meaning. The
writers differ in details that a reader mustn't depend on:

**bsdtar**
:   Pax headers named *folder*/PaxHeader/*name*, with the records
    **ctime**, **atime** and **mtime**; sparse members named
    *folder*/GNUSparseFile.0/*name*.

GNU **tar**
:   Pax headers named *folder*/PaxHeaders/*name*, with **mtime**, **atime**
    and **ctime**; sparse members named *folder*/GNUSparseFile.*pid*/*name*,
    after the process number of **tar**.

Python's **tarfile**, in Virtualbricks
:   Pax headers named *././\@PaxHeader*, with **mtime** only; sparse
    members named as by **bsdtar**; no owner and group names.

# MEMBERS

The name of a member gives its *kind*, the word in italics, which the
archive process uses in its messages:

**contents.toml**
:   *contents*: the list of the other members; see **CONTENTS.TOML**.

**project.toml**
:   *project*: the project file, described in **virtualbricks-config**(5);
    see **THE PROJECT FILE**.

**.project**, **.project~**
:   *legacy project*: the project file of Virtualbricks 2.1 and older; see
    **OLDER ARCHIVES**. An archive with both project files is read from
    **project.toml**.

**README.md**, **README**
:   *readme*: the description of the project, plain text in UTF-8 that
    Virtualbricks reads as Markdown (see **README** in
    **virtualbricks-config**(5)). Before 3.0 it was **README**, which the
    import renames to **README.md**; in an archive with both, **README.md**
    is the README.

*vm*\_*device*.cow
:   *disk*: the private disk of the device *device* of the virtual machine
    *vm*, where *device* is **hda**, **hdb**, **hdc**, **hdd**, **fda**,
    **fdb** or **mtdblock**: the part after the last underscore, so
    *router_1_hda.cow* is the disk **hda** of **router_1**. Only at the top
    of the archive. See **PRIVATE DISKS**.

IMAGES/*image*
:   *image*: the disk image that the project file calls *image*, in
    **[images.***image***]**. The member is named after the image, not after
    its file: the image **debian** whose file is
    */srv/vm/debian-12.qcow2* is the member *IMAGES/debian*. See **IMAGES
    AND DISKS**. The archives of Virtualbricks 2.1 and of the development
    versions of 3.0 have it in *.images/*, which is read the same way.

any other name
:   *other*: a file of the project's folder that you chose to export, as a
    picture of the README, *pictures/map.png*. The import puts it back
    where it was.

An archive never holds what older versions left in a project's folder: its
*.images* folder and its *.project* files. Nor does it hold a folder
*IMAGES* of the project, whose files an import would take for images: the
export leaves it out, and says so.

# ORDER

A new archive starts with **contents.toml**, then the project file and the
README: together, the *head* of the archive. The other files, the private
disks and the images follow, in this order, each group from the smallest
file to the largest:

```
 +----------+---------+--------+-------+-------+----------+
 | contents | project | README | other | disks | IMAGES/  |
 |   .toml  |  .toml  |  .md   | files |       |          |
 +----------+---------+--------+-------+-------+----------+
 |<---------- head ----------->|<- smallest to largest -->|
     read by an inspection          read by the import
```

The order is the writer's promise; a reader accepts any order. With
**contents.toml** first, Virtualbricks reads the archive until it has the
members of the head that the list names, and stops there, whatever the size
of the archive. Without **contents.toml**, it reads the archive to its end.

# CONTENTS.TOML

The list of the other members, in the order of the archive, in TOML 1.0 and
UTF-8. The list of the example:

```
format = 1

[[members]]
name = "project.toml"
size = 6247

[[members]]
name = "README.md"
size = 31

[[members]]
name = "vm1_hda.cow"
size = 328192
packed = true
real_size = 851968

[[members]]
name = "IMAGES/debian"
size = 328192
packed = true
real_size = 1376256

[[members]]
name = "IMAGES/scratch"
size = 33554432
```

**format** = *integer*
:   The version of the layout, **1**. An archive with a higher **format**
    is not read: \"contents.toml: written by a newer Virtualbricks (format
    2)\". The format changes only for what an older reader can't ignore:
    keys it doesn't know are ignored.

**members** = *array of tables*
:   One table for each member but **contents.toml** itself:

    **name** = *string*
    :   The name of the member, as in its header.

    **size** = *integer*
    :   The size of the file that the member holds, holes included: what
        **ls -l** says once it's extracted. A sparse member takes fewer
        bytes in the archive: **IMAGES/scratch** takes 4608 bytes for its
        32 MiB.

    **packed** = *boolean*
    :   Present, and **true**, only when **qemu-img** compressed the
        member; see **PACKED DISKS**.

    **real_size** = *integer*
    :   Only with **packed**: the size of the disk before it was
        compressed, the size it has on the computer it comes from.

The kind of a member comes from its name and is not written. An item of
**members** that isn't a table is skipped, a size that isn't an integer is
read as 0, a **packed** that isn't **true** is false, and other keys are
ignored.

# THE PROJECT FILE

The **project.toml** of an archive is the project file as the project had
it, in the format of the Virtualbricks that exported it: 2 today. The
import upgrades an older one, and refuses a newer one: \"project.toml:
written by a newer Virtualbricks (format 3)\". An archive carries the
paths of the computer it comes from, in these keys, which the import
changes:

**[images.***name***]** **path**
:   The file of the image on the computer it comes from: absolute, or
    relative to the project's folder. The import writes the file that the
    image uses on this computer, or \"\" for an image left unset.

**[bricks.***vm***.disks.***device***]** **image**, **private**
:   The image of a disk, by name, and whether the disk writes to its
    private disk, *vm*\_*device*.cow. The import changes neither.

**[settings]** **qemu_path**, **vde_path**
:   The folders of QEMU and VDE on the computer it comes from. The import
    replaces each with this computer's when the folder doesn't exist here,
    unless you choose otherwise.

The rest of the file is imported as it is. The private disks carry a path
too: see **PRIVATE DISKS**.

# IMAGES AND DISKS

A disk doesn't name a file: it names an image of the project, and the image
has the path of its file. The archive stores the image under that name, so
the name ties the three together:

```
 project.toml                          the archive
 +-----------------------------------+
 | [bricks.vm1.disks.hda]            |
 | image = "debian" --.              |
 | private = true     |              |
 |                    v              |  the name
 | [images.debian] <--+--------------+--> IMAGES/debian
 | path = "/srv/vm/debian-12.qcow2"  |
 +-----------------------------------+
            ^
            '----- backing file ------ vm1_hda.cow
```

The import plans an image for each table **[images.***name***]** of the
project file. Its disks are those whose **image** is *name*, and its copy
in the archive is the member *IMAGES/name*, if the archive has it. The
Import window gives each image a choice, with a default:

- An image that the archive has is copied into the shared images,
  *workspace*/shared_images, under the name of its file on the computer
  it comes from, *debian-12.qcow2*, or the next free one,
  *debian-12.1.qcow2*\...
  When the shared images have a file with that name and the size of the
  image, the **real_size** of a packed one, that file is used instead.
- An image that the archive doesn't have uses its file if this computer has
  it at the same path, otherwise a file of the shared images with the name
  of its file or of the image; otherwise it's left unset, and its disks get an
  image later, in their settings.

Then the import writes the path of each image into **[images.***name***]**,
points the private disks at it (see **PRIVATE DISKS**), and removes the
*IMAGES* folder. A member of *IMAGES/* that no table of the project file
names is dropped. By default, a file of the shared images with the file
name and the size of an image is taken for it: nothing compares their
contents.

The Export window stores every image of the project whose file exists, or
none; it stores none by default, as images are large and often already on
the other computer.

# PRIVATE DISKS

A disk with **private** = **true** writes to *vm*\_*device*.cow in the
project's folder, a qcow2 file on top of the image, which stays unchanged.
The private disk names its image by the image's file, as its *backing
file*: a path of the computer it comes from, kept in the archive, packed or
not:

```
$ qemu-img info vm1_hda.cow
image: vm1_hda.cow
file format: qcow2
virtual size: 64 MiB (67108864 bytes)
disk size: 264 KiB
cluster_size: 65536
backing file: /srv/vm/debian-12.qcow2
backing file format: qcow2
Format specific information:
    compat: 1.1
    compression type: zstd
...
```

The import points each private disk at the file that its image uses on
this computer, in the format of that file:

```
qemu-img rebase -u -b image -F format disk
```

**-u**, the unsafe mode, changes only the name of the backing file: the
image must hold the same data as the one the disk was made on. A private
disk whose image is left unset keeps its backing file as it is, and the
import says so. A private disk made by an older version may be in another
format than qcow2: it's stored as it is, and the import points it at its
image as the others.

# PACKED DISKS

When **qemu-img** is installed, the export compresses each private disk and
each image that is in the qcow2 format:

```
qemu-img convert -p -O qcow2 -m 8 -W \
    -c -o compression_type=zstd \
    [-B backing -F backing-format] disk packed-disk
```

with zlib, without **-o compression_type=zstd**, when QEMU is older than
5.1. A packed disk is a valid qcow2 file whose clusters are compressed, and
QEMU runs it as it is; a private disk keeps its backing file. The member is
marked **packed** in **contents.toml**, with its **real_size**. A disk or an
image in another format, as raw, is stored as it is; so is one that
**qemu-img** can't read, as a private disk whose image is gone, and the
export says so.

The import converts the packed members back into normal qcow2 files, with
**qemu-img convert** without **-c**: the images it copies, and the private
disks on top of their new image. The others stay compressed, and work as
they are: a private disk whose image is left unset, any packed member when
**qemu-img** isn't installed. An archive without **contents.toml** has no
packed member.

# HOLES

A disk is a sparse file: a disk of 20 GB can take 2 GB of space. The
archive keeps the holes of its members, as GNU sparse 1.0 members, which
**bsdtar**, GNU **tar** with **\--sparse** and Virtualbricks itself write. A
sparse member is:

- a pax extended header with the records **GNU.sparse.major=1**,
  **GNU.sparse.minor=0**, **GNU.sparse.name**, the name of the member, and
  **GNU.sparse.realsize**, the size of the file with its holes;
- a header whose name is a placeholder, *GNUSparseFile.0/name* or the like,
  which a reader replaces with **GNU.sparse.name**, and whose size is that
  of the data that follow;
- the map of the data: decimal numbers, each ending with a newline, the
  number of regions, then the offset and the length of each, padded with
  zeros to a whole block;
- the data of the regions, one after the other.

A file that ends with a hole has a last region of length 0, at its size.
The member *IMAGES/scratch* of the example, a file of 32 MiB with 4096
bytes of data at 4 MiB, takes 4608 bytes: one block of map, then the data.
Its map:

```
2
4194304
4096
33554432
0
```

A reader that doesn't know the format extracts
*IMAGES/GNUSparseFile.0/scratch*, a file with the map and the data, which
isn't the image.

A header holds sizes up to 8 GiB, in octal. **bsdtar** and GNU **tar** write
a larger size as a **size** record of the pax header; Virtualbricks, when
it writes the archive itself, writes it in the header, in base 256: the
first byte 0x80, then the size, big-endian. Python's **tarfile** misreads
a sparse member with a **size** record; see **BUGS**.

When the import extracts an archive, **bsdtar -S** turns runs of zeros into
holes, also those that the archive didn't keep. After GNU **tar** or
**tarfile**, the import does the same for the private disks and the copied
images: blocks of 64 KiB of zeros become holes, if they add up to 1 MiB at
least.

# OLDER ARCHIVES

Virtualbricks 2.1 exported a project with **bsdtar** or **tar**, **cfzh**: a tar of the project's folder compressed with gzip, without
**contents.toml**. It holds the files you chose, then the project file,
**.project**, and the **README**, then the images, under *.images/image*:
the export made a folder of links named after the images, which tar
followed. The private disks are *vm*\_*device*.cow, as today.

The **.project** file is the project file of those versions, which the
import converts as the migration does (see **MIGRATION** in
**virtualbricks-config**(5)):

```
[Image:debian]
path=/srv/vm/debian-12.qcow2

[Qemu:vm1]
hda=debian
privatehda=*
```

As the project file comes near the end, an inspection reads such an archive
to its end. It sends what it knows as soon as it has read the project file,
and the full list of members at the end; the Import window shows its form
from the first, and the import starts without waiting for the second.

# READING AN ARCHIVE

Virtualbricks reads an archive as a stream, once, from its start:

1. It recognizes the compression from the first bytes: gzip, bzip2, xz, or
   none.
2. It skips the members that aren't regular files. It takes the name of a
   sparse member from **GNU.sparse.name**, drops a leading *./* and a
   trailing */*, and gets the kind of the member from its name.
3. It reads the members of the head: **contents.toml**, the project file,
   the README. It refuses a **contents.toml** of a newer format.
4. With **contents.toml**, it stops when it has every member of the head
   that the list names. Without it, it reads on to the end, and lists the
   members from their headers.
5. It reads **project.toml**, or converts **.project**, and fails when
   there is neither. **README.md** comes before **README**.

To import an archive, it extracts it whole, into a hidden folder of the
workspace, and goes on as **virtualbricks-archive**(7) describes.

# WRITING AN ARCHIVE

A file that Virtualbricks imports needs only a project file. An archive
that it reads as well as its own:

- is a pax tar file, not compressed when its disks are packed, otherwise
  compressed with gzip;
- starts with **contents.toml**, of format 1, listing every other member,
  then has the project file and the README;
- names the members after their path in the project's folder, the images
  *IMAGES/name* after their name in the project file;
- keeps the holes of the disks;
- packs the qcow2 disks, keeping their backing files, and marks them
  **packed**, with their **real_size**.

The backing file of a private disk can be any path: the import replaces it,
and its format, with the file that the image uses on this computer.

# EXAMPLES

Look into an archive without extracting it:

```
$ tar -xOf lab.vbp contents.toml
$ tar -xOf lab.vbp README.md
$ tar -xOf lab.vbp project.toml |
>     grep -e '^\[images' -e '^path ='
[images.debian]
path = "/srv/vm/debian-12.qcow2"
[images.scratch]
path = "/srv/vm/scratch.img"
```

Extract a private disk, and see its image and its compression:

```
$ tar -xf lab.vbp vm1_hda.cow
$ qemu-img info vm1_hda.cow | grep -e backing -e compression
backing file: /srv/vm/debian-12.qcow2
backing file format: qcow2
    compression type: zstd
```

Point it at the image of this computer, by hand, as the import does:

```
$ qemu-img rebase -u -F qcow2 \
>     -b ~/.virtualbricks/shared_images/debian-12.qcow2 \
>     vm1_hda.cow
```

Make an archive by hand with GNU **tar**, keeping the holes, with the image
**debian** under its name. Virtualbricks imports it, after reading it to
its end, as it has no **contents.toml**:

```
$ tar -c --sparse --format=posix -f lab.vbp \
>     -C ~/.virtualbricks/lab \
>     project.toml README.md vm1_hda.cow \
>     -C /srv/vm \
>     --transform 's,^debian-12\.qcow2$,IMAGES/debian,' \
>     debian-12.qcow2
$ tar -tf lab.vbp
project.toml
README.md
vm1_hda.cow
IMAGES/debian
```

The archive of the whole folder of a project, compressed with gzip, which
doesn't keep the holes of its disks:

```
$ tar -czf ~/lab.vbp -C ~/.virtualbricks/lab .
```

# FILES

*name*.vbp
:   An archive.

*workspace*/shared_images/
:   The shared images, where the import copies the images.

*workspace*/*name*/
:   The project that the import makes of an archive.

# BUGS

Python's **tarfile**, from 3.10 to 3.13, misreads a GNU sparse 1.0 member
whose size is in a pax record, as **bsdtar** and GNU **tar** write the
members larger than 8 GiB, and loses the member after it. Virtualbricks
then reads the archive with **bsdtar** or GNU **tar**; with neither, it
can't read it.

# SEE ALSO

**virtualbricks-archive**(7), **virtualbricks-config**(5),
**virtualbricks**(1), **tar**(5), **tar**(1), **bsdtar**(1),
**qemu-img**(1)

The pax format, POSIX.1-2024:
<https://pubs.opengroup.org/onlinepubs/9799919799/utilities/pax.html>

GNU tar, sparse formats:
<https://www.gnu.org/software/tar/manual/html_node/Sparse-Formats.html>

The qcow2 format:
<https://www.qemu.org/docs/master/interop/qcow2.html>

TOML 1.0: <https://toml.io/en/v1.0.0>
