"""Home-safety gates for every pack and every brain (Claude or local), enforced in code.

Local models told a user that heavily smoking oil is fine for searing (docs/results/local-brain.md). So:
- before(): a question about one of these hazards gets a fixed line, and no model is asked;
- after(): a spoken reply that contradicts a gate (calls the hazard fine, or gives the dangerous step) is
  replaced by that gate's fixed line, whatever the question was.
Wired for all packs in server/packs/__init__.get().
"""
import re
from dataclasses import dataclass

_OK = r"(fine|ok|okay|safe|good|great|perfect|normal|ideal|no problem|nothing to worry|not a problem|totally fine)"


@dataclass(frozen=True)
class Gate:
    id: str
    ask: re.Pattern       # the user's question is about this hazard
    topic: re.Pattern     # a reply talks about this hazard
    wrong: re.Pattern     # inside that reply: approval, or the dangerous step
    line: str


def _re(pattern):
    return re.compile(pattern, re.I)


# Conservative text backstops, not a substitute for visual hazard detection.
_WATER = r"\b(water|wet|spills?|spilled|spilling|drips?|dripping|puddles?)\b"
_ELECTRIC = r"\b(outlet|socket|cords?|plugs?|extension cord|psu|power supply|charger|power strip|computer|laptop)\b"
_PANEL = r"\b(electrical panel|electric panel|breaker (box|panel)|fuse box)\b"
_OPEN = r"\b(open\w*|remov\w*|unscrew\w*|take off|inside)\b"
_SUPPLY = r"\b(charger|power (?:brick|supply)|psu|ac adapter)\b"
_CELL = r"\b(lithium(?:[- ]ion)?|li[- ]?ion|lipo|18650|pouch|battery|cell)\b"
_CAPACITOR = r"\bcapacitors?\b"
_LADDER = r"\b(ladder|stepladder)\b"
_UNSAFE = r"\b(top (rung|step)|wobbl\w*|unstable|uneven|overreach\w*|lean\w* sideways)\b"
_WATER_ON = r"\bwater(?: supply)?\s+(?:(?:is|was)\s+)?(?:still\s+on|(?:still\s+)?running|not\s+off)\b"
WATER_OFF_LINE = ("Stop here until the step checker confirms the water is off. "
                  "Show the shutoff valve and the tap with no water flowing.")


def _pair(a, b):
    return _re(a + r"[\s\S]{0,100}" + b + '|' + b + r"[\s\S]{0,100}" + a)


def plumbing_stop(water_off_passed):
    """Only a trusted checker boolean can unlock a plumbing step; missing is not passed."""
    return None if water_off_passed is True else WATER_OFF_LINE


def _stop(id, pattern, line):
    # For these out-of-scope actions, any proposed instruction is stopped.
    return Gate(id, pattern, pattern, _re(r"[\s\S]+"), line)


_HOT_ACTION = (r"\b(touch\w*|grab\w*|hold\w*|pick\w* up)\b[^.!?;,\n]{0,40}"
               r"\b(hot|soldering)\b[^.!?;,\n]{0,30}\b(tip|iron|metal)\b")
HOT_TOOL = Gate(
    'hot_tool', _re(_HOT_ACTION), _re(_HOT_ACTION),
    _re(r"(?<!don't )(?<!don’t )(?<!not )(?<!never )(?<!avoid )" + _HOT_ACTION),
    "Do not touch the hot soldering iron tip; leave it in its stand.")


# Electrical state must describe the conductor/device, not a nearby hot iron
# or the product name "Live" in a context summary.
_CONDUCTOR = r"\b(?:wire\w*|rewir\w*|outlet|socket|breaker|panel|fuse|electrical circuit|light fixture|switch)\b"
_LIVE_POWER = (
    r"\b(?:live|hot|powered)\s+(?:(?:electrical|mains)\s+)?" + _CONDUCTOR + r"|"
    + _CONDUCTOR + r"[^.!?;,\n]{0,35}\b(?:is|are|remains?)\s+(?:still\s+)?(?:live|powered)\b|"
    r"\b(?:power (?:is )?(?:still )?on|without (?:turning|switching|shutting) (?:the )?(?:power|breaker|it) off)\b"
    r"[^.!?\n]{0,50}" + _CONDUCTOR + r"|"
    + _CONDUCTOR + r"[^.!?\n]{0,50}\b(?:power (?:is )?(?:still )?on|"
    r"while (?:it's|it is) on|plugged (?:in|into)|without (?:turning|switching|shutting) "
    r"(?:the )?(?:power|breaker|it) off)\b|"
    r"\bplugged (?:in|into)\b[^.!?\n]{0,50}" + _CONDUCTOR + r"|"
    r"\b(?:psu|power supply)\b[^.!?\n]{0,50}\b(?:live|power (?:is )?(?:still )?on)\b|"
    r"\b(?:live|power (?:is )?(?:still )?on)\b[^.!?\n]{0,50}\b(?:psu|power supply)\b")


GATES = (
    _stop('open_microwave', _pair(
        r"\b(open\w*|pry\w*|unscrew\w*|disassembl\w*|inside|internal)\b", r"\bmicrowave\b"),
          "Stop; keep the microwave sealed. Have a qualified technician inspect it."),
    _stop('mains_wiring', _re(r"\bmains\s+(?:wir\w*|circuit\w*|terminal\w*)\b"),
          "Stop; leave mains wiring to a qualified electrician."),
    _stop('open_power_supply', _pair(
        r"\b(open\w*|pry\w*|unscrew\w*|disassembl\w*|inside|internal)\b", _SUPPLY),
          "Stop; keep the power supply sealed. Replace it or have a qualified technician inspect it."),
    _stop('damaged_battery', _pair(
        r"\b(punctur\w*|pok\w*|pierc\w*|drill\w*|squeez\w*|swollen|puffy|bulg\w*)\b", _CELL),
          "Stop; do not puncture, squeeze or use the damaged battery. Keep away and contact a battery disposal service."),
    _stop('capacitor_discharge', _pair(_CAPACITOR,
        r"(?:\b(discharg\w*|screwdriver|microwave|television|crt|camera flash|high[- ]voltage)\b|"
        r"\bshort(?:ing|ed)?\b.{0,25}\b(terminals?|leads?|capacitor)\b)"),
          "Stop; stored charge can be dangerous even after unplugging. Leave capacitor discharge to a qualified technician."),
    _stop('solder_fumes', _pair(r"\b(solder\w*|desolder\w*|iron|flux)\b",
        r"(?:\b(?:no|without|skip\w*|avoid\w*)\s+(?:any\s+|the\s+)?(?:ventilation|fume extraction|extractor|fan)\b|"
        r"\b(?:unventilated|sealed room|breath\w* (?:in )?(?:the )?(?:fumes|smoke))\b)"),
          "Stop soldering until ventilation moves fumes away from your face. Use eye protection and an iron stand."),
    _stop('water_electric', _re(_WATER + r'[^.!?\n]{0,100}' + _ELECTRIC + '|'
                               + _ELECTRIC + r'[^.!?\n]{0,100}' + _WATER),
          "Stop and move away from the wet area; don't touch cords, outlets or switches. "
          "Keep others away and call an electrician before continuing."),
    _stop('electrical_panel', _pair(_OPEN, _PANEL),
          "Stop; don't open or touch the electrical panel. Call a qualified electrician."),
    _stop('gas_line', _re(r"\b(gas|propane)\s+(line|pipe|hose|fitting)s?\b"),
          "Stop; don't touch or repair a gas line. Call the gas company or a qualified gas technician."),
    _stop('unsafe_ladder', _pair(_LADDER, _UNSAFE),
          "Stop and don't reach or climb higher. Get help to come down safely and use stable access."),
    _stop('water_on', _re(_WATER_ON), WATER_OFF_LINE),
    HOT_TOOL,
    Gate('hot_oil',
         _re(r"\b(oil|grease|fat|pan)\b.{0,40}\b(smok\w*|on fire|fire|flames?|flaming|burning)\b|"
             r"\b(smok\w*|fire|flames?|flaming)\b.{0,30}\b(oil|grease|fat|pan)\b|\bgrease fire\b"),
         _re(r"\b(oil|grease|fat|pan)\b.{0,60}\b(smok\w*|fire|flames?)\b|\b(smok\w*|fire|flames?)\b.{0,60}\b(oil|grease|pan)\b"),
         _re(r"\b(is|it's|that's|its|are|be)\s+(\w+\s+)?" + _OK + r"\b|\bgood for (searing|frying)\b|\bkeep (cooking|searing|frying)\b|"
             r"(?<!never )(?<!don't )(?<!do not )\b(use|pour|throw|add|put|splash)\s+(some\s+|a little\s+)?water\b"),
         "Turn the heat off now and slide the pan off the burner. Smoking oil can catch fire. If it flames, "
         "cover the pan with a lid or a baking sheet, never water. If the fire spreads, leave and call 911."),
    Gate('gas_smell',
         _re(r"\b(smell\w*|smells like|odou?r)\b.{0,30}\b(gas|rotten eggs?|propane)\b|\bgas\s+(leak\w*|smell\w*)\b"),
         _re(r"\bgas\b.{0,40}\b(leak\w*|smell\w*)\b|\b(smell\w*)\b.{0,30}\bgas\b"),
         _re(r"\b(is|it's|that's|probably)\s+(\w+\s+)?" + _OK + r"\b|\b(turn|switch|flip)\s+(on|off)\s+(the\s+)?(light|switch|stove|burner)s?\b|"
             r"\b(light|strike)\s+(a\s+)?(match|lighter|candle)\b|\bfind the leak\b"),
         "Leave now and get everyone out. Don't touch light switches or anything electric, and don't light "
         "anything. Once you're outside, call 911 or the gas company."),
    Gate('live_power',
         _re(_LIVE_POWER), _re(_LIVE_POWER),
         _re(r"\b(is|it's|that's)\s+(\w+\s+)?" + _OK + r"\b|\bno need to (turn|switch|shut)\b|\b(leave|keep) (it|the power) on\b"),
         "Turn the power off first, at the breaker or by unplugging it, and check it's dead before you touch "
         "anything. If you're not sure, stop and call an electrician."),
    Gate('burning_device',
         _re(r"\b(burn\w*|smok\w*|melt\w*|scorch\w*|sizzl\w*)\b.{0,40}\b(pc|computer|laptop|charger|power supply|psu|cable|"
             r"cord|plug|outlet|socket|battery|power strip|adapter)\b|\b(pc|computer|laptop|charger|power supply|psu|cable|cord|"
             r"plug|outlet|socket|battery|power strip|adapter)\b.{0,40}\b(burn\w*|smok\w*|melt\w*|scorch\w*|sparks?)\b"),
         _re(r"\b(burn\w*|smok\w*|melt\w*)\b.{0,60}\b(pc|computer|charger|psu|power supply|cable|plug|battery|outlet)\b|"
             r"\b(pc|computer|charger|psu|power supply|cable|plug|battery|outlet)\b.{0,60}\b(burn\w*|smok\w*|melt\w*)\b"),
         _re(r"\b(is|it's|that's|probably)\s+(\w+\s+)?" + _OK + r"\b|\b(new|normal) (electronics |pc )?smell\b|\b(ignore|keep using|keep it running)\b"),
         "Unplug it now, or switch it off at the wall if it's hot to touch, and move it away from anything that "
         "burns. Don't use it again until it's checked. If you see flames or a lot of smoke, leave and call 911."),
    Gate('chemical_mix',
         _re(r"\bbleach\b.{0,60}\b(ammonia|vinegar|acid\w*|toilet (bowl )?cleaner|rubbing alcohol|windex|glass cleaner)\b|"
             r"\b(ammonia|vinegar|acid\w*|toilet (bowl )?cleaner|rubbing alcohol|windex|glass cleaner)\b.{0,60}\bbleach\b"),
         _re(r"\bbleach\b.{0,80}\b(ammonia|vinegar|acid\w*|cleaner|alcohol)\b|\b(ammonia|vinegar|acid\w*|alcohol)\b.{0,80}\bbleach\b"),
         _re(r"\b(is|it's|that's|are)\s+(\w+\s+)?" + _OK + r"\b|\byou can (mix|combine|use them together)\b|"
             r"\bsafe to (mix|combine|use together)\b"),
         "Don't mix them. Bleach with ammonia, vinegar or other acids makes a toxic gas. If you already did, "
         "leave the room, open a window on your way out, and call Poison Control at your local poison control service."),
)

LINES = {gate.line for gate in GATES}


def precaution_text(text):
    """Remove only bounded preventive instructions from generated-text checks.

    This is not a whole-step exemption: later clauses and explicit live-state
    reports still face every gate. User questions are never rewritten here.
    """
    text = text or ''
    if re.search(r"\b(?:don't|don’t|do not|never|without|skip|shouldn't|shouldn’t|mustn't|mustn’t)\b|"
                 r"\bnot\s+(?:make sure|check|ensure|unplug|disconnect|let)\b",
                 text, re.I):
        return text
    device = r'(?:the |your )?(?:headphones|device)'
    destination = r'(?:a |any |the |your )?(?:phone|device|power source)'
    text = re.sub(
        r'\b(?:make sure|check|ensure) (?:that )?' + device
        + r' (?:is|are) not plugged (?:in|into ' + destination + r')\b',
        'Device disconnected', text, flags=re.I)
    text = re.sub(
        r'\b(?:unplug|disconnect) ' + device
        + r' if (?:it is |they are )?plugged (?:in|into ' + destination + r')\b',
        'Disconnect device', text, flags=re.I)
    text = re.sub(
        r'\blet (?:the |your )?(?:soldering )?iron cool(?: completely)? before '
        r'(?:touching|handling) (?:the |its )?(?:hot )?(?:tip|iron)\b',
        'Wait for the tool to cool', text, flags=re.I)
    return text


def before(question):
    """The fixed line for a hazard question, or None. Runs before any model."""
    ordered = sorted(GATES, key=lambda g: g.id != 'gas_smell')
    for gate in ordered:
        pattern = gate.wrong if gate is HOT_TOOL else gate.ask
        if pattern.search(question or ''):
            return gate.line
    return None


def violation(text, question=''):
    """Return the rejecting output gate, so diagnostics need never include the text."""
    if not text or text in LINES:
        return None
    text = re.sub(r'[^\S\n]+', ' ', text)
    for gate in GATES:
        about = gate.topic.search(text) or gate.ask.search(question or '')
        if about and gate.wrong.search(text):
            return gate
    return None


def after(text, question=''):
    """A reply that contradicts a gate becomes that gate's line. Fixed lines pass through unchanged."""
    gate = violation(text, question)
    return gate.line if gate else text
