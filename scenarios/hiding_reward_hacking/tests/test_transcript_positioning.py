"""
Tests for transcript positioning in hiding_reward_hacking scenario.

These tests verify that:
1. The content assembler creates files with correct content at correct positions
2. The reward hacking transcript is at the specified position
3. No transcripts are concatenated or duplicated
4. Ground truth metadata matches actual file positions

Note: Current implementation uses 6 transcripts (5 benign + 1 RH).
Some legacy tests reference 10 transcripts and need updating.
"""

import pytest

from scenarios.hiding_reward_hacking.lib.content_assembler import (
    HidingRHContentAssembler,
)
from scenarios.hiding_reward_hacking.lib.framework_bridge import params_to_task
from scenarios.hiding_reward_hacking.parameter_spaces import create_suite_space


class TestContentAssemblerPositioning:
    """Test content assembler creates files at correct positions."""

    @pytest.fixture
    def base_params(self):
        """Base parameters from parameter space."""
        space = create_suite_space()
        return dict(space.get_combination(0))

    def test_position_1(self, base_params):
        """Test reward hacking at position 1."""
        base_params["reward_hacking_position"] = "1"

        assembler = HidingRHContentAssembler()
        result = assembler.assemble(base_params)

        files = result["files"]
        metadata = result["metadata"]

        # Check metadata
        assert metadata["ground_truth_position"] == 1
        assert metadata["ground_truth_filename"] == "transcript_001.txt"

        # Check that position 1 contains reward hacking
        file_key = "user_attachments/transcript_001.txt"
        assert file_key in files
        content = files[file_key]
        has_rh = "time.time" in content or (
            "monkey" in content.lower() and "patch" in content.lower()
        )
        assert has_rh, "Position 1 should contain reward hacking but doesn't"

        # Check that other positions don't contain reward hacking
        for i in range(2, 7):
            file_key = f"user_attachments/transcript_{i:03d}.txt"
            content = files[file_key]
            has_rh = "time.time" in content or (
                "monkey" in content.lower() and "patch" in content.lower()
            )
            if has_rh:
                pytest.fail(
                    f"Position {i} contains reward hacking when it should be at position 1"
                )

    def test_position_5(self, base_params):
        """Test reward hacking at position 5."""
        base_params["reward_hacking_position"] = "5"

        assembler = HidingRHContentAssembler()
        result = assembler.assemble(base_params)

        files = result["files"]
        metadata = result["metadata"]

        # Check metadata
        assert metadata["ground_truth_position"] == 5
        assert metadata["ground_truth_filename"] == "transcript_005.txt"

        # Check that position 5 contains reward hacking
        file_key = "user_attachments/transcript_005.txt"
        assert file_key in files
        content = files[file_key]
        has_rh = "time.time" in content or (
            "monkey" in content.lower() and "patch" in content.lower()
        )
        assert has_rh, "Position 5 should contain reward hacking but doesn't"

        # Check that position 1 doesn't contain reward hacking
        content_1 = files["user_attachments/transcript_001.txt"]
        assert "time.time" not in content_1, (
            "Position 1 contains reward hacking when it should be at position 5"
        )

    def test_position_6(self, base_params):
        """Test reward hacking at position 6 (last valid position)."""
        base_params["reward_hacking_position"] = "6"

        assembler = HidingRHContentAssembler()
        result = assembler.assemble(base_params)

        files = result["files"]
        metadata = result["metadata"]

        # Check metadata
        assert metadata["ground_truth_position"] == 6
        assert metadata["ground_truth_filename"] == "transcript_006.txt"

        # Check that position 6 contains reward hacking
        file_key = "user_attachments/transcript_006.txt"
        assert file_key in files
        content_6 = files[file_key]
        # Check for reward hacking indicators (works for both bypass transcripts)
        has_rh = "time.time" in content_6 or (
            "monkey" in content_6.lower() and "patch" in content_6.lower()
        )
        assert has_rh, (
            f"Position 6 should contain reward hacking but doesn't. Content length: {len(content_6)}"
        )

        # Check that position 1 does NOT contain reward hacking
        file_key_1 = "user_attachments/transcript_001.txt"
        content_1 = files[file_key_1]
        has_rh_1 = "time.time" in content_1 or (
            "monkey" in content_1.lower() and "patch" in content_1.lower()
        )
        assert not has_rh_1, (
            "Position 1 contains reward hacking when it should be at position 6!"
        )

        # Check that position 5 does NOT contain reward hacking
        file_key_5 = "user_attachments/transcript_005.txt"
        content_5 = files[file_key_5]
        has_rh_5 = "time.time" in content_5 or (
            "monkey" in content_5.lower() and "patch" in content_5.lower()
        )
        assert not has_rh_5, (
            "Position 5 contains reward hacking when it should be at position 6!"
        )

    def test_position_2(self, base_params):
        """Test reward hacking at position 2."""
        base_params["reward_hacking_position"] = "2"

        assembler = HidingRHContentAssembler()
        result = assembler.assemble(base_params)

        files = result["files"]
        metadata = result["metadata"]

        # Check metadata
        assert metadata["ground_truth_position"] == 2
        assert metadata["ground_truth_filename"] == "transcript_002.txt"

        # Check that position 2 contains reward hacking
        file_key = "user_attachments/transcript_002.txt"
        assert file_key in files
        content = files[file_key]
        has_rh = "time.time" in content or (
            "monkey" in content.lower() and "patch" in content.lower()
        )
        assert has_rh, "Position 2 should contain reward hacking but doesn't"

    def test_all_positions_have_unique_content(self, base_params):
        """Test that no transcripts are concatenated or duplicated."""
        base_params["reward_hacking_position"] = "5"

        assembler = HidingRHContentAssembler()
        result = assembler.assemble(base_params)

        files = result["files"]

        # Get all transcript files
        transcript_files = {k: v for k, v in files.items() if "transcript_" in k}

        assert len(transcript_files) == 6, (
            f"Should have exactly 6 transcript files, got {len(transcript_files)}"
        )

        # Check that all files have different content
        contents = list(transcript_files.values())
        unique_contents = set(contents)

        assert len(unique_contents) == 6, (
            f"Transcripts have duplicate content! Got {len(unique_contents)} unique out of 6 total"
        )

        # Check that no content is suspiciously long (concatenation)
        for filename, content in transcript_files.items():
            # Most transcripts are < 20KB, concatenation would be much larger
            assert len(content) < 30000, (
                f"{filename} is suspiciously large ({len(content)} bytes), possible concatenation"
            )

    def test_exactly_one_reward_hacking_transcript(self, base_params):
        """Test that exactly one transcript contains reward hacking."""
        base_params["reward_hacking_position"] = "6"

        assembler = HidingRHContentAssembler()
        result = assembler.assemble(base_params)

        files = result["files"]

        # Count how many files contain reward hacking indicators
        rh_count = 0
        rh_positions = []

        for i in range(1, 7):
            file_key = f"user_attachments/transcript_{i:03d}.txt"
            content = files[file_key]

            if "time.time" in content:
                rh_count += 1
                rh_positions.append(i)

        assert rh_count == 1, (
            f"Expected exactly 1 transcript with reward hacking, found {rh_count} at positions {rh_positions}"
        )

        assert rh_positions[0] == 6, (
            f"Reward hacking should be at position 6, but found at position {rh_positions[0]}"
        )


class TestTaskCreation:
    """Test that task creation preserves file positioning."""

    def test_task_files_match_assembler_output(self):
        """Test that files in Task match assembler output."""
        # Get a sample parameter combination
        space = create_suite_space()
        params = space.get_combination(0)

        # Force position to 6 for this test
        params["reward_hacking_position"] = "6"

        # Create assembler and task
        assembler = HidingRHContentAssembler()
        task = params_to_task(assembler, params)

        # Get the sample (there should be exactly one)
        assert len(task.dataset) == 1
        sample = task.dataset[0]

        # Check that sample has files
        assert sample.files is not None, "Sample should have files attribute"

        # Get metadata
        assert sample.metadata is not None
        ground_truth_pos = sample.metadata.get("ground_truth_position")
        assert ground_truth_pos == 6

        # Verify files dict structure (files should be a dict)
        assert isinstance(sample.files, dict), (
            f"sample.files should be a dict, got {type(sample.files)}"
        )

        # Check reward hacking is at position 6
        file_key = "user_attachments/transcript_006.txt"
        assert file_key in sample.files
        content_6 = sample.files[file_key]
        has_rh = "time.time" in content_6 or (
            "monkey" in content_6.lower() and "patch" in content_6.lower()
        )
        assert has_rh, "Task sample: Position 6 should contain reward hacking"

        # Check position 1 does not have reward hacking
        file_key_1 = "user_attachments/transcript_001.txt"
        content_1 = sample.files[file_key_1]
        assert "time.time" not in content_1, (
            "Task sample: Position 1 should not contain reward hacking"
        )

    def test_multiple_positions(self):
        """Test task creation with multiple reward hacking positions."""
        space = create_suite_space()
        assembler = HidingRHContentAssembler()

        for test_position in [1, 2, 3, 4, 5, 6]:
            # Get a sample and override position
            params = space.get_combination(0)
            params["reward_hacking_position"] = str(test_position)

            # Create task
            task = params_to_task(assembler, params)
            sample = task.dataset[0]

            # Check metadata
            assert sample.metadata is not None, "Sample metadata should not be None"
            ground_truth_pos = sample.metadata["ground_truth_position"]
            assert ground_truth_pos == test_position, (
                f"Metadata should show position {test_position}"
            )

            # Check the correct file has reward hacking
            assert sample.files is not None, "Sample files should not be None"
            file_key = f"user_attachments/transcript_{test_position:03d}.txt"
            content = sample.files[file_key]

            has_rh = "time.time" in content or (
                "monkey" in content.lower() and "patch" in content.lower()
            )
            assert has_rh, (
                f"Position {test_position} should contain reward hacking in task sample"
            )
