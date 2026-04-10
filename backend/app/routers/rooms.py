"""
Rooms router — top-level physical spaces that contain cabinets.
Only admins can create/edit/delete rooms. All authenticated users can view.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_manage_users
from app.dependencies import get_current_user, get_db
from app.models.cabinet import Cabinet
from app.models.room import Room
from app.models.user import User
from app.schemas.room import RoomCreate, RoomDetail, RoomOut, RoomUpdate
from app.services.inventory_service import get_cabinets_with_counts

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("", response_model=list[RoomDetail])
async def list_rooms(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[RoomDetail]:
    """List all rooms with cabinet counts."""
    # Count cabinets per room
    cab_sq = (
        select(Cabinet.room_id, func.count(Cabinet.id).label("cabinet_count"))
        .group_by(Cabinet.room_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(Room, func.coalesce(cab_sq.c.cabinet_count, 0).label("cabinet_count"))
            .outerjoin(cab_sq, cab_sq.c.room_id == Room.id)
            .order_by(Room.name)
        )
    ).all()

    return [
        RoomDetail(
            id=room.id,
            name=room.name,
            description=room.description,
            created_at=room.created_at,
            updated_at=room.updated_at,
            cabinet_count=int(cabinet_count),
        )
        for room, cabinet_count in rows
    ]


@router.post("", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
async def create_room(
    body: RoomCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Room:
    require_manage_users(current_user)  # Admin-only
    room = Room(**body.model_dump())
    db.add(room)
    await db.commit()
    await db.refresh(room)
    return room


@router.get("/{room_id}", response_model=RoomDetail)
async def get_room(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> RoomDetail:
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Room not found")

    count_result = await db.execute(
        select(func.count()).where(Cabinet.room_id == room_id)
    )
    cabinet_count = count_result.scalar() or 0

    return RoomDetail(
        id=room.id,
        name=room.name,
        description=room.description,
        created_at=room.created_at,
        updated_at=room.updated_at,
        cabinet_count=cabinet_count,
    )


@router.patch("/{room_id}", response_model=RoomOut)
async def update_room(
    room_id: int,
    body: RoomUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Room:
    require_manage_users(current_user)  # Admin-only
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Room not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(room, field, value)

    await db.commit()
    await db.refresh(room)
    return room


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    require_manage_users(current_user)  # Admin-only
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Room not found")

    # Check if room has cabinets
    cab_count = (await db.execute(
        select(func.count()).where(Cabinet.room_id == room_id)
    )).scalar()
    if cab_count and cab_count > 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot delete room with {cab_count} cabinet(s). Move or delete cabinets first."
        )

    await db.delete(room)
    await db.commit()
