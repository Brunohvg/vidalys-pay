"""Tests for Pagar.me credential normalization."""
import base64

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.integrations.pagarme.credentials import (
    PagarMeConfigurationError,
    build_basic_auth_header,
    normalize_pagarme_api_key,
)


class TestNormalizeApiKey:
    """Tests for normalize_pagarme_api_key from all supported formats."""

    RAW_KEY = "sk_test_mYr3AlK3yH3r3Ex4mpL3L0ngK3y"
    B64_KEY = base64.b64encode(f"{RAW_KEY}:".encode()).decode()

    # --- Format A: Raw Secret Key ---

    def test_raw_secret_key_production(self):
        result = normalize_pagarme_api_key("sk_EXEMPlOK3yPr0duct10n")
        assert result == "sk_EXEMPlOK3yPr0duct10n"

    def test_raw_secret_key_test(self):
        result = normalize_pagarme_api_key(self.RAW_KEY)
        assert result == self.RAW_KEY

    def test_raw_secret_key_live(self):
        result = normalize_pagarme_api_key("sk_live_Pr0duct10nK3yH3re")
        assert result == "sk_live_Pr0duct10nK3yH3re"

    # --- Format B: Pre-encoded Base64 ---

    def test_base64_encoded(self):
        result = normalize_pagarme_api_key(self.B64_KEY)
        assert result == self.RAW_KEY

    # --- Format C: Full Basic header ---

    def test_basic_header(self):
        result = normalize_pagarme_api_key(f"Basic {self.B64_KEY}")
        assert result == self.RAW_KEY

    def test_basic_header_lowercase(self):
        result = normalize_pagarme_api_key(f"basic {self.B64_KEY}")
        assert result == self.RAW_KEY

    # --- Equivalence: all formats produce same auth header ---

    def test_all_formats_produce_same_header(self):
        raw = build_basic_auth_header(self.RAW_KEY)

        api_key_from_b64 = normalize_pagarme_api_key(self.B64_KEY)
        b64_header = build_basic_auth_header(api_key_from_b64)

        api_key_from_basic = normalize_pagarme_api_key(f"Basic {self.B64_KEY}")
        basic_header = build_basic_auth_header(api_key_from_basic)

        assert raw == b64_header
        assert raw == basic_header
        assert raw.startswith("Basic ")

    # --- Decoding verification: output decodes to "sk_...:" ---

    def test_header_decodes_correctly(self):
        header = build_basic_auth_header(self.RAW_KEY)
        encoded_part = header.split(" ", 1)[1]
        decoded = base64.b64decode(encoded_part).decode()
        assert decoded == f"{self.RAW_KEY}:"

    def test_no_double_encoding(self):
        """Basic(B64) must NOT become Basic(Basic(B64))."""
        api_key = normalize_pagarme_api_key(f"Basic {self.B64_KEY}")
        assert api_key == self.RAW_KEY  # returns raw key, not re-encoded

        header = build_basic_auth_header(api_key)
        decoded_header = base64.b64decode(header[6:]).decode()
        assert decoded_header == f"{self.RAW_KEY}:"
        assert "Basic" not in decoded_header

    # --- Invalid cases ---

    def test_empty_raises(self):
        with pytest.raises(PagarMeConfigurationError):
            normalize_pagarme_api_key("")

    def test_none_raises(self):
        with pytest.raises(PagarMeConfigurationError):
            normalize_pagarme_api_key(None)  # type: ignore

    def test_newline_raises(self):
        with pytest.raises(PagarMeConfigurationError):
            normalize_pagarme_api_key("sk_key\nwith_newline")

    def test_invalid_base64_raises(self):
        with pytest.raises(PagarMeConfigurationError):
            normalize_pagarme_api_key("!!!not-valid-base64!!!")

    def test_non_secret_key_user_raises(self):
        b64 = base64.b64encode(b"not-a-secret-key:").decode()
        with pytest.raises(PagarMeConfigurationError, match="Secret Key"):
            normalize_pagarme_api_key(b64)

    def test_non_empty_password_raises(self):
        b64 = base64.b64encode(f"{self.RAW_KEY}:hunter2".encode()).decode()
        with pytest.raises(PagarMeConfigurationError, match="senha"):
            normalize_pagarme_api_key(b64)

    def test_public_key_rejected(self):
        with pytest.raises(PagarMeConfigurationError):
            normalize_pagarme_api_key("pk_test_PuBl1cK3yH3r3")

    def test_bearer_rejected(self):
        with pytest.raises(PagarMeConfigurationError):
            normalize_pagarme_api_key("Bearer sk_t3stK3y")

    def test_whitespace_trimmed(self):
        result = normalize_pagarme_api_key(f"  {self.RAW_KEY}  ")
        assert result == self.RAW_KEY

    # --- Password field must be empty ---

    def test_colon_with_filled_password_rejected(self):
        b64 = base64.b64encode(b"sk_test_key:my_password:").decode()
        with pytest.raises(PagarMeConfigurationError, match="senha"):
            normalize_pagarme_api_key(b64)


class TestBuildBasicAuthHeader:
    """Tests for build_basic_auth_header."""

    def test_returns_basic_prefix(self):
        header = build_basic_auth_header("sk_test_example")
        assert header.startswith("Basic ")

    def test_decodes_back(self):
        secret = "sk_test_example_key"
        header = build_basic_auth_header(secret)
        encoded = header.split(" ", 1)[1]
        decoded = base64.b64decode(encoded).decode()
        assert decoded == f"{secret}:"

    def test_different_keys_produce_different_headers(self):
        h1 = build_basic_auth_header("sk_test_key_a")
        h2 = build_basic_auth_header("sk_test_key_b")
        assert h1 != h2


class TestPagarMeConfigurationError:
    """Tests for PagarMeConfigurationError hierarchy."""

    def test_is_improperly_configured(self):
        with pytest.raises(ImproperlyConfigured):
            normalize_pagarme_api_key("")

    def test_is_pagarme_configuration_error(self):
        with pytest.raises(PagarMeConfigurationError):
            normalize_pagarme_api_key("")

    def test_pagarme_error_is_django_error(self):
        """PagarMeConfigurationError must be a subclass of ImproperlyConfigured."""
        assert issubclass(PagarMeConfigurationError, ImproperlyConfigured)
