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

    MOTION = "motion"  # Pulse event - resets timer
    HOLD_START = "hold_start"  # Hold event - pauses timer
    HOLD_END = "hold_end"  # Hold release - starts trailing timer
    MANUAL = "manual"  # Manual override
    LOCK_CHANGE = "lock_change"  # Lock state change
    PROPAGATED = "propagated"  # Synthetic event for propagation


class LockState(Enum):
    """Lock state for a location."""

    UNLOCKED = "unlocked"
    LOCKED_FROZEN = "locked_frozen"


class OccupancyStrategy(Enum):
    """Occupancy strategy for a location."""

    INDEPENDENT = "independent"  # Occupied only by own sensors or child propagation
    FOLLOW_PARENT = "follow_parent"  # Occupied if own sensors trigger OR if Parent is Occupied


@dataclass(frozen=True)
class LocationConfig:
    """Configuration for a location.

    Attributes:
        id: Unique identifier for the location.
        parent_id: Optional parent location ID for hierarchy.
        kind: Type of location (AREA or VIRTUAL).
        occupancy_strategy: Strategy for determining occupancy.
        contributes_to_parent: If False, occupancy does not bubble up to parent.
        timeouts: Dictionary mapping event categories to timeout minutes.
            For Hold sources, this is the trailing timeout (fudge factor).
    """

    id: str
    parent_id: Optional[str] = None
    kind: LocationKind = LocationKind.AREA
    occupancy_strategy: OccupancyStrategy = OccupancyStrategy.INDEPENDENT
    contributes_to_parent: bool = True
    timeouts: dict[str, int] = field(
        default_factory=lambda: {
            "motion": 10,
            "presence": 2,
            "media": 5,
        }
    )


@dataclass(frozen=True)
class LocationRuntimeState:
    """Runtime state for a location.

    This is immutable (frozen) to support functional updates.

    Attributes:
        is_occupied: Whether the location is currently occupied.
        occupied_until: When the location's occupancy expires (if occupied).
            Ignored if active_holds is non-empty.
        active_occupants: Set of occupant IDs currently in this location.
        active_holds: Set of source IDs currently holding the room open.
        lock_state: Current lock state of the location.
    """

    is_occupied: bool = False
    occupied_until: Optional[datetime] = None
    active_occupants: Set[str] = field(default_factory=set)
    active_holds: Set[str] = field(default_factory=set)
    lock_state: LockState = LockState.UNLOCKED


@dataclass(frozen=True)
class OccupancyEvent:
    """An occupancy event.

    Attributes:
        location_id: The location where the event occurred.
        event_type: Type of event (MOTION, HOLD_START, HOLD_END, MANUAL,
            LOCK_CHANGE, PROPAGATED).
        category: The config key to lookup timeout (e.g., "motion", "presence").
        source_id: Unique ID of the device (e.g., "binary_sensor.radar").
        timestamp: When the event occurred.
        occupant_id: Optional identifier for the occupant.
        duration: Optional override duration (e.g., for "Sauna=60m" scenarios).
    """

    location_id: str
    event_type: EventType
    category: str
    source_id: str
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

