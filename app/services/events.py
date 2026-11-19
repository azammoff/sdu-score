from app.enums import EventType, MatchStatus
from app.errors import BusinessRuleError, ConflictError, NotFoundError
from app.schemas.match import EventCreate
from app.services.common import get_or_404
from app.services.matches import get_match, recompute_score
from app.services.players import full_name


def list_events(store, match_id: int, type: EventType | None = None):
    get_match(store, match_id)
    events = store.events.where(match_id=match_id)
    if type:
        events = [e for e in events if e.type == type]
    return sorted(events, key=lambda e: (e.minute, e.id))


def _is_sent_off(store, match_id: int, player_id: int) -> bool:
    return bool(store.events.where(match_id=match_id, player_id=player_id, type=EventType.RED_CARD))


def _player_in_match(store, match, player_id: int, role: str):
    player = get_or_404(store.players, player_id, role)
    if player.team_id not in (match.home_team_id, match.away_team_id):
        raise BusinessRuleError(f"{full_name(player)} does not play for either team in this match")
    if _is_sent_off(store, match.id, player.id):
        raise BusinessRuleError(f"{full_name(player)} has been sent off and cannot take part any more")
    return player


def record_event(store, match_id: int, data: EventCreate) -> dict:
    match = get_match(store, match_id)
    if match.status != MatchStatus.LIVE:
        raise ConflictError(f"Events can only be recorded during a live match; this one is {match.status}")

    player = _player_in_match(store, match, data.player_id, "Player")
    if data.assist_player_id is not None:
        assister = _player_in_match(store, match, data.assist_player_id, "Assisting player")
        if assister.team_id != player.team_id:
            raise BusinessRuleError("The assisting player must be on the scorer's team")

    auto_events = []
    already_booked = store.events.where(match_id=match_id, player_id=player.id, type=EventType.YELLOW_CARD)
    event = store.events.add(
        match_id=match_id,
        type=data.type,
        minute=data.minute,
        player_id=player.id,
        team_id=player.team_id,
        assist_player_id=data.assist_player_id,
        is_auto=False,
    )
    if data.type == EventType.YELLOW_CARD and already_booked:
        # Second yellow card in the same match means a red card.
        auto_events.append(
            store.events.add(
                match_id=match_id,
                type=EventType.RED_CARD,
                minute=data.minute,
                player_id=player.id,
                team_id=player.team_id,
                assist_player_id=None,
                is_auto=True,
            )
        )
    recompute_score(store, match)
    store.commit()
    return {"event": event, "auto_events": auto_events, "score": {"home": match.home_score, "away": match.away_score}}


def delete_event(store, match_id: int, event_id: int) -> None:
    """Correct a mistake made during a live match. Finished matches are locked."""
    match = get_match(store, match_id)
    event = store.events.get(event_id)
    if event is None or event.match_id != match_id:
        raise NotFoundError(f"Event with id {event_id} not found in match {match_id}")
    if match.status != MatchStatus.LIVE:
        raise ConflictError(f"Events can only be corrected while the match is live; this one is {match.status}")
    if event.is_auto:
        raise BusinessRuleError("This red card was added for a second yellow; delete the yellow card instead")

    if event.type == EventType.YELLOW_CARD:
        for auto_red in store.events.where(match_id=match_id, player_id=event.player_id, is_auto=True):
            store.events.delete(auto_red)
    store.events.delete(event)
    recompute_score(store, match)
    store.commit()
