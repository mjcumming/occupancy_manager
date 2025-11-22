# Occupancy Manager - Technical Design Specification

## 1. System Overview

**Occupancy Manager** is a hierarchical occupancy tracking engine. It accepts raw inputs (events) from sensors, calculates the state of logical "Locations" (Rooms, Floors, Zones), and maintains a hierarchy where occupancy bubbles up (Child -> Parent).

It is designed as a **Pure Python Library** (`library/`) that is hosted by an **Integration** (`custom_components/`). The Library is stateless regarding I/O and time; it receives state and time as inputs and returns state transitions and scheduling instructions as outputs.

---

## 2. Core Data Structures

### 2.1 The Location Configuration (`LocationConfig`)

Static rules defining a node in the hierarchy.

- **`id`** (str): Unique identifier (e.g., "kitchen", "main_floor").

- **`parent_id`** (Optional[str]): The ID of the container location.

- **`kind`** (Enum):

  - `AREA`: Represents a physical room (linked to HA Area).

  - `VIRTUAL`: Represents a logical container (Floor/Zone).

- **`timeouts`** (Dict): Base timeout duration (e.g., `{ "motion": 10m, "door": 5m }`).

### 2.2 The Runtime State (`LocationRuntimeState`)

Immutable snapshot of a location at a specific moment.

- **`is_occupied`** (bool): True if currently occupied.

- **`occupied_until`** (Optional[datetime]): The wall-clock time when vacancy occurs.

- **`active_occupants`** (Set[str]): A list of verified identities (e.g., "person.mike") currently in the space.

- **`lock_state`** (Enum):

  - `UNLOCKED`: Normal operation.

  - `LOCKED_FROZEN`: State is frozen. Ignores all standard events.

### 2.3 The Input (`OccupancyEvent`)

A signal from the outside world.

- **`event_type`** (Enum): `MOTION`, `DOOR`, `MEDIA`, `PRESENCE`, `MANUAL`, `LOCK_CHANGE`.

- **`occupant_id`** (Optional[str]): Identity associated with the event (e.g., "Mike" unlocked door).

- **`duration`** (Optional[timedelta]): Overrides the default timeout (e.g., "Sauna" sets 60m).

- **`force_state`** (Optional[bool]):

  - `True`: Force Occupied.

  - `False`: Force Vacant.

  - `None`: Standard calculation.

---

## 3. The Logic Engine (`Engine.handle_event`)

The Engine processes one event at a time. The logic flow is strict:

### Step 1: Lock Check

If `Location.lock_state` is `LOCKED_FROZEN`:

- Is the event type `MANUAL` or `LOCK_CHANGE`?

  - **Yes:** Process the event.

  - **No:** **DROP THE EVENT.** Return no changes.

### Step 2: Timeout Calculation

Determine the `new_expiry` time.

1. If `event.duration` is provided, use it.

2. Else, lookup default timeout for `event.event_type` in `LocationConfig`.

3. `new_expiry = event.timestamp + duration`.

### Step 3: State Transition Rules

Compare `new_expiry` against `current_state.occupied_until`.

- **Rule A (Vacant -> Occupied):**

  - If currently Vacant: Set `is_occupied=True`, `occupied_until=new_expiry`.

  - **Action:** Emit Transition (OCCUPIED). Trigger Propagation.

- **Rule B (Occupied -> Extend):**

  - If currently Occupied AND `new_expiry > current_state.occupied_until`:

  - Update `occupied_until` to `new_expiry`.

  - **Action:** Emit Transition (EXTENDED). Trigger Propagation.

- **Rule C (Occupied -> Ignore):**

  - If currently Occupied AND `new_expiry <= current_state.occupied_until`:

  - Do nothing. The existing timer is longer than the new event.

### Step 4: Identity Logic

- If `event.occupant_id` is present, add it to `state.active_occupants`.

- If `event.force_state` is `False` (Forced Vacancy), clear `active_occupants`.

---

## 4. Hierarchy & Propagation (`_propagate_up`)

Propagation is **Recursive** and **Child-Driven**.

### Trigger

Propagation runs ONLY when a Child Location:

1. Transitions from **Vacant -> Occupied**.

2. Extends its `occupied_until` time.

3. Updates its `active_occupants` list.

### The Propagation Payload

When Child updates, it generates a synthetic event for the Parent:

- **`event_type`**: `PROPAGATED`

- **`duration`**: The *remaining* duration of the Child (Child.occupied_until - now).

- **`occupant_id`**: The occupants of the Child (merged).

### Vacancy Logic (Crucial)

**Vacancy DOES NOT propagate instantly.**

- When a Child goes Vacant, it does *not* force the Parent to go Vacant.

- The Parent relies on its own timer (which was last updated by the Child's previous "Extend" event).

- **Why:** This prevents "Racing Timers" where a Parent goes dark while you are walking between rooms.

---

## 5. The "Wake Me Up" Timer Protocol (Inversion of Control)

The Library strictly avoids internal scheduling.

1. **Calculate:** The Engine determines the earliest `occupied_until` timestamp across all locations.

2. **Return:** The `EngineResult` object includes `next_expiration` (datetime).

3. **Schedule:** The Host (Integration) sees `next_expiration` and uses `async_track_point_in_time` to wake up the Engine.

4. **Callback:** When the timer fires, the Host calls `Engine.check_timeouts(now)`.

---

## 6. Implementation Guidelines

- **Dataclasses:** All state objects must be `frozen=True`. Use `dataclasses.replace()` to create new states.

- **Time:** Never use `datetime.now()`. All functions accept `now` as an argument.

- **Typing:** Strict Python typing is required. No `Any`.
