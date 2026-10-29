import re
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
DISCLAIMER = "\n\nPlease confirm this with your pharmacist or doctor."

EMERGENCY = r"\b(overdos\w*|can'?t breathe|cannot breathe|severe reaction|swollen (face|throat|tongue)|chest pain|unconscious)\b|\b(swallow\w*|ate|eaten|took|taken|drank|ingested)\b.{0,40}\b(too many|too much|a bunch|a handful|handful|whole (bottle|packet|strip)|a lot of)\b"
BLOCKED_INPUT = [
r"\b(double|triple|half|halve|increase|decrease|reduce|raise|lower|change|adjust|skip|miss|take (more|less|extra))\b.{0,40}\b(dose|dosage|tablets?|pills?|medicines?|medications?|meds?|capsules?)\b",
    r"\b(stop|quit|discontinue|come off|wean off)\b.{0,30}\b(taking|medicines?|medications?|meds?|pills?|tablets?|capsules?)\b",
    r"\b(go|going) (lower|higher)\b",
    r"\b(diagnos\w*|what is wrong with me|what['’]?s wrong with me|what (disease|condition|illness))\b",
    r"\bdo i have (?!to\b|enough\b)",
]
UNSAFE_OUTPUT = [
    r"\byou (should|can|may|must|could) (stop|skip|double|increase|decrease|take more|take less)",
    r"\b(increase|double|reduce|lower|change) your (dose|dosage)",
    r"\bstop taking\b",
]

def hit(patterns, text):
    t = re.sub(r"\s+", " ", text.lower())
    return any(re.search(p, t) for p in patterns)

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
        if hit([EMERGENCY], text):
            return EMERGENCY_MSG
        if hit(BLOCKED_INPUT, text):
            return REFUSAL
        reply = str(self.agent(text)).strip()
        if self.language == "English" and grade_level(reply) > 8:
            reply = str(self.agent("Say that again in shorter sentences and simpler words.")).strip()
        if hit(UNSAFE_OUTPUT, reply):
            return REFUSAL
        return reply + DISCLAIMER

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