"""Tests for Pagar.me credential normalization."""
import base64

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.integrations.pagarme.credentials import (
    CredentialError,
    normalize_credential,
)


class TestNormalizeCredential:
    """Tests for credential normalization from all supported formats."""

    RAW_KEY = "sk_test_mYr3AlK3yH3r3Ex4mpL3L0ngK3y"
    B64_KEY = base64.b64encode(f"{RAW_KEY}:".encode()).decode()

    # --- Format A: Raw Secret Key ---

    def test_raw_secret_key_production(self):
        cred = normalize_credential("sk_EXEMPlOK3yPr0duct10n")
        assert cred.source_format == "raw_secret_key"
        assert cred.environment == "production"
        assert cred.secret_key == "sk_EXEMPlOK3yPr0duct10n"
        assert cred.authorization_header.startswith("Basic ")

    def test_raw_secret_key_test(self):
        cred = normalize_credential(self.RAW_KEY)
        assert cred.source_format == "raw_secret_key"
        assert cred.environment == "test"
        assert cred.secret_key == self.RAW_KEY

    def test_raw_secret_key_live(self):
        cred = normalize_credential("sk_live_Pr0duct10nK3yH3re")
        assert cred.environment == "production"

    # --- Format B: Pre-encoded Base64 ---

    def test_base64_encoded(self):
        cred = normalize_credential(self.B64_KEY)
        assert cred.source_format == "base64_credentials"
        assert cred.secret_key == self.RAW_KEY
        assert cred.environment == "test"

    # --- Format C: Full Basic header ---

    def test_basic_header(self):
        cred = normalize_credential(f"Basic {self.B64_KEY}")
        assert cred.source_format == "basic_header"
        assert cred.secret_key == self.RAW_KEY

    def test_basic_header_lowercase(self):
        cred = normalize_credential(f"basic {self.B64_KEY}")
        assert cred.secret_key == self.RAW_KEY

    # --- Equivalence: all formats produce same header ---

    def test_all_formats_produce_same_header(self):
        raw = normalize_credential(self.RAW_KEY)
        b64 = normalize_credential(self.B64_KEY)
        basic = normalize_credential(f"Basic {self.B64_KEY}")

        assert raw.authorization_header == b64.authorization_header
        assert raw.authorization_header == basic.authorization_header
        assert raw.secret_key == b64.secret_key == basic.secret_key

    # --- Invalid cases ---

    def test_empty_raises(self):
        with pytest.raises(CredentialError):
            normalize_credential("")

    def test_none_raises(self):
        with pytest.raises(CredentialError):
            normalize_credential(None)  # type: ignore

    def test_newline_raises(self):
        with pytest.raises(CredentialError):
            normalize_credential("sk_key\nwith_newline")

    def test_invalid_base64_raises(self):
        with pytest.raises(CredentialError):
            normalize_credential("!!!not-valid-base64!!!")

    def test_non_secret_key_user_raises(self):
        b64 = base64.b64encode(b"not-a-secret-key:").decode()
        with pytest.raises(CredentialError, match="Secret Key"):
            normalize_credential(b64)

    def test_non_empty_password_raises(self):
        b64 = base64.b64encode(f"{self.RAW_KEY}:hunter2".encode()).decode()
        with pytest.raises(CredentialError, match="senha"):
            normalize_credential(b64)

    def test_no_colon_in_decoded_raises(self):
        b64 = base64.b64encode(b"only_user_no_colon").decode()
        with pytest.raises(CredentialError, match="separador"):
            normalize_credential(b64)

    def test_empty_username_raises(self):
        b64 = base64.b64encode(b":").decode()
        with pytest.raises(CredentialError):
            normalize_credential(b64)

    def test_public_key_rejected(self):
        with pytest.raises(CredentialError):
            normalize_credential("pk_test_PuBl1cK3yH3r3")

    def test_bearer_rejected(self):
        with pytest.raises(CredentialError):
            b64 = base64.b64encode(b"Bearer sk_key:").decode()
            normalize_credential(f"Bearer {b64}")

    def test_whitespace_trimmed(self):
        cred = normalize_credential(f"  {self.RAW_KEY}  ")
        assert cred.secret_key == self.RAW_KEY

    # --- No double-encoding ---

    def test_no_double_encoding(self):
        """Basic(B64) must NOT become Basic(Basic(B64))."""
        cred = normalize_credential(f"Basic {self.B64_KEY}")
        header = cred.authorization_header
        decoded_header = base64.b64decode(header[6:]).decode()
        assert decoded_header == f"{self.RAW_KEY}:"
        assert "Basic" not in decoded_header
