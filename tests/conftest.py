"""Pytest configuration and shared fixtures."""
import pytest
from django.test import RequestFactory


@pytest.fixture
def request_factory():
    return RequestFactory()
