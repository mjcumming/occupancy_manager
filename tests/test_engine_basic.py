"""Basic tests for engine event handling."""

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
    """Create a kitchen location config."""
    return LocationConfig(
        id="kitchen",
        parent_id=None,
        kind=LocationKind.AREA,
        timeouts={
            "motion": 10,
            "door": 5,
        },
    )


@pytest.fixture
def engine(kitchen_config):
    """Create an engine with kitchen config."""
    return OccupancyEngine(configs={"kitchen": kitchen_config})


def test_rule_a_vacant_to_occupied(engine):
    """Test Rule A: Vacant -> Occupied transition."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    states = {"kitchen": LocationRuntimeState(is_occupied=False)}

    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.PULSE,
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


def test_rule_c_ignore_shorter_timer(engine):
    """Test Rule C: Ignore event that doesn't extend timer."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    existing_until = now + timedelta(minutes=15)
    states = {
        "kitchen": LocationRuntimeState(
            is_occupied=True,
            occupied_until=existing_until,
        )
    }

    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.PULSE,
        category="motion",
        source_id="binary_sensor.motion",
        timestamp=now,
    )

    result = engine.handle_event(event, now, states)

    # Should not create a transition (ignore the event)
    assert len(result.transitions) == 0
    assert result.next_expiration == existing_until


def test_rule_b_extend_timer(engine):
    """Test Rule B: Extend timer when new expiry is later."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    existing_until = now + timedelta(minutes=5)
    states = {
        "kitchen": LocationRuntimeState(
            is_occupied=True,
            occupied_until=existing_until,
        )
    }

    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.PULSE,
        category="motion",
        source_id="binary_sensor.motion",
        timestamp=now,
    )

    result = engine.handle_event(event, now, states)

    assert len(result.transitions) == 1
    new_state = result.transitions[0].new_state
    assert new_state.is_occupied is True
    assert new_state.occupied_until == now + timedelta(minutes=10)
    assert new_state.occupied_until > existing_until

