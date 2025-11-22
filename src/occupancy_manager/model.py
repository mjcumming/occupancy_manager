"""Data models for the occupancy manager library.

This module defines the core data structures used throughout the library.
All state classes are frozen (immutable) to support functional programming.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Set


class LocationKind(Enum):
    """Type of location."""

    AREA = "area"
    VIRTUAL = "virtual"


class EventType(Enum):
    """Type of occupancy event."""

    MOTION = "motion"
    DOOR = "door"
    MEDIA = "media"
    PRESENCE = "presence"
    MANUAL = "manual"
    LOCK_CHANGE = "lock_change"
    PROPAGATED = "propagated"


class LockState(Enum):
    """Lock state for a location."""

    UNLOCKED = "unlocked"
    LOCKED_FROZEN = "locked_frozen"


@dataclass(frozen=True)
class LocationConfig:
    """Configuration for a location.

    Attributes:
        id: Unique identifier for the location.
        parent_id: Optional parent location ID for hierarchy.
        kind: Type of location (AREA or VIRTUAL).
        timeouts: Dictionary mapping event types to timeout durations.
    """

    id: str
    parent_id: Optional[str] = None
    kind: LocationKind = LocationKind.AREA
    timeouts: dict[EventType, timedelta] = field(
        default_factory=lambda: {
            EventType.MOTION: timedelta(minutes=10),
            EventType.DOOR: timedelta(minutes=5),
        }
    )


@dataclass(frozen=True)
class LocationRuntimeState:
    """Runtime state for a location.

    This is immutable (frozen) to support functional updates.

    Attributes:
        is_occupied: Whether the location is currently occupied.
        occupied_until: When the location's occupancy expires (if occupied).
        active_occupants: Set of occupant IDs currently in this location.
        lock_state: Current lock state of the location.
    """

    is_occupied: bool = False
    occupied_until: Optional[datetime] = None
    active_occupants: Set[str] = field(default_factory=set)
    lock_state: LockState = LockState.UNLOCKED


@dataclass(frozen=True)
class OccupancyEvent:
    """An occupancy event.

    Attributes:
        location_id: The location where the event occurred.
        event_type: Type of event (MOTION, DOOR, MEDIA, PRESENCE, MANUAL,
            LOCK_CHANGE, PROPAGATED).
        timestamp: When the event occurred.
        occupant_id: Optional identifier for the occupant.
        duration: Optional override duration (e.g., for "Sauna=60m" scenarios).
        force_state: Optional force state (True=Occupied, False=Vacant, None=Calculate).
    """

    location_id: str
    event_type: EventType
    timestamp: datetime
    occupant_id: Optional[str] = None
    duration: Optional[timedelta] = None
    force_state: Optional[bool] = None


@dataclass(frozen=True)
class EngineResult:
    """Result from engine operations.

    Attributes:
        next_expiration: Next datetime when a timeout check is needed.
        transitions: List of location state transitions that occurred.
    """

    next_expiration: Optional[datetime]
    transitions: list[tuple[str, LocationRuntimeState]] = field(default_factory=list)

