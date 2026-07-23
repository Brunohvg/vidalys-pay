"""Tests for docker/wait_for_database.py."""
import os
import sys
from unittest.mock import MagicMock, patch

import psycopg
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "docker"))

from wait_for_database import (
    MAX_ATTEMPTS,  # noqa: E402
    _is_dns_error,  # noqa: E402
    _mask_url,  # noqa: E402
    _normalize_url,  # noqa: E402
    main,  # noqa: E402
    wait_for_database,  # noqa: E402
)


class TestMaskUrl:
    def test_masks_password(self):
        url = "postgresql://user:secret@host:5432/dbname"
        result = _mask_url(url)
        assert "secret" not in result
        assert "***" in result
        assert "host:5432/dbname" in result

    def test_mask_url_without_port(self):
        url = "postgresql://user:pass@host/db"
        result = _mask_url(url)
        assert "pass" not in result
        assert "host/db" in result

    def test_mask_url_postgres_prefix(self):
        url = "postgres://user:pass@host:5432/db"
        normalized = url.replace("postgres://", "postgresql://", 1)
        result = _mask_url(normalized)
        assert "pass" not in result


class TestNormalizeUrl:
    def test_normalize_postgres_to_postgresql(self):
        result = _normalize_url("postgres://user:pass@host/db")
        assert result.startswith("postgresql://")
        assert "user:pass@host/db" in result

    def test_keep_postgresql_unchanged(self):
        result = _normalize_url("postgresql://user:pass@host/db")
        assert result == "postgresql://user:pass@host/db"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="must start with"):
            _normalize_url("mysql://user:pass@host/db")

    def test_empty_url_raises(self):
        with pytest.raises(ValueError):
            _normalize_url("not-a-url")


def test_detects_database_dns_errors():
    assert _is_dns_error(
        "failed to resolve host 'postgres-abc': Temporary failure in name resolution"
    )
    assert not _is_dns_error("connection refused")


class TestWaitForDatabase:
    def test_connects_successfully(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        with patch("wait_for_database.psycopg.connect", return_value=mock_conn) as mock_connect:
            mock_conn.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

            wait_for_database("postgresql://user:pass@host/db")

            mock_connect.assert_called_once()
            call_args = mock_connect.call_args[0][0]
            assert "postgresql://user:pass@host/db" in call_args

    def test_retries_on_failure_then_succeeds(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise psycopg.OperationalError("connection refused")
            return mock_conn

        with patch("wait_for_database.psycopg.connect", side_effect=side_effect), patch(
            "wait_for_database.time.sleep", return_value=None
        ):
            mock_conn.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

            wait_for_database("postgresql://user:pass@host/db")

            assert call_count == 3

    def test_exits_after_max_attempts(self):
        with patch("wait_for_database.psycopg.connect", side_effect=psycopg.OperationalError("timeout")), patch(
            "wait_for_database.time.sleep", return_value=None
        ):
            with pytest.raises(SystemExit) as exc_info:
                wait_for_database("postgresql://user:pass@host/db")
            assert exc_info.value.code == 1

    def test_password_not_in_output_on_failure(self, capsys):
        with patch("wait_for_database.psycopg.connect", side_effect=psycopg.OperationalError("timeout")), patch(
            "wait_for_database.time.sleep", return_value=None
        ):
            with pytest.raises(SystemExit):
                wait_for_database("postgresql://user:MySecret123@host:5432/db")

            captured = capsys.readouterr()
            assert "MySecret123" not in captured.out
            assert "MySecret123" not in captured.err

    def test_password_not_in_output_on_success(self, capsys):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        with patch("wait_for_database.psycopg.connect", return_value=mock_conn):
            mock_conn.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

            wait_for_database("postgresql://user:MySecret123@host:5432/db")

            captured = capsys.readouterr()
            assert "MySecret123" not in captured.out

    def test_dns_failure_prints_actionable_coolify_diagnostic(self, capsys):
        error = psycopg.OperationalError(
            "failed to resolve host 'postgres-abc': Temporary failure in name resolution"
        )
        with (
            patch("wait_for_database.psycopg.connect", side_effect=error),
            patch("wait_for_database.time.sleep", return_value=None),
            pytest.raises(SystemExit),
        ):
            wait_for_database("postgresql://user:secret@postgres-abc/db")

        output = capsys.readouterr().out
        assert "Connect to Predefined Network" in output
        assert "Internal URL" in output
        assert "aumentar tentativas não corrige" in output
        assert "secret" not in output


class TestMain:
    def test_missing_database_url_exits(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_empty_database_url_exits(self):
        with patch.dict(os.environ, {"DATABASE_URL": ""}, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_invalid_url_exits(self):
        with patch.dict(os.environ, {"DATABASE_URL": "not-a-valid-url"}, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_keyboard_interrupt_exits(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://u:p@h/db"}, clear=True), patch(
            "wait_for_database.wait_for_database", side_effect=KeyboardInterrupt
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_successful_main(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://u:p@h/db"}, clear=True), patch(
            "wait_for_database.wait_for_database", return_value=None
        ) as mock_wait:
            main()
            mock_wait.assert_called_once_with("postgresql://u:p@h/db")


def test_max_attempts_default():
    assert MAX_ATTEMPTS == 60
