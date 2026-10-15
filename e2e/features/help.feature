Feature: Help
  The user guide: Help, Contents opens its index, and F1 the page about the
  window in view. Where the desktop opens help: links with a program, as
  Yelp, it opens it: as a help: link where its pages are where Yelp looks,
  else the file of the page. Without one, the browser opens the HTML of the
  page.

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

  Scenario: F1 in the Settings window opens the HTML of its page in the browser, without Yelp
    Given yelp isn't on this computer
    And Virtualbricks is running
    When I open the Settings window
    And I press F1 in the Settings window
    Then the browser opens the HTML of the page settings
