// Make retried-then-passed tests impossible to miss in CI.
//
// playwright.config.ts retries once on CI, so a one-off failure does not fail
// the gate. A deterministic failure still fails (both attempts fail). This
// script reads the JSON report and lists every test that only passed on retry
// ("flaky") as a GitHub warning annotation and in the job summary.
// Usage: node report-flaky.mjs <playwright-json-report>
import { appendFileSync, existsSync, readFileSync } from "node:fs";

const file = process.argv[2];
if (!file || !existsSync(file)) {
  process.stdout.write(`no Playwright JSON report at ${file}\n`);
  process.exit(0);
}
const report = JSON.parse(readFileSync(file, "utf8"));
const flaky = [];
const walk = (suite, titles) => {
  for (const child of suite.suites ?? []) walk(child, [...titles, child.title].filter(Boolean));
  for (const spec of suite.specs ?? []) {
    for (const test of spec.tests ?? []) {
      if (test.status !== "flaky") continue;
      const firstError = test.results?.find((result) => result.status !== "passed")?.error?.message ?? "";
      flaky.push({ file: spec.file, line: spec.line, project: test.projectName, title: [...titles, spec.title].join(" › "), error: firstError.split("\n")[0].slice(0, 300) });
    }
  }
};
for (const suite of report.suites ?? []) walk(suite, [suite.title].filter(Boolean));

for (const item of flaky) {
  process.stdout.write(`::warning file=tests/e2e/playwright/${item.file},line=${item.line},title=Flaky test (passed on retry)::[${item.project}] ${item.title} — first attempt: ${item.error}\n`);
}
const summary = flaky.length
  ? [`### ${flaky.length} flaky test(s) — passed only on retry`, "", "| Project | Test | First failure |", "| --- | --- | --- |",
     ...flaky.map((item) => `| ${item.project} | \`${item.file}:${item.line}\` ${item.title.replaceAll("|", "\\|")} | ${item.error.replaceAll("|", "\\|")} |`), ""].join("\n")
  : "### No flaky tests\n";
if (process.env.GITHUB_STEP_SUMMARY) appendFileSync(process.env.GITHUB_STEP_SUMMARY, summary);
process.stdout.write(summary);
