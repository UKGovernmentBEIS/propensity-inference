"""Propensity Inference evaluation framework."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("propensity-inference")
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = ["__version__"]
