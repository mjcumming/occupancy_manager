"""Tests for state serialization and hydration."""

from datetime import datetime, timedelta

import pytest

from occupancy_manager.engine import OccupancyEngine
from occupancy_manager.model import (
    EventType,
    LocationConfig,
    LocationKind,
    LockState,
    OccupancyEvent,
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


def test_export_basic_state(simple_configs):
    """Test: Export state creates JSON-serializable dict."""
    engine = OccupancyEngine(simple_configs)
    now = datetime(2025, 1, 1, 12, 0, 0)

    # Set up some state
    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.MOMENTARY,
        category="motion",
        source_id="pir",
        timestamp=now,
    )
    engine.handle_event(event, now)

    # Export
    snapshot = engine.export_state()

    # Verify structure
    assert "kitchen" in snapshot
    assert isinstance(snapshot["kitchen"], dict)
    assert "is_occupied" in snapshot["kitchen"]
    assert "occupied_until" in snapshot["kitchen"]
    assert "active_occupants" in snapshot["kitchen"]
    assert "active_holds" in snapshot["kitchen"]
    assert "lock_state" in snapshot["kitchen"]

    # Verify types are JSON-serializable
    assert isinstance(snapshot["kitchen"]["is_occupied"], bool)
    assert isinstance(snapshot["kitchen"]["active_occupants"], list)
    assert isinstance(snapshot["kitchen"]["active_holds"], list)
    assert isinstance(snapshot["kitchen"]["lock_state"], str)


def test_export_skips_default_states(simple_configs):
    """Test: Export only includes non-default states."""
    engine = OccupancyEngine(simple_configs)

    # All states are default (vacant, unlocked, no occupants)
    snapshot = engine.export_state()

    # Should be empty (or only include locations with state)
    # Since everything is default, snapshot should be empty
    assert len(snapshot) == 0


def test_export_includes_occupied(simple_configs):
    """Test: Export includes occupied locations."""
    engine = OccupancyEngine(simple_configs)
    now = datetime(2025, 1, 1, 12, 0, 0)

    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.MOMENTARY,
        category="motion",
        source_id="pir",
        timestamp=now,
    )
    engine.handle_event(event, now)

    snapshot = engine.export_state()

    assert "kitchen" in snapshot
    assert snapshot["kitchen"]["is_occupied"] is True
    assert snapshot["kitchen"]["occupied_until"] is not None
    assert isinstance(snapshot["kitchen"]["occupied_until"], str)  # ISO format


def test_export_includes_occupants(simple_configs):
    """Test: Export includes active occupants."""
    engine = OccupancyEngine(simple_configs)
    now = datetime(2025, 1, 1, 12, 0, 0)

    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.HOLD_START,
        category="presence",
        source_id="ble_mike",
        timestamp=now,
        occupant_id="Mike",
    )
    engine.handle_event(event, now)

    snapshot = engine.export_state()

    assert "kitchen" in snapshot
    assert "Mike" in snapshot["kitchen"]["active_occupants"]
    assert isinstance(snapshot["kitchen"]["active_occupants"], list)


def test_export_includes_locked(simple_configs):
    """Test: Export includes locked states even if vacant."""
    engine = OccupancyEngine(simple_configs)
    now = datetime(2025, 1, 1, 12, 0, 0)

    # Lock it
    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.LOCK_CHANGE,
        category="manual",
        source_id="user",
        timestamp=now,
    )
    engine.handle_event(event, now)

    snapshot = engine.export_state()

    assert "kitchen" in snapshot
    assert snapshot["kitchen"]["lock_state"] == LockState.LOCKED_FROZEN.value


def test_restore_fresh_state(simple_configs):
    """Test: Restore state that hasn't expired."""
    engine1 = OccupancyEngine(simple_configs)
    now = datetime(2025, 1, 1, 12, 0, 0)

    # Set up state
    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.MOMENTARY,
        category="motion",
        source_id="pir",
        timestamp=now,
    )
    engine1.handle_event(event, now)

    # Export
    snapshot = engine1.export_state()

    # Restore in new engine (same time - no expiration)
    engine2 = OccupancyEngine(simple_configs)
    engine2.restore_state(snapshot, now)

    # Verify restored
    assert engine2.state["kitchen"].is_occupied is True
    assert (
        engine2.state["kitchen"].occupied_until
        == engine1.state["kitchen"].occupied_until
    )


def test_restore_expired_timer(simple_configs):
    """Test: Restore expired timer forces vacancy."""
    engine1 = OccupancyEngine(simple_configs)
    now = datetime(2025, 1, 1, 12, 0, 0)

    # Set up state with timer
    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.MOMENTARY,
        category="motion",
        source_id="pir",
        timestamp=now,
    )
    engine1.handle_event(event, now)

    # Export
    snapshot = engine1.export_state()

    # Restore 2 hours later (timer expired)
    future = now + timedelta(hours=2)
    engine2 = OccupancyEngine(simple_configs)
    engine2.restore_state(snapshot, future)

    # Should be vacant (expired)
    assert engine2.state["kitchen"].is_occupied is False
    assert engine2.state["kitchen"].occupied_until is None


def test_restore_expired_with_occupants(simple_configs):
    """Test: Restore expired timer but with active occupants - keeps occupied."""
    engine1 = OccupancyEngine(simple_configs)
    now = datetime(2025, 1, 1, 12, 0, 0)

    # Set up state with occupant
    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.HOLD_START,
        category="presence",
        source_id="ble_mike",
        timestamp=now,
        occupant_id="Mike",
    )
    engine1.handle_event(event, now)

    # Export
    snapshot = engine1.export_state()

    # Restore 2 hours later (timer would expire, but occupant keeps it occupied)
    future = now + timedelta(hours=2)
    engine2 = OccupancyEngine(simple_configs)
    engine2.restore_state(snapshot, future)

    # Should still be occupied (active occupant)
    assert engine2.state["kitchen"].is_occupied is True
    assert "Mike" in engine2.state["kitchen"].active_occupants


def test_restore_locked_state(simple_configs):
    """Test: Restore locked state always works (timeless)."""
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

    # Export
    snapshot = engine1.export_state()

    # Restore 2 hours later
    future = now + timedelta(hours=2)
    engine2 = OccupancyEngine(simple_configs)
    engine2.restore_state(snapshot, future)

    # Should still be locked and occupied (locked is timeless)
    assert engine2.state["kitchen"].lock_state == LockState.LOCKED_FROZEN
    assert engine2.state["kitchen"].is_occupied is True


def test_restore_with_holds(simple_configs):
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

    # Export
    snapshot = engine1.export_state()

    # Restore 2 hours later
    future = now + timedelta(hours=2)
    engine2 = OccupancyEngine(simple_configs)
    engine2.restore_state(snapshot, future)

    # Should still be occupied (active hold)
    assert engine2.state["kitchen"].is_occupied is True
    assert "radar" in engine2.state["kitchen"].active_holds


def test_restore_invalid_location_skipped(simple_configs):
    """Test: Restore skips locations not in configs."""
    snapshot = {
        "kitchen": {
            "is_occupied": True,
            "occupied_until": None,
            "active_occupants": [],
            "active_holds": [],
            "lock_state": "unlocked",
        },
        "unknown_location": {
            "is_occupied": True,
            "occupied_until": None,
            "active_occupants": [],
            "active_holds": [],
            "lock_state": "unlocked",
        },
    }

    engine = OccupancyEngine(simple_configs)
    now = datetime(2025, 1, 1, 12, 0, 0)
    engine.restore_state(snapshot, now)

    # Should restore kitchen but skip unknown_location
    assert "kitchen" in engine.state
    assert "unknown_location" not in engine.state


def test_restore_invalid_datetime_handled(simple_configs):
    """Test: Restore handles invalid datetime gracefully."""
    snapshot = {
        "kitchen": {
            "is_occupied": True,
            "occupied_until": "invalid-datetime-string",
            "active_occupants": [],
            "active_holds": [],
            "lock_state": "unlocked",
        },
    }

    engine = OccupancyEngine(simple_configs)
    now = datetime(2025, 1, 1, 12, 0, 0)
    engine.restore_state(snapshot, now)

    # Should handle gracefully (occupied_until becomes None)
    assert engine.state["kitchen"].is_occupied is True
    assert engine.state["kitchen"].occupied_until is None


def test_round_trip_serialization(simple_configs):
    """Test: Export and restore maintains state correctly."""
    engine1 = OccupancyEngine(simple_configs)
    now = datetime(2025, 1, 1, 12, 0, 0)

    # Set up complex state
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
        source_id="radar",
        timestamp=now,
    )
    engine1.handle_event(event2, now)

    # Export
    snapshot = engine1.export_state()

    # Restore
    engine2 = OccupancyEngine(simple_configs)
    engine2.restore_state(snapshot, now)

    # Verify round trip
    assert engine2.state["kitchen"].is_occupied == engine1.state["kitchen"].is_occupied
    assert (
        engine2.state["kitchen"].active_occupants
        == engine1.state["kitchen"].active_occupants
    )
    assert (
        engine2.state["kitchen"].active_holds == engine1.state["kitchen"].active_holds
    )
    assert engine2.state["kitchen"].lock_state == engine1.state["kitchen"].lock_state
