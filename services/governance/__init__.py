"""
Shared cloudcare:* governance-tag conventions (Phase 15).

Three of these conventions used to live in three unrelated places with no
shared home: services/analyzer/rules.py's own is_excluded(), the executor's
execution_allowlist_tag setting, and its schedule_tag_key constant. This
package is the one place new conventions (max-risk) and the tag-parsing
logic itself get added, without every caller re-implementing tag lookups.
"""
