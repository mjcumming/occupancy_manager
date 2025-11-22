"""Occupancy engine implementation.

This module contains the core logic for processing occupancy events
and managing hierarchical location state.
"""

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Optional

from occupancy_manager.model import (
    EngineResult,
    EventType,
    LocationConfig,
    LocationRuntimeState,
    LockState,
    OccupancyEvent,
    OccupancyStrategy,
    StateTransition,
)


class OccupancyEngine:
    """Engine for processing occupancy events and managing location state."""

    def __init__(self, configs: dict[str, LocationConfig]) -> None:
        """Initialize the engine with location configurations.

        Args:
            configs: Dictionary mapping location IDs to their configurations.
        """
        self._configs = configs

    def handle_event(
        self,
        event: OccupancyEvent,
        now: datetime,
        current_states: dict[str, LocationRuntimeState],
    ) -> EngineResult:
        """Process an occupancy event and return state transitions.

        Args:
            event: The occupancy event to process.
            now: Current datetime (time-agnostic).
            current_states: Current state of all locations.

        Returns:
            EngineResult containing transitions and next expiration time.
        """
        # Step 1: Lock Check
        location_id = event.location_id
        if location_id not in current_states:
            current_states[location_id] = LocationRuntimeState()

        current_state = current_states[location_id]

        if current_state.lock_state == LockState.LOCKED_FROZEN:
            if event.event_type not in (EventType.MANUAL, EventType.LOCK_CHANGE):
                # Drop the event
                return self._calculate_result(current_states)

        # Step 2: Update State (Holds & Identity)
        new_occupants = set(current_state.active_occupants)
        new_holds = set(current_state.active_holds)

        # Add occupant if present
        if event.occupant_id:
            new_occupants.add(event.occupant_id)

        # Update holds
        if event.event_type == EventType.HOLD_START:
            new_holds.add(event.source_id)
        elif event.event_type == EventType.HOLD_END:
            new_holds.discard(event.source_id)

        # Step 3: Calculate Expiration (Pulse vs Hold Release)
        new_occupied_until: Optional[datetime] = current_state.occupied_until

        # Condition A: Room is being Held
        if new_holds or new_occupants:
            # Indefinitely occupied
            new_occupied_until = None
        else:
            # Condition B: Pulse Event (Motion)
            if event.event_type == EventType.MOTION:
                timeout_minutes = self._get_timeout(event.category, event.location_id)
                if event.duration:
                    timeout_delta = event.duration
                else:
                    timeout_delta = timedelta(minutes=timeout_minutes)

                new_expiry = event.timestamp + timeout_delta

                # Extend if new > current (or if currently vacant)
                if (
                    current_state.occupied_until is None
                    or new_expiry > current_state.occupied_until
                ):
                    new_occupied_until = new_expiry

            # Condition C: Hold Release (The Fudge Factor)
            elif event.event_type == EventType.HOLD_END:
                # Only apply if holds became empty
                if not new_holds and current_state.active_holds:
                    timeout_minutes = self._get_timeout(event.category, event.location_id)
                    if event.duration:
                        timeout_delta = event.duration
                    else:
                        timeout_delta = timedelta(minutes=timeout_minutes)

                    new_occupied_until = event.timestamp + timeout_delta

        # Step 3 (continued): Determine Occupancy Status
        # A location is Occupied if ANY of the following are true:
        # 1. Timer Active: now < occupied_until
        # 2. Hold Active: active_holds is not empty
        # 3. Identity Present: active_occupants is not empty
        # 4. Child Propagated: (handled in propagation)
        # 5. Parent Followed: (handled below)
        new_is_occupied = False

        # Check conditions 1-3
        if new_holds or new_occupants:
            new_is_occupied = True
        elif new_occupied_until and now < new_occupied_until:
            new_is_occupied = True

        # Condition 5: Parent Followed
        config = self._configs.get(location_id)
        if config and config.occupancy_strategy == OccupancyStrategy.FOLLOW_PARENT:
            if config.parent_id:
                parent_state = current_states.get(config.parent_id)
                if parent_state and parent_state.is_occupied:
                    new_is_occupied = True
                    # If following parent and parent is held, this location is also held
                    if parent_state.active_holds or parent_state.active_occupants:
                        new_occupied_until = None

        # Create new state
        new_state = replace(
            current_state,
            is_occupied=new_is_occupied,
            occupied_until=new_occupied_until,
            active_occupants=new_occupants,
            active_holds=new_holds,
        )

        transitions: list[StateTransition] = []
        
        # Only create transition if state actually changed
        if current_state != new_state:
            transitions.append(
                StateTransition(
                    location_id=location_id,
                    previous_state=current_state,
                    new_state=new_state,
                    reason="event",
                )
            )

        # Step 4: Propagate if needed (with Backyard filter)
        if self._should_propagate(current_state, new_state):
            prop_transitions = self._propagate_up(
                location_id, new_state, now, {**current_states, location_id: new_state}
            )
            transitions.extend(prop_transitions)

        # Update states dict for result calculation
        updated_states = {**current_states, location_id: new_state}
        for transition in transitions:
            updated_states[transition.location_id] = transition.new_state

        return self._calculate_result(updated_states, transitions)

    def check_timeouts(
        self,
        now: datetime,
        current_states: dict[str, LocationRuntimeState],
    ) -> EngineResult:
        """Check for expired timeouts and transition locations to vacant.

        Args:
            now: Current datetime.
            current_states: Current state of all locations.

        Returns:
            EngineResult containing transitions and next expiration time.
        """
        transitions: list[StateTransition] = []
        updated_states = dict(current_states)

        for location_id, state in current_states.items():
            # Skip if held or already vacant
            if state.active_holds or state.active_occupants:
                continue

            if state.is_occupied and state.occupied_until:
                if now >= state.occupied_until:
                    # Step 5: Vacancy Cleanup
                    new_state = replace(
                        state,
                        is_occupied=False,
                        occupied_until=None,
                        active_occupants=set(),
                        active_holds=set(),
                    )
                    transitions.append(
                        StateTransition(
                            location_id=location_id,
                            previous_state=state,
                            new_state=new_state,
                            reason="timeout",
                        )
                    )
                    updated_states[location_id] = new_state

        return self._calculate_result(updated_states, transitions)

    def _should_propagate(
        self, old_state: LocationRuntimeState, new_state: LocationRuntimeState
    ) -> bool:
        """Determine if state change should trigger propagation.

        Args:
            old_state: Previous state.
            new_state: New state.

        Returns:
            True if propagation should occur.
        """
        # Vacant -> Occupied
        if not old_state.is_occupied and new_state.is_occupied:
            return True

        # Extend time or enter indefinite hold
        if old_state.is_occupied and new_state.is_occupied:
            if old_state.occupied_until and new_state.occupied_until:
                if new_state.occupied_until > old_state.occupied_until:
                    return True
            elif not old_state.occupied_until and new_state.occupied_until:
                # Was held, now has timer
                return True
            elif old_state.occupied_until and not new_state.occupied_until:
                # Had timer, now held
                return True

        # Occupants changed
        if old_state.active_occupants != new_state.active_occupants:
            return True

        return False

    def _propagate_up(
        self,
        location_id: str,
        child_state: LocationRuntimeState,
        now: datetime,
        current_states: dict[str, LocationRuntimeState],
    ) -> list[StateTransition]:
        """Propagate child state changes to parent location.

        Args:
            location_id: ID of the child location.
            child_state: New state of the child.
            now: Current datetime.
            current_states: Current state of all locations.

        Returns:
            List of state transitions for parent(s).
        """
        config = self._configs.get(location_id)
        if not config or not config.parent_id:
            return []

        # The "Backyard" Filter: Check contributes_to_parent
        if not config.contributes_to_parent:
            # STOP. Do not send synthetic event to Parent.
            return []

        parent_id = config.parent_id
        if parent_id not in current_states:
            current_states[parent_id] = LocationRuntimeState()

        parent_state = current_states[parent_id]

        # The "Lock" Filter: If Parent is LOCKED_FROZEN, ignore child update
        if parent_state.lock_state == LockState.LOCKED_FROZEN:
            # STOP. Ignore the child update.
            return []

        # Only propagate if child is actually occupied
        if not child_state.is_occupied:
            # Child is vacant - don't propagate (vacancy doesn't bubble up)
            return []

        # Create synthetic event for parent
        # If child is held, parent treats it as a hold
        if child_state.active_holds or child_state.active_occupants:
            # Child is indefinitely occupied - parent should be held
            event = OccupancyEvent(
                location_id=parent_id,
                event_type=EventType.HOLD_START,
                category="propagated",
                source_id=location_id,
                timestamp=now,
            )
        elif child_state.occupied_until:
            # Child has a timer - propagate remaining duration
            remaining = child_state.occupied_until - now
            event = OccupancyEvent(
                location_id=parent_id,
                event_type=EventType.PROPAGATED,
                category="propagated",
                source_id=location_id,
                timestamp=now,
                duration=remaining,
            )
        else:
            return []

        # Process event for parent
        result = self.handle_event(event, now, {parent_id: parent_state})

        # Recursively propagate if parent has changes
        transitions: list[StateTransition] = []
        for transition in result.transitions:
            # Update reason to "propagated" for parent transitions
            transitions.append(
                StateTransition(
                    location_id=transition.location_id,
                    previous_state=transition.previous_state,
                    new_state=transition.new_state,
                    reason="propagated",
                )
            )
            # Recursively propagate parent's changes
            if transition.location_id == parent_id:
                recursive_transitions = self._propagate_up(
                    parent_id,
                    transition.new_state,
                    now,
                    {**current_states, **{transition.location_id: transition.new_state}},
                )
                transitions.extend(recursive_transitions)

        return transitions

    def _get_timeout(self, category: str, location_id: str) -> int:
        """Get timeout in minutes for a category and location.

        Args:
            category: Event category (e.g., "motion", "presence").
            location_id: Location ID.

        Returns:
            Timeout in minutes (default: 10).
        """
        config = self._configs.get(location_id)
        if config and category in config.timeouts:
            return config.timeouts[category]
        return 10  # Default 10 minutes

    def _calculate_result(
        self,
        states: dict[str, LocationRuntimeState],
        transitions: Optional[list[StateTransition]] = None,
    ) -> EngineResult:
        """Calculate next expiration time from all states.

        Args:
            states: Current state of all locations.
            transitions: Optional list of transitions to include.

        Returns:
            EngineResult with next_expiration and transitions.
        """
        if transitions is None:
            transitions = []

        # Find earliest expiration
        next_expiration: Optional[datetime] = None

        for state in states.values():
            # Skip if held (no timer needed)
            if state.active_holds or state.active_occupants:
                continue

            if state.occupied_until:
                if next_expiration is None or state.occupied_until < next_expiration:
                    next_expiration = state.occupied_until

        return EngineResult(
            next_expiration=next_expiration,
            transitions=transitions,
        )

