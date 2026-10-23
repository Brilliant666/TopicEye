from types import SimpleNamespace

import pytest

from app.integrations.rardar.serving_profiles import (
    _key_differentiators,
    _legacy_structured_traits,
    _nonduplicate_differentiators,
    _prioritize_start_here,
    _structured_traits,
    project_reading_semantics,
)
from app.integrations.rardar.serving_schemas import ServingCapability, StartHereLink


def labels(evidence):
    return [[claim.text for claim in group] for group in _structured_traits(evidence)]


def test_android_application_is_not_its_build_sdk_or_installation_host():
    evidence = {
        "description": "An Android TV launcher with a clock and application grid.",
        "readme:section:1": "Build with Android SDK. Windows users can sideload through adb. Open the download in your browser.",
    }
    forms, environments, delivery, _ = labels(evidence)
    assert "完整应用" in forms
    assert environments == ["Android TV"]
    assert "SDK" not in forms + delivery
    # Persisted v2 trait corrections still validate against their original rules.
    legacy = [[claim.text for claim in group] for group in _legacy_structured_traits(evidence)]
    assert "SDK" in legacy[0]


@pytest.mark.parametrize("product", ["桌面", "启动器", "应用"])
def test_mixed_language_platform_identity_is_preserved_without_build_host_claims(product):
    evidence = {
        "readme:narrative:positioning": f"参照电视界面设计的 Android TV {product}：没有广告，只有你的应用和壁纸。",
        "readme:section:3": "安装 Android TV 开发 SDK，在 Windows 上编译。",
    }
    forms, environments, delivery, _ = labels(evidence)
    assert "完整应用" in forms
    assert environments == ["Android TV"]
    assert "SDK" not in forms + delivery
    assert labels({"description": "安装 Android TV 开发 SDK，在 Windows 上编译。"})[1] == []


def test_model_training_material_does_not_change_its_product_identity():
    forms, _, _, _ = labels(
        {
            "description": "A fine-tuned classification model trained on multiple datasets.",
            "readme:section:4": "The training dataset contains examples and annotations.",
        }
    )
    assert "模型" in forms
    assert "数据集" not in forms
    assert "数据集" in labels({"description": "A dataset of annotated acoustic recordings."})[0]


@pytest.mark.parametrize("identity", ["decision models", "classification models", "language models", "embedding model"])
def test_model_family_plural_identity_does_not_become_training_dataset(identity):
    forms, _, _, _ = labels(
        {
            "readme:narrative:positioning": f"Fine-tunes for zero-shot classification: small, fast {identity} you slot into your code.",
            "readme:section:4": "These models were trained on multiple datasets.",
        }
    )
    assert "模型" in forms
    assert "数据集" not in forms


def test_real_sdk_and_explicit_runtime_support_remain_available():
    forms, environments, delivery, _ = labels(
        {
            "description": "A JavaScript SDK for a hosted product.",
            "readme:section:4": "This project supports Windows and Linux. This application runs in your browser.",
        }
    )
    assert "SDK" in forms and "SDK" in delivery
    assert {"Windows", "Linux", "浏览器"} <= set(environments)


def test_description_dependencies_and_tool_targets_are_not_product_traits():
    forms, environments, delivery, _ = labels(
        {
            "description": "A developer tool for building SDKs and Windows apps. It depends on a Python framework and cloud service.",
        }
    )
    assert "开发工具" in forms
    assert not {"SDK", "框架", "服务"} & set(forms)
    assert not {"Windows", "Python"} & set(environments)
    assert "SDK" not in delivery
    assert "SDK" in labels({"description": "An SDK for building Windows applications."})[0]


def capability(detail, title="工程能力"):
    return ServingCapability(title=title, detail=detail, evidenceRefs=["description"], sourceMode="rardar_derived")


def test_capabilities_are_not_manufactured_into_comparisons():
    ordinary = capability("在首页显示时钟和应用网格。")
    genuine = capability("与需要托管服务的方案不同，应用在本地运行且可离线使用。", "离线使用")
    wrapped = capability("与常见替代方案比较时，Rardar 会重点核验这项工程能力：在首页显示时钟和应用网格。")
    assert _key_differentiators([ordinary]) == []
    assert _nonduplicate_differentiators([ordinary, wrapped], [ordinary]) == []
    assert _nonduplicate_differentiators([genuine], [ordinary]) == [genuine]


def test_comparison_qualifiers_and_negation_are_not_removed_as_duplicates():
    ordinary = capability("在本地运行并可离线处理全部输入资料。")
    qualified = capability("与需要托管服务的方案不同，在本地运行并可离线处理全部输入资料。")
    limitation = capability("不同于支持同步的方案，本工具不支持同步，在本地运行并可离线处理全部输入资料。")
    assert _nonduplicate_differentiators([qualified, limitation], [ordinary]) == [qualified, limitation]


def test_start_here_orders_usage_before_resources_without_dropping_resources():
    def link(path):
        return StartHereLink(
            label=path, path=path, htmlUrl=f"https://github.com/team/app/blob/main/{path}", evidenceRefs=["description"]
        )

    links = [link("app/assets/themes.json"), link("README.md#features"), link("docs"), link("README.md#installation")]
    sections = [
        SimpleNamespace(path="README.md#features", purpose="capabilities"),
        SimpleNamespace(path="README.md#installation", purpose="quick_start"),
    ]
    ordered = _prioritize_start_here(links, sections)
    assert [item.path for item in ordered] == [
        "README.md#installation",
        "docs",
        "README.md#features",
        "app/assets/themes.json",
    ]
    assert links[0].path == "app/assets/themes.json"


@pytest.mark.asyncio
async def test_read_projection_preserves_original_material_and_checks_binding(tmp_path):
    from app.integrations.rardar.profile_cache_v2 import ProfileStoreEnvelopeV2
    from tests_rardar_llm.test_managed_materials import seed

    path = await seed(tmp_path)
    record = ProfileStoreEnvelopeV2.model_validate_json(path.read_bytes(), strict=True)
    before = record.model_dump(mode="json")
    projection = project_reading_semantics(record.profile, record.evidence)
    assert "generatedAt" not in projection and "evidenceDigest" not in projection
    for claim, original_refs in record.profile.claimEvidenceRefs.items():
        projected_refs = projection["claimEvidenceRefs"].get(claim, [])
        if set(original_refs) == set(projected_refs):
            assert projected_refs == original_refs
    assert record.model_dump(mode="json") == before
    with pytest.raises(ValueError, match="binding_invalid"):
        project_reading_semantics(record.profile, record.evidence.model_copy(update={"repository": "other/project"}))
