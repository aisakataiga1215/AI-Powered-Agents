"""Tests for feature category taxonomy normalization."""

import pytest

from app.services.normalization_service import normalize_feature_category
from app.agents.writer_agent import _build_feature_comparison
from app.schemas.knowledge import CompetitorKnowledge, FeatureCategory, FeatureItem, ProductProfile


class TestNormalizeFeatureCategory:
    def test_ai_agent_aliases_normalize_to_canonical(self):
        # "Cloud Agents" removed — it is now its own canonical, not an alias for AI Agents
        aliases = [
            "AI Agent", "ai agents", "Agent", "Agentic Editing",
            "Agent Command Center", "TRAE SOLO", "Agent Requests",
            "Agent Management", "Agent Execution",
        ]
        for alias in aliases:
            assert normalize_feature_category(alias) == "AI Agents", (
                f"Expected 'AI Agents' for alias '{alias}'"
            )

    def test_cloud_agents_aliases_normalize_to_cloud_agents(self):
        for alias in ["cloud agents", "Cloud Agents", "devin cloud", "Devin Cloud"]:
            assert normalize_feature_category(alias) == "Cloud Agents", (
                f"Expected 'Cloud Agents' for alias '{alias}'"
            )

    def test_code_completion_aliases_normalize_to_canonical(self):
        aliases = ["autocomplete", "Auto-Complete", "Inline Completion", "Code Completion"]
        for alias in aliases:
            assert normalize_feature_category(alias) == "Code Completion", (
                f"Expected 'Code Completion' for alias '{alias}'"
            )

    def test_unknown_category_passes_through_unchanged(self):
        assert normalize_feature_category("Chat") == "Chat"
        assert normalize_feature_category("Terminal") == "Terminal"
        assert normalize_feature_category("Search") == "Search"

    def test_normalize_is_case_insensitive(self):
        assert normalize_feature_category("AI AGENT") == "AI Agents"
        assert normalize_feature_category("AUTOCOMPLETE") == "Code Completion"
        assert normalize_feature_category("agentic editing") == "AI Agents"


class TestBuildFeatureComparisonMerge:
    def test_same_canonical_categories_are_merged_into_one_row(self):
        """Agent-like raw categories merge into one horizontal capability row."""
        ck = CompetitorKnowledge(
            competitor_id="comp_test",
            competitor_name="TestCo",
            product_profile=ProductProfile(name="TestCo", website=""),
            feature_tree=[
                FeatureCategory(category="AI Agent", features=[
                    FeatureItem(name="Inline Edit", availability="available"),
                ]),
                FeatureCategory(category="Agent Management", features=[
                    FeatureItem(name="Multi-Agent", availability="available"),
                ]),
            ],
        )
        result = _build_feature_comparison([ck])
        assert "TestCo" in result
        assert result["TestCo"].count("Agent 工作流:") == 1
        assert "Inline Edit" in result["TestCo"]
        assert "Multi-Agent" in result["TestCo"]

    def test_distinct_canonical_categories_remain_separate(self):
        ck = CompetitorKnowledge(
            competitor_id="comp_test",
            competitor_name="TestCo",
            product_profile=ProductProfile(name="TestCo", website=""),
            feature_tree=[
                FeatureCategory(category="AI Agent", features=[
                    FeatureItem(name="Autocomplete", availability="available"),
                ]),
                FeatureCategory(category="cloud agents", features=[
                    FeatureItem(name="Cloud Run", availability="available"),
                ]),
            ],
        )
        result = _build_feature_comparison([ck])
        assert "代码补全与生成:" in result["TestCo"]
        assert "云任务与部署:" in result["TestCo"]
        assert result["TestCo"].count("代码补全与生成:") == 1
        assert result["TestCo"].count("云任务与部署:") == 1
