"""Parses/renders the `---`-delimited YAML frontmatter block (WIKI_SPEC.md §4.1).
An I/O-adjacent format concern, deliberately kept out of the domain layer."""

from __future__ import annotations

import yaml

_DELIMITER = "---"


class FrontmatterParseError(ValueError):
    pass


def parse(text: str) -> tuple[dict, str]:
    """Returns (frontmatter_dict, body). Raises FrontmatterParseError if the file
    has no parseable frontmatter block (WIKI_SPEC.md §11: every non-reserved .md
    file must have one)."""
    if not text.startswith(_DELIMITER):
        raise FrontmatterParseError("file does not start with a `---` frontmatter block")

    _, _, rest = text.partition(_DELIMITER)
    rest = rest[1:] if rest.startswith("\n") else rest
    raw_frontmatter, sep, body = rest.partition(f"\n{_DELIMITER}")
    if not sep:
        raise FrontmatterParseError("unterminated frontmatter block (missing closing `---`)")

    try:
        data = yaml.safe_load(raw_frontmatter) or {}
    except yaml.YAMLError as exc:
        raise FrontmatterParseError(f"invalid YAML frontmatter: {exc}") from exc

    if not isinstance(data, dict):
        raise FrontmatterParseError("frontmatter block must be a YAML mapping")

    return data, body.lstrip("\n")


def render(data: dict, body: str) -> str:
    yaml_block = yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip()
    return f"{_DELIMITER}\n{yaml_block}\n{_DELIMITER}\n\n{body.strip()}\n"
