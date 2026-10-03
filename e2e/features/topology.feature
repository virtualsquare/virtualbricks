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
