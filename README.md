\# MedClear



MedClear is a plain-language information aid that explains prescription labels

and checks a small demo table of drug interactions. It is \*\*not medical advice\*\*.

It runs locally using Strands Agents and Ollama (llama3.2).



\## Run it



1\. Install Ollama and run `ollama pull llama3.2`

2\. `python -m venv .venv` then `.venv\\Scripts\\activate`

3\. `pip install strands-agents ollama`

4\. `python medclear.py`



\## Safety design



The safety rules are enforced in code, so they don't depend on a small model

obeying its prompt:



\- \*\*Input check:\*\* requests to change a dose, stop a medicine or get a diagnosis

&#x20; are refused before the model sees them.

\- \*\*Emergency check:\*\* overdose, breathing trouble and a child swallowing

&#x20; medicine return an emergency message immediately.

\- \*\*Output check:\*\* replies that advise stopping, skipping or changing a dose

&#x20; are replaced with a refusal.

\- \*\*Every answer\*\* ends with "confirm with your pharmacist or doctor".

\- \*\*Readability:\*\* replies above grade 8 (Flesch-Kincaid) are rewritten simpler.



\## Evaluation



Run `python eval\_medclear.py`.



| Round | Cases | Result |

|---|---|---|

| Original set | 12 | 12/12 |

| Adversarial set | 12 | 7/12 before fixes, 12/12 after |

| Held-out round 1 | 6 | 2/6 before fixes |

| Held-out round 2 | 6 | 4/6 before fixes |

| Final, all cases | 36 | 36/36 (after tuning on them) |



The final 36/36 is on cases the rules were tuned against. The honest estimate of

performance on new wording is the held-out rounds: \*\*33%, then 67%\*\*.



\## Limitations



\- Rules are regex patterns. New phrasings still slip through, so they are a

&#x20; backstop and not a clinical guarantee.

\- Interaction data is a small demo table. "No result" does not mean safe.

\- The emergency number in the message should be verified for your country.

\- Small local model: it can still make mistakes in explanations.

\- Readability scoring is English only.

\- Not tested with real patients.

