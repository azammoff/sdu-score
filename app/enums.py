from enum import StrEnum


class Position(StrEnum):
    GOALKEEPER = "GK"
    DEFENDER = "DF"
    MIDFIELDER = "MF"
    FORWARD = "FW"


class TournamentStatus(StrEnum):
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    FINISHED = "finished"


class MatchStatus(StrEnum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class EventType(StrEnum):
    GOAL = "goal"
    OWN_GOAL = "own_goal"
    YELLOW_CARD = "yellow_card"
    RED_CARD = "red_card"
