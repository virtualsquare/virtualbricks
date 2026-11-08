Feature: Help
  The user guide: Help, Contents opens its index, and F1 the page about the
  window in view. Where the desktop opens help: links with a program, as
  Yelp, it opens it: as a help: link where the pages Yelp finds are its own,
  else the file of the page, also where Yelp finds the guide of another
  Virtualbricks. Without one, the browser opens the HTML of the page.

  Background:
    Given the browser of the desktop is a program of the tests

  Scenario: F1 in the Settings window opens its page in Yelp as a help: link, where the pages are where Yelp looks
    Given Yelp is a program of the tests
    And the pages of the guide are where Yelp looks
    And Virtualbricks is running
    When I open the Settings window
    And I press F1 in the Settings window
    Then Yelp opens "help:virtualbricks/settings"

  Scenario: F1 in the Settings window opens the file of its page in Yelp, without the pages where Yelp looks
    Given Yelp is a program of the tests
    And Virtualbricks is running
    When I open the Settings window
    And I press F1 in the Settings window
    Then Yelp opens the page settings of the sources

  Scenario: F1 in the Settings window opens the file of its page in Yelp, with the guide of another Virtualbricks where Yelp looks
    Given Yelp is a program of the tests
    And the guide of another Virtualbricks is where Yelp looks
    And Virtualbricks is running
    When I open the Settings window
    And I press F1 in the Settings window
    Then Yelp opens the page settings of the sources

  Scenario: F1 in the Settings window opens the HTML of its page in the browser, without Yelp
    Given yelp isn't on this computer
    And Virtualbricks is running
    When I open the Settings window
    And I press F1 in the Settings window
    Then the browser opens the HTML of the page settings

  Scenario: F1 in the settings of a switch opens the page of the switches in Yelp
    Given Yelp is a program of the tests
    And the pages of the guide are where Yelp looks
    And Virtualbricks is running
    When I add the switch sw1
    And I open the settings of sw1
    And I press F1 in the settings of sw1
    Then Yelp opens "help:virtualbricks/switches"
