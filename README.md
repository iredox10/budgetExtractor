# Budget Extraction Engine (CLI, OCR Deferred)

Deterministic, fail-closed extraction pipeline for single-state budget PDFs.

## Prerequisites
- Python 3.10+
- Poppler tools: `pdfinfo` and `pdftotext`
- Tkinter for UI: `python3-tk` (Ubuntu/Debian)

## Run
From the repo root:

```bash
python -m engine.apps.cli --input "<path-to-pdf>"
```

Optional output directory:

```bash
python -m engine.apps.cli --input "<path-to-pdf>" --output-dir "analysis/engine_runs/<run-name>"
```

## UI
Launch the local UI:

```bash
python -m engine.apps.ui
```

Use the UI to select a PDF and an output folder, then run extraction.
The UI creates a subfolder named `<state>_<year>` in the selected output folder
and copies the source PDF as `source.pdf` inside that folder.

If you run from outside the repo root:

```bash
python /home/iredox/Desktop/scrapers/budgets/run_ui.py
```

## Output
- `output.json` (contract-shaped output with null+reason for missing fields)
- `app_output.json` (flattened adapter output for app UI)
- `sections.json` (section order + classification scheme)
- `text.txt` (layout-preserved full text)
- `page_metrics.json` (per-page layout metrics)
- `review.json` (error summary and taxonomy for review)
- `run.log` (pipeline progress log)

## Notes
- OCR is deferred. Native text extraction is used first.
- The engine fails closed: uncertain fields are null with a reason.
- Administrative units are emitted as a flat list and nested under parent MDAs.
- If `text.txt` or `page_metrics.json` already exist, the pipeline reuses them.
