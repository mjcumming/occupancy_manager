# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Individual occupant departure tracking: `HOLD_END` events with `occupant_id` now remove specific occupants while keeping the room occupied if others remain
- Comprehensive test suite with complex scenario coverage
- GitHub Actions CI/CD workflows for linting, testing, and automated releases

### Changed
- Identity management now treats presence as a continuous state (hold)
- Improved documentation with identity tracking examples

### Fixed
- Bug where individual occupant departures were not processed correctly
- Room would remain occupied for all occupants until the last person left

## [0.1.0] - 2025-01-XX

### Added
- Initial release
- Hierarchical location tracking with parent-child relationships
- Identity management for tracking active occupants
- Locking logic for freezing location state
- Multiple occupancy strategies (INDEPENDENT, FOLLOW_PARENT)
- Support for momentary events, holds, and manual overrides
- Time-agnostic design (all time operations accept `now` as argument)
- Pure Python implementation with no external dependencies

[Unreleased]: https://github.com/yourusername/occupancy-manager/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yourusername/occupancy-manager/releases/tag/v0.1.0

