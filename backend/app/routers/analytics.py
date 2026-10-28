from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.deps import DbSession, get_current_user
from app.schemas.analytics import (
    AnalyticsParams,
    GroupStats,
    Stats,
    TrendParams,
    TrendPoint,
)
from app.services import analytics_service, excel_service
from app.services.excel_service import XLSX_MEDIA_TYPE

# Every logged-in role may analyse both sources
router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/summary", response_model=Stats)
async def summary(
    params: Annotated[AnalyticsParams, Query()], db: DbSession
) -> Stats:
    """count, sum, avg, max and min of the filtered values.

    source=metrics needs `metric` and defaults to the last 24 hours.
    """
    return await analytics_service.summary(db, params)


@router.get("/groups", response_model=list[GroupStats])
async def groups(
    params: Annotated[AnalyticsParams, Query()], db: DbSession
) -> list[GroupStats]:
    """The same statistics per category (records) or server (metrics)."""
    return await analytics_service.groups(db, params)


@router.get("/trend", response_model=list[TrendPoint])
async def trend(
    params: Annotated[TrendParams, Query()], db: DbSession
) -> list[TrendPoint]:
    """Statistics per minute, hour or day, in APP_TIMEZONE intervals."""
    return await analytics_service.trend(db, params, params.interval)


@router.get(
    "/export",
    response_class=Response,
    responses={
        200: {
            "content": {XLSX_MEDIA_TYPE: {}},
            "description": "Sheets: 摘要, 分組聚合, 趨勢（依小時）, 明細",
        }
    },
)
async def export(
    params: Annotated[AnalyticsParams, Query()], db: DbSession
) -> Response:
    """Download the analytics for these filters as an Excel file.

    The detail sheet holds the newest 10,000 rows at most; the summary
    sheet says so when rows were left out.
    """
    filename, content = await excel_service.build_export(db, params)
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
