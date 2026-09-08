"""Requirement-first Find regression; all GitHub and model traffic is mocked."""

import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from app.schemas.rardar_product import FindProjectComparison, FindProjectRequest, FindWireComparison, RequirementProfile
from app.services import rardar_product as service
from app.services.rardar_llm_control import RardarLLMError
from app.services.rardar_project_evidence import ProjectEvidence

BODY = "Self-hosted Markdown documentation includes full-text search without hosted services."


def test_prompt_excerpts_keep_late_capability_context_bounded_and_original_intact():
    evidence = material("fixture/project1")
    index = evidence.payload["evidenceIndex"]
    for number in range(1, 7):
        index[f"readme:body:{number}"] = "Unrelated introduction. " * 85
    tail = "Deployment uses Docker. Community edition does not include granular permission controls; enterprise costs 100 dollars."
    index["readme:body:6"] += tail
    original = json.dumps(evidence.payload, sort_keys=True)
    result = service._find_prompt_evidence(evidence, profile())
    excerpts = result["evidenceIndex"]
    assert tail in excerpts["readme:body:6"]
    assert sum(len(value) for key, value in excerpts.items() if key.startswith("readme:body:")) <= 4200
    assert "remain unknown" in result["materialScope"]
    assert json.dumps(evidence.payload, sort_keys=True) == original
    assert result == service._find_prompt_evidence(evidence, profile())


def test_prompt_disjoint_excerpts_are_not_presented_as_contiguous():
    evidence = material("fixture/project1")
    evidence.payload["evidenceIndex"]["readme:body:1"] = (
        "search is local. " + "x" * 900 + "Permission requires paid edition." + "x" * 900
    )
    result = service._find_prompt_evidence(evidence, profile())
    assert "[... omitted; separate source excerpt ...]" in result["evidenceIndex"]["readme:body:1"]
    value = comparison(["fixture/project1"], status="unknown", refs=[])
    service._validate_find_comparison(value, {"fixture/project1": evidence}, profile())


def profile():
    return RequirementProfile(
        purpose="团队文档站", mustHave=["支持全文搜索"], exclusions=["无需托管服务"], queries=["markdown documentation"]
    )


def repo(index, stars=1):
    return {
        "id": index,
        "full_name": f"fixture/project{index}",
        "private": False,
        "html_url": f"https://github.com/fixture/project{index}",
        "description": "Documentation tools",
        "stargazers_count": stars,
        "updated_at": "2026-09-01T00:00:00Z",
        "pushed_at": "2026-08-01T00:00:00Z",
        "language": "Python",
        "license": {"spdx_id": "MIT"},
        "topics": [],
    }


def material(repository, metadata=None):
    index = {"repository": repository, "description": "Documentation", "readme:body:1": BODY}
    return ProjectEvidence(
        payload={"repository": repository, "evidenceIndex": index, "metadata": metadata or {}},
        digest="a" * 64,
        allowed_refs=frozenset(index),
        path_refs={"readme:body:1": "README.md"},
        official_intro={},
        expected_intro_label="官方介绍",
        cache_hit=False,
    )


def comparison(repositories, status="supported", refs=None):
    refs = ["readme:body:1"] if refs is None else refs
    return FindProjectComparison.model_validate_json(
        json.dumps(
            {
                "candidates": [
                    {
                        "repository": repository,
                        "whatItDoes": "提供文档工具",
                        "whyMatched": "根据文档核对需求",
                        "reusableParts": [],
                        "integrationCost": "unknown",
                        "risks": [],
                        "recommendation": "继续核对部署文档",
                        "reuseType": "whole_product",
                        "requirementChecks": [
                            {
                                "requirement": requirement,
                                "status": status,
                                "reason": "文档明确声明" if status != "unknown" else "尚无足够资料",
                                "evidenceRefs": refs,
                                "supportingQuote": BODY if status != "unknown" else "",
                            }
                            for requirement in profile().mustHave + profile().exclusions
                        ],
                        "evidenceRefs": ["repository"],
                    }
                    for repository in repositories
                ],
                "overallConclusion": "只依据本次取得的公开资料，不等于功能实测。",
            }
        )
    )


def wire_comparison(value):
    payload = value.model_dump()
    ids = {text: identity for identity, text in service._find_conditions(profile()).items()}
    for item in payload["candidates"]:
        for check in item["requirementChecks"]:
            check["conditionId"] = ids[check.pop("requirement")]
    return FindWireComparison.model_validate(payload, strict=True)


def install(monkeypatch, chosen, *, failure=False, captured=None):
    async def model(**kwargs):
        if kwargs["response_model"] is RequirementProfile:
            return SimpleNamespace(value=profile())
        if captured is not None:
            captured.append(kwargs["messages"])
        if failure:
            raise RardarLLMError("rardar_llm_invalid_output")
        return SimpleNamespace(
            value=wire_comparison(comparison(chosen)),
            metadata=SimpleNamespace(model_display_name="mock", provider="mock", cache_hit=False),
        )

    async def evidence(repository, facts, **kwargs):
        assert kwargs["include_readme_body"] is True
        return material(repository, facts)

    async def forbidden(**kwargs):
        pytest.fail("Find must not fall back to unvalidated plain model output")

    monkeypatch.setattr(service, "call_rardar_structured", model)
    monkeypatch.setattr(service, "call_rardar_llm", forbidden)
    monkeypatch.setattr(service, "collect_project_evidence", evidence)


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 1, 2, 3])
async def test_real_candidate_count_not_exactly_three(monkeypatch, count):
    install(monkeypatch, [f"fixture/project{i}" for i in range(1, count + 1)])
    seen = []

    def github(request):
        seen.append(request)
        return httpx.Response(200, json={"items": [repo(i) for i in range(1, count + 1)]})

    async with httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(github)) as client:
        result = await service.find_projects(FindProjectRequest(requirement="团队自托管文档全文搜索"), client=client)
    assert seen and all(request.url.path == "/search/repositories" for request in seen)
    assert len(result.quickCandidates) == count
    assert all(item.dataState == "github_live" for item in result.quickCandidates)
    assert result.aiState == ("ready" if count else "insufficient_candidates")
    if count:
        assert len(result.comparison.candidates) == count


@pytest.mark.asyncio
async def test_relevance_order_not_star_truncation_and_subset(monkeypatch):
    install(monkeypatch, ["fixture/project1"])
    seen = []

    def github(request):
        seen.append(request)
        return httpx.Response(200, json={"items": [repo(i, i * 100000) for i in range(1, 11)]})

    async with httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(github)) as client:
        result = await service.find_projects(FindProjectRequest(requirement="团队自托管文档全文搜索"), client=client)
    assert result.quickCandidates[0].repository == "fixture/project1"
    assert len(result.quickCandidates) == 10
    assert len(result.comparison.candidates) == 1
    assert all("sort" not in request.url.params for request in seen)
    assert result.quickCandidates[6].evidenceState == "not_analyzed"


@pytest.mark.parametrize("reference", ["description", "repository", "invented:body:1"])
def test_supported_requires_real_body_not_metadata(reference):
    with pytest.raises(RardarLLMError):
        service._validate_find_comparison(
            comparison(["fixture/project1"], refs=[reference]),
            {"fixture/project1": material("fixture/project1")},
            profile(),
        )


def test_unknown_does_not_invent_sources_cost_or_risks():
    value = comparison(["fixture/project1"], status="unknown", refs=[])
    service._validate_find_comparison(value, {"fixture/project1": material("fixture/project1")}, profile())
    assert value.candidates[0].integrationCost == "unknown"
    assert value.candidates[0].risks == []


def test_invented_repository_rejected():
    with pytest.raises(RardarLLMError):
        service._validate_find_comparison(
            comparison(["guessed/answer"]), {"fixture/project1": material("fixture/project1")}, profile()
        )


@pytest.mark.parametrize(
    "query",
    ["https://github.com/search", "stars:>10000", "language:python", "repo:owner/name", "x; rm -rf", "docs\nsearch"],
)
def test_query_rejects_urls_qualifiers_commands(query):
    with pytest.raises(ValidationError):
        RequirementProfile(purpose="文档工具", mustHave=["搜索"], queries=[query])


def test_private_candidate_is_rejected():
    value = repo(1)
    value["private"] = True
    assert service._github_candidate(value, match="真实检索") is None


@pytest.mark.asyncio
async def test_comparison_failure_preserves_real_candidates(monkeypatch):
    install(monkeypatch, [], failure=True)
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"items": [repo(1)]})),
    ) as client:
        result = await service.find_projects(FindProjectRequest(requirement="团队自托管文档全文搜索"), client=client)
    assert result.aiState == "unavailable"
    assert len(result.quickCandidates) == 1
    assert result.evidenceSources
    assert result.plainComparison is None


@pytest.mark.asyncio
async def test_supplied_repository_context_cannot_be_silently_omitted(monkeypatch):
    install(monkeypatch, ["fixture/project2"])

    def github(request):
        return httpx.Response(200, json=repo(1) if request.url.path.startswith("/repos/") else {"items": [repo(2)]})

    async with httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(github)) as client:
        result = await service.find_projects(
            FindProjectRequest(
                requirement="团队自托管文档全文搜索", repositoryUrl="https://github.com/fixture/project1"
            ),
            client=client,
        )
    assert result.quickCandidates[0].isProvided is True
    assert result.aiState == "unavailable"
    assert len(result.quickCandidates) == 2


def test_supporting_quote_must_actually_occur_in_referenced_body():
    value = comparison(["fixture/project1"])
    value.candidates[0].requirementChecks[0].supportingQuote = "Enterprise granular role based access is free."
    with pytest.raises(RardarLLMError):
        service._validate_find_comparison(value, {"fixture/project1": material("fixture/project1")}, profile())


@pytest.mark.parametrize("mutation", [None, "negation", "number"])
def test_literal_quote_ending_at_markdown_link_label_is_not_rejected(mutation):
    value = comparison(["fixture/project1"])
    evidence = material("fixture/project1")
    text = "Retries do not exceed 100 attempts with [exponential backoff](https://example.org/retries)."
    check = value.candidates[0].requirementChecks[0]
    evidence.payload["evidenceIndex"][check.evidenceRefs[0]] += "\n" + text
    check.supportingQuote = "Retries do not exceed 100 attempts with [exponential backoff]"
    if mutation:
        check.supportingQuote = (
            check.supportingQuote.replace("do not exceed", "do exceed")
            if mutation == "negation"
            else check.supportingQuote.replace("100", "200")
        )
        with pytest.raises(RardarLLMError):
            service._validate_find_comparison(value, {"fixture/project1": evidence}, profile())
    else:
        service._validate_find_comparison(value, {"fixture/project1": evidence}, profile())


@pytest.mark.parametrize("changed", [False, True])
def test_visible_markdown_link_quote_keeps_factual_words(changed):
    quote = (
        "the search engine feature is 100% local. This means that it does not run on an external service like Algolia"
    )
    evidence = material("fixture/project1")
    evidence.payload["evidenceIndex"]["readme:body:1"] = quote.replace("Algolia", "[Algolia](https://www.algolia.com/)")
    value = comparison(["fixture/project1"])
    for check in value.candidates[0].requirementChecks:
        check.supportingQuote = quote.replace("does not run", "does run") if changed else quote
    if changed:
        with pytest.raises(RardarLLMError):
            service._validate_find_comparison(value, {"fixture/project1": evidence}, profile())
    else:
        service._validate_find_comparison(value, {"fixture/project1": evidence}, profile())
        assert value.candidates[0].requirementChecks[0].supportingQuote == quote
        assert "[Algolia](https://www.algolia.com/)" in evidence.payload["evidenceIndex"]["readme:body:1"]


@pytest.mark.asyncio
async def test_provided_repository_can_be_unknown_and_alternative_ranked_first(monkeypatch):
    install(monkeypatch, [])

    async def model(**kwargs):
        if kwargs["response_model"] is RequirementProfile:
            return SimpleNamespace(value=profile())
        value = comparison(["fixture/project2", "fixture/project1"], status="unknown", refs=[])
        return SimpleNamespace(
            value=wire_comparison(value),
            metadata=SimpleNamespace(model_display_name="mock", provider="mock", cache_hit=False),
        )

    monkeypatch.setattr(service, "call_rardar_structured", model)

    def github(request):
        return httpx.Response(200, json=repo(1) if request.url.path.startswith("/repos/") else {"items": [repo(2)]})

    async with httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(github)) as client:
        result = await service.find_projects(
            FindProjectRequest(
                requirement="团队自托管文档全文搜索", repositoryUrl="https://github.com/fixture/project1"
            ),
            client=client,
        )
    assert result.aiState == "ready"
    assert [item.repository for item in result.comparison.candidates] == ["fixture/project2", "fixture/project1"]
    assert all(check.status == "unknown" for check in result.comparison.candidates[1].requirementChecks)


def test_duplicate_requirement_checks_cannot_contradict_each_other():
    value = comparison(["fixture/project1"])
    value.candidates[0].requirementChecks.append(
        value.candidates[0].requirementChecks[0].model_copy(update={"status": "not_supported"})
    )
    with pytest.raises(RardarLLMError):
        service._validate_find_comparison(value, {"fixture/project1": material("fixture/project1")}, profile())


@pytest.mark.asyncio
async def test_partial_evidence_timeout_preserves_other_candidate(monkeypatch):
    install(monkeypatch, ["fixture/project2"])

    async def evidence(repository, facts, **kwargs):
        if repository.endswith("project1"):
            raise httpx.ReadTimeout("unavailable")
        return material(repository)

    monkeypatch.setattr(service, "collect_project_evidence", evidence)
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"items": [repo(1), repo(2)]})),
    ) as client:
        result = await service.find_projects(FindProjectRequest(requirement="团队自托管文档全文搜索"), client=client)
    assert result.aiState == "ready"
    assert result.quickCandidates[0].evidenceState == "metadata_only"
    assert result.quickCandidates[1].evidenceState == "ready"


@pytest.mark.asyncio
async def test_star_change_does_not_change_comparison_cache_input(monkeypatch):
    captured = []
    install(monkeypatch, ["fixture/project1"], captured=captured)
    for stars in (1, 9999):
        async with httpx.AsyncClient(
            base_url="https://api.github.com",
            transport=httpx.MockTransport(lambda _, stars=stars: httpx.Response(200, json={"items": [repo(1, stars)]})),
        ) as client:
            await service.find_projects(FindProjectRequest(requirement="团队自托管文档全文搜索"), client=client)
    assert captured[0] == captured[1]


@pytest.mark.asyncio
async def test_comparison_keeps_full_index_without_duplicate_payload(monkeypatch):
    captured = []
    install(monkeypatch, ["fixture/project1"], captured=captured)

    async def evidence(repository, facts, **kwargs):
        value = material(repository)
        value.payload["readme"] = {"introduction": BODY, "headings": []}
        value.payload["metadata"] = {"topics": ["irrelevant-to-comparison"]}
        return value

    monkeypatch.setattr(service, "collect_project_evidence", evidence)
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"items": [repo(1)]})),
    ) as client:
        result = await service.find_projects(FindProjectRequest(requirement="团队自托管文档全文搜索"), client=client)
    payload = json.loads(captured[0][1]["content"])
    assert payload["requiredChecks"] == {"c1": "支持全文搜索", "c2": "无需托管服务"}
    assert "requirementProfile" not in payload
    assert "projectEvidence" not in payload
    assert len(captured[0]) == 3
    assert captured[0][1]["role"] == captured[0][2]["role"] == "user"
    sent = json.loads(captured[0][2]["content"])["projectEvidence"]["fixture/project1"]
    assert set(sent) == {"evidenceIndex", "materialScope"}
    assert sent["evidenceIndex"] == material("fixture/project1").payload["evidenceIndex"]
    assert any(row.text == BODY for row in result.evidenceSources)


@pytest.mark.parametrize("defect", ["missing", "duplicate", "unknown_id"])
def test_wire_conditions_fail_closed_instead_of_synthesizing_judgments(defect):
    value = wire_comparison(comparison(["fixture/project1"]))
    checks = value.candidates[0].requirementChecks
    if defect == "missing":
        checks.pop()
    elif defect == "duplicate":
        checks[1].conditionId = checks[0].conditionId
    else:
        checks[1].conditionId = "c99"
    with pytest.raises(RardarLLMError):
        service._expand_find_comparison(value, profile())


def test_wire_expansion_restores_exact_text_without_changing_judgment_or_evidence():
    original = comparison(["fixture/project1"])
    value = wire_comparison(original)
    expanded = service._expand_find_comparison(value, profile())
    assert expanded == original
    service._validate_find_comparison(expanded, {"fixture/project1": material("fixture/project1")}, profile())
    value.candidates[0].requirementChecks[0].supportingQuote = "Invented feature not in README"
    with pytest.raises(RardarLLMError):
        service._validate_find_comparison(
            service._expand_find_comparison(value, profile()),
            {"fixture/project1": material("fixture/project1")},
            profile(),
        )


@pytest.mark.asyncio
async def test_application_rejects_missing_wire_condition_and_preserves_candidate(monkeypatch, caplog):
    install(monkeypatch, ["fixture/project1"])

    async def model(**kwargs):
        if kwargs["response_model"] is RequirementProfile:
            return SimpleNamespace(value=profile())
        value = wire_comparison(comparison(["fixture/project1"]))
        value.candidates[0].requirementChecks.pop()
        return SimpleNamespace(value=value)

    monkeypatch.setattr(service, "call_rardar_structured", model)
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"items": [repo(1)]})),
    ) as client:
        result = await service.find_projects(FindProjectRequest(requirement="团队自托管文档全文搜索"), client=client)
    assert result.aiState == "unavailable"
    assert result.errorCode == "rardar_llm_invalid_output"
    assert result.comparison is None
    assert result.quickCandidates[0].repository == "fixture/project1"
    assert "operation_id=" in caplog.text
    assert "stage=condition_coverage" in caplog.text
    assert "field=$.candidates[0].requirementChecks" in caplog.text
    assert "团队自托管文档全文搜索" not in caplog.text


@pytest.mark.parametrize(
    "defect,stage,path",
    [
        ("identity", "repository_identity", "$.candidates[0].repository"),
        ("refs", "reference_scope", "$.candidates[0].evidenceRefs"),
        ("coverage", "condition_coverage", "$.candidates[0].requirementChecks"),
        ("quote", "quote_text", "$.candidates[0].requirementChecks[0].supportingQuote"),
    ],
)
def test_validation_diagnostics_identify_rule_without_visible_model_text(defect, stage, path):
    value = comparison(["fixture/project1"])
    if defect == "identity":
        value.candidates[0].repository = "untrusted/secret"
    elif defect == "refs":
        value.candidates[0].evidenceRefs = ["untrusted-secret-ref"]
    elif defect == "coverage":
        value.candidates[0].requirementChecks.pop()
    else:
        value.candidates[0].requirementChecks[0].supportingQuote = "untrusted-secret-quote"
    with pytest.raises(RardarLLMError) as captured:
        service._validate_find_comparison(value, {"fixture/project1": material("fixture/project1")}, profile())
    error = captured.value
    assert error.validation_stage == stage
    assert error.field_path == path
    assert "untrusted" not in repr(vars(error))
