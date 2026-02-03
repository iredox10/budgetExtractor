from __future__ import annotations

import re
import shutil
import threading
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk
    from tkinter import filedialog, messagebox
else:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except ModuleNotFoundError as exc:  # pragma: no cover - environment specific
        tk = None
        filedialog = None
        messagebox = None
        _tk_error = exc
    else:
        _tk_error = None

try:
    from engine.pipeline import run_pipeline
except ModuleNotFoundError:  # pragma: no cover - path fallback
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from engine.pipeline import run_pipeline


class EngineUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Budget Extraction Engine")
        self.root.geometry("760x520")

        self.pdf_path: Path | None = None
        self.output_dir: Path | None = None

        self._build_layout()

    def _build_layout(self) -> None:
        container = tk.Frame(self.root, padx=16, pady=16)
        container.pack(fill=tk.BOTH, expand=True)

        title = tk.Label(
            container,
            text="Budget Extraction Engine (OCR deferred)",
            font=("TkDefaultFont", 14, "bold"),
        )
        title.pack(anchor="w")

        pdf_frame = tk.Frame(container)
        pdf_frame.pack(fill=tk.X, pady=(16, 8))
        tk.Button(pdf_frame, text="Select PDF", command=self.select_pdf).pack(
            side=tk.LEFT
        )
        self.pdf_label = tk.Label(pdf_frame, text="No PDF selected", anchor="w")
        self.pdf_label.pack(side=tk.LEFT, padx=12)

        out_frame = tk.Frame(container)
        out_frame.pack(fill=tk.X, pady=8)
        tk.Button(out_frame, text="Select Output Folder", command=self.select_output).pack(
            side=tk.LEFT
        )
        self.output_label = tk.Label(out_frame, text="Using default output folder", anchor="w")
        self.output_label.pack(side=tk.LEFT, padx=12)

        options_frame = tk.Frame(container)
        options_frame.pack(fill=tk.X, pady=(8, 16))
        self.overwrite_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            options_frame,
            text="Overwrite existing output folder",
            variable=self.overwrite_var,
        ).pack(anchor="w")

        run_frame = tk.Frame(container)
        run_frame.pack(fill=tk.X, pady=(0, 12))
        self.run_button = tk.Button(run_frame, text="Run Extraction", command=self.run)
        self.run_button.pack(side=tk.LEFT)
        self.status_label = tk.Label(run_frame, text="Idle", anchor="w")
        self.status_label.pack(side=tk.LEFT, padx=12)

        log_label = tk.Label(container, text="Logs", anchor="w")
        log_label.pack(anchor="w")
        self.log_text = tk.Text(container, height=15, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.log_text.configure(state=tk.DISABLED)

    def log(self, message: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def select_pdf(self) -> None:
        path = filedialog.askopenfilename(
            title="Select budget PDF",
            filetypes=[("PDF files", "*.pdf")],
        )
        if not path:
            return
        self.pdf_path = Path(path)
        self.pdf_label.config(text=str(self.pdf_path))
        self.log(f"Selected PDF: {self.pdf_path}")

    def select_output(self) -> None:
        path = filedialog.askdirectory(title="Select output folder")
        if not path:
            return
        self.output_dir = Path(path)
        self.output_label.config(text=str(self.output_dir))
        self.log(f"Selected output base folder: {self.output_dir}")

    def set_status(self, text: str) -> None:
        self.status_label.config(text=text)

    def run(self) -> None:
        if not self.pdf_path:
            messagebox.showerror("Missing input", "Please select a PDF file.")
            return

        pdf_path = self.pdf_path
        if pdf_path is None:
            messagebox.showerror("Missing input", "Please select a PDF file.")
            return

        self.run_button.config(state=tk.DISABLED)
        self.set_status("Running...")
        self.log("Starting extraction...")

        thread = threading.Thread(target=self._run_pipeline, args=(pdf_path,), daemon=True)
        thread.start()

    def _run_pipeline(self, pdf_path: Path) -> None:
        try:
            output_dir = self._resolve_output_dir(pdf_path)
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = run_pipeline(pdf_path, output_dir, overwrite=self.overwrite_var.get())
            source_path = output_dir / "source.pdf"
            if not source_path.exists() or self.overwrite_var.get():
                shutil.copy2(pdf_path, source_path)
            self.root.after(0, self._on_success, output_path, output_dir)
        except Exception as exc:  # noqa: BLE001
            self.root.after(0, self._on_error, exc)

    def _default_output_dir(self, pdf_path: Path) -> Path:
        return Path.cwd() / "analysis" / "engine_runs" / pdf_path.stem

    def _resolve_output_dir(self, pdf_path: Path) -> Path:
        if self.output_dir is None:
            return self._default_output_dir(pdf_path)
        state, year = _derive_state_year(pdf_path)
        folder_name = _sanitize_folder_name(f"{state}_{year}")
        return self.output_dir / folder_name

    def _on_success(self, output_path: Path, output_dir: Path) -> None:
        self.set_status("Done")
        self.log(f"Output written to: {output_path}")
        self.log(f"Artifacts folder: {output_dir}")
        self.run_button.config(state=tk.NORMAL)
        messagebox.showinfo("Success", f"Extraction completed.\n{output_path}")

    def _on_error(self, exc: Exception) -> None:
        self.set_status("Failed")
        self.log(f"Error: {exc}")
        self.run_button.config(state=tk.NORMAL)
        messagebox.showerror("Extraction failed", str(exc))


def main() -> None:
    if tk is None:
        raise SystemExit(
            "tkinter is not available. Install python3-tk (Ubuntu/Debian) or use the CLI."
        ) from _tk_error
    root = tk.Tk()
    EngineUI(root)
    root.mainloop()


def _derive_state_year(pdf_path: Path) -> tuple[str, str]:
    stem = pdf_path.stem
    year_match = re.search(r"(20\d{2})", stem)
    year = year_match.group(1) if year_match else "unknown_year"

    if "_" in stem:
        state = stem.split("_", 1)[0].strip()
    else:
        state_match = re.search(r"([A-Za-z][A-Za-z ]+)\s+STATE", stem, re.IGNORECASE)
        state = state_match.group(1).strip() if state_match else stem

    return state, year


def _sanitize_folder_name(value: str) -> str:
    cleaned = re.sub(r"\s+", "_", value.strip())
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.strip("_")


if __name__ == "__main__":
    main()
