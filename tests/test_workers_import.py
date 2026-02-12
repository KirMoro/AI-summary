"""Regression tests for RQ task import paths."""

import app.workers as workers_pkg


def test_workers_package_exposes_tasks_module():
    assert hasattr(workers_pkg, "tasks")
