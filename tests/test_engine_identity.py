"""Tests for identity tracking and Ghost Mike scenario."""

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
def identity_config():
    """Create a location config for identity testing."""
    return LocationConfig(
        id="kitchen",
        parent_id=None,
        kind=LocationKind.AREA,
        timeouts={EventType.MOTION: timedelta(minutes=10)},
    )


@pytest.fixture
def identity_engine(identity_config):
    """Create an engine for identity testing."""
    return OccupancyEngine(configs={"kitchen": identity_config})


def test_identity_added_on_occupancy(identity_engine):
    """Test that occupant_id is added to active_occupants."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    states = {"kitchen": LocationRuntimeState(is_occupied=False)}

    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.DOOR,
        timestamp=now,
        occupant_id="person.mike",
    )

    result = identity_engine.handle_event(event, now, states)

    assert len(result.transitions) == 1
    new_state = result.transitions[0][1]
    assert "person.mike" in new_state.active_occupants


def test_identity_added_on_extend(identity_engine):
    """Test that occupant_id is added when extending timer."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    states = {
        "kitchen": LocationRuntimeState(
            is_occupied=True,
            occupied_until=now + timedelta(minutes=5),
            active_occupants={"person.jane"},
        )
    }

    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.MOTION,
        timestamp=now,
        occupant_id="person.mike",
    )

    result = identity_engine.handle_event(event, now, states)

    assert len(result.transitions) == 1
    new_state = result.transitions[0][1]
    assert "person.mike" in new_state.active_occupants
    assert "person.jane" in new_state.active_occupants  # Preserved


def test_ghost_mike_scenario(identity_engine):
    """Test Rule D: active_occupants cleared on vacancy (Ghost Mike fix)."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    # Kitchen is occupied with Mike
    states = {
        "kitchen": LocationRuntimeState(
            is_occupied=True,
            occupied_until=now + timedelta(minutes=5),
            active_occupants={"person.mike"},
        )
    }

    # Time passes, timeout occurs
    result = identity_engine.check_timeouts(now + timedelta(minutes=6), states)

    # Kitchen should go vacant
    kitchen_transitions = [
        (loc_id, state)
        for loc_id, state in result.transitions
        if loc_id == "kitchen"
    ]
    assert len(kitchen_transitions) == 1
    new_state = kitchen_transitions[0][1]

    # CRITICAL: active_occupants must be cleared
    assert new_state.is_occupied is False
    assert new_state.active_occupants == set()
    assert new_state.occupied_until is None


def test_identity_propagates_to_parent(identity_engine):
    """Test that active_occupants propagate up the hierarchy."""
    # Create engine with hierarchy
    configs = {
        "kitchen": LocationConfig(
            id="kitchen",
            parent_id="main_floor",
            kind=LocationKind.AREA,
            timeouts={EventType.MOTION: timedelta(minutes=10)},
        ),
        "main_floor": LocationConfig(
            id="main_floor",
            parent_id=None,
            kind=LocationKind.VIRTUAL,
            timeouts={EventType.PROPAGATED: timedelta(minutes=15)},
        ),
    }
    engine = OccupancyEngine(configs=configs)

    now = datetime(2025, 1, 1, 12, 0, 0)
    states = {
        "kitchen": LocationRuntimeState(is_occupied=False),
        "main_floor": LocationRuntimeState(is_occupied=False),
    }

    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.MOTION,
        timestamp=now,
        occupant_id="person.mike",
    )

    result = engine.handle_event(event, now, states)

    # Find parent state
    main_floor_state = next(
        state for loc_id, state in result.transitions if loc_id == "main_floor"
    )
    assert "person.mike" in main_floor_state.active_occupants

