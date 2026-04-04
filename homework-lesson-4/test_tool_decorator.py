"""Tests for the custom @tool decorator (tools._resolve_json_type + schema generation).

Covers: basic types, Optional[T] unwrapping, auto-schema generation,
required vs optional params, and TOOL_REGISTRY population.
"""

from typing import Optional

import pytest

from tools import _resolve_json_type, TOOL_REGISTRY, TOOL_SCHEMAS


class TestResolveJsonType:
    """Tests for _resolve_json_type helper."""

    def test_str(self):
        assert _resolve_json_type(str) == "string"

    def test_int(self):
        assert _resolve_json_type(int) == "integer"

    def test_float(self):
        assert _resolve_json_type(float) == "number"

    def test_bool(self):
        assert _resolve_json_type(bool) == "boolean"

    def test_optional_int(self):
        """Optional[int] should resolve to 'integer', not 'string'."""
        assert _resolve_json_type(Optional[int]) == "integer"

    def test_optional_str(self):
        assert _resolve_json_type(Optional[str]) == "string"

    def test_optional_float(self):
        assert _resolve_json_type(Optional[float]) == "number"

    def test_optional_bool(self):
        assert _resolve_json_type(Optional[bool]) == "boolean"

    def test_unknown_type_falls_back_to_string(self):
        assert _resolve_json_type(list) == "string"
        assert _resolve_json_type(dict) == "string"


class TestToolSchemaGeneration:
    """Tests for auto-generated tool schemas."""

    def test_web_search_registered(self):
        assert "web_search" in TOOL_REGISTRY

    def test_read_url_registered(self):
        assert "read_url" in TOOL_REGISTRY

    def test_write_report_registered(self):
        assert "write_report" in TOOL_REGISTRY

    def _find_schema(self, name: str) -> dict:
        for s in TOOL_SCHEMAS:
            if s["function"]["name"] == name:
                return s
        pytest.fail(f"Schema for '{name}' not found")

    def test_web_search_schema_structure(self):
        schema = self._find_schema("web_search")

        assert schema["type"] == "function"
        func = schema["function"]
        assert func["name"] == "web_search"
        assert func["description"]  # non-empty docstring

        params = func["parameters"]
        assert "query" in params["properties"]
        assert "max_results" in params["properties"]

    def test_web_search_query_is_required(self):
        schema = self._find_schema("web_search")
        assert "query" in schema["function"]["parameters"]["required"]

    def test_web_search_max_results_is_optional(self):
        schema = self._find_schema("web_search")
        assert "max_results" not in schema["function"]["parameters"]["required"]

    def test_web_search_max_results_type_is_integer(self):
        """Optional[int] should produce 'integer' in the schema, not 'string'."""
        schema = self._find_schema("web_search")
        max_results_prop = schema["function"]["parameters"]["properties"]["max_results"]
        assert max_results_prop["type"] == "integer"

    def test_read_url_schema(self):
        schema = self._find_schema("read_url")
        params = schema["function"]["parameters"]
        assert "url" in params["properties"]
        assert "url" in params["required"]
        assert params["properties"]["url"]["type"] == "string"

    def test_write_report_schema(self):
        schema = self._find_schema("write_report")
        params = schema["function"]["parameters"]
        assert "filename" in params["required"]
        assert "content" in params["required"]
