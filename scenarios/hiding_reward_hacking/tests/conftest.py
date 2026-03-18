"""Pytest configuration for hiding_reward_hacking tests."""

import pytest


def pytest_addoption(parser):
    """Add custom pytest CLI options."""
    parser.addoption(
        "--n-iterations",
        action="store",
        default=20,
        type=int,
        help="Number of iterations to run (default: 20)",
    )
    parser.addoption(
        "--phase",
        action="store",
        default=1,
        type=int,
        help="Solver phase: 1=check position 3 only, 2=scan all positions (default: 1)",
    )


@pytest.fixture
def n_iterations(request):
    """Get number of iterations from CLI."""
    return request.config.getoption("--n-iterations")


@pytest.fixture
def solver_phase(request):
    """Get solver phase from CLI."""
    return request.config.getoption("--phase")
