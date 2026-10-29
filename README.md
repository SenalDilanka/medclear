# MedClear

MedClear is a plain-language medicine information aid. It explains prescription
labels, checks a small demo table of drug interactions, and answers in English,
Sinhala or Tamil. It is **not medical advice**: it refuses to change doses, stop
medicines or diagnose, and every answer tells the user to confirm with a
pharmacist or doctor.

**Who it is for:** people with low health literacy or limited English, who often
cannot read or understand the label on their own medicine.

Built with the [Strands Agents SDK](https://strandsagents.com) and Amazon Bedrock
for the Strands SDK: Workshop to Ship hackathon (Health focus).

## How it works

1. **Code rules (first):** regular expressions catch emergencies (overdose, a child
   swallowing medicine, trouble breathing) and requests to change or stop a dose.
   These run in code, so they do not depend on a small model obeying a prompt.
2. **Triage agent (second):** for Sinhala, Tamil and other non-English input, a
   separate Strands agent classifies the message as `EMERGENCY`, `REFUSE` or `OK`.
   If it fails or is unsure, MedClear refuses.
3. **Main agent (third):** answers using three tools: `parse_label`,
   `check_interactions` and `add_medicine`, with a call-limit hook.
4. **Output check:** replies that advise stopping, skipping or changing a dose are
   replaced with a refusal. Every answer ends with a localised
   "confirm with your pharmacist or doctor" line.

## Runs on AWS

MedClear uses Amazon Bedrock (Amazon Nova Lite, region `ap-southeast-2`) through
the Strands `BedrockModel`. Local Ollama (`llama3.2`) is available as an alternative.

## Run it

```
python -m venv .venv
.venv\Scripts\activate
pip install strands-agents boto3 ollama
```

With Bedrock (PowerShell):

```
$env:MEDCLEAR_BACKEND = "bedrock"
$env:BEDROCK_MODEL_ID = "amazon.nova-lite-v1:0"
$env:AWS_BEARER_TOKEN_BEDROCK = (Read-Host "Paste key" -MaskInput)
python medclear.py
```

With Ollama: install Ollama, run `ollama pull llama3.2`, then `python medclear.py`.

The API key is read from an environment variable and is never stored in this
repository.

## Evaluation

Run `python eval_medclear.py`. Each case is routed as `refuse`, `emergency` or
`answer`, and the result is compared with what it should be.

| Round | Cases | Result |
|---|---|---|
| English, original set | 12 | 12/12 |
| English, adversarial set | 12 | 7/12, then 12/12 after fixes |
| English, held-out round 1 | 6 | 2/6, then fixed |
| English, held-out round 2 | 6 | 4/6, then fixed |
| English, final | 36 | 36/36 (after tuning on them) |
| Sinhala/Tamil, rules only, unseen wording, round 1 | 2 | 0/2 |
| Sinhala/Tamil, rules only, unseen wording, round 2 | 4 | 0/4 |
| Sinhala/Tamil, rules plus triage agent | 12 | 12/12 |
| Sinhala/Tamil, fresh cases | 6 | 6/6 |

The earlier English rounds ran on Ollama; the final runs used Bedrock (Nova Lite).
Scores marked "after fixes" are on cases the rules were tuned against, so the
honest measure of new wording is the held-out and fresh rows: **33%, then 67%** in
English with rules only, and **0/6 with rules only versus 6/6 with the triage
agent** in Sinhala and Tamil.

Note that the eval checks routing (refuse, emergency, answer). It does not
grade the quality of the explanations.

## Limitations

- The test cases were written by me, not collected from real patients.
- Six fresh cases is a small sample. It shows the approach generalises, not that
  it is reliable on all wording.
- The triage agent is a model. It can still make mistakes, and its output can
  vary between runs.
- Sinhala and Tamil answers have not been reviewed by native-speaking clinicians
  at scale.
- Interaction data is a small demo table. "No result" does not mean a combination
  is safe.
- Code rules are a backstop, not a clinical guarantee. New phrasings can slip past
  them.
- The emergency number in the messages should be verified for your country.
- Readability scoring (grade level) is English only.
- Not tested with real patients.

## License

MIT. See `LICENSE`.

Author: Jayasinghe Pelige Senal Dilanka Dilhan Ariyarathna