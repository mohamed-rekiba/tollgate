---
id: retro-print-flag
plan: e310b-08
seams: retro.numbers_table, retro.main
tests: tests/test_retro_print_flag.py
---
## Current behavior
`python3 -m driver.retro --project . --task X` writes .tollgate/lessons/X.md and prints only its path. The numbers table is only in the file.

## Desired behavior
With `--print`, main also prints the numbers table to standard output. Without it, the output is unchanged.

## Checklist
- [C1, must] `numbers_table(nums)` returns the markdown table (header `| Number | Value |`, separator, one row per number with `_` shown as a space) as a string.
- [C2, must] `main([... "--print"])` prints the table to standard output, and still writes the lessons file.
- [C3, must, keeps behavior] Without `--print`, standard output is the file path only, and the lessons file content is the same as before.
- [C4] The table printed with `--print` is the same text as the table in the lessons file.
- [C5] `--print` appears in the argument parser help.

## Out of scope
The candidates section, the retro skill, other drivers.
