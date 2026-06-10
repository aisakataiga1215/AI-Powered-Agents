import os

from app.core.config import Settings, configure_langsmith_environment


def test_configure_langsmith_environment_exports_langchain_aliases(monkeypatch):
    for key in (
        "LANGSMITH_TRACING",
        "LANGSMITH_API_KEY",
        "LANGSMITH_PROJECT",
        "LANGSMITH_ENDPOINT",
        "LANGCHAIN_TRACING_V2",
        "LANGCHAIN_API_KEY",
        "LANGCHAIN_PROJECT",
        "LANGCHAIN_ENDPOINT",
    ):
        monkeypatch.delenv(key, raising=False)

    app_settings = Settings(
        langsmith_tracing=True,
        langsmith_api_key="test-key",
        langsmith_project="BT",
        langsmith_endpoint="https://api.smith.langchain.com",
    )

    configure_langsmith_environment(app_settings)

    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_API_KEY"] == "test-key"
    assert os.environ["LANGSMITH_PROJECT"] == "BT"
    assert os.environ["LANGSMITH_ENDPOINT"] == "https://api.smith.langchain.com"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"
    assert os.environ["LANGCHAIN_API_KEY"] == "test-key"
    assert os.environ["LANGCHAIN_PROJECT"] == "BT"
    assert os.environ["LANGCHAIN_ENDPOINT"] == "https://api.smith.langchain.com"


def test_configure_langsmith_environment_preserves_explicit_env(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "existing-key")

    app_settings = Settings(
        langsmith_tracing=True,
        langsmith_api_key="settings-key",
    )

    configure_langsmith_environment(app_settings)

    assert os.environ["LANGSMITH_API_KEY"] == "existing-key"


def test_configure_langsmith_environment_ignores_disabled_tracing(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)

    app_settings = Settings(
        langsmith_tracing=False,
        langsmith_api_key="test-key",
    )

    configure_langsmith_environment(app_settings)

    assert "LANGSMITH_TRACING" not in os.environ
