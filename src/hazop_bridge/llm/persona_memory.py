#!/usr/bin/env python3
"""persona_memory.py Cross-scenario memory for debate personas."""
import re
from collections import defaultdict

_MEMORY_STORE = defaultdict(list)

def extract_stance(text: str) -> str:
    """Extract SUPPORT, OPPOSE, or MODIFY stance from persona statement text."""
    if not text:
        return "NEUTRAL"
    upper = text.upper()
    # Check for direct capitalized keywords first
    for kw in ["SUPPORT", "OPPOSE", "MODIFY"]:
        if re.search(rf"\b{kw}\b", upper):
            return kw
    return "NEUTRAL"

def record_memory(persona_id: str, scenario_name: str, stance: str, summary: str):
    """Record a settled position for a persona to maintain cross-scenario consistency."""
    _MEMORY_STORE[persona_id].append({
        "scenario": scenario_name,
        "stance": stance,
        "summary": summary
    })

def get_persona_memory(persona_id: str, lookback: int = 3) -> list:
    """Retrieve recent decisions made by this persona."""
    return _MEMORY_STORE[persona_id][-lookback:]

def format_memory_for_prompt(persona_id: str, lookback: int = 3) -> str:
    """Format past decisions into a concise prompt prefix."""
    recent = get_persona_memory(persona_id, lookback)
    if not recent:
        return ""
    lines = ["Your recent prior stances in this session (maintain technical consistency):"]
    for m in recent:
        lines.append(f" - On {m['scenario']}: {m['stance']} ({m['summary']})")
    return "\n".join(lines)

def clear_memory():
    """Clear memory across all personas (useful for test runs)."""
    _MEMORY_STORE.clear()
