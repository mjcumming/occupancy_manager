# Occupancy Manager

[![CI](https://github.com/mjcumming/occupancy_manager/actions/workflows/ci.yml/badge.svg)](https://github.com/mjcumming/occupancy_manager/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/occupancy-manager.svg)](https://badge.fury.io/py/occupancy-manager)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

A hierarchical occupancy tracking engine with locking and identity logic.

## Overview

Occupancy Manager is a pure Python library for managing hierarchical occupancy state. It accepts events from sensors, calculates the state of logical "Locations" (Rooms, Floors, Zones), and maintains a hierarchy where occupancy bubbles up from child to parent locations.

## Features

- **Hierarchical Location Tracking**: Support for parent-child location relationships with upward propagation
- **Identity Management**: Track active occupants across locations with individual arrival/departure handling
- **Locking Logic**: Freeze location state when needed (party mode)
- **Multiple Occupancy Strategies**: Independent locations or locations that follow parent state
- **Time-Agnostic**: All time operations accept `now` as an argument (no system clock access)
- **State Persistence**: Export and restore state with automatic stale data cleanup
- **Pure Python**: No external dependencies, standard library only
- **Event Types**: Support for momentary events (motion), holds (presence/radar), and manual overrides

## Installation

```bash
pip install occupancy-manager
```

## Quick Start

```python
from datetime import datetime, timedelta
from occupancy_manager import (
    LocationConfig,
    LocationKind,
    OccupancyEvent,
    EventType,
    OccupancyEngine,
)

# Create location configuration
kitchen = LocationConfig(
    id="kitchen",
    kind=LocationKind.AREA,
    timeouts={"motion": 10, "presence": 5}
)

# Initialize engine with list of configs
engine = OccupancyEngine([kitchen])

# Create an event
now = datetime.now()
event = OccupancyEvent(
    location_id="kitchen",
    event_type=EventType.MOMENTARY,
    category="motion",
    source_id="binary_sensor.kitchen_motion",
    timestamp=now,
)

# Process event
result = engine.handle_event(event, now)

# Check for transitions
for transition in result.transitions:
    print(f"{transition.location_id}: {'occupied' if transition.new_state.is_occupied else 'vacant'}")
    print(f"  Occupants: {transition.new_state.active_occupants}")
    print(f"  Expires at: {transition.new_state.occupied_until}")

# Check when next timeout check is needed
if result.next_expiration:
    print(f"Next timeout check: {result.next_expiration}")
```

## Identity Tracking Example

```python
from datetime import datetime
from occupancy_manager import (
    LocationConfig,
    LocationKind,
    OccupancyEvent,
    EventType,
    OccupancyEngine,
)

# Setup
kitchen = LocationConfig(id="kitchen", kind=LocationKind.AREA)
engine = OccupancyEngine([kitchen])
now = datetime.now()

# Mike arrives (Bluetooth presence start)
event = OccupancyEvent(
    location_id="kitchen",
    event_type=EventType.HOLD_START,
    category="presence",
    source_id="ble_mike",
    timestamp=now,
    occupant_id="Mike",
)
result = engine.handle_event(event, now)
print(f"Occupants: {engine.state['kitchen'].active_occupants}")  # {'Mike'}

# Marla arrives
event = OccupancyEvent(
    location_id="kitchen",
    event_type=EventType.HOLD_START,
    category="presence",
    source_id="ble_marla",
    timestamp=now,
    occupant_id="Marla",
)
result = engine.handle_event(event, now)
print(f"Occupants: {engine.state['kitchen'].active_occupants}")  # {'Mike', 'Marla'}

# Mike leaves (Bluetooth presence end)
event = OccupancyEvent(
    location_id="kitchen",
    event_type=EventType.HOLD_END,
    category="presence",
    source_id="ble_mike",
    timestamp=now,
    occupant_id="Mike",
)
result = engine.handle_event(event, now)
print(f"Occupants: {engine.state['kitchen'].active_occupants}")  # {'Marla'}
print(f"Still occupied: {engine.state['kitchen'].is_occupied}")  # True
```

## State Persistence

The library supports saving and restoring state for persistence across restarts:

```python
from datetime import datetime
import json
from occupancy_manager import LocationConfig, LocationKind, OccupancyEngine

# Setup
kitchen = LocationConfig(id="kitchen", kind=LocationKind.AREA)
engine = OccupancyEngine([kitchen])
now = datetime.now()

# ... process events ...

# Export state (JSON-serializable)
snapshot = engine.export_state()

# Save to disk (in your integration)
with open("state.json", "w") as f:
    json.dump(snapshot, f)

# On restart, restore state
with open("state.json", "r") as f:
    snapshot = json.load(f)

# Restore with stale data protection
# Expired timers are automatically cleared
engine2 = OccupancyEngine([kitchen])
engine2.restore_state(snapshot, datetime.now())

# Locked states and active occupants/holds are preserved
# Expired timers force vacancy automatically
```

## Development

This project uses:
- Python 3.11+
- `ruff` for linting and formatting
- `mypy` for type checking (strict mode)
- `pytest` for testing

### Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in editable mode
pip install -e .

# Install development dependencies
pip install -e ".[dev]"
```

### Running Tests

```bash
pytest
```

### Running Linters

```bash
ruff check .
ruff format .
mypy src/
```

## License

MIT License

