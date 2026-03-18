"""Compatibility patch for hibayes LogSample.

hibayes's patched eval recorder uses a lightweight LogSample class with only
`id` and `epoch` fields for header-only reads. Newer versions of inspect_ai
(>= 0.3.197) call resolve_sample_message_pool() on every sample after reading,
which accesses `message_pool` and `call_pool` — fields LogSample doesn't have.

This patch adds the missing fields with empty-list defaults so that
resolve_sample_message_pool() finds them falsy and returns immediately.
"""

import logging

logger = logging.getLogger(__name__)


def apply_hibayes_logsample_patch() -> None:
    """Patch hibayes LogSample to add missing message_pool and call_pool fields."""
    try:
        from hibayes.load.utils.patch_inspect_loader import LogSample

        needs_patch = not hasattr(LogSample, "message_pool") or not hasattr(
            LogSample, "call_pool"
        )
        if not needs_patch:
            return

        # Add fields with empty-list defaults via model_rebuild
        from pydantic import Field

        LogSample.model_fields["message_pool"] = Field(default_factory=list)
        LogSample.model_fields["call_pool"] = Field(default_factory=list)
        LogSample.__annotations__["message_pool"] = list
        LogSample.__annotations__["call_pool"] = list
        LogSample.model_rebuild(force=True)

        logger.debug("Patched hibayes LogSample with message_pool/call_pool fields")
    except ImportError:
        pass  # hibayes not installed
    except Exception as e:
        logger.warning(f"Failed to patch hibayes LogSample: {e}")
