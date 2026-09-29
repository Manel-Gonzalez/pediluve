import pytest
from pydantic import ValidationError

from models.sessions import SessionCreate, SessionUpdate


@pytest.mark.parametrize("model_cls", [SessionCreate, SessionUpdate])
class TestSessionTitleValidation:
    def test_strips_surrounding_whitespace(self, model_cls):
        assert model_cls(title="  Standup  ").title == "Standup"

    def test_rejects_an_empty_title(self, model_cls):
        with pytest.raises(ValidationError):
            model_cls(title="")

    def test_rejects_a_whitespace_only_title(self, model_cls):
        with pytest.raises(ValidationError):
            model_cls(title="   ")

    def test_rejects_a_title_over_120_characters(self, model_cls):
        with pytest.raises(ValidationError):
            model_cls(title="x" * 121)

    def test_accepts_a_title_at_exactly_120_characters(self, model_cls):
        assert model_cls(title="x" * 120).title == "x" * 120
