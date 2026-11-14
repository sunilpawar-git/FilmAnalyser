"""Phase 4 guards: planted violations and mutation probes for the rules that phase adds
(DECISIONS #49-#58), and for the opt-in voice separation (#88). Kept apart from guard_probes.py to
stay within the 300-line limit. Each planted violation must fail for its stated reason; each
mutation must turn its named test red."""

from guard_probes import PROBE, Probe, _arch, _mutation, _probe


def phase4_probes() -> list[Probe]:
    """Planted violations for the rules Phase 4 adds (each must fail for its stated reason)."""
    skipped = "import pytest\n\n\ndef test_x() -> None:\n    pytest.skip('no ffmpeg')\n"
    return [
        Probe(
            "test that skips (no skips rule)",
            f"tests/unit/{PROBE}.py",
            skipped,
            _arch("test_no_skips.py"),
            PROBE,
        ),
        _probe(
            "extractor imports media (layer rule)",
            "extractors",
            "from filmanalyser.media import paths\n",
            _arch("test_layer_imports.py"),
        ),
        _probe(
            "plain English text in the CLI (not from strings.toml)",
            "cli",
            'print("Analysis finished")\n',
            _arch("test_no_hardcoded_strings.py"),
        ),
    ]


def pipeline_mutations() -> list[Probe]:
    """Phase 4 measures in the decoder and the extractors: each removal must turn its test red."""
    media = "src/filmanalyser"
    return [
        _mutation(
            "resume grid re-anchored to the first decoded frame (P3-1)",
            f"{media}/media/ffmpeg_stream.py",
            ("setpts=PTS-{seek.origin_s}/TB", "setpts=PTS-STARTPTS"),
            "tests/integration/test_resume_grid.py",
            "test_resumed_chunks_sample_the_same_frames_as_an_uninterrupted_run",
        ),
        _mutation(
            "boundary cut dropped (overlap not compared)",
            f"{media}/extractors/shot_cuts.py",
            (
                "    first = max(1, context_frames)\n    gradual: list[tuple[int, int]] = []",
                "    first = max(1, context_frames + 1)\n    gradual: list[tuple[int, int]] = []",
            ),
            "tests/unit/test_shot_cuts.py",
            "test_a_cut_on_the_first_core_frame_is_counted_once_in_its_own_chunk",
        ),
    ]


def report_mutations() -> list[Probe]:
    """Report and workflow measures: escaping, the content security policy, nightly permissions."""
    report = "src/filmanalyser/report"
    return [
        _mutation(
            "report not autoescaped",
            f"{report}/renderer.py",
            ("autoescape=True,", "autoescape=False,"),
            "tests/unit/test_renderer.py",
            "test_the_film_name_is_escaped_not_injected",
        ),
        _mutation(
            "report allows external requests (CSP removed)",
            f"{report}/templates/report.html",
            (
                "default-src 'none'; style-src 'unsafe-inline'",
                "default-src *; style-src 'unsafe-inline'",
            ),
            "tests/unit/test_renderer.py",
            "test_a_strict_content_security_policy_forbids_network_and_scripts",
        ),
        _mutation(
            "letterbox bars from one dark frame (median removed)",
            "src/filmanalyser/extractors/letterbox.py",
            ("return np.median(means, axis=0)", "return np.min(means, axis=0)"),
            "tests/unit/test_letterbox.py",
            "test_a_single_dark_frame_in_the_chunk_does_not_create_bars",
        ),
        _mutation(
            "nightly workflow gets write access",
            ".github/workflows/nightly.yml",
            ("permissions:\n  contents: read", "permissions: write-all"),
            "tests/architecture/test_nightly_workflow.py",
            "test_nightly_uses_least_privilege_and_pinned_actions",
        ),
    ]


def _separation(name: str, change: tuple[str, str], expect: str) -> Probe:
    """A mutation of media/separation.py that a test in test_separation.py must catch."""
    path = "src/filmanalyser/media/separation.py"
    return _mutation(name, path, change, "tests/unit/test_separation.py", expect)


def separation_mutations() -> list[Probe]:
    """Opt-in voice separation (DECISIONS #88): no download at run time, the same stem every run, a
    verified model only, and never on a 5.1 film."""
    command = "test_the_separation_command_uses_the_pinned_model_offline"
    return [
        _separation(
            "separation may download its model (--repo removed)",
            ('"--repo", str(model_dir), ', ""),
            command,
        ),
        _separation(
            "separation output made random (shifts removed)", ('"--shifts", "0",', ""), command
        ),
        _separation(
            "separation model used without its check",
            ("    verify_model_dir(model_dir, separation_pins() if pins is None else pins)\n", ""),
            "test_the_separator_refuses_a_model_that_fails_its_check",
        ),
        _separation(
            "separation model hash not compared",
            ("if not hmac.compare_digest(actual, expected):", "if False:"),
            "test_a_folder_that_does_not_match_is_refused",
        ),
        _mutation(
            "5.1 film separated instead of using its centre channel",
            "src/filmanalyser/pipeline/runner.py",
            ("audio.channels == FIVE_ONE_CHANNELS:", "audio.channels == -1:"),
            "tests/integration/test_separation_pipeline.py",
            "test_a_five_one_film_uses_its_centre_channel_instead",
        ),
    ]


def phase4_mutation_probes() -> list[Probe]:
    return [*pipeline_mutations(), *report_mutations(), *separation_mutations()]
