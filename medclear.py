import re
from strands import Agent, tool
from strands.models.ollama import OllamaModel
from strands.hooks import HookProvider, HookRegistry, BeforeToolCallEvent

# ---- Made-up demo data (never real patient data) ----
INTERACTIONS = {
    frozenset({"warfarin", "aspirin"}): "Higher risk of bleeding.",
    frozenset({"ibuprofen", "lisinopril"}): "May reduce blood pressure control and strain kidneys.",
    frozenset({"simvastatin", "clarithromycin"}): "Can raise statin levels and cause muscle damage.",
    frozenset({"metformin", "alcohol"}): "Raises risk of low blood sugar or lactic acidosis.",
    frozenset({"sertraline", "tramadol"}): "Risk of serotonin syndrome.",
}

@tool
def check_interactions(drug_a: str, drug_b: str) -> str:
    """Check whether two medicines have a known interaction in the demo table.

    Args:
        drug_a: First medicine name
        drug_b: Second medicine name
    """
    key = frozenset({drug_a.strip().lower(), drug_b.strip().lower()})
    if key in INTERACTIONS:
        return f"Known interaction: {INTERACTIONS[key]} Ask a pharmacist or doctor."
    return "No result in the demo data. This does NOT mean it is safe. Ask a pharmacist."

@tool
def explain_label(label_text: str) -> str:
    """Return a prescription label so it can be explained in plain language.

    Args:
        label_text: The text on the prescription label
    """
    return f"LABEL: {label_text}\nExplain what it says in simple words, nothing more."

# ---- Safety rules enforced in code ----
BLOCKED = [
    r"\b(change|increase|decrease|double|halve|skip|raise|lower)\b.*\b(dose|dosage)\b",
    r"\b(stop|quit|discontinue)\b.*\b(taking|medicine|medication|pills?)\b",
    r"\b(diagnose|what (disease|condition) do i have|do i have)\b",
]
EMERGENCY = r"\b(overdose|overdosed|can'?t breathe|severe reaction|swollen (face|throat))\b"
DISCLAIMER = "\n\nPlease confirm this with your pharmacist or doctor."

SYSTEM_PROMPT = (
    "You are MedClear, an information aid that explains prescription labels in "
    "plain, simple words (6th-grade level). Never advise changing a dose, stopping "
    "a medicine, or diagnosing. Use check_interactions for medicine pairs. "
    "If a tool says no result, say you don't know."
)

class CallLimitHook(HookProvider):
    """Caps tool calls per request (Module 2 pattern)."""
    def __init__(self, max_calls=4):
        self.max_calls, self.n = max_calls, 0
    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeToolCallEvent, self.check)
    def check(self, event: BeforeToolCallEvent) -> None:
        self.n += 1
        if self.n > self.max_calls:
            event.cancel_tool = "Tool limit reached. Answer with what you have."

model = OllamaModel(host="http://localhost:11434", model_id="llama3.2")

def ask(user_text: str) -> str:
    low = user_text.lower()
    if re.search(EMERGENCY, low):
        return ("This may be an emergency. Call your local emergency number now "
                "(in Sri Lanka: 1990 ambulance) or go to the nearest hospital.")
    for pattern in BLOCKED:
        if re.search(pattern, low):
            return ("I can't advise on changing doses, stopping medicines, or "
                    "diagnosing. Please speak to your pharmacist or doctor." )
    agent = Agent(model=model, tools=[check_interactions, explain_label],
                  hooks=[CallLimitHook()], system_prompt=SYSTEM_PROMPT,
                  callback_handler=None)
    return str(agent(user_text)).strip() + DISCLAIMER

if __name__ == "__main__":
    tests = [
        "Explain this label: Amoxicillin 500mg, take 1 capsule 3 times a day for 7 days after food.",
        "I take warfarin. Is it OK with aspirin?",
        "Can I double my dose of metformin?",
        "Can I stop taking my pills?",
        "I think I overdosed.",
    ]
    for t in tests:
        print(f"\n>>> {t}\n{ask(t)}")