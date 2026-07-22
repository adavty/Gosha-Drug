from __future__ import annotations

import json
import sys

import pytest

from gosha.cli import main


def invoke(monkeypatch, capsys, *args):
    monkeypatch.setattr(sys, "argv", ["gosha", *map(str, args)])
    main()
    return capsys.readouterr()


def test_cli_full_deadline_flow(tmp_path, monkeypatch, capsys):
    database = tmp_path / "cli.db"
    assert invoke(monkeypatch, capsys, "--db", database, "setup-chat", "group-1", "Europe/Moscow").out.strip() == "ok"

    preview = json.loads(invoke(
        monkeypatch, capsys, "--db", database, "ask", "group-1", "alen",
        "/deadline_add Защита | 2099-08-20 | 18:00",
    ).out)
    assert preview["status"] == "preview"

    confirmed = json.loads(invoke(
        monkeypatch, capsys, "--db", database, "confirm", "group-1", "alen",
        preview["data"]["pending_id"], "cli-request-1",
    ).out)
    assert confirmed["status"] == "success"

    listed = json.loads(invoke(
        monkeypatch, capsys, "--db", database, "ask", "group-1", "dasha", "/deadlines",
    ).out)
    assert listed["data"]["deadlines"][0]["title"] == "Защита"


def test_cli_evaluate_writes_report_and_rejects_partial_pricing(tmp_path, monkeypatch, capsys):
    output = tmp_path / "evaluation.json"
    result = json.loads(invoke(
        monkeypatch, capsys, "evaluate", "data/synthetic-eval.jsonl", "--output", output,
    ).out)
    assert result["n"] == 26
    assert json.loads(output.read_text(encoding="utf-8"))["dataset_kind"] == "synthetic_smoke_test"

    monkeypatch.setattr(sys, "argv", [
        "gosha", "evaluate", "data/synthetic-eval.jsonl", "--input-usd-per-million", "1.0",
    ])
    with pytest.raises(SystemExit, match="2"):
        main()
    assert "both pricing arguments are required together" in capsys.readouterr().err
