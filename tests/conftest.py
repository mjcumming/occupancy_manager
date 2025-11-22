"""Pytest configuration for occupancy manager tests."""

import logging

# Configure logging for tests
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)8s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

# Set the engine logger to INFO level
logging.getLogger("occupancy_manager.engine").setLevel(logging.INFO)

