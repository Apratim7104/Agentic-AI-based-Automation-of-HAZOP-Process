#!/usr/bin/env python3
"""dexpi_context.py Build a compact, LLM-friendly JSON summary of the DEXPI
plant model, so debate personas can ground their arguments in real topology
instead of hallucinating tag names.

We deliberately do NOT hand the raw DEXPI XML to the LLM (too many tokens,
too much namespace noise). Instead we flatten it to:
{
  "equipment": [{"tag", "class", "description", "nozzles": [...]}],
  "connections": [{"from", "to"}, ...]
}
"""
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"d": "http://dexpi.org/schema/1.3"}

def load_dexpi_summary(xml_path: str) -> dict:
    """Parse a DEXPI 1.3 XML export into a compact dict."""
    root = ET.parse(xml_path).getroot()
    equipment = []
    for eq in root.findall("d:Equipment", NS):
        nozzles = [n.get("Tag") for n in eq.findall("d:Nozzle", NS)]
        equipment.append({
            "tag": eq.get("Tag"),
            "class": eq.get("ComponentClass"),
            "type": eq.get("ComponentType"),
            "description": eq.get("Description", ""),
            "nozzles": nozzles,
        })
    streams = []
    piping = root.find("d:PipingNetworkSystem", NS)
    if piping is not None:
        for seg in piping.findall("d:PipingNetworkSegment", NS):
            streams.append({
                "tag": seg.get("Tag"),
                "line_type": seg.get("LineType"),
                "description": seg.get("Description", ""),
            })
    connections = [
        {"from": c.get("From"), "to": c.get("To")}
        for c in root.findall("d:Connection", NS)
    ]
    return {
        "source_file": str(Path(xml_path).name),
        "equipment": equipment,
        "streams": streams,
        "connections": connections,
    }

def equipment_tags(summary: dict) -> set:
    return {e["tag"] for e in summary.get("equipment", [])}

def find_neighbors(summary: dict, tag: str) -> dict:
    """Return {'upstream': [...], 'downstream': [...]} tags directly
    connected to 'tag' (through streams or directly)."""
    upstream, downstream = [], []
    for c in summary.get("connections", []):
        if c.get("to") == tag:
            upstream.append(c.get("from"))
        if c.get("from") == tag:
            downstream.append(c.get("to"))
    return {"upstream": upstream, "downstream": downstream}

def render_context_text(summary: dict, max_equipment: int = 40) -> str:
    """Render the summary as compact text for LLM prompts (bounded size)."""
    lines = [f"DEXPI source: {summary.get('source_file', 'unknown')}", "", "Equipment:"]
    for e in summary.get("equipment", [])[:max_equipment]:
        lines.append(
            f" - {e['tag']} ({e['class']}/{e['type']}): {e.get('description', '')}"
            f" | nozzles: {', '.join(e.get('nozzles', [])) or 'none'}"
        )
    lines.append("")
    lines.append("Connections (From -> To):")
    for c in summary.get("connections", []):
        lines.append(f" - {c['from']} -> {c['to']}")
    return "\n".join(lines)
