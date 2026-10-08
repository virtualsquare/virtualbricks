Feature: Virtual machines
  The virtual machines of a project run QEMU, on their disks and with
  their network cards.

  @needs-qemu-img @needs-qemu-system-x86_64
  Scenario: A virtual machine with no display runs QEMU on its disk, until it is terminated
    Given the empty disk image disk.qcow2 of 1 GB, in my home folder
    And Virtualbricks is running
    When I add an existing image, disk.qcow2 of my home folder, with the name it suggests, disk
    And I open the tab Bricks
    And I add the virtual machine vm1
    And I choose "x86_64" for "Program" in the settings of vm1, on its page Machine
    And I turn on "No display" in the settings of vm1, on its page Display
    And I give vm1 the image disk, on its disk hda
    Then the list of bricks has
      | Brick | Detail                                              | State   |
      | vm1   | Virtual machine · x86_64 · 64 MiB · no network card | Stopped |
    When I start vm1
    Then vm1 runs qemu-system-x86_64, with no display
    And vm1 runs on a private copy of disk.qcow2 of the shared images
    When I terminate vm1, from its menu
    Then vm1 is stopped
    When I quit Virtualbricks
    Then Virtualbricks has quit

  @needs-vde_switch @needs-qemu-system-i386
  Scenario: A virtual machine connected to a switch with Connect To runs with a card in the socket of the switch
    Given Virtualbricks is running
    When I add the switch sw1
    And I add the virtual machine vm1
    And I connect vm1 to sw1, with Connect To in its menu
    Then the list of bricks has
      | Brick | Detail                                        | State   |
      | sw1   | Switch · 32 ports                             | Stopped |
      | vm1   | Virtual machine · i386 · 64 MiB · eth0 on sw1 | Stopped |
    When I turn on "No display" in the settings of vm1, on its page Display
    And I start sw1
    And I start vm1
    Then vm1 runs with a card in the socket of sw1
    When I terminate vm1, from its menu
    And I stop sw1
    Then no brick runs

  @needs-qemu-system-i386
  Scenario: A virtual machine paused from the menu of its process is stopped by the system, until it continues
    Given Virtualbricks is running
    When I add the virtual machine vm1
    And I turn on "No display" in the settings of vm1, on its page Display
    And I start vm1
    And I pause vm1, from its menu
    Then the process of vm1 is paused
    When I continue vm1, from its menu
    Then the process of vm1 runs again
    And the monitor of vm1 answers "info status" with "VM status: running"
    When I terminate vm1, from its menu
    Then vm1 is stopped

  @needs-qemu-img @needs-qemu-system-i386
  Scenario: A virtual machine deleted takes its private copy to the trash
    Given the empty disk image disk.qcow2 of 1 GB, in my home folder
    And Virtualbricks is running
    When I add an existing image, disk.qcow2 of my home folder, with the name it suggests, disk
    And I open the tab Bricks
    And I add the virtual machine vm1
    And I turn on "No display" in the settings of vm1, on its page Display
    And I give vm1 the image disk, on its disk hda
    And I start vm1
    Then vm1 runs on a private copy of disk.qcow2 of the shared images
    When I terminate vm1, from its menu
    And I ask to delete vm1, from its menu
    Then the Delete dialog says that the private copy vm1_hda.cow goes to the trash
    When I confirm the delete
    Then the list of bricks has
      | Brick | Detail | State |
    And the file vm1_hda.cow of the project folder is in the trash
