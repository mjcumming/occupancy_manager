"""Tests for data model structures."""

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


def test_location_config_creation():
    """Test LocationConfig can be created with required fields."""
    config = LocationConfig(
        id="kitchen",
        parent_id=None,
        kind=LocationKind.AREA,
    )
    assert config.id == "kitchen"
    assert config.parent_id is None
    assert config.kind == LocationKind.AREA
    assert EventType.MOTION in config.timeouts


def test_location_config_with_parent():
    """Test LocationConfig with parent hierarchy."""
    config = LocationConfig(
        id="kitchen",
        parent_id="main_floor",
        kind=LocationKind.AREA,
    )
    assert config.parent_id == "main_floor"


def test_location_runtime_state_defaults():
    """Test LocationRuntimeState default values."""
    state = LocationRuntimeState()
    assert state.is_occupied is False
    assert state.occupied_until is None
    assert state.active_occupants == set()
    assert state.lock_state == LockState.UNLOCKED


def test_location_runtime_state_occupied():
    """Test LocationRuntimeState when occupied."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    state = LocationRuntimeState(
        is_occupied=True,
        occupied_until=now + timedelta(minutes=10),
        active_occupants={"person.mike"},
    )
    assert state.is_occupied is True
    assert state.occupied_until == now + timedelta(minutes=10)
    assert "person.mike" in state.active_occupants


def test_occupancy_event_creation():
    """Test OccupancyEvent can be created."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.MOTION,
        timestamp=now,
    )
    assert event.location_id == "kitchen"
    assert event.event_type == EventType.MOTION
    assert event.timestamp == now
    assert event.occupant_id is None
    assert event.duration is None


def test_occupancy_event_with_occupant():
    """Test OccupancyEvent with occupant identity."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.DOOR,
        timestamp=now,
        occupant_id="person.mike",
    )
    assert event.occupant_id == "person.mike"


def test_occupancy_event_with_duration():
    """Test OccupancyEvent with custom duration."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    event = OccupancyEvent(
        location_id="sauna",
        event_type=EventType.MANUAL,
        timestamp=now,
        duration=timedelta(minutes=60),
    )
    assert event.duration == timedelta(minutes=60)


def test_engine_result_creation():
    """Test EngineResult can be created."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    result = EngineResult(next_expiration=now)
    assert result.next_expiration == now
    assert result.transitions == []


def test_engine_result_with_transitions():
    """Test EngineResult with state transitions."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    state = LocationRuntimeState(is_occupied=True, occupied_until=now)
    result = EngineResult(
        next_expiration=now,
        transitions=[("kitchen", state)],
    )
    assert len(result.transitions) == 1
    assert result.transitions[0][0] == "kitchen"
    assert result.transitions[0][1].is_occupied is True

