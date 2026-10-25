"""Closed-set safety checks; no model decides these gates."""
import re

from contracts import ALLOWED_PARTS

REFUSAL = "I can't help with opening a power supply or mains wiring. Those can hurt you."
PART_REFUSAL = "I can't guide that part. Please use one of the supported PC parts."


def power_off_ok(session):
    return session.power_off is True


def part_allowed(item):
    return item in ALLOWED_PARTS


def refusal_for_text(text):
    text = text.lower()
    supply = re.search(r'\bpsu\b|power\s+supply', text)
    opening = re.search(r'\b(open\w*|disassembl\w*|inside|repair\w*|take\s+apart)\b', text)
    # Ordinary external tool use is not outlet repair. Remove only a complete,
    # bounded instruction; extra clauses still face the original refusal gate.
    outlet_text = re.sub(
        r'\bplug (?:the |a )?soldering iron into (?:the |a )wall (?:outlet|socket)'
        r'(?: and (?:set|place) it in its stand)?[.!]?(?=\s*$)', '', text)
    if re.search(r'\bmains\b|wall\s+(outlet|socket)', outlet_text) or (supply and opening):
        return REFUSAL
    return None


def voice_power_off(text):
    return text.strip().lower() in {"power is off", "it's off"}
