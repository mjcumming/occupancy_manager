"""Occupancy Manager - A hierarchical occupancy tracking engine."""

from occupancy_manager.model import (
    EngineResult,
    EventType,
    LocationConfig,
    LocationKind,
    LocationRuntimeState,
    LockState,
    OccupancyEvent,
)

__version__ = "0.1.0"

__all__ = [
    "EngineResult",
    "EventType",
    "LocationConfig",
    "LocationKind",
    "LocationRuntimeState",
    "LockState",
    "OccupancyEvent",
]

