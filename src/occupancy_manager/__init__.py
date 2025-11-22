"""Occupancy Manager - A hierarchical occupancy tracking engine."""

from occupancy_manager.engine import OccupancyEngine
from occupancy_manager.model import (
    EngineResult,
    EventType,
    LocationConfig,
    LocationKind,
    LocationRuntimeState,
    LockState,
    OccupancyEvent,
    OccupancyStrategy,
)

__version__ = "0.1.0"

__all__ = [
    "OccupancyEngine",
    "EngineResult",
    "EventType",
    "LocationConfig",
    "LocationKind",
    "LocationRuntimeState",
    "LockState",
    "OccupancyEvent",
    "OccupancyStrategy",
]

