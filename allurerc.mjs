// The report of the end-to-end tests, by Allure 3: see e2e/README.md, "The
// report of Allure".
//
//     pytest --alluredir=allure-results --clean-alluredir
//     npx allure@3 generate   # the report, in allure-report/
//     npx allure@3 open       # the report, in the browser
//
// allure-results/ and allure-history.jsonl are in git, to publish the
// report: generate adds the run of allure-results/ to the history, whose
// trends the report shows.

export default {
  name: "Virtualbricks end-to-end tests",
  resultsDir: "allure-results",
  output: "allure-report",
  historyPath: "allure-history.jsonl",
};
