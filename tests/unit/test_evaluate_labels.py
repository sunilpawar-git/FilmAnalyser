"""The label format and the scoring (pure: no film is opened). Tools: scripts/evaluate_labels.py."""

import numpy as np
import pytest

from evaluate_labels import (
    Labels,
    Span,
    gap,
    inside,
    parse_labels,
    score_cuts,
    score_kind,
)

LABELS = """# a film, labelled by hand
speech 12.0 15.5   # dialogue
speech 40 44
music 0 10
silence 20 21
cut 31.04
cut 5.0
ebur128_integrated -34.0
ebur128_true_peak -0.3
"""


def test_a_label_file_parses_spans_cuts_and_reference_readings() -> None:
    labels = parse_labels(LABELS)
    assert labels.spans[0] == Span("speech", 12.0, 15.5)
    assert len(labels.spans) == 4
    assert labels.cuts == (5.0, 31.04)  # sorted
    assert labels.ebur_integrated == -34.0
    assert labels.ebur_true_peak == -0.3


def test_an_empty_label_file_is_valid() -> None:
    assert parse_labels("") == Labels((), ())


@pytest.mark.parametrize(
    "line",
    [
        "speech 5 3",  # start after end
        "speech -1 3",  # negative start
        "laughter 1 2",  # unknown kind
        "cut",  # missing time
        "cut soon",  # not a number
        "ebur128_integrated loud",  # not a number
    ],
)
def test_a_bad_line_is_refused_with_its_line_number(line: str) -> None:
    with pytest.raises(ValueError, match="line 2"):
        parse_labels("# header\n" + line + "\n")


def test_overlapping_spans_of_one_kind_are_refused() -> None:
    with pytest.raises(ValueError, match="overlap"):
        parse_labels("speech 1 5\nspeech 4 6\n")


def test_speech_over_music_is_allowed() -> None:
    labels = parse_labels("music 0 10\nspeech 2 4\n")
    assert len(labels.spans) == 2


def test_inside_marks_the_times_within_a_kind() -> None:
    labels = parse_labels("speech 1 2\nmusic 2 3\n")
    times = np.array([0.5, 1.0, 1.99, 2.0, 2.5])
    assert inside(labels.spans, "speech", times).tolist() == [False, True, True, False, False]


def test_precision_and_recall_count_only_the_covered_windows() -> None:
    labels = parse_labels("speech 0 4\nmusic 4 8\n")
    times = np.arange(0.0, 10.0, 1.0)  # 0..9; 8 and 9 are not labelled
    predicted = np.array([1, 1, 1, 0, 1, 0, 0, 0, 1, 1], dtype=bool)
    score = score_kind(labels, "speech", times, predicted)
    assert score.count == 8
    # covered windows 0..7; predicted speech there: 0,1,2,4 (3 of them right, speech is 0..3)
    assert score.precision == pytest.approx(3 / 4)
    assert score.recall == pytest.approx(3 / 4)


def test_a_kind_with_nothing_predicted_has_no_precision() -> None:
    labels = parse_labels("speech 0 4\n")
    score = score_kind(labels, "speech", np.arange(4.0), np.zeros(4, dtype=bool))
    assert score.precision is None
    assert score.recall == 0.0


def test_cut_precision_and_recall_within_a_tolerance() -> None:
    truth = (3.0, 6.0)
    found = np.array([3.1, 4.5])  # one right, one spurious; 6.0 missed
    score = score_cuts(truth, found, tolerance=0.25)
    assert score.precision == pytest.approx(1 / 2)
    assert score.recall == pytest.approx(1 / 2)


def test_no_cuts_found_or_labelled_gives_no_scores() -> None:
    assert score_cuts((), np.array([]), 0.25) == score_cuts((), np.array([]), 0.25)
    empty = score_cuts((), np.array([1.0]), 0.25)
    assert empty.precision == 0.0 and empty.recall is None


def test_the_gap_is_ours_minus_the_reference() -> None:
    assert gap(-33.9, -34.0) == pytest.approx(0.1)
    assert gap(None, -34.0) is None
