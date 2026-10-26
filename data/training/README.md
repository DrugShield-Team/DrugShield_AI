# Labeled training data

`drug_slang_terms_reviewed.csv` is the reviewed term-level source used by the current English/Hindi slang matcher. It contains 1,275 rows from `adi515/drug_slangs` (Hugging Face), including term, language, category, confidence, source, and review status.

The runtime matcher includes only rows marked `confirmed`, limits languages to English (`en-*`) and Hindi (`hi-*`), and excludes normalized terms with conflicting categories. Rows marked `ambiguous` are not used.

Do not place mock/fallback feeds, simulation conversations, generated test examples, runtime evidence, or unreviewed cases here. Each dataset release must record its source, license/permission, collection date or version, label definitions, class balance, and train/validation/test partitioning method.

This file contains individual terms and short phrases, not complete chat messages or benign examples. It supports term spotting and category evidence; it is not sufficient to train or evaluate a message-level suspicious-versus-benign classifier. The 10,000+ sample goal remains a planning minimum, not a quality guarantee. A message classifier requires reviewed full-message examples from both classes and evaluation on held-out data.

## Full-message drug-topic model

The training entry point is `ml/train_nlp_classifier.py`. It expects the downloaded CardiffNLP X-Sensitive files under `data/training/x_sensitive/` (or a directory supplied with `--data-dir`). Supported exports are CSV, JSON, JSONL, and Parquet. Each row must provide the full-message `text` and the dataset's binary `drugs` label. Preserve the source-provided train, validation, and test splits where available.

Install the training dependencies with `pip install -r requirements-training.txt`, then run `python ml/train_nlp_classifier.py`. The script writes `models/registry/nlp_drug_topic.joblib` and `models/registry/nlp_drug_topic.metrics.json`.

**This model predicts drug-related topic versus not labeled drug-related. It does not predict suspicious dealing or trafficking.** X-Sensitive is English social-media data, so its metrics do not establish performance on Hinglish or on the project's fictional chat simulations. The current model can be used as one evidence signal; a separate, appropriately labeled dealing-versus-benign message dataset is required to train that decision.

Do not place mock/fallback feeds, simulation conversations, generated examples, runtime evidence, or unreviewed cases here. Record each dataset's source, license/permission, collection date or version, label definitions, class balance, and split method before training or promoting any model.
