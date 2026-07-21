"""Tests for health endpoints."""
import pytest
from django.test import Client


@pytest.mark.django_db
def test_health_returns_ok():
    client = Client()
    response = client.get("/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.django_db
def test_ready_returns_ok():
    client = Client()
    response = client.get("/health/ready/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] == "ok"
    assert data["migrations"] == "ok"
