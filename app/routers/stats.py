from fastapi import APIRouter, Depends, Query

from app.deps import get_store
from app.schemas.tournament import TopScorerRow
from app.services import stats as stats_service

router = APIRouter(prefix="/stats", tags=["Statistics"])


@router.get("/top-scorers", response_model=list[TopScorerRow], summary="Top scorers across tournaments")
def get_top_scorers(
    tournament_id: int | None = Query(None, gt=0, description="Leave empty for all-time"),
    team_id: int | None = Query(None, gt=0),
    limit: int = Query(20, ge=1, le=100),
    store=Depends(get_store),
):
    return stats_service.top_scorers(store, tournament_id, limit, team_id=team_id)
