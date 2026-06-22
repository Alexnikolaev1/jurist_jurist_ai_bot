# -*- coding: utf-8 -*-
import pytest

from utils.text_utils import (
    build_fts_query,
    clean_text,
    detect_emergency_keywords,
    extract_keywords,
    split_long_message,
)


class TestCleanText:
    def test_collapses_whitespace(self):
        assert clean_text("  привет   мир  ") == "привет мир"

    def test_empty(self):
        assert clean_text("") == ""
        assert clean_text(None) == ""


class TestExtractKeywords:
    def test_removes_stopwords(self):
        keywords = extract_keywords("я купил товар в магазине")
        assert "я" not in keywords
        assert "купил" in keywords
        assert "магазине" in keywords

    def test_limits_count(self):
        text = " ".join(f"слово{i}" for i in range(20))
        assert len(extract_keywords(text, max_keywords=5)) <= 5


class TestBuildFtsQuery:
    def test_prefix_search(self):
        query = build_fts_query("вернуть товар в магазин")
        assert "*" in query
        assert " OR " in query

    def test_empty_input(self):
        assert build_fts_query("я и ты") == ""


class TestSplitLongMessage:
    def test_short_text_unchanged(self):
        text = "короткий текст"
        assert split_long_message(text) == [text]

    def test_splits_long_text(self):
        text = "а" * 5000
        parts = split_long_message(text, limit=1000)
        assert len(parts) > 1
        assert all(len(p) <= 1000 for p in parts)
        assert "".join(parts) == text


class TestEmergencyKeywords:
    def test_detects_detention(self):
        assert detect_emergency_keywords("меня задержали в отделе") is True

    def test_ignores_normal_query(self):
        assert detect_emergency_keywords("хочу вернуть товар в магазин") is False
