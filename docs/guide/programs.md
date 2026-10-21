---
desc: "VDE and QEMU: what a missing program stops, and where Virtualbricks
  looks for them."
guide: "index#start"
seealso:
- kinds
- settings
sort: 3
---

# The programs it needs

The bricks are programs that Virtualbricks runs: the VDE programs for the
switches, the links and the interfaces of this computer, and QEMU for the
virtual machines. On Debian and Ubuntu they come in these packages:

  Package                                                                                                                                                                                 Programs
  --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- ---------------------------------------------------------------------------------------------------------------------------------------------------
  `vde2`{.sys}                                                                                                                                                                            `vde_switch`{.cmd}, `vde_plug`{.cmd}, `dpipe`{.cmd}, `vde_plug2tap`{.cmd}, `vde_pcapplug`{.cmd}, `vdeterm`{.cmd}, `unixterm`{.cmd}
  `vde2-cryptcab`{.sys}                                                                                                                                                                   `vde_cryptcab`{.cmd}, for the tunnels
  `vde-netemu`{.sys}                                                                                                                                                                      `vde-netemu`{.cmd}, for the Netemu links
  `qemu-system-x86`{.sys}                                                                                                                                                                 `qemu-system-x86_64`{.cmd} and `qemu-system-i386`{.cmd}
  `qemu-system-arm`{.sys}, `qemu-system-mips`{.sys}, `qemu-system-ppc`{.sys}, `qemu-system-riscv`{.sys}, `qemu-system-s390x`{.sys}, `qemu-system-sparc`{.sys}, `qemu-system-misc`{.sys}   The other architectures, as `qemu-system-aarch64`{.cmd} in `qemu-system-arm`{.sys}; on Ubuntu 24.04, `qemu-system-misc`{.sys} has those of RISC-V
  `qemu-utils`{.sys}                                                                                                                                                                      `qemu-img`{.cmd}, which reads and makes the disk images

The menu of the programs shows each once, by the name QEMU gives it: Debian's
other names, as `qemu-system-arm64`{.cmd} for `qemu-system-aarch64`{.cmd}, only
where a machine uses one. Some programs have no default machine type, as
`qemu-system-aarch64`{.cmd} and `qemu-system-arm`{.cmd}: choose one in the
section **Machine**, as `virt`{.sys}, or the machine doesn't start.

No distribution ships `vde_router`{.cmd}, the program of the router.

## Where Virtualbricks looks {#where}

Each project has a folder for the QEMU programs and one for the VDE programs,
in its settings: choose **File › Settings**, then the page of the project. A
program that isn't in its folder is looked for in the folders of `PATH`{.sys}.

Under each folder, the **Settings** window says what it holds: the version of
QEMU and its programs, and whether the programs of the bricks are there, or
which one is missing and the package that has it. A folder that doesn't exist
is an error, and **OK** stays greyed until it is fixed.

## When a program is missing {#missing}

- **New Brick** shows a warning sign on the kinds whose program is missing, and
  says which one.

- At start, Virtualbricks warns about the programs it can't find. **Missing
  programs**, in the settings of this computer, turns the warning off.

- A brick whose program is missing doesn't start, and the **Logs** window says
  why. Install the package, and start it again.
