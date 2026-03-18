"""
Entry script to the "p" CLI command.
"""

from scripts.eval_awareness import cli as eval_awareness_cli
from scripts.log_followup import log_followup
from scripts.run_scenarios import ScenarioCommands


class MainCLI:
    """Entry script to all things propensity."""

    list = staticmethod(ScenarioCommands().list)
    sample = staticmethod(ScenarioCommands().sample)
    followup = staticmethod(log_followup)
    eval_awareness = staticmethod(eval_awareness_cli)


def main():
    import fire.core

    fire.core.Display = lambda lines, out: print("\n".join(lines), file=out)
    fire.Fire(MainCLI)


if __name__ == "__main__":
    main()
