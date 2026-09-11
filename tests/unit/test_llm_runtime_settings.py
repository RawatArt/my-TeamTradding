from pydantic import SecretStr

from ai_trading_team.config import AppSettings, LLMRuntimeSettings


def test_llm_runtime_is_disabled_and_credentials_absent_by_default() -> None:
    settings = AppSettings.model_validate({})

    assert settings.llm.enabled is False
    assert settings.llm.openai_api_key is None
    assert settings.llm.anthropic_api_key is None
    assert settings.llm.gemini_api_key is None


def test_provider_credentials_remain_secret_str() -> None:
    settings = LLMRuntimeSettings(openai_api_key=SecretStr("top-secret"))

    assert isinstance(settings.openai_api_key, SecretStr)
    assert "top-secret" not in repr(settings)
    assert "top-secret" not in settings.model_dump_json()
