# Occupancy Manager (Library Spec)

## 1. Scope

This is a standalone Python library for managing hierarchical occupancy state.

It is **Input/Output only**. It does not access the system clock, network, or disk.

## 2. Architecture

- **Host Application:** The caller (e.g., Home Assistant, Flask, CLI). Responsible for I/O and Timers.

- **Engine:** The logic core. Receives events, returns state and scheduling instructions.

## 3. Data Model

- **`LocationConfig`**:
  - `id`: str
  - `parent_id`: Optional[str]
  - `timeouts`: Dict[EventType, int]

- **`LocationRuntimeState` (Frozen)**:
  - `is_occupied`: bool
  - `occupied_until`: Optional[datetime]
  - `active_occupants`: Set[str]
  - `lock_state`: Enum (UNLOCKED, LOCKED_FROZEN)

- **`OccupancyEvent`**:
  - `event_type`: Enum (MOTION, DOOR, PRESENCE, MANUAL)
  - `occupant_id`: Optional[str]
  - `duration`: Optional[timedelta]

## 4. The "Wake Me Up" Protocol

The Library strictly avoids internal scheduling.

1. **Input**: `Engine.handle_event(event, now)`

2. **Output**: `EngineResult` containing `next_expiration` (datetime).

3. **Contract**: The Host Application MUST call `Engine.check_timeouts(now)` at `next_expiration`.

## 5. Propagation Logic

- **Child -> Parent**: Occupancy and Identity bubble up.

- **Vacancy**: Does NOT bubble up. Parents expire on their own timers.

## 6. Development Rules

- Use `src/` layout.

- No external dependencies (Standard Library only).

- 100% Type Coverage (`mypy`).

- 100% Test Coverage (`pytest`).
