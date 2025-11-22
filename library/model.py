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
        timeout: Base timeout duration for this location.
    """

    id: str
    parent_id: Optional[str] = None
    kind: LocationKind = LocationKind.AREA
    timeout: timedelta = field(default_factory=lambda: timedelta(minutes=5))


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
        event_type: Type of event (MOTION, DOOR, MEDIA, PRESENCE, MANUAL).
        timestamp: When the event occurred.
        occupant_id: Optional identifier for the occupant.
        duration: Optional override duration (e.g., for "Sauna=60m" scenarios).
    """

    location_id: str
    event_type: EventType
    timestamp: datetime
    occupant_id: Optional[str] = None
    duration: Optional[timedelta] = None


@dataclass(frozen=True)
class EngineResult:
    """Result from engine operations.

    Attributes:
        next_expiration: Next datetime when a timeout check is needed.
        transitions: List of location state transitions that occurred.
    """

    next_expiration: Optional[datetime]
    transitions: list[tuple[str, LocationRuntimeState]] = field(default_factory=list)

