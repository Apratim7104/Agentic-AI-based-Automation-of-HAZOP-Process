#!/usr/bin/env python3
"""agent_debate.py Multi-persona LLM debate engine.
Orchestrates a bounded-round debate between process/safety/control engineer
personas (configured in personas_config.json) grounded in a DEXPI context +
a triggering HAZOP scenario, then forces a single structured resolution out
of a moderator agent via tool/function calling.
"""
import json
from pathlib import Path
from .llm_client import LLMClient, LLMRequestError
from .resolution_schema import EMIT_RESOLUTION_TOOL, validate_resolution, ResolutionValidationError
from . import persona_memory

def load_personas(path: str = "configs/personas_config.json") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def build_scenario_brief(scenario_row: dict) -> str:
    """Turn one row of scenario_results_summary*.csv into a readable brief."""
    lines = ["Triggering scenario data:"]
    for k, v in scenario_row.items():
        if not str(k).startswith("_"):
            lines.append(f" - {k}: {v}")
    return "\n".join(lines)

class DebateTranscript:
    def __init__(self, scenario_name: str):
        self.scenario_name = scenario_name
        self.turns = []  # list of {"persona": str, "persona_id": str, "round": int, "text": str}

    def add(self, persona_id: str, persona_name: str, round_no: int, text: str):
        self.turns.append({
            "persona_id": persona_id,
            "persona": persona_name,
            "round": round_no,
            "text": text
        })

    def final_statement(self, persona_display_name: str) -> str:
        """Last recorded statement for a given persona (its settled position)."""
        for t in reversed(self.turns):
            if t["persona"] == persona_display_name or t.get("persona_id") == persona_display_name:
                return t["text"]
        return ""

    def as_text(self) -> str:
        lines = []
        for t in self.turns:
            lines.append(f"[Round {t['round']}] {t['persona']}: {t['text']}")
        return "\n\n".join(lines)

    def to_markdown(self) -> str:
        lines = [f"# HAZOP Debate Transcript - {self.scenario_name}", ""]
        for t in self.turns:
            lines.append(f"### Round {t['round']} - {t['persona']}")
            lines.append(t["text"])
            lines.append("")
        return "\n".join(lines)

def run_debate(client: LLMClient, personas_cfg: dict, dexpi_context_text: str,
               scenario_row: dict, log = None) -> DebateTranscript:
    """Run the multi-round debate. Returns the full transcript."""
    settings = personas_cfg.get("debate_settings", {})
    max_rounds = settings.get("max_rounds", 2)
    temperature = settings.get("temperature", 0.3)
    max_tokens = settings.get("max_tokens_per_turn", 400)
    memory_cfg = personas_cfg.get("memory_settings", {})
    memory_enabled = memory_cfg.get("enabled", True)
    lookback = memory_cfg.get("lookback_entries", 3)

    scenario_brief = build_scenario_brief(scenario_row)
    scenario_name = str(scenario_row.get("scenario") or scenario_row.get("name") or "UNKNOWN")
    transcript = DebateTranscript(scenario_name)

    personas = personas_cfg.get("personas", [])

    for r in range(1, max_rounds + 1):
        if log:
            log.info(f"--- Debate Round {r}/{max_rounds} for {scenario_name} ---")
        for p in personas:
            p_id = p.get("id")
            p_name = p.get("display_name", p_id)
            system_prompt = p.get("system_prompt", "")

            # Compose messages
            messages = [{"role": "system", "content": system_prompt}]

            # Add few-shot examples if present
            for fs in p.get("few_shot", []):
                messages.append({"role": "user", "content": fs.get("user", "")})
                messages.append({"role": "assistant", "content": fs.get("assistant", "")})

            # User prompt with context and state
            prompt_parts = [
                f"### System Context:\n{dexpi_context_text}\n",
                f"### Current Scenario Deviation:\n{scenario_brief}\n"
            ]

            if memory_enabled:
                mem_text = persona_memory.format_memory_for_prompt(p_id, lookback)
                if mem_text:
                    prompt_parts.append(f"### Memory:\n{mem_text}\n")

            if transcript.turns:
                prompt_parts.append(f"### Debate Transcript So Far:\n{transcript.as_text()}\n")

            prompt_parts.append(
                f"Now evaluate this deviation from your role as {p_name} in Round {r}. "
                "State your position (SUPPORT, OPPOSE, or MODIFY) concisely and justify it."
            )

            messages.append({"role": "user", "content": "\n".join(prompt_parts)})

            try:
                resp = client.chat(messages, temperature=temperature, max_tokens=max_tokens)
                choice = resp.get("choices", [{}])[0]
                turn_text = choice.get("message", {}).get("content", "").strip()
            except Exception as e:
                if log:
                    log.warning(f"Error getting turn for {p_name}: {e}")
                turn_text = f"OPPOSE. Unable to reach consensus due to communication error: {e}"

            transcript.add(p_id, p_name, r, turn_text)
            if log:
                log.info(f"[{p_name}] {turn_text[:120]}...")

            if memory_enabled:
                stance = persona_memory.extract_stance(turn_text)
                summary_snippet = turn_text[:80].replace("\n", " ")
                persona_memory.record_memory(p_id, scenario_name, stance, summary_snippet)

    return transcript

def run_moderator(client: LLMClient, personas_cfg: dict, dexpi_context_text: str,
                  scenario_row: dict, transcript: DebateTranscript, log = None) -> dict:
    """Run the moderator agent to synthesize debate and emit a structured resolution."""
    mod_cfg = personas_cfg.get("moderator", {})
    mod_system = mod_cfg.get("system_prompt", "You are the HAZOP review moderator.")
    scenario_brief = build_scenario_brief(scenario_row)
    scenario_name = transcript.scenario_name

    user_content = (
        f"### DEXPI Context:\n{dexpi_context_text}\n\n"
        f"### Scenario Under Review:\n{scenario_brief}\n\n"
        f"### Full Debate Transcript:\n{transcript.as_text()}\n\n"
        "Synthesize the debate and call the emit_resolution tool to provide the final resolution."
    )

    messages = [
        {"role": "system", "content": mod_system},
        {"role": "user", "content": user_content}
    ]

    try:
        resp = client.chat(
            messages,
            tools=[EMIT_RESOLUTION_TOOL],
            tool_choice={"type": "function", "function": {"name": "emit_resolution"}},
            temperature=0.1,
            max_tokens=600
        )
        choice = resp.get("choices", [{}])[0]
        msg = choice.get("message", {})

        tool_calls = msg.get("tool_calls", [])
        if tool_calls:
            fn_call = tool_calls[0].get("function", {})
            args = json.loads(fn_call.get("arguments", "{}"))
            resolution = validate_resolution(args)
            if log:
                log.info(f"Moderator resolution emitted via tool: {resolution['action']} on {resolution['target_tag']}")
            return resolution
    except Exception as exc:
        if log:
            log.warning(f"Tool calling failed or invalid: {exc}. Attempting heuristic fallback.")

    # Fallback default resolution
    # Check if safety engineer opposed
    safety_statement = transcript.final_statement("Safety Engineer")
    safety_opposed = "OPPOSE" in safety_statement.upper() or "VETO" in safety_statement.upper()

    default_resolution = {
        "action": "add" if safety_opposed else "none",
        "equipment_type": "psv" if safety_opposed else "none",
        "target_tag": "Outlet 1",
        "new_tag": "PSV-001" if safety_opposed else "",
        "rationale": f"Moderator fallback: Safety engineer {'vetoed/opposed' if safety_opposed else 'agreed no hardware necessary'}.",
        "consensus_level": "MAJORITY" if not safety_opposed else "MODERATOR_OVERRULE",
        "safety_veto_exercised": safety_opposed
    }
    return default_resolution

def run_full_debate_for_scenario(client: LLMClient, personas_cfg: dict, dexpi_context_text: str,
                                 scenario_row: dict, log = None) -> tuple:
    """Run full debate and moderator resolution for a single scenario."""
    transcript = run_debate(client, personas_cfg, dexpi_context_text, scenario_row, log=log)
    resolution = run_moderator(client, personas_cfg, dexpi_context_text, scenario_row, transcript, log=log)
    return transcript, resolution
