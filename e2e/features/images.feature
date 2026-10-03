Feature: Disk images
  The disk images of a project, which its virtual machines start from.

  @needs-qemu-img
  Scenario: A disk image of my home folder, added from the Images tab, is copied into the image folder
    Given the empty disk image disk.qcow2 of 1 GB, in my home folder
    And Virtualbricks is running
    When I add an existing image, disk.qcow2 of my home folder, with the name it suggests, disk
    Then the list of images has
      | Image | Detail                                | State   |
      | disk  | qcow2 · 1.0 GB disk · no disk uses it | No disk |
    And the image folder has disk.qcow2, a copy of that of my home folder
    When I quit Virtualbricks
    Then Virtualbricks has quit
    And project.toml has the image disk, of disk.qcow2 in the image folder
