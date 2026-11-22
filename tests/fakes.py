"""The sample files the tests share: a test runner that writes a JUnit report, and
ticket T-1. The sample project and the fake store are in driver_fakes.py; the
fake AI roles are in fake_role.py."""

RUN_TESTS = '''"""Run the tests with unittest and write a JUnit report."""
import sys
import unittest
from xml.sax.saxutils import quoteattr

suite = unittest.defaultTestLoader.discover("tests", top_level_dir=".")
cases = []


def walk(s):
    for t in s:
        if isinstance(t, unittest.TestSuite):
            walk(t)
        else:
            cases.append(t)


walk(suite)
out, failed = [], 0
for case in cases:
    r = unittest.TestResult()
    case.run(r)
    cls = type(case).__module__
    name = case._testMethodName
    bad = r.failures or r.errors
    failed += bool(bad)
    inner = "<failure/>" if bad else ("<skipped/>" if r.skipped else "")
    out.append(f"<testcase classname={quoteattr(cls)} name={quoteattr(name)}>{inner}</testcase>")
open("report.xml", "w").write("<testsuites><testsuite>" + "".join(out) + "</testsuite></testsuites>")
sys.exit(1 if failed else 0)
'''

TICKET = """---
id: T-1
plan: demo
seams: app.shout
tests: tests/test_t1.py
---
## Current behavior
There is no shout.

## Desired behavior
shout returns the greeting in capitals.

## Checklist
- [C1, must] shout("ann") returns "HELLO ANN".
- [C2, must, keeps behavior] greet("ann") still returns "hello ann".
- [C3] shout has a docstring.

## Out of scope
Other languages.
"""
