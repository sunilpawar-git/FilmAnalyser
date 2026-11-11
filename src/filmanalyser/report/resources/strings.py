"""Typed accessor for strings.toml: the only way code obtains user-facing text."""

import re
import string
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Self

from filmanalyser.core.errors import ResourceError
from filmanalyser.report.resources._toml import parse, read_packaged

_KEY = re.compile(r"^[a-z][a-z0-9_]*$")
_FILE = "strings.toml"


def _flatten(table: Mapping[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for name, value in table.items():
        key = f"{prefix}{name}"
        if not _KEY.match(name):
            raise ResourceError(f"invalid string key segment {name!r} in {key}")
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{key}."))
        elif isinstance(value, str):
            flat[key] = value
        else:
            raise ResourceError(f"string {key} must be text, got {type(value).__name__}")
    return flat


@dataclass(frozen=True)
class Strings:
    table: Mapping[str, str]

    @classmethod
    def from_text(cls, text: str) -> Self:
        return cls(MappingProxyType(_flatten(parse(text, _FILE))))

    @classmethod
    def load(cls) -> Self:
        return cls.from_text(read_packaged(_FILE))

    def keys(self) -> frozenset[str]:
        return frozenset(self.table)

    def text(self, key: str, **fields: str | int | float) -> str:
        try:
            template = string.Template(self.table[key])
        except KeyError:
            raise ResourceError(f"unknown string key: {key}") from None
        try:
            return template.substitute(fields)
        except KeyError as exc:
            raise ResourceError(f"string {key} needs field {exc.args[0]}") from None
