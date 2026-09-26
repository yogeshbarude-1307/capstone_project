from dsfs.extraction.entity_resolution import resolve_entities


def test_known_single_mention_resolves_to_forecast_key():
    resolved, forecast_key = resolve_entities(["CUST-0001"], {"CUST-0001", "CUST-0002"})
    assert resolved == ["CUST-0001"]
    assert forecast_key == "CUST-0001"


def test_unknown_mention_is_left_unresolved_not_guessed():
    resolved, forecast_key = resolve_entities(["Acme Corp"], {"CUST-0001"})
    assert resolved == []
    assert forecast_key is None


def test_multiple_resolved_mentions_yield_no_single_forecast_key():
    """Ambiguity must not collapse to a guessed single entity."""
    resolved, forecast_key = resolve_entities(["CUST-0001", "CUST-0002"], {"CUST-0001", "CUST-0002"})
    assert set(resolved) == {"CUST-0001", "CUST-0002"}
    assert forecast_key is None


def test_empty_mentions_resolve_to_nothing():
    resolved, forecast_key = resolve_entities([], {"CUST-0001"})
    assert resolved == []
    assert forecast_key is None
