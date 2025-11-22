"""Tests for engine v2.0 - Hold/Pulse logic and Fudge Factor."""

from datetime import datetime, timedelta

import pytest

from occupancy_manager.engine import OccupancyEngine
from occupancy_manager.model import (
    EventType,
    LocationConfig,
    LocationKind,
    LocationRuntimeState,
    OccupancyEvent,
)


@pytest.fixture
def kitchen_config():
    """Create a kitchen location config with v2.0 timeouts."""
    return LocationConfig(
        id="kitchen",
        parent_id=None,
        kind=LocationKind.AREA,
        timeouts={
            "motion": 10,  # 10 minutes for motion
            "presence": 2,  # 2 minutes trailing timeout
            "media": 5,  # 5 minutes trailing timeout
        },
    )


@pytest.fixture
def engine(kitchen_config):
    """Create an engine with kitchen config."""
    return OccupancyEngine(configs={"kitchen": kitchen_config})


def test_momentary_event_resets_timer(engine):
    """Test that MOMENTARY events reset/extend the timer."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    states = {"kitchen": LocationRuntimeState(is_occupied=False)}

    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.MOMENTARY,
        category="motion",
        source_id="binary_sensor.motion",
        timestamp=now,
    )

    result = engine.handle_event(event, now, states)

    assert len(result.transitions) == 1
    new_state = result.transitions[0].new_state
    assert new_state.is_occupied is True
    assert new_state.occupied_until == now + timedelta(minutes=10)
    assert result.next_expiration == now + timedelta(minutes=10)


def test_hold_start_pauses_timer(engine):
    """Test that HOLD_START makes room indefinitely occupied."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    states = {
        "kitchen": LocationRuntimeState(
            is_occupied=True,
            occupied_until=now + timedelta(minutes=5),
        )
    }

    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.HOLD_START,
        category="presence",
        source_id="binary_sensor.mmwave",
        timestamp=now,
    )

    result = engine.handle_event(event, now, states)

    assert len(result.transitions) == 1
    new_state = result.transitions[0].new_state
    assert new_state.is_occupied is True
    assert new_state.occupied_until is None  # Indefinitely occupied
    assert "binary_sensor.mmwave" in new_state.active_holds
    assert result.next_expiration is None  # No timer needed


def test_hold_end_fudge_factor(engine):
    """Test that HOLD_END triggers trailing timeout (fudge factor)."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    states = {
        "kitchen": LocationRuntimeState(
            is_occupied=True,
            occupied_until=None,  # Was held
            active_holds={"binary_sensor.mmwave"},
        )
    }

    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.HOLD_END,
        category="presence",
        source_id="binary_sensor.mmwave",
        timestamp=now,
    )

    result = engine.handle_event(event, now, states)

    assert len(result.transitions) == 1
    new_state = result.transitions[0].new_state
    assert new_state.is_occupied is True
    # Should have 2 minute trailing timeout (fudge factor)
    assert new_state.occupied_until == now + timedelta(minutes=2)
    assert "binary_sensor.mmwave" not in new_state.active_holds
    assert result.next_expiration == now + timedelta(minutes=2)


def test_hold_with_occupants_indefinite(engine):
    """Test that room with active_occupants is indefinitely occupied."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    states = {
        "kitchen": LocationRuntimeState(
            is_occupied=True,
            occupied_until=now + timedelta(minutes=5),
            active_occupants={"person.mike"},
        )
    }

    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.MOMENTARY,
        category="motion",
        source_id="binary_sensor.motion",
        timestamp=now,
    )

    result = engine.handle_event(event, now, states)

    assert len(result.transitions) == 1
    new_state = result.transitions[0].new_state
    # Should remain indefinitely occupied due to active_occupants
    assert new_state.occupied_until is None
    assert new_state.is_occupied is True


def test_multiple_holds(engine):
    """Test that multiple holds keep room occupied until all released."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    states = {
        "kitchen": LocationRuntimeState(
            is_occupied=True,
            active_holds={"binary_sensor.mmwave"},
        )
    }

    # Add second hold
    event1 = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.HOLD_START,
        category="media",
        source_id="media_player.tv",
        timestamp=now,
    )

    result1 = engine.handle_event(event1, now, states)
    new_state1 = result1.transitions[0].new_state
    assert len(new_state1.active_holds) == 2
    assert new_state1.occupied_until is None

    # Remove first hold (room still held by TV)
    event2 = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.HOLD_END,
        category="presence",
        source_id="binary_sensor.mmwave",
        timestamp=now + timedelta(seconds=1),
    )

    result2 = engine.handle_event(
        event2, now + timedelta(seconds=1), {"kitchen": new_state1}
    )
    new_state2 = result2.transitions[0].new_state
    assert "binary_sensor.mmwave" not in new_state2.active_holds
    assert "media_player.tv" in new_state2.active_holds
    assert new_state2.occupied_until is None  # Still held by TV

    # Remove last hold (now fudge factor applies)
    event3 = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.HOLD_END,
        category="media",
        source_id="media_player.tv",
        timestamp=now + timedelta(seconds=2),
    )

    result3 = engine.handle_event(
        event3, now + timedelta(seconds=2), {"kitchen": new_state2}
    )
    new_state3 = result3.transitions[0].new_state
    assert len(new_state3.active_holds) == 0
    # Should have 5 minute trailing timeout (media category)
    assert new_state3.occupied_until == (now + timedelta(seconds=2)) + timedelta(
        minutes=5
    )


def test_vacancy_cleanup_clears_holds(engine):
    """Test that vacancy cleanup clears active_holds."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    states = {
        "kitchen": LocationRuntimeState(
            is_occupied=True,
            occupied_until=now + timedelta(minutes=5),
            active_occupants={"person.mike"},
            active_holds={"binary_sensor.mmwave"},
        )
    }

    # Timeout occurs
    result = engine.check_timeouts(now + timedelta(minutes=6), states)

    kitchen_transitions = [
        (loc_id, state) for loc_id, state in result.transitions if loc_id == "kitchen"
    ]
    if kitchen_transitions:
        new_state = kitchen_transitions[0].new_state
        assert new_state.is_occupied is False
        assert new_state.active_occupants == set()
        assert new_state.active_holds == set()
        assert new_state.occupied_until is None


def test_hold_release_with_occupants_no_fudge(engine):
    """Test that hold release doesn't apply fudge if occupants present."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    states = {
        "kitchen": LocationRuntimeState(
            is_occupied=True,
            occupied_until=None,
            active_holds={"binary_sensor.mmwave"},
            active_occupants={"person.mike"},
        )
    }

    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.HOLD_END,
        category="presence",
        source_id="binary_sensor.mmwave",
        timestamp=now,
    )

    result = engine.handle_event(event, now, states)

    new_state = result.transitions[0].new_state
    # Should remain indefinitely occupied due to active_occupants
    assert new_state.occupied_until is None
    assert "person.mike" in new_state.active_occupants
