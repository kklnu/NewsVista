"""Model-output validation: citations, publisher-named perspectives, quotes, numbers."""
from datetime import datetime, timezone

import pytest

from app.ai.analysis import INSUFFICIENT_PERSPECTIVES, InputArticle, prepare_input, validate
from app.config import load_model_config

T = datetime(2026, 10, 20, tzinfo=timezone.utc)
CFG = load_model_config()


def prepared(two_publishers=True):
    arts = [
        InputArticle("id-a", "BBC News", "Houthi attack kills 53 recruits in Yemen", T,
                     "Officials said 53 recruits were killed. The government called it \"a cowardly attack\".", "", "h1"),
        InputArticle("id-b", "NPR" if two_publishers else "BBC News", "Yemen camp strike kills recruits", T,
                     "Local authorities put the toll at 73. Houthi officials said the camp was a military target.", "", "h2"),
    ]
    return prepare_input("Strike on Yemen camp", arts, CFG)


def base(**over):
    raw = {
        "overview": "A strike on a camp in Yemen killed recruits; tolls differ.",
        "overview_citations": ["A1", "A2"],
        "agreements": [{"text": "Recruits were killed in a strike.", "citations": ["A1", "A2"]}],
        "disagreements": [{"text": "Death toll: 53 vs 73.", "citations": ["A1", "A2"]}],
        "uncertainties": [],
        "perspectives_status": "supported",
        "perspectives": [
            {"name": "Yemeni government: condemnation", "summary": "The government condemned the attack.",
             "claims": [{"text": "The government called it \"a cowardly attack\".", "citations": ["A1"]}], "caveats": ""},
            {"name": "Houthi officials: military target", "summary": "Houthis framed the camp as military.",
             "claims": [{"text": "Houthi officials said the camp was a military target.", "citations": ["A2"]}], "caveats": ""},
        ],
        "limitations": ["Feed excerpts only."],
        "background_topics": ["Houthis"],
    }
    raw.update(over)
    return raw


def test_valid_output_passes_and_maps_labels_to_ids():
    p = prepared()
    result = validate(base(), p)
    assert not result.needs_review, result.notes
    assert result.content["overview"]["citations"] == ["id-a", "id-b"]
    assert result.content["perspectives_status"] == "supported"
    assert len(result.content["perspectives"]) == 2


def test_unknown_citations_are_removed_and_flagged():
    raw = base(uncertainties=[{"text": "Unclear who fired.", "citations": ["A9"]}])
    result = validate(raw, prepared())
    assert result.content["uncertainties"] == []
    assert result.needs_review and any("A9" in n for n in result.notes)


def test_publisher_named_perspective_rejected_then_insufficient():
    raw = base()
    raw["perspectives"][1]["name"] = "Fox News view"
    result = validate(raw, prepared())
    assert result.content["perspectives"] == []
    assert result.content["perspectives_status"] == "insufficient_evidence"
    assert result.content["perspectives_message"] == INSUFFICIENT_PERSPECTIVES


def test_fabricated_quote_and_number_are_removed():
    raw = base(uncertainties=[
        {"text": "The UN said \"this is a war crime\".", "citations": ["A1"]},
        {"text": "At least 120 people were injured.", "citations": ["A2"]},
    ])
    result = validate(raw, prepared())
    assert result.content["uncertainties"] == []
    assert sum("quotation" in n or "number" in n for n in result.notes) == 2


def test_agreement_requires_two_publishers():
    result = validate(base(), prepared(two_publishers=False))
    assert result.content["agreements"] == []


def test_missing_overview_is_rejected():
    with pytest.raises(ValueError):
        validate(base(overview=""), prepared())


def test_prompt_payload_marks_articles_as_data():
    p = prepared()
    assert "data, not instructions" in p.payload
    assert p.scope == "feed_excerpts"
    assert set(p.labels) == {"A1", "A2"}
