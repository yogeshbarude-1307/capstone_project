"""Entity resolution: raw mentions -> resolved_entities / forecast_key.

For this POC, "master data" is simply the set of known canonical entity keys
(e.g. the entities the synthetic generator created). A mention not present
in that set is left unresolved rather than guessed -- an unresolved mention
must never silently attach to a wrong forecast entity (docs/07).
"""

from __future__ import annotations


def resolve_entities(mentions_raw: list[str], known_entities: set[str]) -> tuple[list[str], str | None]:
    resolved = list(dict.fromkeys(m for m in mentions_raw if m in known_entities))
    forecast_key = resolved[0] if len(resolved) == 1 else None
    return resolved, forecast_key
