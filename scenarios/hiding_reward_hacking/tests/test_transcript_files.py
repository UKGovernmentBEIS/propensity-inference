from pathlib import Path

from scenarios.hiding_reward_hacking.create_scenario import create_scenario


def test_files_are_exact_matches():
    scenario = create_scenario()
    assert scenario.variations is not None
    variation = scenario.variations["hiding_reward_hacking"]
    suite_name, suite_space = next(iter(variation.suites.items()))

    space = suite_space()

    all_files = set()
    for path in Path("scenarios/hiding_reward_hacking/templates/transcripts/").glob(
        "**/*.txt"
    ):
        with open(path) as f:
            all_files.add(f.read())
    for params in space.sample_uniformly_random(2):
        task = scenario.params_to_task(params)
        print(f"{task.dataset=}")
        print(f"{task.dataset[-1]=}")
        print(task)
        assert len(task.dataset) > 0
        for sample in task.dataset:
            if not sample.files:
                continue

            # Get ground truth position from metadata
            assert sample.metadata is not None, "Sample metadata is None"
            ground_truth_position = sample.metadata.get("ground_truth_position")
            assert ground_truth_position is not None, (
                "Ground truth position not found in metadata"
            )
            ground_truth_filename = (
                f"user_attachments/transcript_{ground_truth_position:03d}.txt"
            )

            for name, content in sample.files.items():
                if name == "user_input/message_1.md":
                    continue
                # Skip technical report - it's a filled template, not a raw transcript file
                if name == "user_attachments/technical_report_reward_hacking.md":
                    continue
                assert content in all_files, (
                    f"File not found, {name=}. Truncated content:\n{content[:200]}\n\n*********************************************\n\n"
                )
                # Check that the file at the ground truth position contains reward hacking marker
                if name == ground_truth_filename:
                    assert "fake_time" in content, (
                        f"Ground truth file {name} should contain 'fake_time'"
                    )
