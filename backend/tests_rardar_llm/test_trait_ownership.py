from app.integrations.rardar.serving_profiles import _structured_traits


def labels(evidence):
    return [[claim.text for claim in group] for group in _structured_traits(evidence)]


def test_negated_framework_is_not_a_product_form():
    forms, _, _, _ = labels({"readme:section:1": "README.md#start: No framework. Runs locally in your browser."})
    assert "框架" not in forms


def test_tutorial_catalog_does_not_deliver_its_tutorial_subjects():
    forms, environments, _, _ = labels(
        {
            "readme:section:1": "This repository is a compilation of step-by-step guides for re-creating technologies.",
            "readme:section:1:item:6": "README.md#build-your-own: Command-Line Tool",
            "readme:section:2:item:1": "README.md#tutorials: Python framework tutorial",
        }
    )
    assert "CLI" not in forms and "框架" not in forms
    assert environments == []


def test_indexed_third_party_projects_are_not_repository_traits():
    forms, environments, _, _ = labels(
        {
            "description": "Awesome lists about all kinds of interesting topics.",
            "readme:section:5:item:1": "README.md#back-end: Flask - Python framework.",
            "readme:section:12:item:4": "README.md#misc: Command-Line Apps",
            "readme:section:12:item:5": "README.md#misc: ZSH Plugins",
            "readme:section:12:item:6": "README.md#misc: GitHub hosted service",
        }
    )
    assert not {"CLI", "插件", "框架", "服务"} & set(forms)
    assert environments == []


def test_real_cli_framework_and_explicit_collection_tool_are_retained():
    forms, _, _, _ = labels({"description": "A command-line tool and framework for local jobs."})
    assert {"CLI", "框架"} <= set(forms)
    forms, _, _, _ = labels(
        {
            "description": "A collection of tutorials.",
            "readme:section:2": "This repository provides a CLI to search its tutorial index.",
        }
    )
    assert "CLI" in forms
    forms, _, _, _ = labels(
        {
            "description": "A collection of tutorials.",
            "readme:section:2": "This repository provides tutorials for building a CLI.",
        }
    )
    assert "CLI" not in forms


def test_dependencies_and_environment_names_do_not_become_product_forms():
    forms, environments, _, _ = labels(
        {
            "description": "Agent skill supporting Codex CLI and Claude Code.",
            "readme:section:2": "Built with the Flask framework; the app consumes a hosted service.",
        }
    )
    assert "Agent Skill" in forms
    assert not {"CLI", "框架", "服务"} & set(forms)
    assert "Codex CLI" in environments


def test_negation_is_local_not_a_whole_paragraph_veto():
    forms, _, _, _ = labels({"description": "No framework required. This repository provides a CLI."})
    assert "框架" not in forms and "CLI" in forms


def test_contrast_dependency_and_postfixed_negation():
    forms, _, _, _ = labels({"description": "This is not a framework but a CLI."})
    assert "框架" not in forms and "CLI" in forms
    _, environments, delivery, _ = labels(
        {
            "description": "This tool uses a cloud service.",
            "readme:section:1": "Linux is not supported. Exports neither PNG nor SVG.",
        }
    )
    assert "Linux" not in environments
    assert not {"云服务", "PNG", "SVG"} & set(delivery)
    forms, _, delivery, _ = labels({"description": "Use the CLI to render diagrams. Exports PNG, but not SVG."})
    assert "CLI" in forms
    assert "PNG" in delivery and "SVG" not in delivery
    _, _, delivery, _ = labels({"description": "支持 PNG，但不支持 SVG。"})
    assert "PNG" in delivery and "SVG" not in delivery


def test_supported_architecture_outputs_and_agent_environments():
    forms, environments, delivery, _ = labels(
        {
            "description": "Agent skill for verifiable diagrams.",
            "readme:narrative:positioning": "本项目以 Agent Skill 形式支持 Raven、Cursor、Claude Code、Codex CLI 和 OpenCode。",
            "readme:narrative:highlight:4": "Typed JSON IR 和确定性校验生成独立 HTML，并支持 PNG、SVG、WebM。",
            "readme:section:7": "直接询问零依赖 CLI：node tools/bin/render.mjs compare base.json head.json",
        }
    )
    assert {"Agent Skill", "CLI"} <= set(forms)
    assert {"Raven", "Cursor", "Claude Code", "Codex CLI", "OpenCode"} <= set(environments)
    assert {"独立 HTML", "PNG", "SVG", "WebM"} <= set(delivery)


def test_community_name_and_diagram_subject_are_not_runtime_or_form():
    forms, environments, _, _ = labels(
        {
            "description": "Agent skill for architecture, workflow, sequence and lifecycle diagrams.",
            "readme:section:10": "Contribute via our community · LINUX DO",
        }
    )
    assert "工作流" not in forms and "Linux" not in environments
    forms, _, _, _ = labels({"description": "A workflow engine that generates diagrams."})
    assert "工作流" in forms
