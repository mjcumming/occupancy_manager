"""Data models for the occupancy manager library.

This module defines the core data structures used throughout the library.
All state classes are frozen (immutable) to support functional programming.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class LocationKind(Enum):
    """Type of location."""

    AREA = "area"
    VIRTUAL = "virtual"


class EventType(Enum):
    """The mechanical behavior of an occupancy event."""

    MOMENTARY = "momentary"  # Transient signal (Motion, Door Trip) -> Resets timer
    HOLD_START = "hold_start"  # Continuous start (Radar, Media Start) -> Pauses timer
    HOLD_END = "hold_end"  # Continuous end (Radar, Media Stop) -> Starts trailing timer
    MANUAL = "manual"  # Direct override
    LOCK_CHANGE = "lock_change"
    PROPAGATED = "propagated"  # Internal bubble-up


class LockState(Enum):
    """Lock state for a location."""

    UNLOCKED = "unlocked"
    LOCKED_FROZEN = "locked_frozen"


class OccupancyStrategy(Enum):
    """Occupancy strategy for a location."""

    INDEPENDENT = "independent"
    FOLLOW_PARENT = "follow_parent"


@dataclass(frozen=True)
class LocationConfig:
    """Configuration for a location.

    Attributes:
        id: Unique identifier.
        parent_id: Optional container location ID.
        kind: Type of location.
        occupancy_strategy: Strategy logic.
        contributes_to_parent: If False, occupancy stops here.
        timeouts: Dictionary mapping 'category' strings to minutes.
            e.g. { "motion": 10, "door": 2, "my_custom_sensor": 5 }
    """

    id: str
    parent_id: Optional[str] = None
    kind: LocationKind = LocationKind.AREA
    occupancy_strategy: OccupancyStrategy = OccupancyStrategy.INDEPENDENT
    contributes_to_parent: bool = True

    # Defaults are just data examples now, not hardcoded logic
    timeouts: dict[str, int] = field(
        default_factory=lambda: {
            "default": 10,
            "motion": 10,
            "presence": 5,
        }
    )


@dataclass(frozen=True)
class LocationRuntimeState:
    """Runtime state for a location (Immutable)."""

    is_occupied: bool = False
    occupied_until: Optional[datetime] = None
    active_occupants: set[str] = field(default_factory=set)
    active_holds: set[str] = field(default_factory=set)
    lock_state: LockState = LockState.UNLOCKED


@dataclass(frozen=True)
class OccupancyEvent:
    """An occupancy event.

    Attributes:
        location_id: Target location.
        event_type: The mechanic (MOMENTARY vs HOLD).
        category: The config key for looking up timeout (e.g. "motion").
        source_id: Unique device ID (e.g. "binary_sensor.kitchen_pir").
        timestamp: When it happened.
        occupant_id: Optional identity.
        duration: Optional override duration.
    """

    location_id: str
    event_type: EventType
    category: str
    source_id: str
    timestamp: datetime
    occupant_id: Optional[str] = None
    duration: Optional[timedelta] = None


@dataclass(frozen=True)
class StateTransition:
    """A record of a state change for debugging."""

    location_id: str
    previous_state: LocationRuntimeState
    new_state: LocationRuntimeState
    reason: str


@dataclass(frozen=True)
class EngineResult:
    """Instructions for the Host Application."""

    next_expiration: Optional[datetime]
    transitions: list[StateTransition] = field(default_factory=list)
