"""Regression: GSAF-style constant publisher titles must not match as headlines.

The 2026-09-10 GSAF backfill merged 174 submissions onto a single unrelated
incident because every submission carried source_title "Global Shark Attack
File (GSAF)" — 31 chars, clearing the 30-char fingerprint floor — and
_find_source_duplicate treated the constant publisher string as a syndicated
headline. Publisher titles are not headlines; the fingerprint branch must
ignore titles that repeat across unrelated submissions.
"""
import pytest

from app.services.dedup_service import _headline_fingerprint


def test_publisher_title_is_not_a_headline_fingerprint():
    # "Global Shark Attack File (GSAF)" is a publisher name, not a headline.
    # It must not produce a fingerprint, so the source-duplicate branch can
    # never match unrelated incidents on it again.
    assert _headline_fingerprint("Global Shark Attack File (GSAF)") is None
