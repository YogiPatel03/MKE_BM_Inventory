import decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.permissions import require_manage_inventory
from app.dependencies import get_current_user, get_db
from app.models.activity_log import ActivityType
from app.models.bin import Bin
from app.models.item import Item
from app.models.user import User
from app.schemas.item import ItemCreate, ItemOut, ItemUpdate
from app.services.activity_service import log_activity

router = APIRouter(prefix="/items", tags=["items"])


def _attach_bin_fields(item: Item) -> Item:
    bin_ = item.bin
    item.bin_label = bin_.label if bin_ else None
    item.bin_number = bin_.bin_number if bin_ else None
    return item


def _is_sku_unique_error(exc: IntegrityError) -> bool:
    message = str(exc.orig).lower()
    return any(
        token in message
        for token in (
            "ux_items_sku_lower",
            "items_sku_key",
            "items.sku",
        )
    )


@router.get("", response_model=list[ItemOut])
async def list_items(
    cabinet_id: int | None = None,
    bin_id: int | None = None,
    is_active: bool = True,
    search: str | None = None,
    skip: int = 0,
    limit: int = 500,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Item]:
    query = select(Item).options(selectinload(Item.bin)).where(Item.is_active == is_active)
    if cabinet_id:
        query = query.where(Item.cabinet_id == cabinet_id)
    if bin_id:
        query = query.where(Item.bin_id == bin_id)
    if search:
        term = f"%{search}%"
        query = query.outerjoin(Bin, Item.bin_id == Bin.id).where(
            or_(
                Item.name.ilike(term),
                Item.sku.ilike(term),
                Bin.label.ilike(term),
                Bin.bin_number.ilike(term),
            )
        )
    query = query.order_by(Item.name).offset(skip).limit(limit)
    result = await db.execute(query)
    return [_attach_bin_fields(item) for item in result.scalars().all()]


@router.post("", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
async def create_item(
    body: ItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Item:
    require_manage_inventory(current_user)
    if body.sku:
        duplicate = await db.execute(
            select(Item).where(func.lower(Item.sku) == body.sku.lower())
        )
        if duplicate.scalar_one_or_none():
            raise HTTPException(status.HTTP_409_CONFLICT, f"SKU '{body.sku}' already exists")

    item = Item(
        **body.model_dump(),
        quantity_available=body.quantity_total,
    )
    db.add(item)
    try:
        await db.flush()
        await db.refresh(item)

        await log_activity(
            db,
            activity_type=ActivityType.ITEM_CREATED,
            actor_id=current_user.id,
            target_item_id=item.id,
            target_cabinet_id=item.cabinet_id,
            quantity_delta=float(item.quantity_total),
            notes=f"Item created: {item.name}",
            metadata={"name": item.name, "quantity_total": item.quantity_total, "is_consumable": item.is_consumable},
            source_type="item",
            source_id=item.id,
        )

        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if _is_sku_unique_error(exc):
            raise HTTPException(status.HTTP_409_CONFLICT, f"SKU '{body.sku}' already exists") from exc
        raise
    result = await db.execute(
        select(Item).options(selectinload(Item.bin)).where(Item.id == item.id)
    )
    return _attach_bin_fields(result.scalar_one())


@router.get("/{item_id}", response_model=ItemOut)
async def get_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Item:
    result = await db.execute(select(Item).options(selectinload(Item.bin)).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    return _attach_bin_fields(item)


@router.patch("/{item_id}", response_model=ItemOut)
async def update_item(
    item_id: int,
    body: ItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Item:
    require_manage_inventory(current_user)
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")

    def _json_val(v):
        return float(v) if isinstance(v, decimal.Decimal) else v

    changes = body.model_dump(exclude_none=True)
    if "sku" in changes and changes["sku"]:
        duplicate = await db.execute(
            select(Item).where(
                func.lower(Item.sku) == changes["sku"].lower(),
                Item.id != item_id,
            )
        )
        if duplicate.scalar_one_or_none():
            raise HTTPException(status.HTTP_409_CONFLICT, f"SKU '{changes['sku']}' already exists")

    before = {k: _json_val(getattr(item, k)) for k in changes}
    was_active = item.is_active

    for field, value in changes.items():
        setattr(item, field, value)

    # Choose activity type based on is_active changes
    if "is_active" in changes:
        if changes["is_active"] and not was_active:
            activity_type = ActivityType.ITEM_REACTIVATED
        elif not changes["is_active"] and was_active:
            activity_type = ActivityType.ITEM_DEACTIVATED
        else:
            activity_type = ActivityType.ITEM_EDITED
    else:
        activity_type = ActivityType.ITEM_EDITED

    after = {k: _json_val(getattr(item, k)) for k in changes}

    await log_activity(
        db,
        activity_type=activity_type,
        actor_id=current_user.id,
        target_item_id=item.id,
        target_cabinet_id=item.cabinet_id,
        metadata={"before": before, "after": after},
        source_type="item",
        source_id=item.id,
    )

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if _is_sku_unique_error(exc):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"SKU '{changes.get('sku', item.sku)}' already exists",
            ) from exc
        raise
    result = await db.execute(
        select(Item).options(selectinload(Item.bin)).where(Item.id == item_id)
    )
    return _attach_bin_fields(result.scalar_one())


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Soft-delete: sets is_active=False rather than destroying the record."""
    require_manage_inventory(current_user)
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    item.is_active = False

    await log_activity(
        db,
        activity_type=ActivityType.ITEM_DEACTIVATED,
        actor_id=current_user.id,
        target_item_id=item.id,
        target_cabinet_id=item.cabinet_id,
        source_type="item",
        source_id=item.id,
    )

    await db.commit()
