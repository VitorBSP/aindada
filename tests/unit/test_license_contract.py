"""Contrato de licença do manifesto (ADR-0008, Decisão 2). Valores SINTÉTICOS."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from brasileirao.contracts import AllowedUse, LicenseStatus, SourceManifest, most_restrictive_license


def _manifest(**changes: Any) -> SourceManifest:
    fields: dict[str, Any] = {
        "source_name": "synthetic_source",
        "origin": "https://example.org/synthetic",
        "version": "synthetic-1",
        "retrieved_at": datetime(2032, 1, 1, tzinfo=UTC),
        "files": {"matches.json": "0" * 64},
        "license_status": LicenseStatus.LICENSED_WITH_ATTRIBUTION,
        "license_notes": "synthetic",
        "allowed_uses": [AllowedUse.RESEARCH_LOCAL, AllowedUse.PUBLIC_DISPLAY_DERIVED],
        "license_name": "Synthetic License",
        "terms_url": "https://example.org/terms",
        "terms_checked_at": date(2032, 1, 1),
        "attribution": "Synthetic data provided by Example",
    }
    fields.update(changes)
    return SourceManifest.model_validate(fields)


def test_licensed_with_attribution_value_is_exact() -> None:
    assert LicenseStatus.LICENSED_WITH_ATTRIBUTION.value == "licensed_with_attribution"


def test_allowed_use_vocabulary_is_closed() -> None:
    assert {use.value for use in AllowedUse} == {
        "research_local",
        "prototype_local",
        "public_display_derived",
        "redistribution",
    }


def test_complete_licensed_manifest_is_valid() -> None:
    assert _manifest().allows_public_display


def test_unknown_allowed_use_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _manifest(allowed_uses=["public_display_with_attribution"])


def test_public_display_requires_publishable_status() -> None:
    with pytest.raises(ValidationError):
        _manifest(license_status=LicenseStatus.RESEARCH_ONLY_UNVERIFIED)


def test_redistribution_requires_publishable_status() -> None:
    with pytest.raises(ValidationError):
        _manifest(license_status=LicenseStatus.REQUIRES_AGREEMENT, allowed_uses=[AllowedUse.REDISTRIBUTION])


def test_licensed_with_attribution_requires_attribution() -> None:
    with pytest.raises(ValidationError):
        _manifest(attribution=None)


def test_licensed_with_attribution_rejects_blank_attribution() -> None:
    with pytest.raises(ValidationError):
        _manifest(attribution="  ")


def test_licensed_with_attribution_requires_terms_url() -> None:
    with pytest.raises(ValidationError):
        _manifest(terms_url=None)


def test_licensed_with_attribution_requires_terms_checked_at() -> None:
    with pytest.raises(ValidationError):
        _manifest(terms_checked_at=None)


def test_verified_open_requires_license_name() -> None:
    with pytest.raises(ValidationError):
        _manifest(license_status=LicenseStatus.VERIFIED_OPEN, license_name=None)


def test_verified_open_does_not_require_attribution() -> None:
    assert _manifest(license_status=LicenseStatus.VERIFIED_OPEN, attribution=None).attribution is None


def test_legacy_research_manifest_stays_valid() -> None:
    legacy = _manifest(
        license_status=LicenseStatus.RESEARCH_ONLY_UNVERIFIED,
        allowed_uses=["research_local", "prototype_local"],
        license_name=None,
        terms_url=None,
        terms_checked_at=None,
        attribution=None,
    )
    assert not legacy.allows_public_display


def test_most_restrictive_license_follows_declared_order() -> None:
    statuses = [LicenseStatus.LICENSED_WITH_ATTRIBUTION, LicenseStatus.VERIFIED_OPEN]
    assert most_restrictive_license(statuses) == LicenseStatus.LICENSED_WITH_ATTRIBUTION


def test_research_source_is_more_restrictive_than_licensed() -> None:
    statuses = [LicenseStatus.RESEARCH_ONLY_UNVERIFIED, LicenseStatus.LICENSED_WITH_ATTRIBUTION]
    assert most_restrictive_license(statuses) == LicenseStatus.RESEARCH_ONLY_UNVERIFIED


def test_manifest_is_immutable() -> None:
    with pytest.raises(ValidationError):
        _manifest().license_status = LicenseStatus.BLOCKED  # type: ignore[misc]
