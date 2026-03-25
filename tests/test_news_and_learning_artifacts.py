import json
from pathlib import Path

from newsworker.worker import run_demo
from vaiiixaprende.colab_artifacts import save_stats


def test_newsworker_generates_snapshot(tmp_path: Path):
    cwd = Path.cwd()
    try:
        import os
        os.chdir(tmp_path)
        run_demo()
        payload = json.loads((tmp_path / "artifacts" / "news_snapshot.json").read_text(encoding="utf-8"))
        assert payload["symbol"] == "ITUB4"
        assert "summary" in payload
    finally:
        os.chdir(cwd)


def test_vaiiixaprende_generates_stats(tmp_path: Path):
    target = save_stats(str(tmp_path / "artifacts"))
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["samples"] > 0
    assert payload["model_version"]
