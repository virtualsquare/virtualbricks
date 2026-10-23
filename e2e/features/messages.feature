Feature: Messages window
  The messages of the run, in the window Logs of the menu File: those of
  Virtualbricks and of its bricks, and the output of their programs.

  Scenario: The output of a program that failed shows its first line, and the others behind a toggle that unfolds them
    Given a vde_switch that writes these lines, and exits with 3
      """
      no switch today
      the socket is busy
      try again later
      """
    And Virtualbricks is running
    When I add the switch sw1
    And I try to start sw1
    Then an error says "Process terminated. process ended with exit code 3"
    When I close the error
    And I open the messages window
    Then the messages window has the message of sw1: "Process terminated. process ended with exit code 3"
    And the messages window has the output of sw1: "no switch today", and 2 more lines folded
    When I unfold the output of sw1 in the messages window
    Then the messages window has the output of sw1, unfolded
      """
      no switch today
      the socket is busy
      try again later
      """
