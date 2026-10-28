from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

try:
    from rdkit import Chem
except ImportError:  # The GUI can still explain the missing dependency.
    Chem = None


AROMATIC_TO_BONDS = "aromatic_to_bonds"
BONDS_TO_AROMATIC = "bonds_to_aromatic"


def convert_smiles_line(smiles: str, direction: str) -> str:
    value = smiles.strip()
    if not value:
        return ""
    if Chem is None:
        return "[ERROR] RDKit is not installed"
    if direction not in {AROMATIC_TO_BONDS, BONDS_TO_AROMATIC}:
        return f"[ERROR] Unknown conversion direction: {direction}"

    molecule = Chem.MolFromSmiles(value)
    if molecule is None:
        return f"[ERROR] Invalid SMILES: {value}"

    try:
        return Chem.MolToSmiles(
            molecule,
            canonical=True,
            isomericSmiles=True,
            kekuleSmiles=direction == AROMATIC_TO_BONDS,
        )
    except Exception as exc:
        return f"[ERROR] Conversion failed: {exc}"


def convert_smiles_lines(text: str, direction: str) -> str:
    return "\n".join(convert_smiles_line(line, direction) for line in text.splitlines())


class AromaticSmilesConverterApp(ttk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master, padding=12)
        self.master = master
        self.direction = tk.StringVar(value=AROMATIC_TO_BONDS)
        self._build_ui()

    def _build_ui(self) -> None:
        self.pack(fill="both", expand=True)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(2, weight=1)
        self.rowconfigure(3, weight=1)

        ttk.Label(
            self,
            text="Aromatic SMILES Converter",
            font=("Segoe UI", 16, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        directions = ttk.Frame(self)
        directions.grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Label(directions, text="Conversion:").pack(side="left", padx=(0, 8))
        ttk.Radiobutton(
            directions,
            text="Aromatic rings → explicit alternating bonds",
            value=AROMATIC_TO_BONDS,
            variable=self.direction,
        ).pack(side="left", padx=(0, 16))
        ttk.Radiobutton(
            directions,
            text="Explicit alternating bonds → aromatic rings",
            value=BONDS_TO_AROMATIC,
            variable=self.direction,
        ).pack(side="left")

        ttk.Label(self, text="Input SMILES", font=("Segoe UI", 10, "bold")).grid(
            row=2, column=0, sticky="w", pady=(0, 4)
        )
        ttk.Label(self, text="Converted SMILES", font=("Segoe UI", 10, "bold")).grid(
            row=2, column=2, sticky="w", padx=(8, 0), pady=(0, 4)
        )

        self.input_text = tk.Text(self, wrap="none", font=("Consolas", 11), undo=True)
        self.input_text.grid(row=3, column=0, sticky="nsew", padx=(0, 8))

        actions = ttk.Frame(self)
        actions.grid(row=3, column=1, sticky="ns", padx=4)
        ttk.Button(actions, text="Convert →", command=self.convert).pack(fill="x", pady=(24, 8))
        ttk.Button(actions, text="Clear", command=self.clear).pack(fill="x", pady=8)
        ttk.Button(actions, text="Copy Output", command=self.copy_output).pack(fill="x", pady=8)

        self.output_text = tk.Text(self, wrap="none", font=("Consolas", 11), undo=True)
        self.output_text.grid(row=3, column=2, sticky="nsew", padx=(8, 0))

        ttk.Label(
            self,
            text=(
                "Enter one SMILES per line. Output is canonicalized, so atom order may change while "
                "stereochemistry, isotopes, and formal charges are retained."
            ),
            foreground="#555555",
            wraplength=1040,
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))

        if Chem is None:
            ttk.Label(
                self,
                text="RDKit is unavailable. Launch this tool from the XinPilot Python environment.",
                foreground="#a33a3a",
            ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))

    def convert(self) -> None:
        result = convert_smiles_lines(
            self.input_text.get("1.0", "end-1c"),
            self.direction.get(),
        )
        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", result)

    def clear(self) -> None:
        self.input_text.delete("1.0", "end")
        self.output_text.delete("1.0", "end")

    def copy_output(self) -> None:
        result = self.output_text.get("1.0", "end-1c").strip()
        if not result:
            messagebox.showinfo("Aromatic SMILES Converter", "There is no output to copy.", parent=self.master)
            return
        self.master.clipboard_clear()
        self.master.clipboard_append(result)
        messagebox.showinfo("Aromatic SMILES Converter", "Converted SMILES copied.", parent=self.master)


def main() -> None:
    root = tk.Tk()
    root.title("Aromatic SMILES Converter")
    root.geometry("1200x680")
    root.minsize(900, 560)
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    AromaticSmilesConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
