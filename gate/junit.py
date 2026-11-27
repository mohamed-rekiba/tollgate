"""Read a JUnit XML test report.

A test id is `<classname>::<name>`. A test belongs to a file when the test case
has a `file` attribute with that path, or when its class name, with dots read as
folders, names that file without its extension.

A Go report, such as gotestsum's, has no `file` attribute, and its class name is the
package's import path, such as `example.com/app/internal/logging`. A test of it belongs
to a Go test file when the import path ends with the file's folder and the file
defines the test's function. Only the caller can read the file, so it passes the names
each Go file defines. A package that does not compile has no test case for its tests: gotestsum writes
an empty test suite or one failed `<import path>::TestMain`.
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


def in_package(package: str, path: str) -> bool:
    """True when a Go import path is the package of the folder of a file. A file in the
    project's root folder matches no import path: the module's name is not known here."""
    folder = str(PurePosixPath(path).parent)
    return folder != "." and (package == folder or package.endswith("/" + folder))


def in_files(result: TestResult, files, defined: dict | None = None) -> bool:
    """Return True when the test comes from one of the files. defined maps a Go test file
    to the names of the test functions it defines."""
    if result.file:
        return result.file in files
    classname = result.id.split("::")[0]
    function = result.id.split("::")[-1].split("/")[0]
    for path in files:
        if path.endswith("_test.go"):
            if function in (defined or {}).get(path, ()) and in_package(classname, path):
                return True
            continue
        module = classname.replace(".", "/")
        stem = str(PurePosixPath(path).with_suffix(""))
        if module == stem or module.startswith(stem + "/"):
            return True
    return False
