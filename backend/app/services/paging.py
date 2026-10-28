"""Pagination shared by the list queries."""

from sqlalchemy import Select

from app.schemas.common import PageParams


def page_of(query: Select, params: PageParams) -> Select:
    """Restrict an ordered query to the requested page."""
    return query.offset(params.offset).limit(params.page_size)
