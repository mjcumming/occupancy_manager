"""Real-world test script for occupancy manager."""

from datetime import datetime, timedelta

from occupancy_manager.model import (
    EventType,
    LocationConfig,
    LocationKind,
    OccupancyEvent,
)
from occupancy_manager.engine import OccupancyEngine


# 1. Setup Config
kitchen = LocationConfig(id="kitchen", kind=LocationKind.AREA)
engine = OccupancyEngine([kitchen])

now = datetime.now()

# 2. Create Event (Motion in Kitchen) with 5-second timeout
event = OccupancyEvent(
    location_id="kitchen",
    event_type=EventType.MOMENTARY,
    category="motion",
    source_id="binary_sensor.kitchen_motion",
    timestamp=now,
    duration=timedelta(seconds=5),  # 5-second timeout instead of default 10 minutes
)

# 3. Run Engine
result = engine.handle_event(event, now)

# 4. Check Result
if result.transitions:
    print(f"Initial state: {result.transitions[0].previous_state.is_occupied}")
    print(f"New state: {result.transitions[0].new_state.is_occupied}")  # Should be True
print(f"Current time: {now}")
print(f"Expires at: {result.next_expiration}")  # Should be Now + 5 seconds
if result.next_expiration:
    timeout_duration = result.next_expiration - now
    print(f"Timeout duration: {timeout_duration.total_seconds():.2f} seconds")

