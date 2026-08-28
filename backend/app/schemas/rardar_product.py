"""Strict public contracts for the local Rardar product MVP."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal
from urllib.parse import urlparse

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class StrictProductModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ReuseType(StrEnum):
    WHOLE_PRODUCT = "whole_product"
    MODULE_LIBRARY = "module_library"
    PROVIDER_CONNECTOR = "provider_connector"
    WORKFLOW = "workflow"
    REFERENCE_ONLY = "reference_only"
    NOT_RECOMMENDED = "not_recommended"


class ProjectExplanationRequest(StrictProductModel):
    repository: str = Field(min_length=3, max_length=200, pattern=_REPOSITORY.pattern)
    generationId: str = Field(min_length=1, max_length=128)


class ProjectInsightRequest(StrictProductModel):
    generationId: str = Field(min_length=1, max_length=128)


class EvidenceBackedText(StrictProductModel):
    text: str = Field(min_length=2, max_length=600)
    evidenceRefs: list[str] = Field(min_length=1, max_length=5)

    @field_validator("evidenceRefs")
    @classmethod
    def _bounded_items(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values) or any(not value.strip() or len(value) > 240 for value in values):
            raise ValueError("evidence refs must be unique and bounded")
        return values


class OfficialIntro(EvidenceBackedText):
    sourceLabel: Literal["官方介绍", "官方介绍（译）", "AI受限概括"]


class ReusableAsset(StrictProductModel):
    reuseType: ReuseType
    asset: str = Field(min_length=2, max_length=300)
    howToUse: str = Field(min_length=2, max_length=500)
    evidenceRefs: list[str] = Field(min_length=1, max_length=5)

    @field_validator("evidenceRefs")
    @classmethod
    def _bounded_refs(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values) or any(not value.strip() or len(value) > 240 for value in values):
            raise ValueError("evidence refs must be unique and bounded")
        return values


class StartHere(StrictProductModel):
    label: str = Field(min_length=2, max_length=200)
    path: str = Field(min_length=1, max_length=240)
    evidenceRefs: list[str] = Field(min_length=1, max_length=5)

    @field_validator("evidenceRefs")
    @classmethod
    def _bounded_refs(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values) or any(not value.strip() or len(value) > 240 for value in values):
            raise ValueError("evidence refs must be unique and bounded")
        return values


class ProjectExplanation(StrictProductModel):
    officialIntro: OfficialIntro
    coreHighlights: list[EvidenceBackedText] = Field(min_length=1, max_length=3)
    reusableAssets: list[ReusableAsset] = Field(min_length=1, max_length=3)
    startHere: list[StartHere] = Field(min_length=1, max_length=3)
    implementationBoundaries: list[EvidenceBackedText] = Field(default_factory=list, max_length=3)


class ProjectExplanationResponse(StrictProductModel):
    state: Literal["ready", "unavailable"]
    repository: str
    githubRepositoryId: int | None = Field(default=None, gt=0)
    generationId: str
    promptVersion: Literal["rardar-project-insight-v2"]
    schemaVersion: Literal["rardar-project-insight-schema-v2"]
    format: Literal["structured", "none"]
    officialIntro: OfficialIntro
    analysis: ProjectExplanation | None = None
    errorCode: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=200)
    provider: str | None = Field(default=None, max_length=100)
    cacheHit: bool = False
    evidenceDigest: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidenceCacheHit: bool = False
    evidenceKinds: list[str] = Field(min_length=1, max_length=160)

    @model_validator(mode="after")
    def _state_matches_payload(self) -> ProjectExplanationResponse:
        if self.state == "ready" and (self.analysis is None or self.format != "structured"):
            raise ValueError("ready explanation requires structured analysis")
        if self.state == "unavailable" and (not self.errorCode or self.format != "none"):
            raise ValueError("unavailable explanation requires a stable error code")
        return self


class FindProjectRequest(StrictProductModel):
    requirement: str = Field(min_length=6, max_length=1200)
    repositoryUrl: str | None = Field(default=None, max_length=300)

    @field_validator("repositoryUrl")
    @classmethod
    def _public_github_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normalized = value.strip().rstrip("/")
        parsed = urlparse(normalized)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "github.com"
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ValueError("repositoryUrl must be a public https://github.com URL")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 2 or not _REPOSITORY.fullmatch("/".join(parts)):
            raise ValueError("repositoryUrl must identify exactly one public repository")
        return f"https://github.com/{parts[0]}/{parts[1]}"


class QuickProjectCandidate(StrictProductModel):
    githubRepositoryId: int = Field(gt=0)
    repository: str = Field(pattern=_REPOSITORY.pattern)
    description: str | None = Field(default=None, max_length=1000)
    totalStars: int = Field(ge=0)
    updatedAt: AwareDatetime
    primaryLanguage: str | None = Field(default=None, max_length=100)
    licenseSpdxId: str | None = Field(default=None, max_length=100)
    topics: list[str] = Field(default_factory=list, max_length=20)
    htmlUrl: HttpUrl
    preliminaryMatch: str = Field(min_length=2, max_length=400)
    dataState: Literal["github_live", "local_demo"]


class ComparedProject(StrictProductModel):
    repository: str = Field(pattern=_REPOSITORY.pattern)
    whatItDoes: str = Field(min_length=2, max_length=500)
    whyMatched: str = Field(min_length=2, max_length=700)
    reusableParts: list[str] = Field(min_length=1, max_length=5)
    integrationCost: Literal["low", "medium", "high"]
    risks: list[str] = Field(min_length=1, max_length=5)
    recommendation: str = Field(min_length=2, max_length=700)
    reuseType: ReuseType

    @field_validator("reusableParts", "risks")
    @classmethod
    def _bounded_items(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 300 for value in values):
            raise ValueError("items must be non-empty and bounded")
        return values


class FindProjectComparison(StrictProductModel):
    candidates: list[ComparedProject] = Field(min_length=3, max_length=3)
    overallConclusion: str = Field(min_length=2, max_length=900)


class FindProjectResponse(StrictProductModel):
    requirement: str
    repositoryUrl: str | None
    searchState: Literal["github_live", "limited", "demo"]
    coverageLabel: str
    sources: list[str]
    quickCandidates: list[QuickProjectCandidate] = Field(max_length=10)
    aiState: Literal["ready", "plain", "unavailable", "insufficient_candidates"]
    comparison: FindProjectComparison | None = None
    plainComparison: str | None = Field(default=None, max_length=2400)
    errorCode: str | None = Field(default=None, max_length=100)
    promptVersion: Literal["rardar-find-project-v1"]
    model: str | None = Field(default=None, max_length=200)
    provider: str | None = Field(default=None, max_length=100)
    cacheHit: bool = False

    @model_validator(mode="after")
    def _ai_state_matches_payload(self) -> FindProjectResponse:
        if self.aiState == "ready" and self.comparison is None:
            raise ValueError("ready comparison requires structured output")
        if self.aiState == "plain" and not self.plainComparison:
            raise ValueError("plain comparison requires bounded text")
        if self.aiState == "unavailable" and not self.errorCode:
            raise ValueError("unavailable comparison requires an error code")
        return self
