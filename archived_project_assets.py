"""Compatibility imports for completed-synthesis asset persistence.

Implementation lives in xinpilot.application.project_history. Historical module
imports remain supported for controllers, tools, and existing project tests.
"""
from xinpilot.application.project_history import (
    IMAGE_SUFFIXES,
    RESULT_DIRS,
    RESULT_TABLES,
    _existing_file,
    _token,
    package_archived_steps,
    resolve_archived_steps,
)

__all__ = [
    "IMAGE_SUFFIXES", "RESULT_DIRS", "RESULT_TABLES",
    "package_archived_steps", "resolve_archived_steps",
]
