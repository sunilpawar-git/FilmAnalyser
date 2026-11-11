"""strings.toml / colors.toml loaders and their typed accessors."""

import dataclasses

import pytest

from filmanalyser.core.errors import ERROR_TAXONOMY, ResourceError
from filmanalyser.report.resources._toml import read_packaged
from filmanalyser.report.resources.colors import ColorTokens
from filmanalyser.report.resources.strings import Strings

PALETTE = 'background = "#ffffff"\ntext = "#000000"\n'
VALID_COLORS = f'[light]\n{PALETTE}\n[dark]\nbackground = "#000000"\ntext = "#ffffff"\n'


# ------------------------------------------------------------------ strings
def test_packaged_strings_load_and_resolve() -> None:
    assert Strings.load().text("app.name") == "FilmAnalyser"


def test_nested_tables_flatten_to_dotted_keys() -> None:
    strings = Strings.from_text('[a]\nb = "x"\n[a.c]\nd = "y"\n')
    assert strings.keys() == frozenset({"a.b", "a.c.d"})


def test_text_substitutes_fields() -> None:
    strings = Strings.from_text('[cli]\nversion = "$name $version"\n')
    assert strings.text("cli.version", name="FA", version=1) == "FA 1"


def test_text_does_not_interpret_attribute_access() -> None:
    strings = Strings.from_text('[a]\nb = "{0.__class__} ${x}"\n')
    assert strings.text("a.b", x="ok") == "{0.__class__} ok"


def test_unknown_key_raises() -> None:
    with pytest.raises(ResourceError, match="no.such"):
        Strings.load().text("no.such")


def test_missing_field_raises() -> None:
    with pytest.raises(ResourceError, match="version"):
        Strings.from_text('[a]\nb = "$version"\n').text("a.b")


def test_non_string_value_rejected() -> None:
    with pytest.raises(ResourceError, match="a.b"):
        Strings.from_text("[a]\nb = 3\n")


def test_bad_key_name_rejected() -> None:
    with pytest.raises(ResourceError, match="Bad-Key"):
        Strings.from_text('[a]\nBad-Key = "x"\n')


def test_invalid_toml_rejected() -> None:
    with pytest.raises(ResourceError):
        Strings.from_text("this is = = not toml")


def test_strings_are_immutable() -> None:
    strings = Strings.load()
    with pytest.raises(dataclasses.FrozenInstanceError):
        strings.table = {}  # type: ignore[misc]
    with pytest.raises(TypeError):
        strings.table["x"] = "y"  # type: ignore[index]


def test_every_error_message_key_exists() -> None:
    keys = Strings.load().keys()
    assert {cls.message_key for cls in ERROR_TAXONOMY} <= keys


# ------------------------------------------------------------------- colors
def test_packaged_tokens_have_matching_light_and_dark_sets() -> None:
    tokens = ColorTokens.load()
    assert set(tokens.theme("light")) == set(tokens.theme("dark")) != set()


def test_css_defines_light_root_and_dark_media_query() -> None:
    css = ColorTokens.from_text(VALID_COLORS).css()
    assert ":root {\n  --background: #ffffff;" in css
    assert "@media (prefers-color-scheme: dark)" in css
    assert "--background: #000000;" in css


def test_css_emits_every_token_in_both_themes() -> None:
    tokens = ColorTokens.load()
    css = tokens.css()
    for name in tokens.theme("light"):
        assert css.count(f"--{name}:") == 2


def test_dark_theme_must_match_light_token_names() -> None:
    text = f'[light]\n{PALETTE}\n[dark]\nbackground = "#000000"\n'
    with pytest.raises(ResourceError, match="text"):
        ColorTokens.from_text(text)


def test_missing_theme_rejected() -> None:
    with pytest.raises(ResourceError, match="dark"):
        ColorTokens.from_text(f"[light]\n{PALETTE}")


@pytest.mark.parametrize("bad", ["red", "#fff", "#GGGGGG", "#FFFFFF", "rgb(0,0,0)"])
def test_only_lowercase_six_digit_hex_accepted(bad: str) -> None:
    text = f'[light]\nbackground = "{bad}"\n[dark]\nbackground = "#000000"\n'
    with pytest.raises(ResourceError, match="background"):
        ColorTokens.from_text(text)


def test_bad_token_name_rejected() -> None:
    text = '[light]\nBad = "#000000"\n[dark]\nBad = "#000000"\n'
    with pytest.raises(ResourceError, match="Bad"):
        ColorTokens.from_text(text)


def test_unknown_theme_lookup_raises() -> None:
    with pytest.raises(ResourceError, match="sepia"):
        ColorTokens.load().theme("sepia")


def test_tokens_are_immutable() -> None:
    tokens = ColorTokens.load()
    with pytest.raises(dataclasses.FrozenInstanceError):
        tokens.light = {}  # type: ignore[misc]
    with pytest.raises(TypeError):
        tokens.theme("light")["text"] = "#000000"  # type: ignore[index]


def test_invalid_color_toml_rejected() -> None:
    with pytest.raises(ResourceError):
        ColorTokens.from_text("[light\n")


def test_missing_packaged_file_raises() -> None:
    with pytest.raises(ResourceError, match="nope.toml"):
        read_packaged("nope.toml")
