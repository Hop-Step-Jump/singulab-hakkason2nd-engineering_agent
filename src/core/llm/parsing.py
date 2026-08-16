"""LLM response parsing with explicit observability.

Cycle 11 (Codex P0): every prior cycle relied on a `find("{")` /
`rfind("}")` plus `json.loads` slice and silently fell back to
hard-coded defaults on any failure. C10 (qwen3:14b) burned a 90-minute
run because every action produced empty `reasoning` / `memory` —
classified as "behavior change" until manual inspection revealed
*all 360 agent steps were parser fallbacks*.

This module exposes:

- `strip_thinking_tags(text)`  — robust against multiple thinking-tag
  conventions (`<think>`, `<thinking>`, `<thought>`) and unclosed
  thinking blocks (truncation at max_tokens).

- `extract_json_block(text)` — locates the most plausible balanced JSON
  block in a response. Prefers the LAST balanced object (LLMs that
  emit thinking and then JSON tend to put the answer at the end).

- `parse_json_response(text, required, alias)` — runs the strip +
  extract + json.loads pipeline and returns a `ParsedResponse` with
  `data`, `status`, `error`, `raw_excerpt`, `clean_excerpt`. The caller
  classifies status (`ok` / `partial` / `fallback` / `empty_response`)
  using the parsed data and required-field set.

Status semantics (used downstream by emergence_metrics for
`parse_fallback_rate`):
  ok            — JSON parsed AND all required fields present and
                  valid. Behavioral signal is trustworthy.
  partial       — JSON parsed but some required field missing /
                  invalid; default substituted. Behavioral signal is
                  partially trustworthy.
  fallback      — JSON could not be parsed. All defaults used. Do
                  NOT treat the action as agent decision.
  empty_response — LLM returned empty or whitespace-only text.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple


# Multiple thinking-tag conventions seen across Ollama- and vLLM-served models.
# Closed forms first; unclosed last (so we only strip-to-end if no closer).
_THINKING_TAG_RE = re.compile(
    r"<(?:think|thinking|thought)>.*?</(?:think|thinking|thought)>",
    re.DOTALL | re.IGNORECASE,
)
_UNCLOSED_THINKING_RE = re.compile(
    r"<(?:think|thinking|thought)>.*$",
    re.DOTALL | re.IGNORECASE,
)


def strip_thinking_tags(text: str) -> str:
    """Remove `<think>...</think>` and similar reasoning blocks.

    Handles closed and unclosed variants. Qwen3 in thinking mode under
    a tight max_tokens often truncates inside the thinking block; an
    unclosed `<think>` then leaves the answer never written. We strip
    everything from an unclosed thinking tag onward as a defensive
    measure (this is what the legacy parser missed).
    """
    if not text:
        return text
    text = _THINKING_TAG_RE.sub("", text)
    text = _UNCLOSED_THINKING_RE.sub("", text)
    return text


def extract_json_block(text: str) -> Optional[str]:
    """Return the last balanced JSON object substring in `text`.

    Why the LAST: LLMs that produce both reasoning and a final JSON
    answer typically place the answer last. Prior code used the FIRST
    `{`, which on a model that emits "I think the action should be ..."
    before the JSON would slice a non-JSON prefix.

    Robustness (CR-1 Finding 4): if a `{` opens an unbalanced region,
    we skip past that `{` and keep searching from the next character.
    Prior implementation `break`-ed on the first unbalanced opener,
    which made `analysis { not json\n{"action":"stay"}` return None.

    Walks the string with a depth counter, ignoring braces inside
    strings. Returns None if no balanced object is found anywhere.
    """
    if not text:
        return None
    n = len(text)
    last_block: Optional[Tuple[int, int]] = None
    i = 0
    while i < n:
        if text[i] == "{":
            depth = 1
            j = i + 1
            in_string = False
            escape = False
            while j < n and depth > 0:
                ch = text[j]
                if in_string:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_string = False
                else:
                    if ch == '"':
                        in_string = True
                    elif ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                j += 1
            if depth == 0:
                last_block = (i, j)
                i = j
                continue
            # Unbalanced opener: skip past this `{` and keep searching
            # so that broken preambles ("analysis { not json\n{...}")
            # do not hide a valid JSON later in the response.
            i += 1
            continue
        i += 1
    if last_block is None:
        return None
    s, e = last_block
    return text[s:e]


@dataclass
class ParsedResponse:
    data: Dict[str, Any]
    status: str          # "ok" | "partial" | "fallback" | "empty_response"
    error: Optional[str]
    raw_excerpt: str     # truncated raw response for logging
    clean_excerpt: str   # post strip-thinking-tags excerpt

    def to_log_fields(self) -> Dict[str, Any]:
        """Flat fields ready to embed in a JSONL log row."""
        return {
            "parse_status": self.status,
            "parse_error": self.error,
            "raw_response_excerpt": self.raw_excerpt,
        }


def _excerpt(text: str, head: int = 240, tail: int = 240) -> str:
    if text is None:
        return ""
    s = str(text)
    if len(s) <= head + tail + 16:
        return s
    return f"{s[:head]} … [truncated {len(s) - head - tail} chars] … {s[-tail:]}"


def parse_json_response(
    text: str,
    required: Iterable[str] = (),
    aliases: Optional[Dict[str, Iterable[str]]] = None,
) -> ParsedResponse:
    """Parse a JSON-bearing LLM response with rich diagnostics.

    Parameters
    ----------
    text : raw model response.
    required : field names the caller treats as required for `ok` status.
    aliases : optional map from canonical name → alternate names the
        caller is willing to accept (e.g. {"action": ["decision"]}).
        If a canonical key is missing but an alias is present, we copy
        the alias value into the canonical key and mark `status=partial`.

    Returns ParsedResponse. On any failure the data is `{}` and the
    caller substitutes defaults.
    """
    raw_excerpt = _excerpt(text or "")
    if not text or not text.strip():
        return ParsedResponse({}, "empty_response", "empty or whitespace only",
                              raw_excerpt, "")

    cleaned = strip_thinking_tags(text)
    clean_excerpt = _excerpt(cleaned)
    block = extract_json_block(cleaned)
    if block is None:
        return ParsedResponse({}, "fallback", "no balanced JSON object found",
                              raw_excerpt, clean_excerpt)
    try:
        data = json.loads(block)
    except json.JSONDecodeError as exc:
        return ParsedResponse({}, "fallback", f"json decode: {exc.msg}",
                              raw_excerpt, clean_excerpt)
    if not isinstance(data, dict):
        return ParsedResponse({}, "fallback", "JSON root is not an object",
                              raw_excerpt, clean_excerpt)

    aliases = aliases or {}
    used_alias = False
    for canon, alts in aliases.items():
        if canon not in data:
            for alt in alts:
                if alt in data:
                    data[canon] = data[alt]
                    used_alias = True
                    break

    missing = [k for k in required if k not in data]
    if missing:
        return ParsedResponse(
            data, "partial",
            f"missing required: {', '.join(missing)}",
            raw_excerpt, clean_excerpt,
        )
    if used_alias:
        return ParsedResponse(data, "partial", "used alias mapping",
                              raw_excerpt, clean_excerpt)
    return ParsedResponse(data, "ok", None, raw_excerpt, clean_excerpt)
