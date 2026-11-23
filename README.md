# Mistral-test: document decision app

Reads incoming documents (`.txt`, `.md`, `.json`; `.pdf` with the optional `pdf` extra)
and suggests a decision (e.g. `approve`, `escalate`, `review`, `request_more_info`)
using a declarative, config-driven rule engine.

## Install

```bash
pip install -e '.[pdf]'   # pdf extra optional
```

## Usage

```bash
python -m docdecision process samples/invoice_small.txt
python -m docdecision read    samples/invoice_large.txt
python -m docdecision watch   samples/          # process every supported file in a directory
docdecision process path/to/document.pdf        # once installed
```

Each command prints one JSON object per document:

```json
{"decision": "approve", "rule": "small-invoice-auto-approve", "reasons": ["..."], "fields": {"amount": 412.9}, "source": "samples/invoice_small.txt"}
```

Exit code is `0` when every document was processed and `1` when any document failed.

## Configuration

- `fields.yaml` — regex-based field extraction. Each field has a `regex` with a named
  `value` group and an optional `cast` (`string`, `number`, `float`).
- `rules.yaml` — declarative rules. Each rule has `name`, `when` (field conditions),
  `suggest` (the decision), `reasons`, and a `priority`; lower priority wins and the
  first match is returned. Conditions support `eq`, `ne`, `lt`, `lte`, `gt`, `gte`,
  `in`, `not_in`, `regex`, `present`, `missing`, and `any_of` groups. `default` is the
  decision used when no rule matches (default `needs_review`).

Adapt both files to your own document types and policies.

## Tests

```bash
python -m unittest discover -s tests -v
```
