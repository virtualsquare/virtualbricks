Feature: Events
  An event waits, then runs its actions: it starts or stops bricks.

  @needs-vde_switch
  Scenario: An event made with the name it suggests counts down its wait, then starts sw1
    Given Virtualbricks is running
    When I add the switch sw1
    And I make an event that starts sw1 after 2 seconds, with the name it suggests, new_event
    Then the list of events has
      | Event     | Detail                | State |
      | new_event | After 2 s, starts sw1 | Ready |
    When I start the event new_event
    Then new_event counts down from 2 seconds, then starts sw1
    When I open the tab Bricks
    Then sw1 is running

  @needs-vde_switch
  Scenario: Run Now runs the actions of an event at once, without its wait
    Given Virtualbricks is running
    When I add the switch sw1
    And I make an event that starts sw1 after 60 seconds, with the name it suggests, new_event
    And I run the event new_event now, from its menu
    Then the list of events has
      | Event     | Detail                 | State |
      | new_event | After 60 s, starts sw1 | Ready |
    When I open the tab Bricks
    Then sw1 is running

  @needs-vde_switch
  Scenario: An event stopped while it waits never starts sw1
    Given Virtualbricks is running
    When I add the switch sw1
    And I make an event that starts sw1 after 3 seconds, with the name it suggests, new_event
    And I start the event new_event
    And I stop the event new_event while it waits
    Then the list of events has
      | Event     | Detail                | State |
      | new_event | After 3 s, starts sw1 | Ready |
    When I wait 5 seconds
    And I open the tab Bricks
    Then sw1 is not running

  @needs-vde_switch
  Scenario: An event chosen in When It Starts of sw1 runs when sw1 starts
    Given Virtualbricks is running
    When I add the switch sw1
    And I add the switch sw2
    And I make an event that starts sw2 at once, with the name it suggests, new_event
    And I open the tab Bricks
    And I choose new_event in When It Starts, in the menu of sw1
    And I open the tab Events
    Then the list of events has
      | Event     | Detail                                | State |
      | new_event | At once, starts sw2 · when sw1 starts | Ready |
    When I open the tab Bricks
    And I start sw1
    Then sw1 is running
    And sw2 is running

  Scenario: An event without actions can't start, and its row says why
    Given Virtualbricks is running
    When I make an event without actions, with the name it suggests, new_event
    Then the list of events has
      | Event     | Detail         | State          |
      | new_event | No actions yet | Not configured |
    And new_event can't start: "Add an action to new_event first"
    When I try to start new_event
    Then new_event is not configured

  Scenario: A switch deleted leaves the event that started it without that action
    Given Virtualbricks is running
    When I add the switch sw1
    And I make an event that starts sw1 after 2 seconds, with the name it suggests, new_event
    And I open the tab Bricks
    And I ask to delete sw1, from its menu
    Then the Delete dialog says "The event new_event will no longer start sw1."
    When I confirm the delete
    And I open the tab Events
    Then the list of events has
      | Event     | Detail         | State          |
      | new_event | No actions yet | Not configured |
    When I quit Virtualbricks
    Then Virtualbricks has quit
    And project.toml has the event new_event, without actions

  Scenario: An event deleted is no longer the one a brick runs when it starts
    Given Virtualbricks is running
    When I add the switch sw1
    And I add the switch sw2
    And I make an event that starts sw2 at once, with the name it suggests, new_event
    And I open the tab Bricks
    And I choose new_event in When It Starts, in the menu of sw1
    And I ask to delete the event new_event, from its menu
    Then the Delete dialog says "sw1 will no longer run new_event when it starts."
    When I confirm the delete
    Then the list of events has
      | Event | Detail | State |
    When I quit Virtualbricks
    Then Virtualbricks has quit
    And project.toml has sw1 with
      | Setting  | Value |
      | on_start | ""    |
