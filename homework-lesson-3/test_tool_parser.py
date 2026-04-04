"""Tests for XML tool call parser.

Covers: happy path, multiple params, multiple tool calls, numeric parsing,
mixed content with text, malformed/incomplete XML, and empty input.
"""

import pytest

from tool_parser import parse_xml_tool_calls


class TestParseXmlToolCalls:
    """Tests for parse_xml_tool_calls function."""

    # --- Happy path ---

    def test_single_tool_call_single_param(self):
        content = (
            "<tool_call>\n"
            "<function=web_search>\n"
            "<parameter=query>LangGraph framework</parameter>\n"
            "</function>\n"
            "</tool_call>"
        )
        remaining, tool_calls = parse_xml_tool_calls(content)

        assert remaining == ""
        assert len(tool_calls) == 1
        assert tool_calls[0]["name"] == "web_search"
        assert tool_calls[0]["args"] == {"query": "LangGraph framework"}
        assert tool_calls[0]["id"].startswith("call_")

    def test_single_tool_call_multiple_params(self):
        content = (
            "<tool_call>\n"
            "<function=web_search>\n"
            "<parameter=query>RAG comparison</parameter>\n"
            "<parameter=max_results>3</parameter>\n"
            "</function>\n"
            "</tool_call>"
        )
        remaining, tool_calls = parse_xml_tool_calls(content)

        assert len(tool_calls) == 1
        assert tool_calls[0]["args"]["query"] == "RAG comparison"
        assert tool_calls[0]["args"]["max_results"] == 3  # parsed as int

    def test_multiple_tool_calls(self):
        content = (
            "<tool_call>\n"
            "<function=web_search>\n"
            "<parameter=query>first query</parameter>\n"
            "</function>\n"
            "</tool_call>\n"
            "<tool_call>\n"
            "<function=read_url>\n"
            "<parameter=url>https://example.com</parameter>\n"
            "</function>\n"
            "</tool_call>"
        )
        remaining, tool_calls = parse_xml_tool_calls(content)

        assert len(tool_calls) == 2
        assert tool_calls[0]["name"] == "web_search"
        assert tool_calls[1]["name"] == "read_url"
        assert tool_calls[1]["args"]["url"] == "https://example.com"

    # --- Mixed content (text + tool calls) ---

    def test_text_before_tool_call(self):
        content = (
            "Let me search for that.\n"
            "<tool_call>\n"
            "<function=web_search>\n"
            "<parameter=query>test</parameter>\n"
            "</function>\n"
            "</tool_call>"
        )
        remaining, tool_calls = parse_xml_tool_calls(content)

        assert remaining == "Let me search for that."
        assert len(tool_calls) == 1

    def test_text_around_tool_call(self):
        content = (
            "I'll search now.\n"
            "<tool_call>\n"
            "<function=web_search>\n"
            "<parameter=query>test</parameter>\n"
            "</function>\n"
            "</tool_call>\n"
            "And then read the results."
        )
        remaining, tool_calls = parse_xml_tool_calls(content)

        assert "I'll search now." in remaining
        assert "And then read the results." in remaining
        assert len(tool_calls) == 1

    # --- Numeric parsing ---

    def test_numeric_value_parsed_as_int(self):
        content = (
            "<tool_call>\n"
            "<function=web_search>\n"
            "<parameter=max_results>10</parameter>\n"
            "</function>\n"
            "</tool_call>"
        )
        _, tool_calls = parse_xml_tool_calls(content)

        assert tool_calls[0]["args"]["max_results"] == 10
        assert isinstance(tool_calls[0]["args"]["max_results"], int)

    def test_non_numeric_string_stays_string(self):
        content = (
            "<tool_call>\n"
            "<function=web_search>\n"
            "<parameter=query>123abc</parameter>\n"
            "</function>\n"
            "</tool_call>"
        )
        _, tool_calls = parse_xml_tool_calls(content)

        assert tool_calls[0]["args"]["query"] == "123abc"
        assert isinstance(tool_calls[0]["args"]["query"], str)

    # --- Unique IDs ---

    def test_tool_calls_have_unique_ids(self):
        content = (
            "<tool_call>\n"
            "<function=web_search>\n"
            "<parameter=query>first</parameter>\n"
            "</function>\n"
            "</tool_call>\n"
            "<tool_call>\n"
            "<function=web_search>\n"
            "<parameter=query>second</parameter>\n"
            "</function>\n"
            "</tool_call>"
        )
        _, tool_calls = parse_xml_tool_calls(content)

        assert tool_calls[0]["id"] != tool_calls[1]["id"]

    # --- Edge cases: no tool calls ---

    def test_empty_string(self):
        remaining, tool_calls = parse_xml_tool_calls("")

        assert remaining == ""
        assert tool_calls == []

    def test_plain_text_no_xml(self):
        content = "This is just a regular response with no tool calls."
        remaining, tool_calls = parse_xml_tool_calls(content)

        assert remaining == content
        assert tool_calls == []

    # --- Malformed XML ---

    def test_incomplete_tool_call_no_closing_tag(self):
        content = (
            "<tool_call>\n"
            "<function=web_search>\n"
            "<parameter=query>test</parameter>\n"
            "</function>\n"
            # missing </tool_call>
        )
        remaining, tool_calls = parse_xml_tool_calls(content)

        assert tool_calls == []
        assert "<tool_call>" in remaining

    def test_tool_call_without_parameters(self):
        content = (
            "<tool_call>\n"
            "<function=some_tool>\n"
            "</function>\n"
            "</tool_call>"
        )
        _, tool_calls = parse_xml_tool_calls(content)

        assert len(tool_calls) == 1
        assert tool_calls[0]["name"] == "some_tool"
        assert tool_calls[0]["args"] == {}

    def test_malformed_parameter_ignored(self):
        content = (
            "<tool_call>\n"
            "<function=web_search>\n"
            "<parameter=query>valid</parameter>\n"
            "<parameter=broken>unclosed\n"
            "</function>\n"
            "</tool_call>"
        )
        _, tool_calls = parse_xml_tool_calls(content)

        assert len(tool_calls) == 1
        # Only the valid parameter should be parsed
        assert tool_calls[0]["args"]["query"] == "valid"

    # --- Whitespace handling ---

    def test_compact_format_no_newlines(self):
        content = "<tool_call><function=web_search><parameter=query>test</parameter></function></tool_call>"
        _, tool_calls = parse_xml_tool_calls(content)

        assert len(tool_calls) == 1
        assert tool_calls[0]["args"]["query"] == "test"

    def test_extra_whitespace_in_parameter_value(self):
        content = (
            "<tool_call>\n"
            "<function=web_search>\n"
            "<parameter=query>  spaced query  </parameter>\n"
            "</function>\n"
            "</tool_call>"
        )
        _, tool_calls = parse_xml_tool_calls(content)

        assert tool_calls[0]["args"]["query"] == "spaced query"
