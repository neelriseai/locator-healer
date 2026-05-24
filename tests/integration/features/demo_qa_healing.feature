Feature: Demo QA App healing with broken fallback xpaths
  As a test automation engineer
  I want locator healing to recover target web elements from context anchors
  So that broken xpaths do not fail end-to-end tests

  Scenario: TC1 text-box form fill and submit
    Given I open the "text-box" demo page
    When I heal and fill all text-box form fields
    And I heal and click the text-box submit button
    Then I should see submitted text-box output values
    And trace logs should contain expected healing stages

  Scenario: TC2 checkbox tree expand and select Desktop + Excel
    Given I open the "checkbox" demo page
    When I heal and click the expand button for Home
    And I heal and click the Desktop checkbox icon
    And I heal and click the expand button for Downloads
    And I heal and click the Excel File.doc checkbox icon
    Then I should see checkbox selection message for Desktop and Excel File
    And trace logs should contain expected healing stages

  Scenario: TC3 webtables first row verification
    Given I open the "webtables" demo page
    When I heal and verify the first row first name is "Cierra"
    Then I heal and verify the first row last name is one of:
      | last_name |
      | Vega      |
    And trace logs should contain expected healing stages

  @negative
  Scenario: TC4 raw fallback xpath fails without healer
    Given I open the "text-box" demo page
    When I query raw invalid fallback xpath without healer
    Then report and logs should show xpath failure reason
