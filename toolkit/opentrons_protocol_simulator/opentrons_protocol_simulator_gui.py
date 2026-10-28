import os
import shutil
import tempfile
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from opentrons import simulate

APP_TITLE = "Opentrons Protocol Simulator"


class SimulatorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1120x860")
        self.root.minsize(980, 760)

        self.protocol_path = tk.StringVar()
        self.status_text = tk.StringVar(value="Ready")
        self.imported_labware_files: list[str] = []
        self._build_ui()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        title = ttk.Label(frame, text=APP_TITLE, font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))

        ttk.Label(frame, text="Protocol file (.py or .json)").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.protocol_path).grid(row=1, column=1, columnspan=2, sticky="ew", padx=8)
        ttk.Button(frame, text="Browse...", command=self._browse_protocol).grid(row=1, column=3, sticky="ew")

        ttk.Label(frame, text="Imported custom labware JSONs").grid(row=2, column=0, sticky="nw", pady=4)
        labware_frame = ttk.Frame(frame)
        labware_frame.grid(row=2, column=1, columnspan=2, sticky="nsew", padx=8)
        labware_frame.columnconfigure(0, weight=1)

        self.labware_listbox = tk.Listbox(labware_frame, height=8, selectmode=tk.EXTENDED)
        self.labware_listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(labware_frame, orient="vertical", command=self.labware_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.labware_listbox.config(yscrollcommand=scrollbar.set)
        labware_frame.rowconfigure(0, weight=1)

        labware_buttons = ttk.Frame(frame)
        labware_buttons.grid(row=2, column=3, sticky="ne")
        ttk.Button(labware_buttons, text="Import JSON...", command=self._import_labware_file).pack(fill="x")
        ttk.Button(labware_buttons, text="Import Folder...", command=self._import_labware_folder).pack(fill="x", pady=(6, 0))
        ttk.Button(labware_buttons, text="Remove Selected", command=self._remove_selected_labware).pack(fill="x", pady=(18, 0))
        ttk.Button(labware_buttons, text="Clear All", command=self._clear_labware).pack(fill="x", pady=(6, 0))

        actions = ttk.Frame(frame)
        actions.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(10, 8))
        ttk.Button(actions, text="Simulate", command=self._start_simulation).pack(side="left")
        ttk.Button(actions, text="Save Output...", command=self._save_output).pack(side="left", padx=8)
        ttk.Button(actions, text="Clear Output", command=self._clear_output).pack(side="left")

        help_text = (
            "This build is self-contained: simulation runs using the bundled Opentrons stack inside the distributable. "
            "Import labware one JSON at a time if you want; each imported file is registered in the list."
        )
        ttk.Label(frame, text=help_text, wraplength=1060, foreground="#444").grid(row=4, column=0, columnspan=4, sticky="w", pady=(0, 8))

        self.output = scrolledtext.ScrolledText(frame, wrap="word", font=("Consolas", 10))
        self.output.grid(row=5, column=0, columnspan=4, sticky="nsew")
        frame.rowconfigure(5, weight=1)

        status_bar = ttk.Label(frame, textvariable=self.status_text, relief="sunken", anchor="w")
        status_bar.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(8, 0))

    def _browse_protocol(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Opentrons protocol",
            filetypes=[("Protocols", "*.py *.json"), ("Python", "*.py"), ("JSON", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.protocol_path.set(path)

    def _import_labware_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Select custom labware JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self._add_labware_paths([path])

    def _import_labware_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select folder containing custom labware JSON files")
        if not folder:
            return
        json_files = [str(path) for path in sorted(Path(folder).glob("*.json"))]
        if not json_files:
            messagebox.showinfo(APP_TITLE, "No JSON files found in that folder.")
            return
        self._add_labware_paths(json_files)

    def _add_labware_paths(self, paths):
        added = 0
        for path in paths:
            normalized = str(Path(path))
            if normalized not in self.imported_labware_files:
                self.imported_labware_files.append(normalized)
                self.labware_listbox.insert("end", normalized)
                added += 1
        self._set_status(f"Imported {added} custom labware file(s)")

    def _remove_selected_labware(self) -> None:
        selected = list(self.labware_listbox.curselection())
        if not selected:
            return
        for index in reversed(selected):
            del self.imported_labware_files[index]
            self.labware_listbox.delete(index)
        self._set_status("Removed selected labware")

    def _clear_labware(self) -> None:
        self.imported_labware_files.clear()
        self.labware_listbox.delete(0, "end")
        self._set_status("Cleared imported labware")

    def _append_output(self, text: str) -> None:
        self.output.insert("end", text)
        self.output.see("end")

    def _set_status(self, text: str) -> None:
        self.status_text.set(text)
        self.root.update_idletasks()

    def _clear_output(self) -> None:
        self.output.delete("1.0", "end")
        self._set_status("Output cleared")

    def _save_output(self) -> None:
        content = self.output.get("1.0", "end").strip()
        if not content:
            messagebox.showinfo(APP_TITLE, "There is no output to save yet.")
            return
        path = filedialog.asksaveasfilename(
            title="Save simulation output",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        Path(path).write_text(content, encoding="utf-8")
        self._set_status(f"Saved output to {path}")

    def _start_simulation(self) -> None:
        protocol = self.protocol_path.get().strip()
        if not protocol:
            messagebox.showerror(APP_TITLE, "Please select a protocol file first.")
            return
        if not os.path.isfile(protocol):
            messagebox.showerror(APP_TITLE, f"Protocol file not found:\n{protocol}")
            return

        self._set_status("Simulating...")
        self._append_output("\n" + "=" * 90 + "\n")
        self._append_output(f"Protocol: {protocol}\n")
        if self.imported_labware_files:
            self._append_output("Imported labware:\n")
            for path in self.imported_labware_files:
                self._append_output(f"  - {path}\n")

        worker = threading.Thread(target=self._run_simulation, daemon=True)
        worker.start()

    def _run_simulation(self) -> None:
        temp_dirs = []
        try:
            protocol_path = self.protocol_path.get().strip()
            custom_labware_dir, labware_note = self._prepare_labware_directory()
            if custom_labware_dir:
                temp_dirs.append(custom_labware_dir)

            if labware_note:
                self.root.after(0, lambda: self._append_output(labware_note + "\n"))

            with open(protocol_path, "rb") as handle:
                runlog, bundle = simulate.simulate(
                    handle,
                    file_name=os.path.basename(protocol_path),
                    custom_labware_paths=[custom_labware_dir] if custom_labware_dir else None,
                    log_level="warning",
                )

            formatted = simulate.format_runlog(runlog)
            lines = [
                "Simulation completed successfully.\n",
                f"Runlog entries: {len(runlog)}\n",
                f"Bundle emitted: {'yes' if bundle else 'no'}\n\n",
                formatted if formatted.endswith("\n") else formatted + "\n",
            ]
            self.root.after(0, lambda: self._on_success("".join(lines)))
        except Exception:
            error_text = traceback.format_exc()
            self.root.after(0, lambda: self._on_error(error_text))
        finally:
            for temp_dir in temp_dirs:
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _prepare_labware_directory(self):
        if not self.imported_labware_files:
            return None, ""

        json_files = [path for path in self.imported_labware_files if os.path.isfile(path) and path.lower().endswith(".json")]
        if not json_files:
            return None, "No valid custom labware JSON files found."

        temp_dir = tempfile.mkdtemp(prefix="opentrons_labware_")
        copied = []
        for src in json_files:
            destination = Path(temp_dir) / Path(src).name
            base = destination.stem
            suffix = destination.suffix
            counter = 2
            while destination.exists():
                destination = Path(temp_dir) / f"{base}_{counter}{suffix}"
                counter += 1
            shutil.copy2(src, destination)
            copied.append(str(destination.name))

        note = f"Prepared {len(copied)} custom labware JSON file(s): " + ", ".join(copied)
        return temp_dir, note

    def _on_success(self, text: str) -> None:
        self._append_output(text)
        self._set_status("Simulation finished")

    def _on_error(self, error_text: str) -> None:
        self._append_output("Simulation failed.\n\n")
        self._append_output(error_text + "\n")
        self._set_status("Simulation failed")
        messagebox.showerror(APP_TITLE, "Simulation failed. See output panel for details.")


def main() -> int:
    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    SimulatorApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
