"""Next-action ranking and explain/next/tag prompt builders for pulse.

Public API re-exported for back-compat. Implementation lives in:
``prompt_common``, ``prompts_explain``, ``prompts_next``, ``prompts_tag``.
"""

from __future__ import annotations

from pulse_lib.prompt_common import (
    SPECKIT_LOOP,
    _card_path,
    _list_preview,
    _meta_flags,
    _quality_raise_block,
    _speckit_enabled,
    _speckit_feature_block,
    _speckit_next_playbook,
    _speckit_rules_block,
    feature_spec_insights,
    findings_for_feature,
    health_summary,
    inspect_spec_slice,
    load_mismatch_summary,
)
from pulse_lib.prompts_explain import (
    build_explain_feature_prompt,
    build_explain_project_prompt,
)
from pulse_lib.prompts_next import (
    _backlog_card_block,
    _backlog_speckit_block,
    _find_backlog_card,
    _recommended_action,
    build_backlog_action_prompt,
    build_next_action_prompt,
    list_sub_actions,
    rank_next_actions,
)
from pulse_lib.prompts_tag import build_tag_prompt, build_untagged_cleanup_prompt

__all__ = [
    "SPECKIT_LOOP",
    "build_backlog_action_prompt",
    "build_explain_feature_prompt",
    "build_explain_project_prompt",
    "build_next_action_prompt",
    "build_tag_prompt",
    "build_untagged_cleanup_prompt",
    "feature_spec_insights",
    "findings_for_feature",
    "health_summary",
    "inspect_spec_slice",
    "list_sub_actions",
    "load_mismatch_summary",
    "rank_next_actions",
    "_speckit_enabled",
]
