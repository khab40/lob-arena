"""Apply reviewed workload placement before collection and fixture setup."""
from scripts.ci_pytest_guard import (  # noqa: F401
    pytest_collection_modifyitems,
    pytest_configure,
    pytest_report_header,
)
