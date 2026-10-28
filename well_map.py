from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional, Sequence, Set


WELL_LABEL_RE = re.compile(r"^([A-Za-z]+)([0-9]+)$")


def row_label_to_number(label: str) -> int:
    number = 0
    for character in label.upper():
        number = number * 26 + (ord(character) - ord("A") + 1)
    return number


def row_number_to_label(number: int) -> str:
    label = ""
    while number > 0:
        number, remainder = divmod(number - 1, 26)
        label = chr(ord("A") + remainder) + label
    return label


def index_to_label(index: int, rows: int, cols: int, order: str) -> str:
    if not 1 <= index <= rows * cols:
        raise ValueError(f"Well index {index} out of range 1..{rows * cols}")
    if order == "column-major":
        col = (index - 1) // rows + 1
        row = (index - 1) % rows + 1
    elif order == "row-major":
        row = (index - 1) // cols + 1
        col = (index - 1) % cols + 1
    elif order == "row-major-reverse-columns":
        row = (index - 1) // cols + 1
        col = cols - ((index - 1) % cols + 1) + 1
    else:
        raise ValueError(f"Unknown order {order}")
    return f"{row_number_to_label(row)}{col}"


def label_to_index(label: str, rows: int, cols: int, order: str) -> int:
    match = WELL_LABEL_RE.match((label or "").strip())
    if not match:
        raise ValueError(f"Invalid well label: {label}")
    row = row_label_to_number(match.group(1))
    col = int(match.group(2))
    if not 1 <= row <= rows:
        raise ValueError(f"Row out of range in {label} (1..{rows})")
    if not 1 <= col <= cols:
        raise ValueError(f"Column out of range in {label} (1..{cols})")
    if order == "column-major":
        return (col - 1) * rows + row
    if order == "row-major":
        return (row - 1) * cols + col
    if order == "row-major-reverse-columns":
        return (row - 1) * cols + (cols - col + 1)
    raise ValueError(f"Unknown order {order}")


def parse_well_expr(expr: str, rows: int, cols: int, order: str) -> List[int]:
    text = (expr or "").strip()
    if not text:
        return []
    parsed: List[int] = []
    for part in [value.strip() for value in text.split(",") if value.strip()]:
        if WELL_LABEL_RE.match(part):
            parsed.append(label_to_index(part, rows, cols, order))
            continue
        if "-" in part and part[0].isdigit():
            range_part, _, step_part = part.partition(":")
            step = int(step_part) if step_part else 1
            if step <= 0:
                raise ValueError(f"Invalid step in '{part}'")
            start_text, end_text = range_part.split("-", 1)
            start, end = int(start_text), int(end_text)
            parsed.extend(range(start, end + (1 if start <= end else -1), step if start <= end else -step))
            continue
        parsed.append(int(part))

    result: List[int] = []
    seen = set()
    for index in parsed:
        if not 1 <= index <= rows * cols:
            raise ValueError(f"Well index {index} out of range 1..{rows * cols}")
        if index not in seen:
            result.append(index)
            seen.add(index)
    return result


def position_toplevel_near(dialog: tk.Toplevel, anchor: Optional[tk.Widget] = None):
    if anchor is None:
        return
    try:
        dialog.update_idletasks()
        anchor.update_idletasks()
        x = anchor.winfo_rootx() + anchor.winfo_width() + 8
        y = anchor.winfo_rooty() - 8
        width = dialog.winfo_reqwidth()
        height = dialog.winfo_reqheight()
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        if x + width + 16 > screen_width:
            x = anchor.winfo_rootx() - width - 8
        x = max(0, min(x, screen_width - width - 8))
        y = max(0, min(y, screen_height - height - 40))
        dialog.geometry(f"+{x}+{y}")
    except Exception:
        pass


class WellMapDialog(tk.Toplevel):
    def __init__(
        self,
        master,
        rows: int,
        cols: int,
        initial_labels: str = "",
        vertical_view: bool = False,
        anchor: Optional[tk.Widget] = None,
        single_select: bool = False,
        highlight_labels: Optional[Set[str]] = None,
        disabled_labels: Optional[Set[str]] = None,
        highlight_hint: str = "Light blue wells are already referenced and remain reusable.",
        disabled_hint: str = "Gray wells are unavailable.",
        instruction: str = "",
        selection_limit: Optional[int] = None,
        required_count: Optional[int] = None,
        pattern_groups: Optional[Sequence[Sequence[str]]] = None,
        batch_command: Optional[Callable[[], None]] = None,
        destination_set_mode: bool = False,
        initial_groups: Optional[Sequence[Sequence[str]]] = None,
        show_back: bool = False,
        labware_value: str = "",
        labware_values: Optional[Sequence[str]] = None,
    ):
        super().__init__(master)
        self.title("Select Source Well" if single_select else "Select Destination Wells")
        self.transient(master.winfo_toplevel())
        self.grab_set()
        self.resizable(False, False)
        self.rows, self.cols = rows, cols
        self.vertical_view = bool(vertical_view)
        self.single_select = bool(single_select)
        self.disabled = {str(label).strip().upper() for label in (disabled_labels or set()) if str(label).strip()}
        self.highlighted = {
            str(label).strip().upper() for label in (highlight_labels or set()) if str(label).strip()
        } - self.disabled
        self.highlight_hint = str(highlight_hint or "").strip()
        self.disabled_hint = str(disabled_hint or "").strip()
        self.instruction = str(instruction or "").strip()
        self.selection_limit = selection_limit
        self.required_count = required_count
        self.pattern_groups = [
            tuple(str(label).strip().upper() for label in group if str(label).strip())
            for group in (pattern_groups or ())
        ]
        self.pattern_by_label = {
            label: group for group in self.pattern_groups for label in group
        }
        self.batch_command = batch_command
        self.destination_set_mode = bool(destination_set_mode)
        self.batch_requested = False
        self.back_requested = False
        self.labware_change_requested = False
        self.requested_labware = str(labware_value or "")
        self.validation_message = tk.StringVar(value="")
        self.result_labels = ""
        self.result_groups: List[List[str]] = []
        self.recorded_sets: List[List[str]] = [
            [str(label).strip().upper() for label in group if str(label).strip()]
            for group in (initial_groups or ())
        ]
        labels = [value.strip().upper() for value in (initial_labels or "").split(",") if value.strip()]
        self.selected = set(labels[-1:] if self.single_select else labels)
        self.drag_state = None

        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)

        grid_start_row = 0
        if labware_values:
            labware_bar = ttk.Frame(frame)
            labware_bar.grid(
                row=0,
                column=0,
                columnspan=(self.rows if self.vertical_view else self.cols) + 1,
                sticky="ew",
                pady=(0, 6),
            )
            ttk.Label(labware_bar, text="Destination labware").pack(side="left", padx=(0, 6))
            self.labware_var = tk.StringVar(value=self.requested_labware)
            labware_combo = ttk.Combobox(
                labware_bar,
                textvariable=self.labware_var,
                values=list(labware_values),
                state="readonly",
                width=24,
            )
            labware_combo.pack(side="left")
            labware_combo.bind("<<ComboboxSelected>>", self._request_labware_change)
            grid_start_row = 1
        if self.instruction:
            ttk.Label(frame, text=self.instruction, wraplength=760).grid(
                row=grid_start_row, column=0, columnspan=(self.rows if self.vertical_view else self.cols) + 1,
                sticky="w", pady=(0, 6)
            )
            grid_start_row += 1

        def display_to_label(display_row: int, display_col: int) -> str:
            if not self.vertical_view:
                return f"{row_number_to_label(display_row)}{display_col}"
            logical_row = display_col
            logical_col = self.cols - display_row + 1
            return f"{row_number_to_label(logical_row)}{logical_col}"

        display_rows = self.cols if self.vertical_view else self.rows
        display_cols = self.rows if self.vertical_view else self.cols
        self.cells = {}
        for display_row in range(1, display_rows + 1):
            side_label = str(self.cols - display_row + 1) if self.vertical_view else row_number_to_label(display_row)
            ttk.Label(frame, text=side_label, width=3, anchor="center").grid(row=display_row + grid_start_row, column=0, padx=1, pady=1)
        for display_col in range(1, display_cols + 1):
            top_label = row_number_to_label(display_col) if self.vertical_view else str(display_col)
            ttk.Label(frame, text=top_label, width=5, anchor="center").grid(row=grid_start_row, column=display_col, padx=1, pady=1)
        for display_row in range(1, display_rows + 1):
            for display_col in range(1, display_cols + 1):
                label = display_to_label(display_row, display_col)
                cell = tk.Label(frame, text=label, width=6, relief="groove", bg="white")
                cell.grid(row=display_row + grid_start_row, column=display_col, padx=1, pady=1)
                cell.bind("<Button-1>", lambda _event, value=label: self._on_press(value))
                cell.bind("<Enter>", lambda _event, value=label: self._on_enter(value))
                cell.bind("<B1-Motion>", self._on_motion)
                cell.bind("<ButtonRelease-1>", self._on_release)
                self.cells[label] = cell

        footer_row = display_rows + grid_start_row + 1
        if self.highlighted and self.highlight_hint:
            ttk.Label(frame, text=self.highlight_hint).grid(row=footer_row, column=0, columnspan=display_cols + 1, sticky="w", pady=(6, 0))
            footer_row += 1
        if self.disabled and self.disabled_hint:
            ttk.Label(frame, text=self.disabled_hint).grid(row=footer_row, column=0, columnspan=display_cols + 1, sticky="w", pady=(6, 0))
            footer_row += 1
        if self.destination_set_mode:
            self.recorded_sets_frame = ttk.LabelFrame(frame, text="Recorded destination sets", padding=6)
            self.recorded_sets_frame.grid(
                row=footer_row, column=0, columnspan=display_cols + 1, sticky="ew", pady=(6, 0)
            )
            self.recorded_sets_frame.columnconfigure(0, weight=1)
            self.recorded_sets_tree = ttk.Treeview(
                self.recorded_sets_frame,
                columns=("wells",),
                show="tree headings",
                height=4,
                selectmode="browse",
            )
            self.recorded_sets_tree.heading("#0", text="Set")
            self.recorded_sets_tree.column("#0", width=55, stretch=False)
            self.recorded_sets_tree.heading("wells", text="Wells")
            self.recorded_sets_tree.column("wells", width=510, stretch=True)
            self.recorded_sets_tree.grid(row=0, column=0, columnspan=2, sticky="ew")
            ttk.Button(
                self.recorded_sets_frame,
                text="Redo Selected",
                command=lambda: self._change_selected_recorded_set(redo=True),
            ).grid(row=1, column=0, sticky="e", padx=(0, 4), pady=(4, 0))
            ttk.Button(
                self.recorded_sets_frame,
                text="Remove Selected",
                command=self._change_selected_recorded_set,
            ).grid(row=1, column=1, sticky="w", padx=(4, 0), pady=(4, 0))
            footer_row += 1

        buttons = ttk.Frame(frame)
        buttons.grid(row=footer_row, column=0, columnspan=display_cols + 1, sticky="ew", pady=(6, 0))
        ttk.Button(buttons, text="Clear Selection", command=self.clear).pack(side="left")
        if show_back:
            ttk.Button(buttons, text="Back", command=self.request_back).pack(side="left", padx=(6, 0))
        if self.batch_command is not None:
            ttk.Button(buttons, text="Batch Transfer", command=self.request_batch).pack(side="left", padx=(6, 0))
        if self.destination_set_mode:
            ttk.Button(
                buttons,
                text="Add Destination Set",
                command=self.add_destination_set,
                style="ChemAction.TButton",
            ).pack(side="left", padx=(6, 0))
            ttk.Button(buttons, text="Finish Destination Sets", command=self.accept).pack(side="right")
        else:
            ttk.Button(buttons, text="Use Selection", command=self.accept).pack(side="right")
        if show_back:
            ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=(0, 6))
        ttk.Label(frame, textvariable=self.validation_message, foreground="#A33A2B").grid(
            row=footer_row + 1, column=0, columnspan=display_cols + 1, sticky="w", pady=(4, 0)
        )
        if self.destination_set_mode:
            self._refresh_recorded_sets()
        self._paint()
        position_toplevel_near(self, anchor)

    def request_back(self):
        self.back_requested = True
        self.destroy()

    def _request_labware_change(self, _event=None):
        self.requested_labware = self.labware_var.get().strip()
        self.labware_change_requested = True
        self.result_groups = [list(group) for group in self.recorded_sets]
        self.destroy()

    def _on_press(self, label: str):
        if label in self.disabled or label in self._recorded_labels():
            return
        if self.single_select:
            self.selected = {label}
            self.drag_state = None
            self._paint()
            return
        if label in self.pattern_by_label:
            group = set(self.pattern_by_label[label]) - self.disabled
            if group & self._recorded_labels():
                self.validation_message.set("That destination pattern overlaps a recorded set.")
                return
            self.selected = set() if group <= self.selected else group
            self.drag_state = None
            self.validation_message.set("")
            self._paint()
            return
        self.drag_state = label not in self.selected
        self._apply_drag_to_label(label)

    def _on_enter(self, label: str):
        if self.drag_state is not None:
            self._apply_drag_to_label(label)

    def _on_motion(self, event):
        if self.drag_state is None:
            return
        widget = self.winfo_containing(event.x_root, event.y_root)
        for label, cell in self.cells.items():
            if cell == widget:
                self._apply_drag_to_label(label)
                break

    def _on_release(self, _event):
        self.drag_state = None

    def _apply_drag_to_label(self, label: str):
        if label in self.disabled or label in self._recorded_labels():
            return
        if self.drag_state is True:
            if self.selection_limit is not None and len(self.selected) >= self.selection_limit:
                self.validation_message.set(f"Select no more than {self.selection_limit} wells.")
                return
            self.selected.add(label)
            self.validation_message.set("")
        elif self.drag_state is False:
            self.selected.discard(label)
            self.validation_message.set("")
        self._paint()

    def request_batch(self):
        self.batch_requested = True
        self.destroy()

    def clear(self):
        self.selected.clear()
        self.validation_message.set("")
        self._paint()

    def _recorded_labels(self) -> Set[str]:
        return {label for group in self.recorded_sets for label in group}

    def _ordered_selection(self) -> List[str]:
        return sorted(
            self.selected,
            key=lambda label: (
                int(WELL_LABEL_RE.match(label).group(2)),
                row_label_to_number(WELL_LABEL_RE.match(label).group(1)),
            ),
        )

    def add_destination_set(self):
        if not self.destination_set_mode:
            return
        if self.required_count is not None and len(self.selected) != self.required_count:
            self.validation_message.set(f"Select exactly {self.required_count} wells before adding the set.")
            return
        if not self.selected:
            self.validation_message.set("Select destination wells before adding the set.")
            return
        ordered = self._ordered_selection()
        if set(ordered) & self._recorded_labels():
            self.validation_message.set("Recorded destination wells cannot be selected again.")
            return
        self.recorded_sets.append(ordered)
        self.selected.clear()
        self.validation_message.set(f"Recorded destination set {len(self.recorded_sets)}. Select the next set or finish.")
        self._refresh_recorded_sets()
        self._paint()

    def _remove_recorded_set(self, index: int, *, redo: bool = False):
        if not 0 <= index < len(self.recorded_sets):
            return
        if redo and self.selected:
            self.validation_message.set("Clear or add the current green selection before redoing a recorded set.")
            return
        group = self.recorded_sets.pop(index)
        if redo:
            self.selected = set(group)
            self.validation_message.set("Edit the green selection, then click Add Destination Set.")
        else:
            self.validation_message.set("Destination set removed.")
        self._refresh_recorded_sets()
        self._paint()

    def _refresh_recorded_sets(self):
        if not self.destination_set_mode:
            return
        self.recorded_sets_tree.delete(*self.recorded_sets_tree.get_children())
        for index, group in enumerate(self.recorded_sets):
            self.recorded_sets_tree.insert("", "end", iid=str(index), text=str(index + 1), values=(", ".join(group),))

    def _change_selected_recorded_set(self, redo: bool = False):
        selection = self.recorded_sets_tree.selection()
        if not selection:
            self.validation_message.set("Select a recorded destination set first.")
            return
        self._remove_recorded_set(int(selection[0]), redo=redo)

    def _paint(self):
        for label, widget in self.cells.items():
            if label in self.disabled:
                widget.configure(bg="#D8D8D8", fg="#777777", relief="sunken")
            elif label in self.selected:
                widget.configure(bg="#2E7D32", fg="white")
            elif label in self._recorded_labels():
                widget.configure(bg="#B9DCF4", fg="#17324D", relief="sunken")
            elif label in self.highlighted:
                widget.configure(bg="#DCEAF7", fg="#17324D")
            else:
                widget.configure(bg="SystemButtonFace", fg="black")

    def accept(self):
        self.selected.difference_update(self.disabled)
        if self.destination_set_mode:
            if self.selected:
                self.validation_message.set("Click Add Destination Set to record the green selection before finishing.")
                return
            if not self.recorded_sets:
                self.validation_message.set("Add at least one destination set.")
                return
            self.result_groups = [list(group) for group in self.recorded_sets]
            self.result_labels = ";".join(",".join(group) for group in self.result_groups)
            self.destroy()
            return
        if self.required_count is not None and len(self.selected) != self.required_count:
            self.validation_message.set(f"Select exactly {self.required_count} wells.")
            return
        if self.selection_limit is not None and len(self.selected) > self.selection_limit:
            self.validation_message.set(f"Select no more than {self.selection_limit} wells.")
            return
        ordered = self._ordered_selection()
        self.result_labels = ",".join(ordered)
        self.destroy()
