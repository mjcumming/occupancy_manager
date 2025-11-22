# Occupancy Manager Specification

## 1. Core Architecture

- **Pattern:** Functional Core (Library), Imperative Shell (Integration).

- **Library:** Pure Python. Stateless. No `asyncio`. No `homeassistant` imports.

- **Integration:** Handles HA Event Bus, Entity Registry, and Timers.

## 2. The "Wake Me Up" Protocol (Inversion of Control)

The Library does NOT manage timers.

1. Input: `Engine.handle_event(event, now)`

2. Output: `EngineResult` containing `next_expiration` (datetime).

3. Action: Integration schedules `async_track_point_in_time` for that datetime.

4. Callback: When timer fires, Integration calls `Engine.check_timeouts(now)`.

## 3. Data Model (Strict Typing)

- `LocationConfig`: id, parent_id (optional), kind (AREA/VIRTUAL), timeouts.

- `LocationRuntimeState` (Frozen): is_occupied, occupied_until, active_occupants (Set[str]), lock_state.

- `OccupancyEvent`: location_id, event_type, timestamp, occupant_id (optional), duration (optional).

## 4. Propagation Rules

- **Occupancy:** Bubbles up (Child -> Parent).

- **Vacancy:** Does NOT bubble up. Parents expire on their own calculated timers.

- **Locking:** `LOCKED_FROZEN` ignores all events except `MANUAL`.

## 5. Coding Standards

- Use `ruff` formatting.

- Use `frozen=True` for all state dataclasses.

- All time math uses the `now` argument passed into functions.

