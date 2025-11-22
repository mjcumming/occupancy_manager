# Occupancy Manager Specification

## 1. Core Architecture

- **Pattern:** Functional Core (Library), Imperative Shell (Integration).

- **Library:** Pure Python. Stateless. No `asyncio`. No `homeassistant` imports.

- **Integration:** Handles HA Event Bus, Entity Registry, and Timers.

## 2. The "Wake Me Up" Protocol (Inversion of Control)

The Library does NOT manage timers.

1. Input: `Engine.handle_event(event, now)`

2. Output: `EngineResult` containing `next_expiration` (datetime) and `transitions`.

3. Action: Integration schedules `async_track_point_in_time` for `next_expiration`.

4. Callback: When timer fires, Integration calls `Engine.check_timeouts(now)`.

## 3. Data Model (Strict Typing)

- **LocationConfig:**
  - `id`: Unique str.
  - `parent_id`: Optional[str] (Single parent).
  - `kind`: Enum (AREA / VIRTUAL).
  - `timeouts`: Base timeout logic.

- **LocationRuntimeState (Frozen):**
  - `is_occupied`: bool.
  - `occupied_until`: Optional[datetime].
  - `active_occupants`: Set[str] (Identity tracking).
  - `lock_state`: Enum (UNLOCKED / LOCKED_FROZEN).

- **OccupancyEvent:**
  - `location_id`: str.
  - `event_type`: Enum (MOTION, DOOR, MEDIA, PRESENCE, MANUAL).
  - `occupant_id`: Optional[str] (Identity).
  - `duration`: Optional[timedelta] (Variable duration override, e.g., "Sauna=60m").

## 4. Hierarchy & Propagation Rules

- **Occupancy (Bubbles Up):**
  - If Child becomes Occupied OR extends its timer -> Trigger recursive update to Parent.
  - Identity (`active_occupants`) also bubbles up.

- **Vacancy (Does NOT Bubble Up):**
  - Parents have their own independent trailing timers calculated from the last child event.
  - When a child goes vacant, the parent does nothing until its *own* timer expires.

## 5. Locking Logic

- **LOCKED_FROZEN:**
  - Ignores all incoming events (Motion, Door, etc).
  - DOES NOT ignore `MANUAL` events (Overrides).
  - State remains static until unlocked or manually changed.

## 6. Coding Standards

- Use `frozen=True` for all state dataclasses (Immutable).

- All time math uses the `now` argument passed into functions.

