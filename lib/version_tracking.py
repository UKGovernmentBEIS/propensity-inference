"""Version tracking utilities.

Simplified for public release — returns the static package version.
"""

from importlib.metadata import PackageNotFoundError, version


def get_current_version() -> str:
    """Get the current version of the package.

    Returns:
        Current version string.
    """
    try:
        return version("propensity-inference")
    except PackageNotFoundError:
        return "unknown"
