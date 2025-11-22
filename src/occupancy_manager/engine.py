"""The Core Logic Engine for Occupancy Manager.

This module contains the pure business logic. It accepts events and time,
and returns state transitions and scheduling instructions.
"""

import logging
from dataclasses import replace
from datetime import datetime, timedelta

from .model import (
    EngineResult,
    EventType,
    LocationConfig,
    LocationRuntimeState,
    LockState,
    OccupancyEvent,
    OccupancyStrategy,
    StateTransition,
)

_LOGGER = logging.getLogger(__name__)


class OccupancyEngine:
    """The functional core of the occupancy system."""

    def __init__(
        self,
        configs: list[LocationConfig],
        initial_state: dict[str, LocationRuntimeState] | None = None,
    ) -> None:
        """Initialize the engine with static configuration.

        Args:
            configs: List of location configurations.
            initial_state: Optional initial state dictionary for restoration.
        """
        # Store configs as dict for fast lookup
        self.configs: dict[str, LocationConfig] = {c.id: c for c in configs}

        # Initialize or restore state
        if initial_state:
            self.state = initial_state
        else:
            self.state = {
                c.id: LocationRuntimeState() for c in configs
            }

        # Build Parent -> Children map for "FOLLOW_PARENT" logic (Downward)
        self.children_map: dict[str, list[str]] = {}
        for c in configs:
            if c.parent_id:
                if c.parent_id not in self.children_map:
                    self.children_map[c.parent_id] = []
                self.children_map[c.parent_id].append(c.id)

    def handle_event(self, event: OccupancyEvent, now: datetime) -> EngineResult:
        """Process a single external event and return the results.

        Args:
            event: The occupancy event to process.
            now: Current datetime (time-agnostic).

        Returns:
            EngineResult with state transitions and next expiration time.
        """
        if event.location_id not in self.configs:
            _LOGGER.warning(f"Event for unknown location: {event.location_id}")
            return EngineResult(next_expiration=self._calculate_next_expiration(now))

        _LOGGER.info(
            f"Handling event: {event.event_type.value} in {event.location_id} "
            f"(category={event.category}, source={event.source_id})"
        )

        transitions: list[StateTransition] = []

        # Process the location update (recursive: handles up and down)
        self._process_location_update(event.location_id, event, now, transitions)

        if transitions:
            for transition in transitions:
                prev_state = (
                    "VACANT"
                    if not transition.previous_state.is_occupied
                    else "OCCUPIED"
                )
                new_state = (
                    "OCCUPIED" if transition.new_state.is_occupied else "VACANT"
                )
                _LOGGER.info(
                    f"  {transition.location_id}: {prev_state} -> {new_state} "
                    f"({transition.reason})"
                )

        # Return the package (New States + Next Wakeup Time)
        return EngineResult(
            next_expiration=self._calculate_next_expiration(now),
            transitions=transitions,
        )

    def check_timeouts(self, now: datetime) -> EngineResult:
        """Periodic garbage collection. Checks for expired timers.

        Args:
            now: Current datetime.

        Returns:
            EngineResult with state transitions and next expiration time.
        """
        _LOGGER.info(f"Checking timeouts at {now}")
        transitions: list[StateTransition] = []

        for location_id in self.configs:
            state = self.state[location_id]

            # If locked frozen, we don't timeout (state is static)
            if state.lock_state == LockState.LOCKED_FROZEN:
                _LOGGER.debug(f"  {location_id}: Skipped (locked)")
                continue

            # If not occupied, nothing to timeout
            if not state.is_occupied:
                continue

            # Check if timer expired
            if state.occupied_until and state.occupied_until <= now:
                _LOGGER.info(
                    f"  {location_id}: Timer expired (was {state.occupied_until})"
                )

            # We pass a 'None' event to trigger re-evaluation of the state
            # based purely on time and holds. This will also handle FOLLOW_PARENT
            # children that need to re-evaluate when parent times out.
            self._process_location_update(location_id, None, now, transitions)

        if transitions:
            for transition in transitions:
                prev_state = (
                    "VACANT"
                    if not transition.previous_state.is_occupied
                    else "OCCUPIED"
                )
                new_state = (
                    "OCCUPIED" if transition.new_state.is_occupied else "VACANT"
                )
                _LOGGER.info(
                    f"  {transition.location_id}: {prev_state} -> {new_state} "
                    f"(timeout)"
                )

        return EngineResult(
            next_expiration=self._calculate_next_expiration(now),
            transitions=transitions,
        )

    def _process_location_update(
        self,
        location_id: str,
        event: OccupancyEvent | None,
        now: datetime,
        transitions: list[StateTransition],
    ) -> None:
        """Recursive update handler with upward and downward propagation.

        Args:
            location_id: The location to update.
            event: Optional event triggering this update.
            now: Current datetime.
            transitions: List to append state transitions to.
        """
        # 1. Evaluate this location
        state_changed = self._evaluate_state(location_id, event, now, transitions)

        if not state_changed:
            return

        config = self.configs[location_id]
        new_state = self.state[location_id]

        # 2. Upward Propagation (Child -> Parent)
        # If we contribute to parent, bubble up occupancy or identity changes
        if config.parent_id and config.contributes_to_parent:
            # We propagate if we are occupied (or extended) or have occupants
            # Note: We do NOT propagate vacancy.
            should_propagate = new_state.is_occupied or new_state.active_occupants

            if should_propagate:
                _LOGGER.debug(
                    f"  Propagating {location_id} -> {config.parent_id} "
                    f"(occupied={new_state.is_occupied})"
                )
                # Construct synthetic event
                parent_event = OccupancyEvent(
                    location_id=config.parent_id,
                    event_type=EventType.PROPAGATED,
                    category="propagated",
                    source_id=location_id,
                    timestamp=now,
                    # Pass identity up if needed
                    occupant_id=None,  # Could merge identities here if needed
                )
                self._process_location_update(
                    config.parent_id, parent_event, now, transitions
                )
            else:
                _LOGGER.debug(
                    f"  {location_id} -> {config.parent_id}: "
                    f"Not propagating (vacant, contributes_to_parent=True)"
                )

        # 3. Downward Dependency (Parent -> Child with FOLLOW_PARENT)
        # If this location changed, check if any children are watching it
        if location_id in self.children_map:
            for child_id in self.children_map[location_id]:
                child_config = self.configs[child_id]
                if child_config.occupancy_strategy == OccupancyStrategy.FOLLOW_PARENT:
                    _LOGGER.debug(
                        f"  {location_id} -> {child_id}: "
                        f"Triggering re-eval (FOLLOW_PARENT)"
                    )
                    # Trigger re-eval of child (with no event, just context update)
                    # This is the "Proactive" approach:
                    # parent change forces child re-eval
                    self._process_location_update(child_id, None, now, transitions)

    def _evaluate_state(
        self,
        location_id: str,
        event: OccupancyEvent | None,
        now: datetime,
        transitions: list[StateTransition],
    ) -> bool:
        """Core math. Calculates the new state for a location.

        Args:
            location_id: The location to evaluate.
            event: Optional event triggering evaluation.
            now: Current datetime.
            transitions: List to append state transitions to.

        Returns:
            True if state changed, False otherwise.
        """
        config = self.configs[location_id]
        current_state = self.state[location_id]

        # --- A. Lock Check ---
        if current_state.lock_state == LockState.LOCKED_FROZEN:
            # Ignore everything except Manual or Lock changes
            if not event or event.event_type not in (
                EventType.MANUAL,
                EventType.LOCK_CHANGE,
            ):
                _LOGGER.debug(
                    f"  {location_id}: Event ignored (locked, "
                    f"event_type={event.event_type.value if event else 'None'})"
                )
                return False

        # --- B. Calculate Inputs (Next State Candidates) ---
        next_occupants = set(current_state.active_occupants)
        next_holds = set(current_state.active_holds)
        next_occupied_until = current_state.occupied_until
        next_lock_state = current_state.lock_state

        if event:
            # 1. Handle Locking
            if event.event_type == EventType.LOCK_CHANGE:
                # Toggle lock state
                if next_lock_state == LockState.LOCKED_FROZEN:
                    next_lock_state = LockState.UNLOCKED
                    _LOGGER.info(f"  {location_id}: UNLOCKED")
                else:
                    next_lock_state = LockState.LOCKED_FROZEN
                    _LOGGER.info(f"  {location_id}: LOCKED")

            # 2. Handle Identity
            if event.occupant_id:
                if event.event_type == EventType.HOLD_END:
                    # Specific Departure: Mike left, but Marla might be here
                    if event.occupant_id in next_occupants:
                        next_occupants.remove(event.occupant_id)
                else:
                    # Arrival or Action: Mike is here
                    next_occupants.add(event.occupant_id)

            # 3. Handle Holds
            if event.event_type == EventType.HOLD_START:
                next_holds.add(event.source_id)
            elif event.event_type == EventType.HOLD_END:
                if event.source_id in next_holds:
                    next_holds.remove(event.source_id)

            # 4. Handle Manual Override
            if event.event_type == EventType.MANUAL:
                # Manual events force occupancy on
                # If duration provided, use it; otherwise use default timeout
                timeout_minutes = self._get_timeout(event.category, location_id)
                if event.duration:
                    timeout_delta = event.duration
                else:
                    timeout_delta = timedelta(minutes=timeout_minutes)

                calculated_expiry = now + timeout_delta
                if (
                    next_occupied_until is None
                    or calculated_expiry > next_occupied_until
                ):
                    next_occupied_until = calculated_expiry

            # 5. Timer Logic (Momentary vs Hold Release vs Propagated)
            if event.event_type == EventType.MOMENTARY:
                timeout_minutes = self._get_timeout(event.category, location_id)
                if event.duration:
                    timeout_delta = event.duration
                else:
                    timeout_delta = timedelta(minutes=timeout_minutes)

                calculated_expiry = now + timeout_delta

                # Extend timer if new > current (or if currently vacant)
                if (
                    next_occupied_until is None
                    or calculated_expiry > next_occupied_until
                ):
                    next_occupied_until = calculated_expiry

            elif event.event_type == EventType.HOLD_END:
                # Fudge factor applies when the LAST hold drops
                if not next_holds and current_state.active_holds:
                    timeout_minutes = self._get_timeout(event.category, location_id)
                    if event.duration:
                        timeout_delta = event.duration
                    else:
                        timeout_delta = timedelta(minutes=timeout_minutes)

                    next_occupied_until = now + timeout_delta

            elif event.event_type == EventType.PROPAGATED:
                # Propagation extends timer
                timeout_minutes = self._get_timeout(event.category, location_id)
                if event.duration:
                    timeout_delta = event.duration
                else:
                    timeout_delta = timedelta(minutes=timeout_minutes)

                calculated_expiry = now + timeout_delta
                if (
                    next_occupied_until is None
                    or calculated_expiry > next_occupied_until
                ):
                    next_occupied_until = calculated_expiry

        # --- C. Determine Occupancy Status (The Strategy) ---
        is_occupied_candidate = False

        # 1. Timer Active
        if next_occupied_until and next_occupied_until > now:
            is_occupied_candidate = True

        # 2. Active Hold
        if next_holds:
            is_occupied_candidate = True
            # Note: While held, occupied_until is technically irrelevant
            # until the hold releases, but we keep the underlying timer if set.

        # 3. Identity Present
        if next_occupants:
            is_occupied_candidate = True

        # 4. Strategy: FOLLOW_PARENT
        if config.occupancy_strategy == OccupancyStrategy.FOLLOW_PARENT:
            if config.parent_id:
                parent_state = self.state.get(config.parent_id)
                if parent_state and parent_state.is_occupied:
                    is_occupied_candidate = True
                    # If following parent and parent is held, this location is also held
                    if parent_state.active_holds or parent_state.active_occupants:
                        next_occupied_until = None

        # --- D. Vacancy Cleanup ---
        if not is_occupied_candidate:
            # Reset ephemeral data on vacancy
            next_occupants.clear()
            next_holds.clear()
            next_occupied_until = None

        # --- E. Commit State ---
        # Check if anything actually changed
        if (
            is_occupied_candidate != current_state.is_occupied
            or next_occupied_until != current_state.occupied_until
            or next_occupants != current_state.active_occupants
            or next_holds != current_state.active_holds
            or next_lock_state != current_state.lock_state
        ):
            new_state = replace(
                current_state,
                is_occupied=is_occupied_candidate,
                occupied_until=next_occupied_until,
                active_occupants=next_occupants,
                active_holds=next_holds,
                lock_state=next_lock_state,
            )

            self.state[location_id] = new_state

            transitions.append(
                StateTransition(
                    location_id=location_id,
                    previous_state=current_state,
                    new_state=new_state,
                    reason="event" if event else "timeout",
                )
            )
            return True

        return False

    def _calculate_next_expiration(self, now: datetime) -> datetime | None:
        """Find the earliest future timeout across all locations.

        Args:
            now: Current datetime.

        Returns:
            Earliest expiration datetime, or None if no timers active.
        """
        next_exp: datetime | None = None

        for state in self.state.values():
            # Skip if held (no timer needed)
            if state.active_holds or state.active_occupants:
                continue

            if state.occupied_until and state.occupied_until > now:
                if next_exp is None or state.occupied_until < next_exp:
                    next_exp = state.occupied_until

        return next_exp

    def _get_timeout(self, category: str, location_id: str) -> int:
        """Get timeout in minutes for a category and location.

        Args:
            category: Event category (e.g., "motion", "presence").
            location_id: Location ID.

        Returns:
            Timeout in minutes (default: 10).
        """
        config = self.configs.get(location_id)
        if config:
            # Try category-specific timeout
            if category in config.timeouts:
                return config.timeouts[category]
            # Fall back to default
            if "default" in config.timeouts:
                return config.timeouts["default"]
        return 10  # Final fallback
