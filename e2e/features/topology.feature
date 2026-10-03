Feature: Topology
  The picture of the lab: its bricks and the links between them, at a zoom.

  Scenario: The picture of the lab, zoomed in, moves with the pointer that drags it
    Given Virtualbricks is running
    When I add the switch sw1
    And I add the switch sw2
    And I join sw1 and sw2 with the wire w1
    And I zoom in on the picture of the lab 5 times
    And I drag the picture of the lab 100 pixels to the left
    Then the picture of the lab moved 100 pixels to the left
    When I drag the picture of the lab 100 pixels to the right
    Then the picture of the lab moved 100 pixels to the right

  Scenario: The buttons over the picture of the lab zoom it in, out and back to 100%, and its zoom level says so
    Given Virtualbricks is running
    When I add the switch sw1
    And I add the switch sw2
    And I join sw1 and sw2 with the wire w1
    And I zoom in on the picture of the lab 2 times
    Then the zoom level of the picture of the lab is 150%
    When I zoom out on the picture of the lab 4 times
    Then the zoom level of the picture of the lab is 67%
    When I zoom the picture of the lab back to 100%
    Then the zoom level of the picture of the lab is 100%

  Scenario: The picture of the lab exported as an image is a PNG file
    Given Virtualbricks is running
    When I add the switch sw1
    And I add the switch sw2
    And I join sw1 and sw2 with the wire w1
    And I export the picture of the lab to lab.png of my home folder, typing its path
    Then the file lab.png of my home folder is a PNG image, not blank
