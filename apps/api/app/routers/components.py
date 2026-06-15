from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AppError
from app.core.pagination import PageParams, page_params
from app.schemas.generated import Component, PaginatedComponent
from app.services import component_service

router = APIRouter()


@router.get("", response_model=PaginatedComponent)
async def list_components(
    page_params: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_db),
) -> PaginatedComponent:
    """Public, paginated. No filters."""
    rows, total = await component_service.list_components(db, page_params)
    return PaginatedComponent(
        data=[Component.model_validate(row, from_attributes=True) for row in rows],
        total=total,
        page=page_params.page,
        page_size=page_params.page_size,
    )


@router.get("/{component_id}", response_model=Component)
async def get_component(
    component_id: int,
    db: AsyncSession = Depends(get_db),
) -> Component:
    """Public. Returns a single component."""
    row = await component_service.get_component(db, component_id)
    if row is None:
        raise AppError(404, "not_found", f"Component '{component_id}' not found")
    return Component.model_validate(row, from_attributes=True)
