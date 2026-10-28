from __future__ import annotations

from xinpilot_tooltips import Tooltip

from xinpilot_shared import *
from xinpilot.application.analysis_jobs import (
    AnalysisJob as _AnalysisJob,
    input_signature as _analysis_input_signature,
    platemap_kind as _pyparse_platemap_kind,
    has_analysis_results as _output_dir_has_pyparse_results,
    platemap_signature as _pyparse_platemap_signature,
)


class PyParseRunnerFrame(ttk.Frame):
    def __init__(self, master, title: str, default_target: Path, modified: bool, result_callback=None, input_change_callback=None, analysis_kind=None, result_context_callback=None):
        super().__init__(master)
        self.title = title
        self.modified = modified
        self.analysis_kind = analysis_kind
        self.result_callback = result_callback
        self.input_change_callback = input_change_callback
        self.result_context_callback = result_context_callback
        self._project_generation = 0
        self._job_counter = 0
        self._active_job = None
        self._run_input_containers = []
        self._run_control_states = []
        self.proc = None
        self.log_q = queue.Queue()
        self.start_time = None
        self.default_target = Path(default_target)
        self.current_analysis_kind = "product" if modified else "standard"
        self._suspend_platemap_invalidation = True
        self._output_platemap_signature = None
        self._output_picker_parent = ""

        self.input_data_var = tk.StringVar(value="")
        self.platemap_var = tk.StringVar(value="")
        self.target_var = tk.StringVar(value=str(default_target))
        self.output_dir_var = tk.StringVar(value="")
        self.instrument_var = tk.StringVar(value="Waters")
        self.detector_var = tk.StringVar(value="UV")
        self.analysis_name_var = tk.StringVar(value="")
        self.split_product_peaks_var = tk.BooleanVar(value=False)
        self.strict_product_assignment_var = tk.BooleanVar(value=True)
        self.uv254_exclude_rt_var = tk.StringVar(value="")
        self.product_isotope_rt_block_var = tk.StringVar(value="")

        self.platemap_var.trace_add("write", self._on_platemap_var_changed)
        self.output_dir_var.trace_add("write", self._on_output_dir_var_changed)

        self._build_ui()
        self._suspend_platemap_invalidation = False
        self.after(100, self._drain_logs)

    def _build_ui(self):
        files = ttk.LabelFrame(self, text=f"{self.title} inputs", padding=8, style="FileRegion.TLabelframe")
        files.pack(fill="x", padx=8, pady=8)
        self._run_input_containers.append(files)
        files.columnconfigure(1, weight=1)

        self._file_row(files, 0, "LCMS input (Waters UV254 .rpt)" if self.modified else "LCMS input (.rpt/.daml/folder)", self.input_data_var, self._pick_input_data)
        self._file_row(files, 1, "Generated PyParse platemap", self.platemap_var, self._pick_platemap)
        self._folder_row(files, 2, "Output folder (choose a new folder for each analysis)", self.output_dir_var, self._pick_output_dir)
        style_region_widgets(files, "FileRegion")

        if self.modified and self.analysis_kind != "impurity":
            opts = ttk.LabelFrame(self, text="Run options", padding=8, style="ChemRegion.TLabelframe")
            opts.pack(fill="x", padx=8, pady=(0, 8))
            self._run_input_containers.append(opts)
            split = ttk.Checkbutton(opts, text="Split product peaks", variable=self.split_product_peaks_var)
            split.grid(row=0, column=0, columnspan=4, sticky="w", padx=4)
            split._xinpilot_tooltip = Tooltip(split, "Keep multiple accepted product peaks in each well and sum their areas and purity contribution. Leave off to select one peak. Matching masses alone do not confirm chemical identity.")
            exclude_label = ttk.Label(opts, text="UV254 exclude RT")
            exclude_label.grid(row=2, column=0, sticky="w", padx=4, pady=3)
            exclude_label._xinpilot_tooltip = Tooltip(exclude_label, "Exclude whole peaks overlapping these retention-time ranges from UV purity, for example 0.0-0.8 3.2-3.8 (minutes). This does not remove peaks from identification or erase the original trace.")
            entry = ttk.Entry(opts, textvariable=self.uv254_exclude_rt_var, width=38)
            entry.grid(row=2, column=1, columnspan=3, sticky="ew")
            entry._xinpilot_tooltip = Tooltip(entry, exclude_label._xinpilot_tooltip.text)
            isotope_label = ttk.Label(opts, text="Product isotope block RT")
            isotope_label.grid(row=3, column=0, sticky="w", padx=4, pady=3)
            isotope_label._xinpilot_tooltip = Tooltip(isotope_label, "Advanced: reject product candidates overlapping these time ranges when the secondary target mass (mass2) matches. mass2 may represent a halogen isotope or a Boc-loss fragment. Leave blank unless you have reviewed the evidence.")
            entry = ttk.Entry(opts, textvariable=self.product_isotope_rt_block_var, width=38)
            entry.grid(row=3, column=1, columnspan=3, sticky="ew")
            entry._xinpilot_tooltip = Tooltip(entry, isotope_label._xinpilot_tooltip.text)
            ttk.Label(opts, text="Analysis name").grid(row=4, column=0, sticky="w", padx=4, pady=3)
            ttk.Entry(opts, textvariable=self.analysis_name_var, width=38).grid(row=4, column=1, columnspan=3, sticky="ew")
            opts.columnconfigure(3, weight=1)
            style_region_widgets(opts, "ChemRegion")

        ctl = ttk.Frame(self, padding=(8, 0, 8, 6))
        ctl.pack(fill="x")
        self.run_btn = ttk.Button(ctl, text=f"Run {self.title}", command=self._run, style="ChemAction.TButton")
        self.run_btn.pack(side="left")
        ttk.Button(ctl, text="Clear Log", command=lambda: self.log.delete("1.0", "end"), style="Danger.TButton").pack(side="left", padx=8)
        self.status_label = ttk.Label(ctl, text="Ready")
        self.status_label.pack(side="right")

        log_box = ttk.LabelFrame(self, text="Log", padding=8, style="RowRegion.TLabelframe")
        log_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.log = ScrolledText(log_box, height=18, wrap="word")
        self.log.pack(fill="both", expand=True)
        style_region_widgets(log_box, "RowRegion")

    def _file_row(self, parent, row, label, var, command):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 6), pady=3)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", pady=3)
        ttk.Button(parent, text="Browse", command=command, style="FileAction.TButton").grid(row=row, column=2, padx=(6, 0), pady=3)

    def _folder_row(self, parent, row, label, var, command):
        self._file_row(parent, row, label, var, command)

    def _clear_output_for_platemap_change(self):
        """Require an explicit output-folder choice for every platemap revision."""
        self._output_platemap_signature = None
        if self.output_dir_var.get():
            self.output_dir_var.set("")

    def _on_platemap_var_changed(self, *_args):
        if not self._suspend_platemap_invalidation:
            self._clear_output_for_platemap_change()

    def _on_output_dir_var_changed(self, *_args):
        if self._suspend_platemap_invalidation:
            return
        if self.output_dir_var.get().strip():
            self._output_picker_parent = str(Path(self.output_dir_var.get().strip()).expanduser().parent)
            self._output_platemap_signature = _pyparse_platemap_signature(
                self.platemap_var.get()
            )
        else:
            self._output_platemap_signature = None

    def _clear_stale_output_for_in_place_platemap_edit(self) -> bool:
        """Clear output if the selected platemap changed since folder selection."""
        if not self.output_dir_var.get().strip():
            return False
        current_signature = _pyparse_platemap_signature(self.platemap_var.get())
        if self._output_platemap_signature == current_signature:
            return False
        self._clear_output_for_platemap_change()
        return True

    def set_platemap(self, path: Path):
        # Generation frequently rewrites the same internal CSV path. Invalidate
        # the output explicitly even when the visible path string is unchanged.
        self._clear_output_for_platemap_change()
        self._suspend_platemap_invalidation = True
        try:
            self.platemap_var.set(str(path))
        finally:
            self._suspend_platemap_invalidation = False

    def export_state(self) -> Dict[str, object]:
        return {
            "target": self.target_var.get(),
            "input_data": self.input_data_var.get(),
            "platemap": self.platemap_var.get(),
            "output_dir": self.output_dir_var.get(),
            "detector": self.detector_var.get(),
            "split_product_peaks": bool(self.split_product_peaks_var.get()),
            "strict_product_assignment": bool(self.strict_product_assignment_var.get()),
            "uv254_exclude_rt": self.uv254_exclude_rt_var.get(),
            "product_isotope_rt_block": self.product_isotope_rt_block_var.get(),
            "analysis_name": self.analysis_name_var.get(),
        }

    def import_state(self, data: Dict[str, object]):
        if not isinstance(data, dict):
            return
        self.invalidate_pending_results()
        self._suspend_platemap_invalidation = True
        try:
            self.target_var.set(str(self.default_target))
            self.input_data_var.set(str(data.get("input_data", "") or ""))
            self.platemap_var.set(str(data.get("platemap", "") or ""))
            self.output_dir_var.set(str(data.get("output_dir", "") or ""))
            output_path = self.output_dir_var.get().strip()
            self._output_picker_parent = str(Path(output_path).expanduser().parent) if output_path else ""
            self.detector_var.set("UV")
            self.split_product_peaks_var.set(bool(data.get("split_product_peaks", False)) if self.analysis_kind != "impurity" else False)
            self.strict_product_assignment_var.set(True)
            self.uv254_exclude_rt_var.set(str(data.get("uv254_exclude_rt", "") or ""))
            self.product_isotope_rt_block_var.set(str(data.get("product_isotope_rt_block", "") or ""))
            self.analysis_name_var.set(str(data.get("analysis_name", "") or ""))
        finally:
            self._suspend_platemap_invalidation = False
        self._output_platemap_signature = (
            _pyparse_platemap_signature(self.platemap_var.get())
            if self.output_dir_var.get().strip()
            else None
        )

    def _pick_input_data(self):
        p = filedialog.askopenfilename(
            title="Select LCMS input",
            filetypes=([("Waters UV254 report", "*.rpt")] if self.modified else [("LCMS files", "*.rpt;*.daml"), ("All files", "*.*")]),
        )
        if not p and not self.modified:
            p = filedialog.askdirectory(title="Select LCMS input folder")
        if p:
            self.input_data_var.set(p)
            if self.input_change_callback:
                self.input_change_callback(p)

    def _pick_platemap(self):
        p = filedialog.askopenfilename(filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        if p:
            self.platemap_var.set(p)

    def _pick_target(self):
        p = filedialog.askopenfilename(filetypes=[("PyParse target", "*.exe;*.py"), ("Executable", "*.exe"), ("Python file", "*.py"), ("All files", "*.*")])
        if p:
            self.target_var.set(p)

    def _pick_output_dir(self):
        # Always provide an explicit start directory: native dialogs otherwise
        # reuse the last folder visited by any of the analysis pages.
        current = self.output_dir_var.get().strip()
        start = Path(current).expanduser().parent if current else None
        if start is None and self._output_picker_parent:
            start = Path(self._output_picker_parent)
        if start is None:
            reference = self.platemap_var.get().strip() or self.input_data_var.get().strip()
            start = Path(reference).expanduser().parent if reference else Path.home()
        start = start.resolve()
        while not start.is_dir() and start != start.parent:
            start = start.parent
        p = filedialog.askdirectory(
            parent=self.winfo_toplevel(),
            title=f"{self.title}: choose a new output folder",
            initialdir=str(start),
            mustexist=False,
        )
        if p:
            if _output_dir_has_pyparse_results(Path(p)):
                messagebox.showwarning(
                    "New output folder required",
                    "This folder already contains PyParse results. Choose or create a new folder for this analysis.",
                    parent=self.winfo_toplevel(),
                )
                return
            self.output_dir_var.set(p)

    def _validate(self):
        input_text = self.input_data_var.get().strip()
        platemap_text = self.platemap_var.get().strip()
        target_text = self.target_var.get().strip()
        output_text = self.output_dir_var.get().strip()
        if self._clear_stale_output_for_in_place_platemap_edit():
            return (
                "The generated PyParse platemap changed after the output folder was selected.\n\n"
                "Reselect an output folder before running this analysis."
            )
        if not input_text:
            return "Select an LCMS input file or folder."
        if not platemap_text:
            return "Select or generate a PyParse platemap CSV."
        if not target_text:
            return "PyParse target is not configured."
        if not output_text:
            return "Select an output folder."
        input_data = Path(input_text)
        platemap = Path(platemap_text)
        target = Path(target_text)
        output_dir = Path(output_text)
        if not input_data.exists():
            return f"LCMS input does not exist:\n{input_data}"
        if not platemap.is_file():
            return f"Generated PyParse platemap does not exist:\n{platemap}"
        if not target.is_file():
            return f"PyParse target does not exist:\n{target}"
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            return f"Could not create output folder:\n{output_dir}\n\n{exc}"
        analysis_kind = _pyparse_platemap_kind(platemap) if self.modified else "standard"
        if self.modified and self.analysis_kind and analysis_kind != self.analysis_kind:
            return f"This input belongs to {analysis_kind} analysis. Use the Modified PyParse - {analysis_kind.title()} analysis page."
        if _output_dir_has_pyparse_results(output_dir):
            label = "impurity" if analysis_kind == "impurity" else "product"
            return (
                "This output folder already contains PyParse analysis files.\n\n"
                f"Select or create a new empty folder for this {label} analysis. "
                "Product and impurity analyses must use separate folders so stale or "
                "unrelated images cannot be displayed."
            )
        return None

    def _build_cmd(self):
        target = self.target_var.get().strip()
        platemap = self.platemap_var.get().strip()
        if not self.modified:
            platemap = self._standard_pyparse_platemap()
        base = [
            self.input_data_var.get().strip(),
            platemap,
            "-o",
            self.output_dir_var.get().strip(),
        ]
        if self.modified:
            base += [
                "-i", self.instrument_var.get(),
                "-d", "UV",
                "-g", "True",
                "-z", "True",
                "-a", "True",
                "-u254", "True",
                "-spp", str(self.split_product_peaks_var.get() if self.analysis_kind != "impurity" else False),
                "-spa", "True",
            ]
            if self.analysis_kind != "impurity" and self.uv254_exclude_rt_var.get().strip():
                base += ["-u254x", self.uv254_exclude_rt_var.get().strip()]
            if self.analysis_kind != "impurity" and self.product_isotope_rt_block_var.get().strip():
                base += ["-pir", self.product_isotope_rt_block_var.get().strip()]
            if self.analysis_kind != "impurity" and self.analysis_name_var.get().strip():
                base += ["-n", self.analysis_name_var.get().strip()]
        if getattr(sys, "frozen", False):
            runner = "modified" if self.modified else "standard"
            return [sys.executable, "--oneclick-run-pyparse", runner] + base
        if target.lower().endswith(".exe"):
            return [target] + base
        return [sys.executable, target] + base

    def _standard_pyparse_platemap(self) -> str:
        source = Path(self.platemap_var.get().strip())
        output_dir = Path(self.output_dir_var.get().strip())
        target = output_dir / "_oneclick_original_pyparse_platemap.csv"
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            with source.open("r", encoding="utf-8-sig", newline="") as src:
                reader = csv.DictReader(src)
                if not reader.fieldnames:
                    return str(source)
                fieldnames = list(reader.fieldnames)
                rows = list(reader)
            for row in rows:
                if "desired product name" in row:
                    row["desired product name"] = ""
                if "desired product id" in row:
                    row["desired product id"] = ""
            with target.open("w", encoding="utf-8", newline="") as dst:
                writer = csv.DictWriter(dst, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
            return str(target)
        except Exception:
            return str(source)

    def invalidate_pending_results(self):
        """Keep a running job's files, but never attach them to another project."""
        self._project_generation += 1

    def _set_run_controls(self, running):
        if running:
            self._run_control_states = []
            pending = list(self._run_input_containers)
            while pending:
                widget = pending.pop()
                pending.extend(widget.winfo_children())
                if isinstance(widget, (ttk.Entry, ttk.Button, ttk.Checkbutton, ttk.Combobox)):
                    self._run_control_states.append((widget, widget.state()))
                    widget.state(["disabled"])
        else:
            for widget, previous in self._run_control_states:
                widget.state(["!disabled"])
                if previous:
                    widget.state(previous)
            self._run_control_states = []
        self.run_btn.config(state="disabled" if running else "normal")

    def _run(self):
        # Reserve the job before starting its thread: Popen may not exist yet
        # when a second click arrives through the desktop bridge.
        if self._active_job is not None or (self.proc and self.proc.poll() is None):
            messagebox.showwarning("Running", f"{self.title} is already running.")
            return
        err = self._validate()
        if err:
            messagebox.showerror("Input error", err)
            return
        cmd = self._build_cmd()
        self.current_analysis_kind = (
            _pyparse_platemap_kind(Path(self.platemap_var.get().strip()))
            if self.modified else "standard"
        )
        try:
            context = self.result_context_callback() if self.result_context_callback else None
            self._job_counter += 1
            job = _AnalysisJob(
                token=self._job_counter,
                project_generation=self._project_generation,
                output_dir=Path(self.output_dir_var.get().strip()).resolve(),
                analysis_kind=self.current_analysis_kind,
                context_signature=context,
                platemap_signature=_pyparse_platemap_signature(self.platemap_var.get()),
                started_at=time.time(),
                input_signature=_analysis_input_signature(self.input_data_var.get()),
            )
            manifest = {
                "analysis_kind": self.current_analysis_kind,
                "input_data": self.input_data_var.get().strip(),
                "platemap": self.platemap_var.get().strip(),
                "created_by": "XinPilot",
            }
            manifest_path = job.output_dir / "xinpilot_pyparse_run.json"
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("Output error", f"Could not prepare the analysis folder:\n{exc}")
            return
        printable = " ".join(f'"{part}"' if " " in part else part for part in cmd)
        self.log.insert("end", "\n=== Running command ===\n" + printable + "\n\n")
        self.log.see("end")
        self.status_label.config(text="Running...")
        self._active_job = job
        self._set_run_controls(True)
        self.start_time = job.started_at
        threading.Thread(target=self._worker, args=(cmd, job), daemon=True).start()

    def _worker(self, cmd, job):
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            for line in self.proc.stdout:
                self.log_q.put(("__LOG__", job.token, line))
            rc = self.proc.wait()
            elapsed = time.time() - job.started_at
            self.log_q.put(("__LOG__", job.token, f"\n=== Finished with code {rc} in {elapsed:.1f}s ===\n"))
            self.log_q.put(("__DONE__", job, rc, elapsed))
        except Exception as exc:
            self.log_q.put(("__LOG__", job.token, f"\n[ERROR] {exc}\n"))
            self.log_q.put(("__DONE__", job, -1, 0.0))

    def _complete_job(self, job, rc, elapsed):
        if self._active_job is None or job.token != self._active_job.token:
            return
        self._active_job = None
        self.proc = None
        self._set_run_controls(False)
        self.status_label.config(text=f"Done (code {rc}, {elapsed:.1f}s)" if rc == 0 else f"Failed (code {rc})")
        try:
            current_context = self.result_context_callback() if self.result_context_callback else None
            relevant = (
                job.project_generation == self._project_generation
                and job.context_signature == current_context
                and job.platemap_signature == _pyparse_platemap_signature(self.platemap_var.get())
                and (not job.input_signature or job.input_signature == _analysis_input_signature(self.input_data_var.get()))
            )
        except Exception:
            relevant = False
        if not relevant:
            self.status_label.config(text="Finished; results kept in original output folder")
            self.log.insert("end", f"\nProject or analytical targets changed during analysis. Results were not attached to the current project. Output: {job.output_dir}\n")
            self.log.see("end")
        elif rc == 0 and self.result_callback:
            self.result_callback(job.output_dir, job.analysis_kind)
        elif rc != 0:
            messagebox.showerror(f"{self.title} failed", "The run ended with an error. Check the log panel.")

    def _drain_logs(self):
        try:
            while True:
                item = self.log_q.get_nowait()
                if isinstance(item, tuple) and item and item[0] == "__DONE__":
                    _, job, rc, elapsed = item
                    self._complete_job(job, rc, elapsed)
                elif isinstance(item, tuple) and item and item[0] == "__LOG__":
                    _, token, line = item
                    if self._active_job is not None and token == self._active_job.token:
                        self.log.insert("end", line)
                        self.log.see("end")
                else:
                    self.log.insert("end", item)
                    self.log.see("end")
        except queue.Empty:
            pass
        self.after(100, self._drain_logs)
