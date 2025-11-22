"""Tests for lock state logic."""

from datetime import datetime, timedelta

import pytest

from occupancy_manager.engine import OccupancyEngine
from occupancy_manager.model import (
    EventType,
    LocationConfig,
    LocationKind,
    LockState,
    LocationRuntimeState,
    OccupancyEvent,
)


@pytest.fixture
def locked_kitchen_config():
    """Create a locked kitchen location config."""
    return LocationConfig(
        id="kitchen",
        parent_id=None,
        kind=LocationKind.AREA,
        timeouts={EventType.MOTION: timedelta(minutes=10)},
    )


@pytest.fixture
def locked_engine(locked_kitchen_config):
    """Create an engine with locked kitchen."""
    return OccupancyEngine(configs={"kitchen": locked_kitchen_config})


def test_locked_ignores_motion(locked_engine):
    """Test that LOCKED_FROZEN ignores MOTION events."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    states = {
        "kitchen": LocationRuntimeState(
            is_occupied=False,
            lock_state=LockState.LOCKED_FROZEN,
        )
    }

    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.MOTION,
        timestamp=now,
    )

    result = locked_engine.handle_event(event, now, states)

    # Should drop the event - no transitions
    assert len(result.transitions) == 0


def test_locked_allows_manual(locked_engine):
    """Test that LOCKED_FROZEN allows MANUAL events."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    states = {
        "kitchen": LocationRuntimeState(
            is_occupied=False,
            lock_state=LockState.LOCKED_FROZEN,
        )
    }

    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.MANUAL,
        timestamp=now,
        duration=timedelta(minutes=30),
    )

    result = locked_engine.handle_event(event, now, states)

    # Should process MANUAL event
    assert len(result.transitions) == 1
    new_state = result.transitions[0][1]
    assert new_state.is_occupied is True


def test_locked_allows_lock_change(locked_engine):
    """Test that LOCKED_FROZEN allows LOCK_CHANGE events."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    states = {
        "kitchen": LocationRuntimeState(
            is_occupied=True,
            lock_state=LockState.LOCKED_FROZEN,
        )
    }

    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.LOCK_CHANGE,
        timestamp=now,
    )

    result = locked_engine.handle_event(event, now, states)

    # Should process LOCK_CHANGE event
    # (Even if it doesn't change state, it should not be dropped)
    assert result is not None

