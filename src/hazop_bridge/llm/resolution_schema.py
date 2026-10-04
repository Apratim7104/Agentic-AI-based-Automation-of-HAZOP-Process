#!/usr/bin/env python3
"""resolution_schema.py Schema and validation for final HAZOP moderator resolution."""

EMIT_RESOLUTION_TOOL = {
    "type": "function",
    "function": {
        "name": "emit_resolution",
        "description": "Emit the final consensus or moderator resolution for a HAZOP deviation.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["none", "add", "modify", "remove", "manual_review"],
                    "description": "Recommended action: 'add' (new equipment like PSV, check valve), 'modify', 'remove', 'none', or 'manual_review'."
                },
                "equipment_type": {
                    "type": "string",
                    "enum": ["psv", "valve", "check_valve", "pump", "heat_exchanger", "vessel", "interlock", "instrument", "none"],
                    "description": "Type of equipment involved."
                },
                "target_tag": {
                    "type": "string",
                    "description": "Existing DEXPI equipment tag or line near which the action takes place."
                },
                "new_tag": {
                    "type": "string",
                    "description": "Suggested tag for the new equipment (e.g. PSV-001, CKV-001)."
                },
                "rationale": {
                    "type": "string",
                    "description": "Engineering rationale summarizing the consensus or moderator decision."
                },
                "consensus_level": {
                    "type": "string",
                    "enum": ["UNANIMOUS", "MAJORITY", "MODERATOR_OVERRULE"],
                    "description": "Level of agreement among the debate personas."
                },
                "safety_veto_exercised": {
                    "type": "boolean",
                    "description": "Whether the safety engineer exercised a veto on an unmitigated risk."
                }
            },
            "required": ["action", "equipment_type", "target_tag", "rationale", "consensus_level"]
        }
    }
}

class ResolutionValidationError(ValueError):
    pass

def validate_resolution(data: dict) -> dict:
    """Validate that the emitted resolution dictionary adheres to the schema."""
    if not isinstance(data, dict):
        raise ResolutionValidationError("Resolution must be a dictionary.")

    required_keys = ["action", "equipment_type", "target_tag", "rationale", "consensus_level"]
    for k in required_keys:
        if k not in data or data[k] is None:
            raise ResolutionValidationError(f"Missing required key in resolution: '{k}'")

    valid_actions = ["none", "add", "modify", "remove", "manual_review"]
    if data["action"] not in valid_actions:
        raise ResolutionValidationError(f"Invalid action '{data['action']}'. Expected one of {valid_actions}")

    valid_eq_types = ["psv", "valve", "check_valve", "pump", "heat_exchanger", "vessel", "interlock", "instrument", "none"]
    if str(data["equipment_type"]).lower() not in valid_eq_types:
        raise ResolutionValidationError(f"Invalid equipment_type '{data['equipment_type']}'. Expected one of {valid_eq_types}")

    valid_consensus = ["UNANIMOUS", "MAJORITY", "MODERATOR_OVERRULE"]
    if data["consensus_level"] not in valid_consensus:
        raise ResolutionValidationError(f"Invalid consensus_level '{data['consensus_level']}'. Expected one of {valid_consensus}")

    # Standardize types
    clean = dict(data)
    clean["action"] = str(clean["action"]).lower()
    clean["equipment_type"] = str(clean["equipment_type"]).lower()
    clean["safety_veto_exercised"] = bool(clean.get("safety_veto_exercised", False))
    return clean
