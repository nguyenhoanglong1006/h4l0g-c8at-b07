from types import SimpleNamespace

import pytest
from google.genai import errors

from optibot.assistant import service
from optibot.config import Settings


def server_error(code: int) -> errors.ServerError:
    return errors.ServerError(code, {"error": {"code": code, "message": "x", "status": "X"}})


class FakeModels:
    def __init__(self, failures: dict[str, errors.ServerError]):
        self.failures = failures
        self.called: list[str] = []

    def generate_content(self, *, model: str, contents: str, config: object) -> SimpleNamespace:
        self.called.append(model)
        if model in self.failures:
            raise self.failures[model]
        return SimpleNamespace(text=f"answer from {model}")


class FakeClient:
    def __init__(self, models: FakeModels):
        self.models = models

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, *_: object) -> None:
        return None


@pytest.fixture
def use_models(monkeypatch):
    def install(failures: dict[str, errors.ServerError]) -> FakeModels:
        models = FakeModels(failures)
        monkeypatch.delenv("GEMINI_MODEL", raising=False)
        monkeypatch.setattr(service, "load_settings", lambda: Settings("key", "fileSearchStores/x"))
        monkeypatch.setattr(service.genai, "Client", lambda api_key: FakeClient(models))
        return models

    return install


def test_primary_model_answers(use_models):
    models = use_models({})

    assert service.ask("q") == f"answer from {service.DEFAULT_MODEL}"
    assert models.called == [service.DEFAULT_MODEL]


def test_overloaded_primary_falls_back(use_models):
    models = use_models({service.DEFAULT_MODEL: server_error(503)})

    assert service.ask("q") == f"answer from {service.FALLBACK_MODEL}"
    assert models.called == [service.DEFAULT_MODEL, service.FALLBACK_MODEL]


def test_other_server_errors_are_raised(use_models):
    models = use_models({service.DEFAULT_MODEL: server_error(500)})

    with pytest.raises(errors.ServerError):
        service.ask("q")
    assert models.called == [service.DEFAULT_MODEL]
