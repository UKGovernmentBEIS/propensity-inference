from collections.abc import Callable

from inspect_ai.scorer import Scorer

from lib.scorers.refusal_scorer import refusal_scorer

SCORER_REGISTRY: dict[str, Callable[[], Scorer]] = {
    "refusal": refusal_scorer,
}
