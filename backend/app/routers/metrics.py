from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.deps import DbSession, require_admin
from app.schemas.common import Page
from app.schemas.metric import MetricListParams, MetricRead
from app.services import metric_service

# Admin only for now; opening it to other roles means changing this line
router = APIRouter(
    prefix="/metrics",
    tags=["metrics"],
    dependencies=[Depends(require_admin)],
)


@router.get("", response_model=Page[MetricRead])
async def list_metrics(
    params: Annotated[MetricListParams, Query()], db: DbSession
) -> Page[MetricRead]:
    """History of the stored realtime metrics, newest first."""
    metrics, total = await metric_service.list_metrics(db, params)
    return Page[MetricRead].of(metrics, total, params)
