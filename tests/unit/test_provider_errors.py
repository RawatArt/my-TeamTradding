from ai_trading_team.runtime.providers.base import classify_provider_exception
from ai_trading_team.schemas.enums import RuntimeFailureCategory


class AuthenticationError(Exception):
    pass


def test_provider_error_classification_does_not_expose_exception_message() -> None:
    secret = "credential-that-must-not-escape"
    error = classify_provider_exception(AuthenticationError(secret))

    assert error.category is RuntimeFailureCategory.PROVIDER_AUTHENTICATION
    assert secret not in str(error)
