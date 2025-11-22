"""Tests for state saving and restoration functionality."""

from datetime import datetime, timedelta

import pytest

from occupancy_manager.engine import OccupancyEngine
from occupancy_manager.model import (
    EventType,
    LocationConfig,
    LocationKind,
    LockState,
    OccupancyEvent,
    OccupancyStrategy,
)


@pytest.fixture
def simple_configs():
    """Simple configuration for testing."""
    return [
        LocationConfig(
            id="kitchen",
            parent_id="main_floor",
            kind=LocationKind.AREA,
        ),
        LocationConfig(
            id="main_floor",
            parent_id="home",
            kind=LocationKind.VIRTUAL,
        ),
        LocationConfig(id="home", kind=LocationKind.VIRTUAL),
    ]


def test_basic_state_restoration(simple_configs):
    """Test: Save state and restore it in a new engine."""
    # 1. Create engine and set up some state
    engine1 = OccupancyEngine(simple_configs)
    now = datetime(2025, 1, 1, 12, 0, 0)

    # Trigger occupancy
    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.MOMENTARY,
        category="motion",
        source_id="pir",
        timestamp=now,
    )
    engine1.handle_event(event, now)

    # Verify state
    assert engine1.state["kitchen"].is_occupied is True
    assert engine1.state["main_floor"].is_occupied is True
    assert engine1.state["home"].is_occupied is True

    # 2. Save state
    saved_state = engine1.state.copy()

    # 3. Create new engine with restored state
    engine2 = OccupancyEngine(simple_configs, initial_state=saved_state)

    # 4. Verify restored state matches
    assert engine2.state["kitchen"].is_occupied is True
    assert engine2.state["main_floor"].is_occupied is True
    assert engine2.state["home"].is_occupied is True
    assert (
        engine2.state["kitchen"].occupied_until
        == engine1.state["kitchen"].occupied_until
    )


def test_restore_with_active_occupants(simple_configs):
    """Test: Restore state with active occupants."""
    engine1 = OccupancyEngine(simple_configs)
    now = datetime(2025, 1, 1, 12, 0, 0)

    # Add occupants
    event1 = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.HOLD_START,
        category="presence",
        source_id="ble_mike",
        timestamp=now,
        occupant_id="Mike",
    )
    engine1.handle_event(event1, now)

    event2 = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.HOLD_START,
        category="presence",
        source_id="ble_marla",
        timestamp=now,
        occupant_id="Marla",
    )
    engine1.handle_event(event2, now)

    assert engine1.state["kitchen"].active_occupants == {"Mike", "Marla"}

    # Save and restore
    saved_state = engine1.state.copy()
    engine2 = OccupancyEngine(simple_configs, initial_state=saved_state)

    # Verify occupants restored
    assert engine2.state["kitchen"].active_occupants == {"Mike", "Marla"}
    assert engine2.state["kitchen"].is_occupied is True


def test_restore_with_active_holds(simple_configs):
    """Test: Restore state with active holds."""
    engine1 = OccupancyEngine(simple_configs)
    now = datetime(2025, 1, 1, 12, 0, 0)

    # Start a hold
    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.HOLD_START,
        category="presence",
        source_id="radar",
        timestamp=now,
    )
    engine1.handle_event(event, now)

    assert "radar" in engine1.state["kitchen"].active_holds
    assert engine1.state["kitchen"].is_occupied is True

    # Save and restore
    saved_state = engine1.state.copy()
    engine2 = OccupancyEngine(simple_configs, initial_state=saved_state)

    # Verify holds restored
    assert "radar" in engine2.state["kitchen"].active_holds
    assert engine2.state["kitchen"].is_occupied is True


def test_restore_with_locked_state(simple_configs):
    """Test: Restore state with locked locations."""
    engine1 = OccupancyEngine(simple_configs)
    now = datetime(2025, 1, 1, 12, 0, 0)

    # Make it occupied and locked
    event1 = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.MOMENTARY,
        category="motion",
        source_id="pir",
        timestamp=now,
    )
    engine1.handle_event(event1, now)

    event2 = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.LOCK_CHANGE,
        category="manual",
        source_id="user",
        timestamp=now,
    )
    engine1.handle_event(event2, now)

    assert engine1.state["kitchen"].lock_state == LockState.LOCKED_FROZEN
    assert engine1.state["kitchen"].is_occupied is True

    # Save and restore
    saved_state = engine1.state.copy()
    engine2 = OccupancyEngine(simple_configs, initial_state=saved_state)

    # Verify lock state restored
    assert engine2.state["kitchen"].lock_state == LockState.LOCKED_FROZEN
    assert engine2.state["kitchen"].is_occupied is True


def test_restore_with_expired_timer(simple_configs):
    """Test: Restore state with expired timer - should handle gracefully."""
    engine1 = OccupancyEngine(simple_configs)
    now = datetime(2025, 1, 1, 12, 0, 0)

    # Set up occupancy with timer
    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.MOMENTARY,
        category="motion",
        source_id="pir",
        timestamp=now,
    )
    engine1.handle_event(event, now)

    # Manually set expired timer (simulating restore after restart)
    from dataclasses import replace

    expired_time = now - timedelta(hours=1)
    engine1.state["kitchen"] = replace(
        engine1.state["kitchen"], occupied_until=expired_time
    )

    # Save and restore
    saved_state = engine1.state.copy()
    engine2 = OccupancyEngine(simple_configs, initial_state=saved_state)

    # Check timeouts - should clean up expired state
    engine2.check_timeouts(now)
    assert engine2.state["kitchen"].is_occupied is False
    assert engine2.state["kitchen"].occupied_until is None


def test_restore_with_hierarchy(simple_configs):
    """Test: Restore hierarchical state correctly."""
    engine1 = OccupancyEngine(simple_configs)
    now = datetime(2025, 1, 1, 12, 0, 0)

    # Trigger kitchen (should propagate up)
    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.MOMENTARY,
        category="motion",
        source_id="pir",
        timestamp=now,
    )
    engine1.handle_event(event, now)

    # Verify hierarchy
    assert engine1.state["kitchen"].is_occupied is True
    assert engine1.state["main_floor"].is_occupied is True
    assert engine1.state["home"].is_occupied is True

    # Save and restore
    saved_state = engine1.state.copy()
    engine2 = OccupancyEngine(simple_configs, initial_state=saved_state)

    # Verify hierarchy restored
    assert engine2.state["kitchen"].is_occupied is True
    assert engine2.state["main_floor"].is_occupied is True
    assert engine2.state["home"].is_occupied is True


def test_restore_continues_working(simple_configs):
    """Test: Restored engine continues to process events correctly."""
    engine1 = OccupancyEngine(simple_configs)
    now = datetime(2025, 1, 1, 12, 0, 0)

    # Set up some state
    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.MOMENTARY,
        category="motion",
        source_id="pir",
        timestamp=now,
    )
    engine1.handle_event(event, now)

    # Save and restore
    saved_state = engine1.state.copy()
    engine2 = OccupancyEngine(simple_configs, initial_state=saved_state)

    # Process new event on restored engine
    later = now + timedelta(minutes=5)
    new_event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.MOMENTARY,
        category="motion",
        source_id="pir",
        timestamp=later,
    )
    result = engine2.handle_event(new_event, later)

    # Should work normally
    assert engine2.state["kitchen"].is_occupied is True
    assert len(result.transitions) > 0


def test_restore_partial_state(simple_configs):
    """Test: Restore state with only some locations."""
    engine1 = OccupancyEngine(simple_configs)
    now = datetime(2025, 1, 1, 12, 0, 0)

    # Only set kitchen state
    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.MOMENTARY,
        category="motion",
        source_id="pir",
        timestamp=now,
    )
    engine1.handle_event(event, now)

    # Save only kitchen state
    saved_state = {"kitchen": engine1.state["kitchen"]}

    # Restore - other locations should be initialized as vacant
    engine2 = OccupancyEngine(simple_configs, initial_state=saved_state)

    assert engine2.state["kitchen"].is_occupied is True
    # Other locations should exist but be vacant (or re-evaluated)
    assert "main_floor" in engine2.state
    assert "home" in engine2.state


def test_restore_with_follow_parent_strategy():
    """Test: Restore state with FOLLOW_PARENT strategy."""
    configs = [
        LocationConfig(id="main_floor", kind=LocationKind.VIRTUAL),
        LocationConfig(
            id="living_room",
            parent_id="main_floor",
            occupancy_strategy=OccupancyStrategy.FOLLOW_PARENT,
        ),
    ]

    engine1 = OccupancyEngine(configs)
    now = datetime(2025, 1, 1, 12, 0, 0)

    # Make main_floor occupied
    event = OccupancyEvent(
        location_id="main_floor",
        event_type=EventType.MOMENTARY,
        category="motion",
        source_id="pir",
        timestamp=now,
    )
    engine1.handle_event(event, now)

    # living_room should follow
    assert engine1.state["main_floor"].is_occupied is True
    assert engine1.state["living_room"].is_occupied is True

    # Save and restore
    saved_state = engine1.state.copy()
    engine2 = OccupancyEngine(configs, initial_state=saved_state)

    # Verify restored
    assert engine2.state["main_floor"].is_occupied is True
    assert engine2.state["living_room"].is_occupied is True


def test_restore_with_occupants_and_holds(simple_configs):
    """Test: Restore complex state with both occupants and holds."""
    engine1 = OccupancyEngine(simple_configs)
    now = datetime(2025, 1, 1, 12, 0, 0)

    # Add occupant
    event1 = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.HOLD_START,
        category="presence",
        source_id="ble_mike",
        timestamp=now,
        occupant_id="Mike",
    )
    engine1.handle_event(event1, now)

    # Add hold
    event2 = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.HOLD_START,
        category="presence",
        source_id="radar",
        timestamp=now,
    )
    engine1.handle_event(event2, now)

    assert engine1.state["kitchen"].active_occupants == {"Mike"}
    assert "radar" in engine1.state["kitchen"].active_holds
    assert engine1.state["kitchen"].is_occupied is True

    # Save and restore
    saved_state = engine1.state.copy()
    engine2 = OccupancyEngine(simple_configs, initial_state=saved_state)

    # Verify everything restored
    assert engine2.state["kitchen"].active_occupants == {"Mike"}
    assert "radar" in engine2.state["kitchen"].active_holds
    assert engine2.state["kitchen"].is_occupied is True
