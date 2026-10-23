Feature: Readme
  The README of the open project, in the tab Readme: rendered from its
  Markdown, or its text in the editor.

  Scenario: The README of a project shows rendered in the Readme tab
    Given the project new_project has the README
      """
      # The lab

      Two switches and a **wire** between them, *for now*.

      - sw1
      - sw2
      """
    And Virtualbricks is running
    When I open the tab Readme
    Then the Readme tab shows the README rendered
      | Text               | Style       |
      | The lab            | large, bold |
      | Two switches and a |             |
      | wire               | bold        |
      | between them,      |             |
      | for now            | italic      |
      | .                  |             |
      | • sw1              |             |
      | • sw2              |             |

  Scenario: A README written in the editor of the Readme tab shows in its preview, and the project saves it
    Given Virtualbricks is running
    When I write the README in the Readme tab
      """
      # The lab

      Two switches and a **wire** between them.
      """
    And I show the preview of the README
    Then the Readme tab shows the README rendered
      | Text               | Style       |
      | The lab            | large, bold |
      | Two switches and a |             |
      | wire               | bold        |
      | between them.      |             |
    When I save the project
    Then the README file of new_project has
      """
      # The lab

      Two switches and a **wire** between them.
      """
