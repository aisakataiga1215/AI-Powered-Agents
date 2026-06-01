"""WriterAgent ``output_language`` unit tests.

These tests exercise the pure-helper language-toggle behaviour added to
:mod:`app.agents.writer_agent`:

* ``_build_user_message`` appends a Chinese-language instruction when
  ``output_language == "zh"`` and stays English-only by default.
* ``_build_pricing_markdown`` swaps the section title and table headers
  between English and Simplified Chinese.

No DB, LLM, or network access is needed — these helpers operate purely on
Pydantic inputs. ``conftest.py`` adds the backend directory to ``sys.path``
so the ``app.*`` imports resolve regardless of where pytest is invoked.
"""

from app.agents.writer_agent import (
    _build_pricing_markdown,
    _build_user_message,
)
from app.schemas.knowledge import (
    CompetitorKnowledge,
    PricingModel,
    PricingPlan,
)


def _knowledge_with_one_plan() -> CompetitorKnowledge:
    """Minimal CompetitorKnowledge carrying a single pricing plan.

    Kept tiny on purpose: the pricing-markdown helper only reads
    ``competitor_name`` and ``pricing_model.plans``.
    """
    return CompetitorKnowledge(
        competitor_id="comp_1",
        competitor_name="Cursor",
        pricing_model=PricingModel(
            has_free_plan=False,
            plans=[
                PricingPlan(
                    name="Pro",
                    price="$20",
                    billing_cycle="monthly",
                ),
            ],
        ),
    )


def test_user_message_en_has_no_lang_instruction():
    """Default (``output_language='en'``) should not leak a CN instruction."""
    msg = _build_user_message([], [], [], None, output_language="en")
    assert "简体中文" not in msg
    assert "OUTPUT LANGUAGE" not in msg


def test_user_message_zh_contains_chinese_instruction():
    """``output_language='zh'`` should append a Chinese-language directive."""
    msg = _build_user_message([], [], [], None, output_language="zh")
    # Accept either the Chinese literal or the English label that pairs
    # with it in the instruction, so the test stays robust to minor
    # wording tweaks of the directive itself.
    assert "简体中文" in msg or "Simplified Chinese" in msg


def test_pricing_markdown_en_header():
    """English mode renders the English section title and column headers."""
    knowledge = [_knowledge_with_one_plan()]
    rendered = _build_pricing_markdown(knowledge, output_language="en")
    assert "## Pricing Comparison" in rendered
    assert "Competitor" in rendered
    # Sanity-check that the row content from the fixture made it through.
    assert "Cursor" in rendered
    assert "Pro" in rendered


def test_pricing_markdown_zh_header():
    """Chinese mode renders the Chinese section title and column header."""
    knowledge = [_knowledge_with_one_plan()]
    rendered = _build_pricing_markdown(knowledge, output_language="zh")
    assert "## 定价对比" in rendered
    assert "竞品" in rendered
    # Row content is structured data and should still appear verbatim.
    assert "Cursor" in rendered
    assert "Pro" in rendered


def test_pricing_markdown_empty_returns_empty():
    """No competitor plans → no table, regardless of language."""
    assert _build_pricing_markdown([], output_language="zh") == ""
