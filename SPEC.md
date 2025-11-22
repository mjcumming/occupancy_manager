# Occupancy Manager - Library Specification (v2.0)

## 1. System Overview

**Occupancy Manager** is a hierarchical occupancy tracking engine. It accepts raw inputs (events) from sensors, calculates the state of logical "Locations" (Rooms, Floors, Zones), and maintains a hierarchy where occupancy bubbles up (Child -> Parent).

This is a **Pure Python Library** (`src/occupancy_manager`). It is agnostic to the host platform (Home Assistant/CLI). It creates no threads and performs no I/O.

---

## 2. Core Data Structures

### 2.1 The Location Configuration (`LocationConfig`)

Static rules defining a node in the hierarchy.

- **`id`** (str): Unique identifier.

- **`parent_id`** (Optional[str]): The ID of the container location.

- **`timeouts`** (Dict[str, int]): Mapping of event categories to minutes.

  - e.g., `{ "motion": 10, "presence": 2, "media": 5 }`

  - *Note:* For "Hold" sources (Presence/Media), this value serves as the **Trailing Timeout** (Fudge Factor) applied when the hold is released.

### 2.2 The Runtime State (`LocationRuntimeState`)

Immutable snapshot.

- **`is_occupied`** (bool): True if currently occupied.

- **`occupied_until`** (Optional[datetime]): The wall-clock time when vacancy occurs.

  - *Note:* If `active_holds` is non-empty, this is ignored/irrelevant.

- **`active_occupants`** (Set[str]): Verified identities (e.g., "Mike") currently in the space.

- **`active_holds`** (Set[str]): Unique IDs of sources currently holding the room open (e.g., "binary_sensor.mmwave", "media_player.tv").

- **`lock_state`** (Enum): `UNLOCKED` vs `LOCKED_FROZEN`.

### 2.3 The Input (`OccupancyEvent`)

A signal from the outside world.

- **`event_type`** (Enum): `MOTION` (Pulse), `HOLD_START`, `HOLD_END`, `MANUAL`, `LOCK_CHANGE`.

- **`category`** (str): The config key to lookup timeout (e.g., "motion", "presence").

- **`source_id`** (str): Unique ID of the device (e.g., "binary_sensor.radar").

- **`occupant_id`** (Optional[str]): Identity associated with the event.

- **`duration`** (Optional[timedelta]): Overrides the default timeout.

---

## 3. The Logic Engine (`Engine.handle_event`)

### Step 1: Lock Check

If `lock_state` is `LOCKED_FROZEN`:

- Ignore all events EXCEPT `MANUAL` or `LOCK_CHANGE`.

### Step 2: Update State (Holds & Identity)

1. **Identity:** If `occupant_id` is present:

   - Add to `active_occupants` (Persists until Vacancy).

2. **Hold Logic:**

   - If `event_type == HOLD_START`: Add `source_id` to `active_holds`.

   - If `event_type == HOLD_END`: Remove `source_id` from `active_holds`.

### Step 3: Calculate Expiration (The "Fudge Factor" Logic)

We determine the new `occupied_until` timestamp.

**Condition A: Room is being Held**

- If `active_holds` is NOT empty OR `active_occupants` is NOT empty:

- The room is **Indefinitely Occupied**.

- `occupied_until` = `None`.

- `is_occupied` = `True`.

**Condition B: Pulse Event (Motion)**

- If `event_type == MOTION`:

- Lookup timeout for `category` (default: 10m).

- `new_expiry = now + timeout`.

- Extend `occupied_until` if `new_expiry > current`.

**Condition C: Hold Release (The Fudge Factor)**

- If `event_type == HOLD_END` AND `active_holds` became empty:

- We do NOT vacate immediately.

- Lookup trailing timeout for `category` (default: 2m).

- `occupied_until = now + timeout`.

### Step 4: Vacancy Cleanup

- If state transitions to Vacant (via timeout check or manual force):

- Clear `active_occupants`.

- Clear `active_holds` (Force reset).

- `occupied_until` = `None`.

---

## 4. Hierarchy & Propagation

Propagation is **Recursive** and **Child-Driven**.

### The Trigger

Propagation runs when a Child Location:

1. Transitions Vacant -> Occupied.

2. Extends its time (or enters "Indefinite Hold").

3. Updates its `active_occupants`.

### The Payload (Synthetic Event)

The Child sends an event to the Parent:

- **`event_type`**: `PROPAGATED`

- **`category`**: "propagated"

- **`source_id`**: Child Location ID.

- **`active_holds`**: If Child is held, Parent treats it as a Hold.

### Vacancy Logic

- **Vacancy DOES NOT bubble up.**

- When a Child goes Vacant, the Parent does *nothing*. The Parent relies on its own timer.

---

## 5. The "Wake Me Up" Timer Protocol (Inversion of Control)

1. **Calculate:** The Engine scans all locations.

   - If `active_holds` is not empty -> Ignore (No timer needed).

   - If `occupied_until` exists -> Collect timestamp.

2. **Return:** `EngineResult` includes `next_expiration` (Earliest datetime found).

3. **Contract:** Host MUST call `Engine.check_timeouts(now)` at that time.
