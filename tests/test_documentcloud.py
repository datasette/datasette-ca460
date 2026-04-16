"""Tests for DocumentCloud URL parsing and CDN URL building."""

import pytest

from datasette_ca460.documentcloud import parse_documentcloud_url, page_image_url


class TestParseDocumentcloudUrl:
    def test_document_url(self):
        result = parse_documentcloud_url(
            "https://www.documentcloud.org/documents/12345-some-slug"
        )
        assert result == {"type": "document", "id": 12345}

    def test_document_url_no_slug(self):
        result = parse_documentcloud_url(
            "https://www.documentcloud.org/documents/99999"
        )
        assert result == {"type": "document", "id": 99999}

    def test_document_url_trailing_slash(self):
        result = parse_documentcloud_url(
            "https://www.documentcloud.org/documents/12345-slug/"
        )
        assert result == {"type": "document", "id": 12345}

    def test_project_url(self):
        result = parse_documentcloud_url(
            "https://www.documentcloud.org/projects/some-project-67890/"
        )
        assert result == {"type": "project", "id": 67890}

    def test_project_url_no_trailing_slash(self):
        result = parse_documentcloud_url(
            "https://www.documentcloud.org/projects/my-proj-42"
        )
        assert result == {"type": "project", "id": 42}

    def test_unrecognized_url_returns_none(self):
        assert parse_documentcloud_url("https://example.com") is None

    def test_empty_string_returns_none(self):
        assert parse_documentcloud_url("") is None

    def test_case_insensitive(self):
        result = parse_documentcloud_url(
            "https://WWW.DOCUMENTCLOUD.ORG/documents/555-slug"
        )
        assert result == {"type": "document", "id": 555}

    def test_document_preferred_over_project(self):
        """If URL matches both patterns, document match wins (checked first)."""
        result = parse_documentcloud_url(
            "https://www.documentcloud.org/documents/111-slug"
        )
        assert result["type"] == "document"


class TestPageImageUrl:
    def test_large_image(self):
        url = page_image_url(
            "https://assets.documentcloud.org/",
            12345,
            "my-doc",
            3,
        )
        assert url == "https://assets.documentcloud.org/documents/12345/pages/my-doc-p3-large.gif"

    def test_small_size(self):
        url = page_image_url(
            "https://assets.documentcloud.org/",
            12345,
            "my-doc",
            1,
            size="small",
        )
        assert url == "https://assets.documentcloud.org/documents/12345/pages/my-doc-p1-small.gif"

    def test_thumbnail_size(self):
        url = page_image_url(
            "https://assets.documentcloud.org/",
            1,
            "s",
            10,
            size="thumbnail",
        )
        assert url == "https://assets.documentcloud.org/documents/1/pages/s-p10-thumbnail.gif"
