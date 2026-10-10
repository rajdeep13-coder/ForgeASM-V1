from __future__ import annotations

import json

from eval.run import render_report, task_files, validate_references
from eval.task_catalog import task_records


def test_task_corpus_has_25_to_30_tasks_and_all_references_pass():
    assert 25 <= len(task_files()) <= 30
    assert len(task_records()) <= len(task_files())
    references = validate_references()
    assert len(references) >= 25


def test_results_report_is_replayable(tmp_path):
    data = {"schema_version": 1, "references": [], "cells": []}
    path = tmp_path / "results.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert "No completed cells" in render_report(json.loads(path.read_text()))
