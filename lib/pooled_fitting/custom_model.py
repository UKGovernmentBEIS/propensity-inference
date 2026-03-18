"""Custom HiBayES model with per-variable prior support.

Default priors:
- model_variation (pair intercepts): N(-3, 3²)
- Interaction effects: N(0, 0.3²) - configurable via prior_interaction_scale
- All other main effects: N(0, 1²) - configurable via prior_main_effects_scale

Both use effect coding. Post-hoc normalization skips model_variation.
"""

from typing import cast

import jax
import jax.numpy as jnp
import numpyro
import numpyro.distributions as dist
from hibayes.model.models import Features, Model, check_features, model
from numpyro._typing import DistributionT


@model
def linear_group_binomial_pervar(
    main_effects: list[str] | None = None,
    interactions: list[tuple[str, str]] | None = None,
    prior_main_effects_loc: dict[str, float] | None = None,
    prior_main_effects_scale: dict[str, float] | None = None,
    prior_interaction_scale: float = 0.3,
) -> Model:
    """Linear binomial with per-variable prior support.

    Args:
        main_effects: List of categorical variables
        interactions: List of tuples specifying interactions
        prior_main_effects_loc: Dict mapping variable name to prior mean
        prior_main_effects_scale: Dict mapping variable name to prior scale
        prior_interaction_scale: Prior scale for interaction effects (default 0.3)
    """
    from hibayes.model.models import create_interaction_effects

    if prior_main_effects_loc is None:
        prior_main_effects_loc = {}
    if prior_main_effects_scale is None:
        prior_main_effects_scale = {}

    def model_fn(features: Features) -> None:
        required_features = ["obs", "n_total"]

        if main_effects:
            for effect in main_effects:
                required_features.extend([f"{effect}_index", f"num_{effect}"])

        if interactions:
            for var1, var2 in interactions:
                for feat in [
                    f"{var1}_index",
                    f"num_{var1}",
                    f"{var2}_index",
                    f"num_{var2}",
                ]:
                    if feat not in required_features:
                        required_features.append(feat)

        check_features(features, required_features)

        logit_p = 0.0

        if main_effects:
            for effect in main_effects:
                n_levels = int(features[f"num_{effect}"])
                idx = features[f"{effect}_index"]

                loc = prior_main_effects_loc.get(effect, 0.0)
                scale = prior_main_effects_scale.get(effect, 1.0)
                prior = dist.Normal(loc, scale)

                if n_levels > 1:
                    # cast needed: numpyro Distribution doesn't satisfy its own DistributionT protocol
                    free_coefs = numpyro.sample(
                        f"{effect}_effects_constrained",
                        cast(DistributionT, prior.expand((n_levels - 1,))),
                    )
                    last_coef = -jnp.sum(free_coefs)
                    coefs = jnp.concatenate([free_coefs, jnp.array([last_coef])])
                    numpyro.deterministic(f"{effect}_effects", coefs)
                else:
                    coefs = jnp.array([0.0])

                logit_p = logit_p + coefs[idx]

        if interactions:
            prior_interaction = dist.Normal(0.0, prior_interaction_scale)
            for var1, var2 in interactions:
                interaction_matrix = create_interaction_effects(
                    var1, var2, features, prior_interaction
                )
                idx1 = features[f"{var1}_index"]
                idx2 = features[f"{var2}_index"]
                logit_p = logit_p + interaction_matrix[idx1, idx2]

        # cast needed: numpyro Binomial doesn't satisfy its own DistributionT protocol
        numpyro.sample(
            "obs",
            cast(
                DistributionT,
                dist.Binomial(
                    total_count=int(features["n_total"]),
                    probs=jax.nn.sigmoid(logit_p),
                ),
            ),
            obs=features["obs"],
        )

    return model_fn


# The @model decorator automatically registers the model when this module is imported.
