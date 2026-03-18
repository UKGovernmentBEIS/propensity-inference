# Cross-Scenario Parameter Usage Validation

## Overview

`test_parameter_usage_all_scenarios.py` automatically validates that all parameters defined in scenario parameter spaces are actually used in templates.

## What It Does

1. **Auto-discovers** all scenarios in `scenarios/` directory
2. **Checks** which scenarios support tracking
3. **Tests** scenarios by:
   - Sampling 5 random parameter combinations
   - Assembling with `track_usage=True`
   - Comparing accessed vs. defined parameters
   - Failing if unexpected unused parameters are found

## Running the Tests

```bash
# Run all parameter validation tests
pytest tests/test_parameter_usage_all_scenarios.py -v

# Run just the cross-scenario test
pytest tests/test_parameter_usage_all_scenarios.py::test_scenario_parameter_usage -v

# Run validation for a specific scenario (use pytest -k filter)
pytest tests/test_parameter_usage_all_scenarios.py -k sem_v2 -v
```

## Test Results

- ✅ **PASSED**: All parameters are used (or are known exceptions)
- ❌ **FAILED**: Unused parameters detected (needs fixing)
- ⏭️ **SKIPPED**: Scenario opted out or doesn't support tracking

## Configuration

### Opting Out Scenarios

Add to `OPTED_OUT_SCENARIOS` in the test file:

```python
OPTED_OUT_SCENARIOS = {
    "agentic_misalignment",  # Old architecture
    "gpu_decision_email_assistant",  # Not converted to TemplateEngine yet
}
```

### Known Exceptions

Some parameters are legitimately unused in templates (used in Python logic instead):

```python
KNOWN_EXCEPTIONS = {
    "sem_v2": {
        "_false_alarms_combo",  # Used to select which files to load
        "_true_positive_file",   # Used to select which file to load
        "report_start_index",    # Used for file numbering
        "user_instruction",      # Passed through directly
    },
}
```

## When Tests Fail

If the test fails with unexpected unused parameters:

```
sem_v2: Found 1 unexpected unused parameters:
  ['foo']

These parameters are defined in the parameter space but never accessed in templates.
Either:
  1. Remove them from the parameter space if truly unused
  2. Add them to KNOWN_EXCEPTIONS if they're used in Python logic
  3. Fix templates to actually use these parameters
```

**Resolution steps:**
1. **Check if it's a bug**: Is the parameter supposed to be used? Add it to templates.
2. **Check if it's used in Python**: Is it used for control flow? Add to `KNOWN_EXCEPTIONS`.
3. **Check if it's dead code**: Not needed anymore? Remove from parameter space.

## Adding New Scenarios

When you create a new scenario with TemplateEngine support:

1. **Automatic discovery**: The test will automatically find it
2. **No opt-out needed**: If it has `SUITES` and `track_usage`, it will be tested
3. **Add exceptions**: If it has known exceptions, add them to `KNOWN_EXCEPTIONS`

Example:
```python
KNOWN_EXCEPTIONS = {
    "sem_v2": {...},
    "my_new_scenario": {
        "_internal_param",  # Used in Python logic
        "control_variable",  # Used for conditional logic
    },
}
```

## Benefits

- 🔍 **Catches unused parameters** across all scenarios automatically
- 🚀 **CI/CD ready** - fails fast when parameters are added but not used
- 🔧 **Easy maintenance** - new scenarios are auto-discovered
- 📊 **Clear errors** - detailed messages explain what's wrong and how to fix

## Implementation Details

The test uses the tracking feature from `lib/template_engine.py`:
- Calls `assembler.assemble(params, track_usage=True)`
- Compares `result['usage_info']['accessed_variables']` against `ParameterSpace.get_all_variables()`
- Accounts for legitimate exceptions via `KNOWN_EXCEPTIONS`

See `lib/TEMPLATE_ENGINE_TRACKING.md` for more on the tracking system.
