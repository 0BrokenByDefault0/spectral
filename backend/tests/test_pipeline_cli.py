"""End-to-end run over a written file, plus the CLI's rendering and exit codes."""

from __future__ import annotations

import json

import numpy as np
import soundfile as sf

from app import cli
from app.analysis.pipeline import analyze_file
from app.db.repository import CatalogUnavailableError
from app.models.schemas import (
    AnalysisResult,
    PluginRecommendation,
    ProcessingCategory,
    SignalChain,
    SourceType,
    Tier,
)
from tests import synth


def write(tmp_path, signal, name="take.wav"):
    path = tmp_path / name
    sf.write(path, signal, synth.SR)
    return path


def test_pipeline_runs_without_the_llm(tmp_path):
    profile = analyze_file(write(tmp_path, synth.vocal()), use_llm=False)
    assert profile.source.source_type is SourceType.DRY_VOCAL
    assert profile.qualitative_summary
    assert any("Listening pass disabled" in note for note in profile.analysis_notes)


def test_pipeline_notes_a_missing_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    profile = analyze_file(write(tmp_path, synth.vocal()), use_llm=True)
    assert any("GEMINI_API_KEY" in note for note in profile.analysis_notes)


def test_pipeline_flags_a_full_mix(tmp_path):
    profile = analyze_file(write(tmp_path, synth.full_mix()), use_llm=False)
    assert profile.source.source_type is SourceType.FULL_MIX
    assert any("full mix" in note for note in profile.analysis_notes)


def test_cli_writes_json_and_prints_a_report(tmp_path, capsys):
    audio = write(tmp_path, synth.with_sibilance(synth.vocal()))
    out = tmp_path / "result.json"
    assert cli.main([str(audio), "--no-llm", "--json", str(out)]) == 0

    printed = capsys.readouterr().out
    assert "--- issues" in printed
    assert "Sibilance" in printed
    for tier in ("FREE", "MID", "PREMIUM"):
        assert f"--- {tier} chain" in printed

    saved = AnalysisResult.model_validate(json.loads(out.read_text()))
    assert any(issue.name == "Sibilance" for issue in saved.profile.issues)
    assert [chain.tier for chain in saved.chains] == [Tier.FREE, Tier.MID, Tier.PREMIUM]
    assert all(chain.steps for chain in saved.chains)


def test_cli_can_print_one_tier(tmp_path, capsys):
    audio = write(tmp_path, synth.vocal())
    assert cli.main([str(audio), "--no-llm", "--tier", "free"]) == 0

    printed = capsys.readouterr().out
    assert "--- FREE chain" in printed
    assert "--- PREMIUM chain" not in printed


def test_cli_can_skip_the_chains(tmp_path, capsys):
    audio = write(tmp_path, synth.vocal())
    assert cli.main([str(audio), "--no-llm", "--no-chains"]) == 0
    assert "chain" not in capsys.readouterr().out


def test_cli_still_analyses_without_a_catalog(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli.PluginCatalog, "load", _missing_catalog)
    audio = write(tmp_path, synth.vocal())
    assert cli.main([str(audio), "--no-llm"]) == 0

    captured = capsys.readouterr()
    assert "--- issues" in captured.out
    assert "skipping chains" in captured.err


def _missing_catalog(*args, **kwargs):
    raise CatalogUnavailableError("no plugin database at nowhere.db; run `python -m app.db.seed`")


def test_chain_rendering_shows_the_signal_flow(tmp_path, capsys):
    audio = write(tmp_path, synth.vocal())
    cli.main([str(audio), "--no-llm", "--tier", "MID"])
    printed = capsys.readouterr().out
    flow = next(line for line in printed.splitlines() if "→" in line)
    assert len(flow.split(" → ")) >= 2
    assert "to buy outright" in printed


def test_a_reused_plugin_is_only_counted_once_in_the_total():
    twice = SignalChain(
        tier=Tier.PREMIUM,
        steps=[_recommendation("Pro-Q 4", "$199"), _recommendation("Pro-Q 4", "$199")],
    )
    assert "about $199" in cli.render_chain(twice)


def _recommendation(name, price):
    return PluginRecommendation(
        plugin_name=name,
        tier=Tier.PREMIUM,
        category=ProcessingCategory.EQ,
        suggested_settings="x",
        why="y",
        price=price,
    )


def test_cli_rejects_a_missing_file(tmp_path, capsys):
    assert cli.main([str(tmp_path / "gone.wav"), "--no-llm"]) == 2
    assert "no such file" in capsys.readouterr().err


def test_cli_reports_a_clip_that_is_too_short(tmp_path, capsys):
    audio = write(tmp_path, np.zeros(int(0.3 * synth.SR), dtype=np.float32), "blip.wav")
    assert cli.main([str(audio), "--no-llm"]) == 1
    assert "cannot analyse" in capsys.readouterr().err


def test_deviation_bar_is_centred():
    assert cli._bar(0.0).strip() == ""
    assert cli._bar(12.0).startswith(" ")
    assert cli._bar(-12.0).endswith("#")
    assert len(cli._bar(99.0)) <= cli._BAR_WIDTH
