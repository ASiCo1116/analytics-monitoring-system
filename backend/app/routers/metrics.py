from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.deps import DbSession, require_roles
from app.models import Role
from app.schemas.common import Page
from app.schemas.metric import MetricListParams, MetricRead
from app.services import metric_service

# Admin only for now; opening it to other roles means changing this line
router = APIRouter(
    prefix="/metrics",
    tags=["metrics"],
    dependencies=[Depends(require_roles(Role.admin))],
)


@router.get("", response_model=Page[MetricRead])
async def list_metrics(
    params: Annotated[MetricListParams, Query()], db: DbSession
) -> Page[MetricRead]:
    """History of the stored realtime metrics, newest first."""
    metrics, total = await metric_service.list_metrics(db, params)
    return Page[MetricRead](
        items=[MetricRead.model_validate(m) for m in metrics],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )
