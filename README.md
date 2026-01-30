# Budget Extraction Engine (CLI, OCR Deferred)

Deterministic, fail-closed extraction pipeline for single-state budget PDFs.

## Prerequisites
- Python 3.10+
- Poppler tools: `pdfinfo` and `pdftotext`

## Run
From the repo root:

```bash
python -m engine.cli --input "<path-to-pdf>"
```

Optional output directory:

```bash
python -m engine.cli --input "<path-to-pdf>" --output-dir "analysis/engine_runs/<run-name>"
```

## UI
Launch the local UI:

```bash
python -m engine.ui
```

Use the UI to select a PDF and an output folder, then run extraction.

## Output
- `output.json` (contract-shaped output with null+reason for missing fields)
- `text.txt` (layout-preserved full text)
- `page_metrics.json` (per-page layout metrics)

## Notes
- OCR is deferred. Native text extraction is used first.
- The engine fails closed: uncertain fields are null with a reason.
- Administrative units are emitted as a flat list and nested under parent MDAs.
