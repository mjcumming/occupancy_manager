"""Tests for hierarchy and propagation."""

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
def hierarchy_configs():
    """Create a parent-child hierarchy."""
    return {
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


@pytest.fixture
def hierarchy_engine(hierarchy_configs):
    """Create an engine with hierarchy."""
    return OccupancyEngine(configs=hierarchy_configs)


def test_propagation_child_to_parent(hierarchy_engine):
    """Test that child occupancy propagates to parent."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    states = {
        "kitchen": LocationRuntimeState(is_occupied=False),
        "main_floor": LocationRuntimeState(is_occupied=False),
    }

    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.MOTION,
        timestamp=now,
    )

    result = hierarchy_engine.handle_event(event, now, states)

    # Should have transitions for both kitchen and main_floor
    location_ids = [loc_id for loc_id, _ in result.transitions]
    assert "kitchen" in location_ids
    assert "main_floor" in location_ids

    # Find the parent state
    parent_state = next(
        state for loc_id, state in result.transitions if loc_id == "main_floor"
    )
    assert parent_state.is_occupied is True


def test_vacancy_does_not_propagate(hierarchy_engine):
    """Test that vacancy does NOT bubble up to parent."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    # Both locations are occupied
    states = {
        "kitchen": LocationRuntimeState(
            is_occupied=True,
            occupied_until=now + timedelta(minutes=5),
        ),
        "main_floor": LocationRuntimeState(
            is_occupied=True,
            occupied_until=now + timedelta(minutes=10),
        ),
    }

    # Simulate kitchen going vacant (timeout check)
    result = hierarchy_engine.check_timeouts(now + timedelta(minutes=6), states)

    # Kitchen should go vacant
    kitchen_transitions = [
        (loc_id, state)
        for loc_id, state in result.transitions
        if loc_id == "kitchen"
    ]
    if kitchen_transitions:
        assert kitchen_transitions[0][1].is_occupied is False

    # Main floor should NOT be affected (vacancy doesn't propagate)
    main_floor_transitions = [
        (loc_id, state)
        for loc_id, state in result.transitions
        if loc_id == "main_floor"
    ]
    # Main floor should still be occupied or not in transitions
    assert len(main_floor_transitions) == 0 or main_floor_transitions[0][
        1
    ].is_occupied is True


def test_propagation_extends_parent_timer(hierarchy_engine):
    """Test that child extension propagates and extends parent."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    states = {
        "kitchen": LocationRuntimeState(
            is_occupied=True,
            occupied_until=now + timedelta(minutes=5),
        ),
        "main_floor": LocationRuntimeState(
            is_occupied=True,
            occupied_until=now + timedelta(minutes=6),
        ),
    }

    # New motion event extends kitchen timer
    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.MOTION,
        timestamp=now,
    )

    result = hierarchy_engine.handle_event(event, now, states)

    # Main floor should be extended
    main_floor_state = next(
        state for loc_id, state in result.transitions if loc_id == "main_floor"
    )
    assert main_floor_state.is_occupied is True
    assert main_floor_state.occupied_until > now + timedelta(minutes=6)

