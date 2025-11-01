"""JSON contracts for x_make_progress_board_x."""

from __future__ import annotations

_JSON_VALUE_SCHEMA: dict[str, object] = {
    "type": ["object", "array", "string", "number", "boolean", "null"],
}

_NON_EMPTY_STRING: dict[str, object] = {"type": "string", "minLength": 1}

_STAGE_DEFINITION_IN: dict[str, object] = {
    "type": "object",
    "properties": {
        "id": _NON_EMPTY_STRING,
        "title": {"type": "string"},
    },
    "required": ["id"],
    "additionalProperties": False,
}

_STAGE_DEFINITION_OUT: dict[str, object] = {
    "type": "object",
    "properties": {
        "id": _NON_EMPTY_STRING,
        "title": _NON_EMPTY_STRING,
    },
    "required": ["id", "title"],
    "additionalProperties": False,
}

_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "snapshot_path": _NON_EMPTY_STRING,
        "stage_definitions": {
            "type": "array",
            "items": _STAGE_DEFINITION_IN,
        },
        "fallback_stage": _STAGE_DEFINITION_IN,
        "launch": {"type": "boolean"},
    },
    "additionalProperties": False,
}

INPUT_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "x_make_progress_board_x input",
    "type": "object",
    "properties": {
        "command": {"const": "x_make_progress_board_x"},
        "parameters": _PARAMETERS_SCHEMA,
    },
    "required": ["command"],
    "additionalProperties": False,
}

OUTPUT_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "x_make_progress_board_x output",
    "type": "object",
    "properties": {
        "status": {"const": "success"},
        "schema_version": {"const": "x_make_progress_board_x.run/1.0"},
        "message": _NON_EMPTY_STRING,
        "snapshot_path": _NON_EMPTY_STRING,
        "stage_definitions": {
            "type": "array",
            "items": _STAGE_DEFINITION_OUT,
        },
        "metadata": {
            "type": "object",
            "additionalProperties": _JSON_VALUE_SCHEMA,
        },
    },
    "required": [
        "status",
        "schema_version",
        "message",
        "snapshot_path",
        "stage_definitions",
    ],
    "additionalProperties": False,
}

ERROR_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "x_make_progress_board_x error",
    "type": "object",
    "properties": {
        "status": {"const": "failure"},
        "message": _NON_EMPTY_STRING,
        "details": {
            "type": "object",
            "additionalProperties": _JSON_VALUE_SCHEMA,
        },
    },
    "required": ["status", "message"],
    "additionalProperties": True,
}

__all__ = ["ERROR_SCHEMA", "INPUT_SCHEMA", "OUTPUT_SCHEMA"]
