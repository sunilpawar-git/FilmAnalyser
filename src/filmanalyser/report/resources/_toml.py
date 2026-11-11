"""Shared TOML reading for the resource loaders."""

import tomllib
from collections.abc import Mapping
from importlib import resources
from typing import Any

from filmanalyser.core.errors import ResourceError


def read_packaged(filename: str) -> str:
    try:
        return resources.files(__package__).joinpath(filename).read_text(encoding="utf-8")
    except OSError as exc:
        raise ResourceError(f"cannot read packaged resource {filename}") from exc


def parse(text: str, source: str) -> Mapping[str, Any]:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ResourceError(f"{source} is not valid TOML: {exc}") from exc
