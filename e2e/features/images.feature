Feature: Disk images
  The disk images of a project, which its virtual machines start from.

  @needs-qemu-img
  Scenario: A disk image of my home folder, added from the Images tab, is copied into the shared images
    Given the empty disk image disk.qcow2 of 1 GB, in my home folder
    And Virtualbricks is running
    When I add an existing image, disk.qcow2 of my home folder, with the name it suggests, disk
    Then the list of images has
      | Image | Detail                                | State   |
      | disk  | qcow2 · 1.0 GB disk · no disk uses it | No disk |
    And the shared images have disk.qcow2, a copy of that of my home folder
    When I quit Virtualbricks
    Then Virtualbricks has quit
    And project.toml has the image disk, of disk.qcow2 in the shared images

  @needs-qemu-img
  Scenario: A disk image of my home folder, added to be used where it is, keeps its path and isn't copied
    Given the empty disk image disk.qcow2 of 1 GB, in my home folder
    And Virtualbricks is running
    When I add an existing image, disk.qcow2 of my home folder, used where it is, with the name it suggests, disk
    Then the list of images has
      | Image | Detail                                | State   |
      | disk  | qcow2 · 1.0 GB disk · no disk uses it | No disk |
    And the shared images have no copy of disk.qcow2
    When I open the details of disk
    Then the details of disk have
      | Fact   | Value        |
      | File   | ~/disk.qcow2 |
      | Format | qcow2        |
    When I quit Virtualbricks
    Then Virtualbricks has quit
    And project.toml has the image disk, of disk.qcow2 of my home folder

  @needs-qemu-img
  Scenario: A new empty disk added from the Images tab is a file of the shared images, of the size and the format chosen
    Given Virtualbricks is running
    When I add a new empty disk, disk, of 20 MB in the format raw
    Then the list of images has
      | Image | Detail                               | State   |
      | disk  | raw · 20.0 MB disk · no disk uses it | No disk |
    And the shared images have disk.raw, a raw disk of 20 MB
    When I quit Virtualbricks
    Then Virtualbricks has quit
    And project.toml has the image disk, of disk.raw in the shared images

  @needs-qemu-img
  Scenario: The details of a disk image say what qemu-img info says of its file
    Given the empty disk image disk.qcow2 of 1 GB, in my home folder, with the snapshot clean
    And Virtualbricks is running
    When I add an existing image, disk.qcow2 of my home folder, with the name it suggests, disk
    And I open the details of disk
    Then the details of disk say what qemu-img info says of disk.qcow2 of the shared images

  @needs-qemu-img @needs-qemu-system-i386
  Scenario: A disk image given to a virtual machine names it in its row, and is in use while the machine runs
    Given the empty disk image disk.qcow2 of 1 GB, in my home folder
    And Virtualbricks is running
    When I add an existing image, disk.qcow2 of my home folder, with the name it suggests, disk
    And I open the tab Bricks
    And I add the virtual machine vm1
    And I turn on "No display" in the settings of vm1, on its page Display
    And I give vm1 the image disk, on its disk hda
    And I open the tab Images
    Then the list of images has
      | Image | Detail                                  | State      |
      | disk  | qcow2 · 1.0 GB disk · vm1, private copy | Not in use |
    When I open the tab Bricks
    And I start vm1
    Then vm1 runs on a private copy of disk.qcow2 of the shared images
    When I open the tab Images
    Then the list of images has
      | Image | Detail                                  | State  |
      | disk  | qcow2 · 1.0 GB disk · vm1, private copy | In use |
    When I open the tab Bricks
    And I terminate vm1, from its menu
    And I open the tab Images
    Then the list of images has
      | Image | Detail                                  | State      |
      | disk  | qcow2 · 1.0 GB disk · vm1, private copy | Not in use |

  @needs-qemu-img
  Scenario: A disk image removed, whose file no other project uses, moves its file to the trash, once confirmed
    Given Virtualbricks is running
    When I add a new empty disk, disk, of 20 MB in the format raw
    And I open the tab Bricks
    And I add the virtual machine vm1
    And I give vm1 the image disk, on its disk hda
    And I remove the image disk, which the disk vm1 (hda) loses, and move its file to the trash
    Then the list of images has
      | Image | Detail | State |
    And the file disk.raw of the shared images is in the trash
    When I quit Virtualbricks
    Then Virtualbricks has quit
    And project.toml has the disk hda of vm1, without an image

  @needs-qemu-img
  Scenario: A disk image removed, whose file another project uses, leaves its file where it is
    Given Virtualbricks is running
    When I add a new empty disk, disk, of 20 MB in the format raw
    And I open the tab Bricks
    And I add the virtual machine vm1
    And I give vm1 the image disk, on its disk hda
    And I open the Projects window
    And I duplicate the project new_project with the name it suggests, new_project-copy
    And I remove the image disk, which the disk vm1 (hda) loses, and whose file new_project uses too
    Then the list of images has
      | Image | Detail | State |
    When I quit Virtualbricks
    Then Virtualbricks has quit
    And the shared images still have disk.raw, in no trash

  @needs-qemu-img
  Scenario: The file of an image that is missing, found in my home folder, is the file of the image again
    Given the project DTN2hops_26_Feb_2026 of Virtualbricks 2.1
    And the settings of Virtualbricks 2.1, with DTN2hops_26_Feb_2026 open last
    And the empty disk image debian13.qcow2 of 1 GB, in my home folder
    And Virtualbricks migrated DTN2hops_26_Feb_2026 at its first start
    When I open the tab Images
    Then the list of images has
      | Image    | Detail                                                                                            | State        |
      | debian13 | /home/carlo/VB_images/debian13.qcow2 isn't there · node1, node2, node3 and node4, private copies | File missing |
    When I find the file of debian13, debian13.qcow2 of my home folder
    Then the list of images has
      | Image    | Detail                                                              | State      |
      | debian13 | qcow2 · 1.0 GB disk · node1, node2, node3 and node4, private copies | Not in use |
    When I quit Virtualbricks
    Then Virtualbricks has quit
    And project.toml has the image debian13, of debian13.qcow2 of my home folder
