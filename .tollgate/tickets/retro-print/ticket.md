---
id: retro-print
plan: e310-08
seams: retro.numbers_table, retro.main, retro.write
tests: tests/test_retro_print.py
---
## Current behavior
`python3 -m driver.retro --project . --task T` writes .tollgate/lessons/T.md and prints only its path. The numbers table is visible only in the file.

## Desired behavior
With `--print`, main() also prints the numbers table (the "| Number | Value |" table with its separator and one row per number) to standard output. The lessons file is written as before, with the same content.

## Checklist
- [C1, must] `numbers_table(nums)` returns the table lines: the header "| Number | Value |", the separator "| --- | --- |", then one "| name with spaces | value |" row per number.
- [C2, must] `main([... "--print"])` prints the numbers table to stdout and still writes the lessons file.
- [C3, must, keeps behavior] Without `--print`, stdout is only the path of the lessons file, and the file content is identical to today's.
- [C4] With `--print`, the lessons file holds the same table that was printed.
- [C5] The candidates section (the "## Candidates for lessons" heading and its lines, which stay in the file) is not printed with `--print`; only the numbers table is.

## Test cases (tests/test_retro_print.py)
- C1: `numbers_table({"mean_attempts": 2, "tests_rejected": 0})` equals `["| Number | Value |", "| --- | --- |", "| mean attempts | 2 |", "| tests rejected | 0 |"]`. `nums` is the first value of `numbers(project, task)`: a dict of name (underscores) to value.
- Setup for C2 to C5: temp project with `.tollgate/logs/t-a.jsonl` holding an `attempt_failed` (attempt 1) and an `attempt_passed` (attempt 2) event for ticket t-a, task "demo" (fields as in tests/test_report_minutes.py); run `main(["--project", tmp, "--task", "demo", ...])` with stdout captured. Expected table = `numbers_table(numbers(tmp, "demo")[0])`. The lessons file is `<tmp>/.tollgate/lessons/demo.md`; the path line is the last stdout line and equals that path.
- C2: main with `--print` on a temp project: stdout contains the header, separator and every row, the table appears before the path line, and the lessons file exists.
- C3: main without `--print`: stdout.strip() equals the lessons file path alone (no "| Number" text); the file content equals the content written with `--print` for the same data.
- C4: every table line printed with `--print` appears in the lessons file.
- C5: with `--print`, stdout has no "## Candidates for lessons" heading and no candidate lines (such as "- None." or "- <ticket>: a ..."), while the file still contains them.

## Out of scope
Printing candidates, other flags, changes to the numbers themselves.
