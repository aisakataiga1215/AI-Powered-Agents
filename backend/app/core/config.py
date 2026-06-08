"""Application configuration loaded from environment variables.

Settings are populated from the project root .env file. Defaults are safe
for local development; production deployments must override secrets.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent.parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_env: str = "development"
    app_name: str = "competitive-agent-system"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Database
    database_url: str = "sqlite:///./dev.db"

    # LLM
    openai_api_key: str = ""
    openai_base_url: str = ""
    anthropic_api_key: str = ""
    default_model: str = "gpt-4.1-mini"
    # Set true for providers whose models have thinking enabled by default
    # (e.g. deepseek-v4-pro). Passes {"thinking": {"type": "disabled"}} in
    # extra_body so function_calling structured output works correctly.
    llm_disable_thinking: bool = False

    # Tracing
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "competitive-agent-system"

    # Search / Data
    enable_live_search: bool = False
    enable_demo_fixtures: bool = True
    # ``demo_scenario`` lets the demo deliberately exercise the QA rework
    # loop. ``happy_path`` (default) loads every fixture as-is. Set to
    # ``missing_pricing_source`` to have the CollectorAgent initially
    # withhold the pricing_page source for ``demo_withheld_pricing_competitor``;
    # the rework hint from QA then makes the second collector pass include
    # it, proving the failure → rework → repair path end to end.
    demo_scenario: str = "happy_path"
    demo_withheld_pricing_competitor: str = "Windsurf"

    # Runtime
    agent_timeout_seconds: int = 60
    max_repair_loops: int = 1
    log_level: str = "INFO"


settings = Settings()
