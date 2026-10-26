# Evaluation data

This folder is for **reviewed, held-out evaluation messages**, not training
data. `hinglish_simulation_messages.csv` is a header-only template. Do not
score it until real fictional simulation examples have been added and reviewed.

Required columns:

- `message_id`: stable unique message identifier
- `conversation_id`: keep one conversation entirely in one dataset split
- `channel`: `instagram`, `telegram`, or `whatsapp`
- `language`: `en`, `hi`, or `hinglish` (use the language actually reviewed)
- `text`: the exact text that the model will receive
- `drug_related_label`: `0` for not drug-related, `1` for drug-related topic
- `review_notes`: optional explanation for ambiguous labels

This label matches the X-Sensitive model task. It does **not** mean suspicious
dealing or trafficking. Create a separate reviewed target and evaluation set if
those behaviors are ever modeled. Keep simulation examples out of training
until they have passed review and are assigned to a training split explicitly.

Run `python ml/evaluate_nlp_classifier.py` after adding reviewed rows. The
script reports results overall and by channel/language. It does not create
examples or alter model thresholds.
