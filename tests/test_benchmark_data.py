from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from gosha.evaluation import evaluate
from scripts.generate_synthetic_benchmark import build_rows, perturbations, serialized

DATASET = Path("data/synthetic-benchmark-v1.jsonl")


def test_frozen_synthetic_benchmark_is_reproducible_and_balanced():
    rows = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines()]
    assert rows == build_rows()
    assert DATASET.read_text(encoding="utf-8") == serialized()
    assert len(rows) == 300
    assert len({row["id"] for row in rows}) == 300
    assert len({row["semantic_seed"] for row in rows}) == 30
    assert Counter(row["perturbation"] for row in rows) == Counter(
        {name: 30 for name, _ in perturbations("@gosha test")}
    )
    assert set(row["slice"] for row in rows) >= {"deadline_create", "material_save", "safety", "out_of_scope"}


def test_synthetic_benchmark_report_keeps_claim_boundary():
    report = evaluate(DATASET)
    assert report["n"] == 300
    assert report["dataset_kind"] == "synthetic_perturbation_benchmark"
    assert report["reproducibility"]["semantic_seeds"] == 30
    assert report["perturbation_metrics"]
    assert "not 300 independent cases" in report["claim_limit"]
