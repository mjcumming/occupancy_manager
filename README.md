# Occupancy Manager

A hierarchical occupancy tracking engine with locking and identity logic.

## Overview

Occupancy Manager is a pure Python library for managing hierarchical occupancy state. It accepts events from sensors, calculates the state of logical "Locations" (Rooms, Floors, Zones), and maintains a hierarchy where occupancy bubbles up from child to parent locations.

## Features

- **Hierarchical Location Tracking**: Support for parent-child location relationships
- **Identity Management**: Track active occupants across locations
- **Locking Logic**: Freeze location state when needed
- **Time-Agnostic**: All time operations accept `now` as an argument (no system clock access)
- **Pure Python**: No external dependencies, standard library only

## Installation

```bash
pip install occupancy-manager
```

## Quick Start

```python
from datetime import datetime, timedelta
from occupancy_manager import (
    LocationConfig,
    LocationRuntimeState,
    OccupancyEvent,
    EventType,
    OccupancyEngine,
)

# Create location configuration
kitchen = LocationConfig(
    id="kitchen",
    timeouts={EventType.MOTION: timedelta(minutes=10)}
)

# Initialize engine
engine = OccupancyEngine(configs={"kitchen": kitchen})

# Create an event
now = datetime.now()
event = OccupancyEvent(
    location_id="kitchen",
    event_type=EventType.MOTION,
    timestamp=now,
)

# Process event
states = {"kitchen": LocationRuntimeState()}
result = engine.handle_event(event, now, states)

# Check for transitions
for location_id, new_state in result.transitions:
    print(f"{location_id}: {'occupied' if new_state.is_occupied else 'vacant'}")
```

## Development

This project uses:
- Python 3.11+
- `ruff` for formatting
- `mypy` for type checking
- `pytest` for testing

## License

MIT License

