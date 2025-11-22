"""Tests for data model v2.0 structures."""

from datetime import datetime, timedelta

import pytest

from occupancy_manager.model import (
    EngineResult,
    EventType,
    LocationConfig,
    LocationKind,
    LocationRuntimeState,
    LockState,
    OccupancyEvent,
)


def test_location_config_v2_timeouts():
    """Test LocationConfig with v2.0 string-based timeouts."""
    config = LocationConfig(
        id="kitchen",
        timeouts={"motion": 10, "presence": 2, "media": 5},
    )
    assert config.timeouts["motion"] == 10
    assert config.timeouts["presence"] == 2
    assert isinstance(config.timeouts["motion"], int)


def test_location_runtime_state_with_holds():
    """Test LocationRuntimeState with active_holds."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    state = LocationRuntimeState(
        is_occupied=True,
        occupied_until=None,
        active_holds={"binary_sensor.mmwave", "media_player.tv"},
        active_occupants={"person.mike"},
    )
    assert len(state.active_holds) == 2
    assert "binary_sensor.mmwave" in state.active_holds
    assert "media_player.tv" in state.active_holds


def test_occupancy_event_v2_required_fields():
    """Test OccupancyEvent v2.0 with required category and source_id."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.MOTION,
        category="motion",
        source_id="binary_sensor.motion",
        timestamp=now,
    )
    assert event.category == "motion"
    assert event.source_id == "binary_sensor.motion"
    assert event.location_id == "kitchen"


def test_occupancy_event_hold_start():
    """Test OccupancyEvent with HOLD_START."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.HOLD_START,
        category="presence",
        source_id="binary_sensor.mmwave",
        timestamp=now,
    )
    assert event.event_type == EventType.HOLD_START
    assert event.category == "presence"


def test_occupancy_event_hold_end():
    """Test OccupancyEvent with HOLD_END."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.HOLD_END,
        category="media",
        source_id="media_player.tv",
        timestamp=now,
    )
    assert event.event_type == EventType.HOLD_END
    assert event.category == "media"


def test_event_type_enum_v2():
    """Test EventType enum includes v2.0 types."""
    assert EventType.MOTION in EventType
    assert EventType.HOLD_START in EventType
    assert EventType.HOLD_END in EventType
    assert EventType.MANUAL in EventType
    assert EventType.LOCK_CHANGE in EventType
    assert EventType.PROPAGATED in EventType

