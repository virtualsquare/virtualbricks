Feature: Help
  The user guide: Help, Contents opens its index, and F1 the page about the
  window in view. Where its pages are where Yelp looks, the desktop opens a
  help: link, as Yelp does; elsewhere the HTML of the page, in the browser.

  Background:
    Given the desktop opens help: links and web pages with a program of the tests

  Scenario: F1 in the Settings window opens its page as a help: link, where the pages are where Yelp looks
    Given the pages of the guide are where Yelp looks
    And Virtualbricks is running
    When I open the Settings window
    And I press F1 in the Settings window
    Then the desktop opens "help:virtualbricks/settings"

  Scenario: F1 in the Settings window opens the HTML of its page, without the pages where Yelp looks
    Given Virtualbricks is running
    When I open the Settings window
    And I press F1 in the Settings window
    Then the desktop opens the HTML of the page settings
