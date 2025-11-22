# Testing Protocol

This document outlines the testing strategy and protocols for the Occupancy Manager library.

## Test Structure

The test suite is organized into focused test files:

- `test_model.py` / `test_model_v2.py`: Data structure validation
- `test_engine_basic.py`: Basic event handling (legacy v1.0 tests)
- `test_engine_locking.py`: Lock state logic
- `test_engine_hierarchy.py`: Propagation and hierarchy
- `test_engine_identity.py`: Identity tracking
- `test_engine_v2.py`: **v2.0 Hold/Pulse logic and Fudge Factor**

## Testing Principles

### 1. Time-Agnostic Testing

All tests pass `now` as an argument. Never use `datetime.now()` in tests.

```python
now = datetime(2025, 1, 1, 12, 0, 0)
result = engine.handle_event(event, now, states)
```

### 2. Immutable State

All state objects are frozen dataclasses. Use `dataclasses.replace()` to create new states.

### 3. Coverage Requirements

- **100% coverage** for `src/occupancy_manager/`
- All public methods must have tests
- Edge cases must be covered

## Test Categories

### Pulse Events (MOTION)

**Purpose**: Test that pulse events reset/extend timers.

**Key Scenarios**:
- Vacant → Occupied (timer starts)
- Occupied → Extended (timer extends if new > old)
- Occupied → Ignored (timer doesn't shorten)

**Example**:
```python
def test_pulse_event_motion_resets_timer(engine):
    # Motion event should set 10 minute timer
    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.MOTION,
        category="motion",
        source_id="binary_sensor.motion",
        timestamp=now,
    )
    # Verify occupied_until is set correctly
```

### Hold Events (HOLD_START/HOLD_END)

**Purpose**: Test that hold events pause timers and apply fudge factor.

**Key Scenarios**:
- HOLD_START → Room becomes indefinitely occupied
- HOLD_END → Trailing timeout (fudge factor) applied
- Multiple holds → Room stays occupied until all released
- Hold + Occupants → Still indefinitely occupied

**Example**:
```python
def test_hold_end_fudge_factor(engine):
    # When hold ends, should apply trailing timeout
    event = OccupancyEvent(
        location_id="kitchen",
        event_type=EventType.HOLD_END,
        category="presence",  # 2 minute trailing timeout
        source_id="binary_sensor.mmwave",
        timestamp=now,
    )
    # Verify occupied_until = now + 2 minutes
```

### Identity Tracking

**Purpose**: Test occupant tracking and cleanup.

**Key Scenarios**:
- Occupant added on event
- Occupant persists across events
- Occupants cleared on vacancy (Ghost Mike fix)
- Occupants propagate to parent

### Propagation

**Purpose**: Test hierarchical behavior.

**Key Scenarios**:
- Child → Parent propagation
- Vacancy does NOT bubble up
- Hold state propagates as hold
- Timer state propagates with remaining duration

### Lock State

**Purpose**: Test locking logic.

**Key Scenarios**:
- LOCKED_FROZEN ignores MOTION
- LOCKED_FROZEN allows MANUAL
- LOCKED_FROZEN allows LOCK_CHANGE

## Running Tests

### Basic Test Run

```bash
pytest tests/
```

### With Coverage

```bash
pytest --cov=src/occupancy_manager --cov-report=term-missing
```

### Specific Test File

```bash
pytest tests/test_engine_v2.py -v
```

### Specific Test

```bash
pytest tests/test_engine_v2.py::test_hold_end_fudge_factor -v
```

## Test Data Patterns

### Minimal Config

```python
config = LocationConfig(
    id="kitchen",
    timeouts={"motion": 10, "presence": 2}
)
```

### Empty State

```python
state = LocationRuntimeState(is_occupied=False)
```

### Held State

```python
state = LocationRuntimeState(
    is_occupied=True,
    occupied_until=None,
    active_holds={"binary_sensor.mmwave"}
)
```

### Occupied with Timer

```python
state = LocationRuntimeState(
    is_occupied=True,
    occupied_until=now + timedelta(minutes=10)
)
```

## Assertion Patterns

### State Transitions

```python
assert len(result.transitions) == 1
new_state = result.transitions[0][1]
assert new_state.is_occupied is True
```

### Timer Values

```python
assert new_state.occupied_until == now + timedelta(minutes=10)
```

### Hold Sets

```python
assert "binary_sensor.mmwave" in new_state.active_holds
assert len(new_state.active_holds) == 2
```

### Next Expiration

```python
assert result.next_expiration == now + timedelta(minutes=10)
# Or None if held
assert result.next_expiration is None
```

## Common Pitfalls

1. **Forgetting to pass `now`**: Always pass explicit datetime
2. **Using mutable sets**: Use `set()` not `frozenset()` for dataclass fields
3. **Not checking all transitions**: Propagation may create multiple transitions
4. **Ignoring None values**: `occupied_until=None` means indefinitely occupied

## Continuous Integration

Tests should run on:
- Every commit
- Before merging PRs
- Before releases

Target: **100% coverage, 0 failures**

