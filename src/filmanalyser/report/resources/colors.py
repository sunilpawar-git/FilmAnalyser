"""Typed accessor for colors.toml (design tokens, light and dark) and the WCAG contrast maths."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Self

from filmanalyser.core.errors import ResourceError
from filmanalyser.report.resources._toml import parse, read_packaged

_NAME = re.compile(r"^[a-z][a-z0-9-]*$")
_HEX = re.compile(r"^#[0-9a-f]{6}$")
_FILE = "colors.toml"
THEMES = ("light", "dark")


@dataclass(frozen=True)
class ContrastRule:
    """foreground on background must reach `minimum` (4.5 = AA text, 3.0 = AA non-text)."""

    foreground: str
    background: str
    minimum: float


_TEXT, _UI = 4.5, 3.0
CONTRAST_RULES: tuple[ContrastRule, ...] = (
    *(
        ContrastRule(fg, bg, _TEXT)
        for fg in ("text", "text-muted", "accent", "warning", "danger")
        for bg in ("background", "surface")
    ),
    ContrastRule("border", "background", _UI),
)


def _channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(color: str) -> float:
    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG 2.x contrast ratio between two #rrggbb colours (1.0 to 21.0)."""
    light, dark = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def _palette(table: Mapping[str, Any], theme: str) -> Mapping[str, str]:
    raw = table.get(theme)
    if not isinstance(raw, dict):
        raise ResourceError(f"{_FILE} is missing the [{theme}] theme")
    for name, value in raw.items():
        if not _NAME.match(name):
            raise ResourceError(f"invalid token name {name!r} in [{theme}]")
        if not isinstance(value, str) or not _HEX.match(value):
            raise ResourceError(f"token {name} in [{theme}] must be lowercase #rrggbb")
    return MappingProxyType(dict(raw))


@dataclass(frozen=True)
class ColorTokens:
    light: Mapping[str, str]
    dark: Mapping[str, str]

    def __post_init__(self) -> None:
        if set(self.light) != set(self.dark):
            diff = sorted(set(self.light) ^ set(self.dark))
            raise ResourceError(f"light and dark themes differ in tokens: {', '.join(diff)}")

    @classmethod
    def from_text(cls, text: str) -> Self:
        table = parse(text, _FILE)
        return cls(light=_palette(table, "light"), dark=_palette(table, "dark"))

    @classmethod
    def load(cls) -> Self:
        return cls.from_text(read_packaged(_FILE))

    def theme(self, name: str) -> Mapping[str, str]:
        if name not in THEMES:
            raise ResourceError(f"unknown theme: {name}")
        return self.light if name == "light" else self.dark

    def css(self) -> str:
        """CSS custom properties: light on :root, dark under prefers-color-scheme."""
        return (
            f":root {{\n{_declarations(self.light, 2)}}}\n"
            f"@media (prefers-color-scheme: dark) {{\n  :root {{\n"
            f"{_declarations(self.dark, 4)}  }}\n}}\n"
        )


def _declarations(palette: Mapping[str, str], indent: int) -> str:
    pad = " " * indent
    return "".join(f"{pad}--{name}: {value};\n" for name, value in palette.items())
