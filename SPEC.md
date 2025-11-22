# Occupancy Manager - Library Specification (v4.0)

## 1. System Overview

**Occupancy Manager** is a hierarchical occupancy tracking engine. It accepts raw inputs (events) from sensors, calculates the state of logical "Locations" (Rooms, Floors, Zones), and maintains a hierarchy where occupancy bubbles up (Child -> Parent).

This is a **Pure Python Library** (`src/occupancy_manager`). It is agnostic to the host platform.

---

## 2. Core Data Structures

### 2.1 The Location Configuration (`LocationConfig`)

- **`id`** (str): Unique identifier.

- **`parent_id`** (Optional[str]): Container location.

- **`occupancy_strategy`** (Enum):

  - `INDEPENDENT` (Default): Occupied only by own sensors or child propagation.

  - `FOLLOW_PARENT`: Occupied if own sensors trigger OR if Parent is Occupied. (Solves the "Living Room with no sensors" problem).

- **`contributes_to_parent`** (bool):

  - Default `True`.

  - If `False`, occupancy here DOES NOT bubble up. (Solves the "Backyard" problem).

- **`timeouts`** (Dict[str, int]): Base timeouts (e.g., `{ "motion": 10 }`).

### 2.2 The Runtime State (`LocationRuntimeState`)

Immutable snapshot.

- **`is_occupied`** (bool): True if currently occupied.

- **`occupied_until`** (Optional[datetime]): The wall-clock time when vacancy occurs.

- **`active_occupants`** (Set[str]): Verified identities (e.g., "Mike").

- **`active_holds`** (Set[str]): Sources holding the room open (e.g., Radar, Media).

- **`lock_state`** (Enum): `UNLOCKED` vs `LOCKED_FROZEN`.

### 2.3 The Input (`OccupancyEvent`)

- **`event_type`**: `MOMENTARY`, `HOLD_START`, `HOLD_END`, `MANUAL`, `LOCK_CHANGE`.

- **`category`**: Config key for timeout lookup.

- **`source_id`**: Device ID.

- **`occupant_id`**: Optional identity.

- **`duration`**: Optional override.

---

## 3. The Logic Engine (`Engine.handle_event`)

### Step 1: Lock Check

If `lock_state` is `LOCKED_FROZEN`:

- Ignore all events EXCEPT `MANUAL` or `LOCK_CHANGE`.

- **Crucial:** If a Child propagates occupancy to a Locked Parent, the Parent IGNORES it.

### Step 2: Update State (Holds & Identity)

1. **Identity Logic:**
   - **Arrival (`HOLD_START` + `occupant_id`):** Add person to `active_occupants`.
   - **Departure (`HOLD_END` + `occupant_id`):** Remove specific person from `active_occupants`.
   - **Action (`MOMENTARY` + `occupant_id`):** Add person (inferred presence from button press/lock code).
   - **Note:** Presence is treated as a continuous state (hold). Individual departures are tracked, allowing one person to leave while others remain.

2. **Hold Logic:** Add/Remove `source_id` from `active_holds`.

### Step 3: Determine Occupancy Status

A location is **Occupied** if ANY of the following are true:

1. **Timer Active:** `now < occupied_until`.

2. **Hold Active:** `active_holds` is not empty.

3. **Identity Present:** `active_occupants` is not empty.

4. **Child Propagated:** A child location is reporting Occupancy (AND `Child.contributes_to_parent == True`).

5. **Parent Followed:** `config.occupancy_strategy == FOLLOW_PARENT` AND `Parent.is_occupied == True`.

### Step 4: Calculate Expiration (Momentary vs Hold Release)

- **Momentary Event:** `occupied_until = now + timeout`. (Transient signal resets timer)

- **Hold Release:** When `active_holds` empties, `occupied_until = now + trailing_timeout`. (Fudge factor applied)

### Step 5: Vacancy Cleanup

- If transitioning to Vacant: Clear `active_occupants` and `active_holds`.

---

## 4. Hierarchy & Propagation

### The Trigger

Propagation runs when a Child Location:

1. Transitions Vacant -> Occupied.

2. Extends its time.

3. Updates its `active_occupants`.

### The "Backyard" Filter

Before propagating, check `Child.config.contributes_to_parent`.

- If `False`: **STOP.** Do not send synthetic event to Parent.

### The "Lock" Filter

When Parent receives event:

- If Parent is `LOCKED_FROZEN`: **STOP.** Ignore the child update.

### Lock Propagation Rule (CRITICAL)

- **Lock State is LOCAL.** It does NOT propagate up or down.

- **However:** If a Child is Locked Occupied, it reports `is_occupied=True` to the Parent (if `contributes_to_parent == True`).

- **Result:** The Parent will naturally stay Occupied (via standard propagation) but is NOT itself Locked (it can still process its own events).

- **Locking Down:** Locking a Parent does *not* force the Children to wake up. Children maintain independent behavior.

---

## 5. Locking Logic

### 5.1 Lock States

- **`UNLOCKED`**: Normal operation.

- **`LOCKED_FROZEN`**: Ignores all events (Momentary & Hold) except `MANUAL` or `LOCK_CHANGE`.

  - Used for: "Don't change anything, just leave it as is."

### 5.2 Behavior

- **If Locked Occupied:** The Location is effectively in an "Indefinite Hold." It will propagate `is_occupied=True` up the tree (if `contributes_to_parent == True`).

- **If Locked Vacant:** The Location is effectively disabled. It will not propagate anything.

---

## 6. The "Wake Me Up" Timer Protocol (Inversion of Control)

1. **Calculate:** The Engine scans all locations.

   - If `active_holds` is not empty -> Ignore (No timer needed).

   - If `occupied_until` exists -> Collect timestamp.

2. **Return:** `EngineResult` includes `next_expiration` (Earliest datetime found).

3. **Contract:** Host MUST call `Engine.check_timeouts(now)` at that time.

---

## 7. State Serialization and Hydration

The Library provides methods for exporting and restoring state, enabling persistence across restarts.

### 7.1 Export State (`export_state()`)

Creates a JSON-serializable snapshot of the current engine state.

- **Returns:** `dict[str, dict]` with location IDs as keys
- **Format:** Each location contains `is_occupied`, `occupied_until` (ISO string), `active_occupants` (list), `active_holds` (list), `lock_state` (string)
- **Optimization:** Only exports non-default states (skips vacant, unlocked locations with no occupants/holds)

### 7.2 Restore State (`restore_state()`)

Hydrates engine state from a snapshot with **Stale Data Protection**.

**Restoration Rules:**

1. **Locked Frozen States:** Always restore (timeless, for party mode)
2. **Active Occupants/Holds:** Override expired timers (trust the data)
3. **Expired Timers:** Force vacancy if `occupied_until < now` (unless occupants/holds present)
4. **Invalid Data:** Gracefully handles missing locations, invalid datetimes

**Usage:**

```python
# Host saves state on shutdown
snapshot = engine.export_state()
save_to_disk(snapshot)

# Host restores on startup
snapshot = load_from_disk()
engine.restore_state(snapshot, dt_util.utcnow())
engine.check_timeouts(dt_util.utcnow())  # Clean up any about-to-expire timers
```

### 7.3 Stale Data Protection

The restore process automatically handles stale data:

- **Quick Restart (< timeout):** Everything persists normally
- **Long Outage (> timeout):** Expired timers cleared, occupants/holds preserved
- **Locked States:** Always restore regardless of time (timeless)
