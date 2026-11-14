"""Phase 6 guards (DECISIONS #90 to #92): planted violations of the analysis layer's purity rules,
and mutations of the act-break rules that a named test must catch. Each planted violation must fail
for its stated reason; each mutation must turn its named test red."""

from guard_probes import Probe, _arch, _mutation, _probe

ANALYSIS = "src/filmanalyser/analysis"
CONFIG = "src/filmanalyser/core/config.py"
ACT_TESTS = "tests/unit/test_act_breaks.py"


def phase6_probes() -> list[Probe]:
    purity = _arch("test_analysis_purity.py")
    return [
        _probe("analysis uses randomness", "analysis", "import random\n", purity),
        _probe("analysis reads the clock", "analysis", "import time\n", purity),
        _probe("analysis prints", "analysis", "def f() -> None:\n    print(1)\n", purity),
        _probe("analysis hides a threshold in code", "analysis", "LIMIT = 0.75\n", purity),
        _probe(
            "analysis imports report",
            "analysis",
            "from filmanalyser.report import resources\n",
            _arch("test_layer_imports.py"),
        ),
        _probe("analysis imports os", "analysis", "import os\n", _arch("test_layer_imports.py")),
    ]


def phase6_mutation_probes() -> list[Probe]:
    return [
        _mutation(
            "loudness floor read as a value, not as missing",
            f"{ANALYSIS}/timeline.py",
            ("series[f.LUFS] <= LOUDNESS_ABS_GATE_LUFS", "series[f.LUFS] <= -999.0"),
            ACT_TESTS,
            "test_a_silent_stretch_does_not_read_as_a_loudness_drop",
        ),
        _mutation(
            "first zone widened to the film's start (changes outside the zone reported)",
            CONFIG,
            ("ACT_ZONE_1 = (0.15, 0.40)", "ACT_ZONE_1 = (0.0, 0.40)"),
            ACT_TESTS,
            "test_a_change_outside_both_zones_is_not_reported",
        ),
        _mutation(
            "break threshold ignored",
            f"{ANALYSIS}/act_breaks.py",
            ("_local_maxima(scores, settings.min_score,", "_local_maxima(scores, -1.0,"),
            ACT_TESTS,
            "test_the_threshold_is_the_setting_not_a_constant",
        ),
        _mutation(
            "close candidates not merged",
            f"{ANALYSIS}/act_breaks.py",
            ("abs(t - other) >= gap", "abs(t - other) >= 0"),
            ACT_TESTS,
            "test_a_stronger_change_just_outside_a_zone_absorbs_a_close_candidate_inside_it",
        ),
    ]
