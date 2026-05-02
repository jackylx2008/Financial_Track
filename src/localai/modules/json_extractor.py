from __future__ import annotations

import json
import re
from typing import Any


def parse_json_from_text(text: str) -> dict[str, Any]:
    cleaned = _strip_code_fence(text.strip())
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        value = json.loads(_find_first_json_object(cleaned))

    if not isinstance(value, dict):
        raise ValueError("Model output JSON must be an object")
    return value


def _strip_code_fence(text: str) -> str:
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text


def _find_first_json_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        raise ValueError("No JSON object found in model output")

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    raise ValueError("JSON object was not closed in model output")
