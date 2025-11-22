# Occupancy Manager - Technical Design Specification

## 1. System Overview

**Occupancy Manager** is a hierarchical occupancy tracking engine. It accepts raw inputs (events) from sensors, calculates the state of logical "Locations" (Rooms, Floors, Zones), and maintains a hierarchy where occupancy bubbles up (Child -> Parent).

It is designed as a **Pure Python Library** (`library/`) hosted by an **Integration** (`custom_components/`). The Library is stateless regarding I/O and time; it receives state and time as inputs and returns state transitions and scheduling instructions.

---

## 2. Core Data Structures

### 2.1 The Location Configuration (`LocationConfig`)

Static rules defining a node in the hierarchy.

- **`id`** (str): Unique identifier.

- **`parent_id`** (Optional[str]): The ID of the container location.

- **`kind`** (Enum): `AREA` (Physical) vs `VIRTUAL` (Container).

- **`timeouts`** (Dict[EventType, int]): Base timeouts in minutes (e.g., `{ "motion": 10, "door": 2 }`).

### 2.2 The Runtime State (`LocationRuntimeState`)

Immutable snapshot.

- **`is_occupied`** (bool): True if currently occupied.

- **`occupied_until`** (Optional[datetime]): The wall-clock time when vacancy occurs.

- **`active_occupants`** (Set[str]): Verified identities (e.g., "person.mike") currently in the space.

- **`lock_state`** (Enum): `UNLOCKED` vs `LOCKED_FROZEN`.

### 2.3 The Input (`OccupancyEvent`)

A signal from the outside world.

- **`event_type`** (Enum): `MOTION`, `DOOR`, `MEDIA`, `PRESENCE`, `MANUAL`, `LOCK_CHANGE`.

- **`occupant_id`** (Optional[str]): Identity associated with the event.

- **`duration`** (Optional[timedelta]): Overrides the default timeout (e.g., "Sauna" sets 60m).

---

## 3. The Logic Engine (`Engine.handle_event`)

### Step 1: Lock Check

If `lock_state` is `LOCKED_FROZEN`:

- Ignore all events EXCEPT `MANUAL` or `LOCK_CHANGE`.

### Step 2: Timeout Calculation

Determine the `new_expiry` time.

1. If `event.duration` is provided, use it.

2. Else, lookup default timeout for `event_type` in `LocationConfig`.

3. `new_expiry = event.timestamp + duration`.

### Step 3: State Transition Rules (The "A/B/C" Logic)

Compare `new_expiry` against `current_state.occupied_until`.

- **Rule A (Vacant -> Occupied):**

  - Set `is_occupied=True`, `occupied_until=new_expiry`.

  - **Identity:** Add `event.occupant_id` (if present) to `active_occupants`.

  - **Action:** Emit Transition (OCCUPIED). Trigger Propagation.

- **Rule B (Occupied -> Extend):**

  - If `new_expiry > current_state.occupied_until`:

  - Update `occupied_until` to `new_expiry`.

  - **Identity:** Add `event.occupant_id` (if present) to `active_occupants`.

  - **Action:** Emit Transition (EXTENDED). Trigger Propagation.

- **Rule C (Occupied -> Ignore):**

  - If `new_expiry <= current_state.occupied_until` AND `occupant_id` is unchanged:

  - Do nothing. (Don't shorten the timer).

- **Rule D (Vacancy / Cleanup):**

  - If state transitions to Vacant (via timeout check or manual force):

  - **CRITICAL:** `active_occupants` must be cleared (set to empty).

  - `occupied_until` set to None.

---

## 4. Hierarchy & Propagation (`_propagate_up`)

Propagation is **Recursive** and **Child-Driven**.

### The Trigger

Propagation runs when a Child Location:

1. Becomes Occupied.

2. Extends its time (Rule B).

3. Changes its `active_occupants`.

### The Payload (Synthetic Event)

The Child sends an event to the Parent:

- **`event_type`**: `PROPAGATED`

- **`duration`**: `Child.occupied_until - now` (The remaining time).

- **`occupant_id`**: Passing up all identities found in Child.

### Vacancy Logic

- **Vacancy DOES NOT bubble up.**

- When a Child goes Vacant, the Parent does *nothing*. The Parent relies on its own timer (which was set by the last Propagation event).

---

## 5. The "Wake Me Up" Timer Protocol

1. **Calculate:** The Engine determines the earliest `occupied_until` timestamp across all locations.

2. **Return:** The `EngineResult` object includes `next_expiration` (datetime).

3. **Schedule:** The Integration schedules `async_track_point_in_time` for `next_expiration`.

4. **Callback:** When timer fires, Integration calls `Engine.check_timeouts(now)`.
