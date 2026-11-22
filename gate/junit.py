"""Read a JUnit XML test report.

A test id is `<classname>::<name>`. A test belongs to a file when the test case
has a `file` attribute with that path, or when its class name, with dots read as
folders, names that file without its extension.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass
class TestResult:
    id: str
    status: str  # passed, failed, skipped
    file: str


def _status(case) -> str:
    if case.find("skipped") is not None:
        return "skipped"
    if case.find("failure") is not None or case.find("error") is not None:
        return "failed"
    return "passed"


def read(path) -> dict:
    """Return {test id: TestResult} for every test case in the report."""
    results = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        classname = case.get("classname", "")
        name = case.get("name", "")
        test_id = f"{classname}::{name}" if classname else name
        results[test_id] = TestResult(test_id, _status(case), case.get("file", ""))
    return results


def in_files(result: TestResult, files) -> bool:
    """Return True when the test comes from one of the files."""
    if result.file:
        return result.file in files
    module = result.id.split("::")[0].replace(".", "/")
    for path in files:
        stem = str(PurePosixPath(path).with_suffix(""))
        if module == stem or module.startswith(stem + "/"):
            return True
    return False
