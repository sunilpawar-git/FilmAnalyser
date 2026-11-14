"""Phase 8 guards (CLI and release): mutations that remove one safety measure of the command or
of the release workflow; the named test must then fail."""

from guard_probes import Probe, _mutation

CLI = "src/filmanalyser/cli"
UNIT = "tests/unit"
INTEGRATION = "tests/integration"
ARCH = "tests/architecture"
RELEASE = ".github/workflows/release.yml"


def _command_mutations() -> list[Probe]:
    codes = f"{INTEGRATION}/test_exit_codes.py"
    return [
        _mutation(
            "the report may overwrite the film",
            f"{CLI}/run.py",
            ("if report.resolve() == film:", "if False:"),
            codes,
            "test_the_report_may_not_overwrite_the_film",
        ),
        _mutation(
            "an interrupt exits as an internal error",
            f"{CLI}/main.py",
            ("return EXIT_INTERRUPTED", "return 1"),
            codes,
            "test_an_interrupt_is_130_and_says_how_to_resume",
        ),
        _mutation(
            "an unexpected failure prints its traceback without -v",
            f"{CLI}/main.py",
            (
                "        if options.verbose:\n            traceback",
                "        if True:\n            traceback",
            ),
            codes,
            "test_an_unexpected_failure_is_1_with_a_message_and_no_traceback",
        ),
        _mutation(
            "a file name's terminal escape is printed as it is",
            f"{CLI}/main.py",
            ('ch if ch.isprintable() else "?"', "ch"),
            f"{INTEGRATION}/test_hostile_names.py",
            "test_a_terminal_escape_in_the_name_never_reaches_the_screen",
        ),
    ]


def _reset_mutations() -> list[Probe]:
    reset = f"{UNIT}/test_store_reset.py"
    return [
        _mutation(
            "--fresh deletes files that are not the store's",
            "src/filmanalyser/storage/reset.py",
            ("(CHUNK_GLOB,", '("*",'),
            reset,
            "test_clear_store_leaves_every_other_file_alone",
        ),
        _mutation(
            "--fresh follows a symlink",
            "src/filmanalyser/storage/files.py",
            (
                "if path.is_file() and not path.is_symlink():\n                path.unlink()",
                "if path.is_file():\n                path.unlink()",
            ),
            reset,
            "test_clear_store_never_follows_a_symlink",
        ),
    ]


def _release_mutations() -> list[Probe]:
    workflow = f"{ARCH}/test_release_workflow.py"
    return [
        _mutation(
            "release builds before the suite passed",
            RELEASE,
            ("    needs: check\n", ""),
            workflow,
            "test_the_full_suite_is_ci_itself_and_runs_first",
        ),
        _mutation(
            "release workflow can write in every job",
            RELEASE,
            (
                "permissions:\n  contents: read\n\nconcurrency",
                "permissions:\n  contents: write\n\nconcurrency",
            ),
            workflow,
            "test_only_the_publish_job_can_write",
        ),
        _mutation(
            "release published without a checksum check",
            RELEASE,
            ("(cd dist && shasum -a 256 -c SHA256SUMS)\n", ""),
            workflow,
            "test_the_checksums_are_verified_before_publishing_and_the_tag_must_exist",
        ),
        _mutation(
            "release notes accept a tag that is not the version",
            "scripts/release_notes.py",
            ("or version != project_version(pyproject)", ""),
            f"{UNIT}/test_release_notes.py",
            "test_a_tag_that_is_not_the_project_version_is_refused",
        ),
    ]


def _quality_mutations() -> list[Probe]:
    return [
        _mutation(
            "an extractor version is bumped without updating the frozen schema",
            "src/filmanalyser/extractors/loudness.py",
            ("VERSION = 3", "VERSION = 4"),
            f"{UNIT}/test_schema_frozen.py",
            "test_the_extractors_and_their_features_are_the_frozen_ones",
        ),
        _mutation(
            "the luma weights change without updating the golden clip",
            "src/filmanalyser/core/config.py",
            ("LUMA_WEIGHTS = (0.2126, 0.7152, 0.0722)", "LUMA_WEIGHTS = (0.3333, 0.3333, 0.3334)"),
            f"{INTEGRATION}/test_golden_clip.py",
            "test_the_stored_features_match_the_golden_file",
        ),
    ]


def _memory_mutations() -> list[Probe]:
    return [
        _mutation(
            "loudness transforms a whole window at once (5.1 memory peak)",
            "src/filmanalyser/extractors/_convolve.py",
            ("BLOCK = 1 << 16", "BLOCK = 1 << 24"),
            f"{UNIT}/test_convolve.py",
            "test_five_one_loudness_work_stays_under_a_bound",
        ),
    ]


def phase8_mutation_probes() -> list[Probe]:
    return [
        *_command_mutations(),
        *_reset_mutations(),
        *_release_mutations(),
        *_quality_mutations(),
        *_memory_mutations(),
    ]
