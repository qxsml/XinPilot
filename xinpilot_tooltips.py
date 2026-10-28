"""Small, delayed hover explanations; no layout or command changes."""
import tkinter as tk
from tkinter import ttk


class Tooltip:
    def __init__(self, widget, text):
        self.widget, self.text = widget, text
        widget._xinpilot_tooltip = self
        self.timer = self.popup = None
        widget.bind("<Enter>", self.schedule, add="+")
        for event in ("<Leave>", "<ButtonPress>", "<Unmap>", "<Destroy>"):
            widget.bind(event, self.hide, add="+")

    def schedule(self, event=None):
        self.hide()
        self.timer = self.widget.after(550, self.show)

    def show(self):
        self.timer = None
        if not self.widget.winfo_viewable():
            return
        self.popup = win = tk.Toplevel(self.widget)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        tk.Label(win, text=self.text, wraplength=330, justify="left",
                 background="#fffbe8", foreground="#203346", relief="solid",
                 borderwidth=1, padx=9, pady=7, font=("Segoe UI", 9)).pack()
        win.update_idletasks()
        x = min(self.widget.winfo_pointerx() + 12, win.winfo_screenwidth() - win.winfo_reqwidth() - 8)
        y = min(self.widget.winfo_pointery() + 20, win.winfo_screenheight() - win.winfo_reqheight() - 8)
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
        win.deiconify()

    def hide(self, event=None):
        if self.timer:
            self.widget.after_cancel(self.timer)
            self.timer = None
        if self.popup:
            self.popup.destroy()
            self.popup = None


HELP = {
    "Source labware": "The plate or container holding the liquid the robot will aspirate.",
    "Destination labware": "The plate or container receiving the transferred liquid.",
    "Source well": "The position in the source labware from which liquid is aspirated, for example A1.",
    "Destination wells": "The receiving positions in the destination labware. Each mapped well receives its assigned transfer.",
    "umol per rxn": "Amount of this chemical per reaction in micromoles. When a stock concentration is available, XinPilot uses it to calculate the transfer volume.",
    "Dispense volume/uL": "Liquid volume delivered to each destination, in microlitres. This is a transfer volume, not the total reaction volume.",
    "Building block": "Marks this chemical as a reactant for product prediction. Leave unchecked for solvents and other chemicals that should not be used as building blocks.",
    "Strategy": "Single transfer aspirates separately for each destination. Multi-dispense divides one aspiration among several destinations, within pipette capacity.",
    "Pipette": "Choose a configured pipette mount, or Auto to let protocol generation resolve a suitable pipette from the transfer requirements.",
    "Tip touch": "Touches the tip against the well wall after dispensing to help release a remaining droplet.",
    "SMILES": "A text representation of the molecular structure, including stereochemistry and charges when specified.",
    "Conc. (M)": "Your recorded stock concentration in mol/L. This is separate from a predicted solubility limit.",
    "Generate Product Details": "Predict products from the pushed building blocks using the selected reaction type. Review the generated structures before preparing LCMS input.",
    "Generate Input for LCMS Analysis": "Prepare the LCMS target representations and write the analysis input. Review ion and counterion choices when prompted.",
    "LCMS target structure": "The structure used for analytical mass matching. It may differ from Product Details after ion or counterion preparation.",
    "Export Project": "Save the current work as a portable project file. An imported file is only overwritten if you choose it as the export destination.",
    "Import Project": "Load a saved project into the application. Editing the loaded project does not automatically overwrite its original file.",
    "Generate Protocol...": "Generate and save an Opentrons Python protocol from the current transfer plan. This button does not run the robot.",
    "Send products to Solution Calculator": "Send chosen products for stock calculations without advancing the synthesis step or changing Compound Notes.",
}
PUSH = "Send chemical assignments and well information to Cheminformatics. Replaces this editor's previously pushed rows, preserves rows from other editors, and invalidates generated product details and LCMS targets. Generate Product Details again afterward."


def install_tooltips(root):
    """Attach once to existing controls; invoked after the main UI is built."""
    for widget in root.winfo_children():
        if isinstance(widget, (ttk.Label, ttk.Button, ttk.Checkbutton)):
            label = str(widget.cget("text")).strip().rstrip(":")
            text = HELP.get(label)
            if label in ("Push All to Cheminformatics", "Push Listed GWLs to Cheminformatics"):
                text = PUSH
            if text and not hasattr(widget, "_xinpilot_tooltip"):
                widget._xinpilot_tooltip = Tooltip(widget, text)
        install_tooltips(widget)
