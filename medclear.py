import re
import os
from strands.models import BedrockModel
from strands import Agent, tool
from strands.models.ollama import OllamaModel
from strands.hooks import (HookProvider, HookRegistry,
                           BeforeInvocationEvent, BeforeToolCallEvent)

# ---- Made-up demo data: NOT medical data, never use real patient info ----
INTERACTIONS = {
    frozenset({"warfarin", "aspirin"}): "Higher risk of bleeding.",
    frozenset({"ibuprofen", "lisinopril"}): "May weaken blood pressure control and strain the kidneys.",
    frozenset({"simvastatin", "clarithromycin"}): "Can raise statin levels and cause muscle damage.",
    frozenset({"metformin", "alcohol"}): "Raises risk of low blood sugar or lactic acidosis.",
    frozenset({"sertraline", "tramadol"}): "Risk of serotonin syndrome.",
    frozenset({"warfarin", "ibuprofen"}): "Higher risk of bleeding.",
    frozenset({"sildenafil", "nitroglycerin"}): "Can cause a dangerous drop in blood pressure.",
}

def lookup(a: str, b: str):
    return INTERACTIONS.get(frozenset({a.strip().lower(), b.strip().lower()}))

# ---- Safety rules, enforced in code ----
REFUSAL = ("I can't advise on changing doses, stopping medicines, or diagnosing. "
           "Please speak to your pharmacist or doctor.")
EMERGENCY_MSG = ("This may be an emergency. Call your local emergency number now "
                 "(Sri Lanka: 1990 ambulance - please verify) or go to the nearest hospital.")
DISCLAIMERS = {
    "English": "\n\nPlease confirm this with your pharmacist or doctor.",
    "Sinhala": "\n\nකරුණාකර මෙය ඔබේ ඖෂධවේදියා හෝ වෛද්‍යවරයා සමඟ තහවුරු කරගන්න.",
    "Tamil": "\n\nஇதை உங்கள் மருந்தாளர் அல்லது மருத்துவரிடம் உறுதிப்படுத்திக் கொள்ளுங்கள்.",
}
REFUSALS = {
    "English": REFUSAL,
    "Sinhala": "මට මාත්‍රා වෙනස් කිරීම, ඖෂධ නවත්වීම හෝ රෝග විනිශ්චය ගැන උපදෙස් දිය නොහැක. කරුණාකර ඔබේ ඖෂධවේදියා හෝ වෛද්‍යවරයා සමඟ කතා කරන්න.",
    "Tamil": "மருந்தின் அளவை மாற்றுவது, மருந்தை நிறுத்துவது அல்லது நோயைக் கண்டறிவது குறித்து என்னால் ஆலோசனை வழங்க முடியாது. உங்கள் மருந்தாளர் அல்லது மருத்துவரிடம் பேசுங்கள்.",
}
EMERGENCY_MSGS = {
    "English": EMERGENCY_MSG,
    "Sinhala": "මෙය හදිසි අවස්ථාවක් විය හැක. දැන්ම හදිසි අංකයට (ශ්‍රී ලංකාව: 1990 - කරුණාකර තහවුරු කරගන්න) අමතන්න, නැතහොත් ළඟම රෝහලට යන්න.",
    "Tamil": "இது அவசர நிலையாக இருக்கலாம். உடனே அவசர எண்ணை (இலங்கை: 1990 - உறுதிப்படுத்திக் கொள்ளுங்கள்) அழைக்கவும், அல்லது அருகிலுள்ள மருத்துவமனைக்குச் செல்லவும்.",
}
EMERGENCY_LOCAL = [
    r"(අධි ?මාත්‍රා|වැඩිපුර (බෙහෙත්|ඖෂධ|පෙති)|බෙහෙත් ගුලි ගොඩක්|හුස්ම ගන්න බැ)",
    r"(அதிகமாக\s*(மாத்திரை|மருந்து)|அளவுக்கு (மீறி|அதிகமாக)|மிகை ?அளவு|மூச்சு (விட|வாங்க) முடியவில்லை)",
]
BLOCKED_LOCAL = [
    r"(බෙහෙත්|ඖෂධ|පෙති).{0,30}නවත්ව|නවත්ව.{0,30}(බෙහෙත්|ඖෂධ|පෙති)",
    r"(மாத்திரை|மருந்து).{0,30}நிறுத்த|நிறுத்த.{0,30}(மாத்திரை|மருந்து)",
]

EMERGENCY = r"\b(overdos\w*|can'?t breathe|cannot breathe|severe reaction|swollen (face|throat|tongue)|chest pain|unconscious)\b|\b(swallow\w*|ate|eaten|took|taken|drank|ingested)\b.{0,40}\b(too many|too much|a bunch|a handful|handful|whole (bottle|packet|strip)|a lot of)\b"
EMERGENCY_CHILD = r"\b(child|kid|baby|toddler|infant|son|daughter|boy|girl)\b.{0,50}\b(got into|swallow\w*|ate|eaten|drank|took|taken|ingest\w*|chew\w*)\b.{0,50}\b(tablets?|pills?|medicines?|medications?|meds?|bottle|packet|strip|capsules?|syrup)\b"
BLOCKED_INPUT = [
r"\b(double|triple|half|halve|increase|decrease|reduce|raise|lower|change|adjust|skip|miss|take (more|less|extra))\b.{0,40}\b(dose|dosage|tablets?|pills?|medicines?|medications?|meds?|capsules?)\b",
    r"\b(stop|quit|discontinue|come off|wean off)\b.{0,30}\b(taking|medicines?|medications?|meds?|pills?|tablets?|capsules?)\b",
    r"\b(go|going) (lower|higher)\b",
    r"\b(diagnos\w*|what is wrong with me|what['’]?s wrong with me|what (disease|condition|illness))\b",
    r"\bdo i have (?!to\b|enough\b)",
    r"\b(less|fewer|smaller)\b.{0,30}\b(dose|dosage|tablets?|pills?|medicines?|medications?|meds?|capsules?)\b",
    r"\b(not|don'?t|do not|didn'?t|no need to) (finish|complete|take|use)\b.{0,30}\b(antibiotics?|course|medicines?|medications?|meds?|pills?|tablets?|capsules?)\b",
    r"\bwhat(?:['’]s| is| could be| might be) (?:causing|wrong|behind)\b",
    r"\bwhy (?:do|am|does|have|is|are) (?:i|my)\b.{0,30}\b(pain|ache|rash|fever|dizz\w*|nause\w*|vomit\w*|cough\w*|sick|tired|swelling|breathless)\b",
    r"\b(two|three|four|2|3|4|another|an extra|extra)\b.{0,10}\b(tablets?|pills?|capsules?)\b.{0,20}\binstead\b|\binstead of (one|1)\b",
]
UNSAFE_OUTPUT = [
    r"\byou (should|can|may|must|could) (stop|skip|double|increase|decrease|take more|take less)",
    r"\b(increase|double|reduce|lower|change) your (dose|dosage)",
    r"\bstop taking\b",
]

def hit(patterns, text):
    t = re.sub(r"\s+", " ", text.lower())
    return any(re.search(p, t) for p in patterns)
def clean(reply: str) -> str:
    return re.sub(r"<thinking>.*?</thinking>\s*", "", reply, flags=re.S | re.I).strip()

# ---- Readability (Flesch-Kincaid grade, English only) ----
def _syl(w):
    n = len(re.findall(r"[aeiouy]+", w.lower()))
    if w.lower().endswith("e") and n > 1:
        n -= 1
    return max(n, 1)

def grade_level(text: str) -> float:
    words = re.findall(r"[A-Za-z']+", text)
    if not words:
        return 0.0
    sents = max(1, len(re.findall(r"[.!?]+", text)))
    syl = sum(_syl(w) for w in words)
    return 0.39 * len(words) / sents + 11.8 * syl / len(words) - 15.59

class CallLimitHook(HookProvider):
    def __init__(self, max_calls=5):
        self.max_calls, self.n = max_calls, 0
    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeInvocationEvent, self.reset)
        registry.add_callback(BeforeToolCallEvent, self.check)
    def reset(self, event) -> None:
        self.n = 0
    def check(self, event) -> None:
        self.n += 1
        if self.n > self.max_calls:
            event.cancel_tool = "Tool limit reached. Answer with what you have."

if os.getenv("MEDCLEAR_BACKEND", "ollama") == "bedrock":
    model = BedrockModel(
        model_id=os.environ["BEDROCK_MODEL_ID"],
        region_name="ap-southeast-2",
        temperature=0.2,
    )
else:
    model = OllamaModel(host="http://localhost:11434", model_id="llama3.2")
def make_tools(my_meds: list):
    @tool
    def parse_label(label_text: str) -> str:
        """Extract medicine, strength, amount and frequency from a label.

        Args:
            label_text: The text on the prescription label
        """
        t = label_text
        drug = re.match(r"\s*([A-Za-z][A-Za-z\- ]*?)\s*\d", t)
        strength = re.search(r"\d+(?:\.\d+)?\s?(?:mg|mcg|g|ml)", t, re.I)
        amount = re.search(r"(\d+|one|two|three)\s+(?:capsules?|tablets?|pills?|drops?|teaspoons?)", t, re.I)
        freq = re.search(r"(once|twice|\d+ times)( a| per)? day|every \d+ hours?|at night|in the morning", t, re.I)
        days = re.search(r"for (\d+) (?:days?|weeks?)", t, re.I)
        return (f"Medicine: {drug.group(1) if drug else 'unknown'}\n"
                f"Strength: {strength.group(0) if strength else 'not found'}\n"
                f"Amount each time: {amount.group(0) if amount else 'not found'}\n"
                f"How often: {freq.group(0) if freq else 'not found'}\n"
                f"Duration: {days.group(0) if days else 'not stated'}\n"
                "Explain these facts in simple words. Add nothing that is not listed.")

    @tool
    def check_interactions(drug_a: str, drug_b: str) -> str:
        """Check two medicines for a known interaction in the demo table.

        Args:
            drug_a: First medicine name
            drug_b: Second medicine name
        """
        r = lookup(drug_a, drug_b)
        return (f"Known interaction: {r}" if r else
                "No result in the demo data. This does NOT mean it is safe.")

    @tool
    def add_medicine(name: str) -> str:
        """Remember a medicine the user takes and check it against the others.

        Args:
            name: Medicine name
        """
        name = name.strip().lower()
        found = [f"{name} + {m}: {lookup(name, m)}" for m in my_meds if lookup(name, m)]
        if name not in my_meds:
            my_meds.append(name)
        return (f"Saved. Medicines now: {', '.join(my_meds)}. " +
                ("Interactions: " + "; ".join(found) if found else "No known interactions in demo data."))

    return [parse_label, check_interactions, add_medicine]

def system_prompt(language: str) -> str:
    return (f"You are MedClear, an information aid that explains prescription labels in "
            f"plain words a 12-year-old can follow. Short sentences. Reply in {language}. "
            "Use parse_label for labels, check_interactions for pairs, add_medicine when "
            "the user says what they take. Never advise changing a dose, stopping a medicine, "
            "or diagnosing. If a tool has no result, say you don't know.")

class MedClear:
    def __init__(self, language="English"):
        self.language = language
        self.my_meds = []
        self.agent = Agent(model=model, tools=make_tools(self.my_meds),
                           hooks=[CallLimitHook()], system_prompt=system_prompt(language),
                           callback_handler=None)

    def ask(self, text: str) -> str:
        lang = self.language if self.language in REFUSALS else "English"
        if hit([EMERGENCY, EMERGENCY_CHILD] + EMERGENCY_LOCAL, text):
            return EMERGENCY_MSGS[lang]
        if hit(BLOCKED_INPUT + BLOCKED_LOCAL, text):
            return REFUSALS[lang]
        reply = clean(str(self.agent(text)))
        if self.language == "English" and grade_level(reply) > 8:
            reply = clean(str(self.agent("Say that again in shorter sentences and simpler words.")))
        if hit(UNSAFE_OUTPUT, reply):
            return REFUSALS[lang]
        return reply + DISCLAIMERS.get(self.language, DISCLAIMERS["English"])

def ask(text: str) -> str:          # used by eval_medclear.py
    return MedClear().ask(text)

if __name__ == "__main__":
    lang = input("Language (English/Sinhala/Tamil) [English]: ").strip() or "English"
    bot = MedClear(lang)
    print("MedClear (information aid, not medical advice). Type 'quit' to exit.")
    while True:
        q = input("\nYou: ").strip()
        if q.lower() in ("quit", "exit"):
            break
        print("\nMedClear:", bot.ask(q))