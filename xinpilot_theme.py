"""Shared, static ttk theme for XinPilot's existing desktop screens."""
from tkinter import ttk


COLORS = {
    "bg": "#e9eef3", "panel": "#f5f6f7", "panel_alt": "#eff2f5",
    "line": "#d2dce5", "text": "#203346", "muted": "#586b7c",
    "accent": "#28669c", "accent_dark": "#19466f", "accent_light": "#eef4fa",
    "accent_mid": "#a8c9e5", "button": "#f5f6f7", "button_active": "#e5eff9",
    "select": "#d9eafa", "blue": "#28669c", "blue_dark": "#19466f",
    "blue_light": "#e8f1fa", "violet": "#28669c", "violet_dark": "#19466f",
    "violet_light": "#eef4fa", "rose": "#28669c", "rose_light": "#eef4fa",
    "amber": "#805b20", "amber_light": "#fff5df", "green": "#28669c", "green_light": "#eef4fa",
    "file_region": "#f5f6f7", "file_region_border": "#d2dce5",
    "file_action": "#f5f6f7", "file_action_dark": "#203346",
    "chem_region": "#f5f6f7", "chem_region_border": "#d2dce5",
    "chem_action": "#28669c", "chem_action_dark": "#19466f",
    "row_region": "#f5f6f7", "row_region_border": "#d2dce5",
    "row_action": "#f5f6f7", "row_action_dark": "#203346",
    "toolkit_action": "#f5f6f7", "toolkit_action_active": "#e5eff9",
    "toolkit_action_dark": "#dce7ee", "toolkit_text": "#203346",
    "danger": "#a33a3a", "danger_dark": "#722323", "danger_light": "#f7dada",
    "warning": "#805b20", "warning_light": "#fff5df", "stripe": "#edf1f5",
}


def configure_controls(root):
    """Configure once per Tk interpreter; child frames must not reset the theme."""
    if getattr(root, "_xinpilot_controls_styled", False):
        return
    root.configure(background=COLORS["bg"])
    root.option_add("*Font", "{Segoe UI} 10")
    root.option_add("*Dialog.msg.font", "{Segoe UI} 10")
    root.option_add("*TCombobox*Listbox.background", COLORS["panel"])
    root.option_add("*TCombobox*Listbox.foreground", COLORS["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", COLORS["select"])
    root.option_add("*TCombobox*Listbox.selectForeground", COLORS["text"])
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=("Segoe UI", 10), background=COLORS["bg"], foreground=COLORS["text"])
    for prefix, fill in (("", COLORS["panel"]), ("Chem.", COLORS["bg"]),
                         ("FileRegion.", COLORS["panel"]), ("ChemRegion.", COLORS["panel"]),
                         ("RowRegion.", COLORS["panel"])):
        style.configure(prefix + "TFrame", background=fill)
        style.configure(prefix + "TLabel", background=fill, foreground=COLORS["text"])
        style.configure(prefix + "Muted.TLabel", background=fill, foreground=COLORS["muted"], font=("Segoe UI", 9))
        style.configure(prefix + "LiveEdit.TLabel", background=fill, foreground=COLORS["accent_dark"], font=("Segoe UI", 9, "bold"))
        for label in ("TLabel", "Muted.TLabel", "LiveEdit.TLabel"):
            style.map(prefix + label, background=[("disabled", fill)], foreground=[("disabled", COLORS["muted"])])
        for control in ("TCheckbutton", "TRadiobutton"):
            style.configure(prefix + control, background=fill, foreground=COLORS["text"], padding=(2, 2), focuscolor=COLORS["accent"])
            style.map(prefix + control, background=[("active", fill)], foreground=[("disabled", COLORS["muted"])])

    sections = ("TLabelframe", "FileRegion.TLabelframe", "ChemRegion.TLabelframe", "RowRegion.TLabelframe",
                "CompoundToolbar.TLabelframe", "CompoundRequired.TLabelframe", "CompoundCalc.TLabelframe",
                "CompoundOptional.TLabelframe", "CompoundPreview.TLabelframe", "CompoundTable.TLabelframe")
    for name in sections:
        style.configure(name, background=COLORS["panel"], bordercolor=COLORS["panel"], relief="flat", borderwidth=0)
        style.configure(name + ".Label", background=COLORS["panel"], foreground=COLORS["accent_dark"], font=("Segoe UI", 10, "bold"))
    for name in ("CompoundTop.TFrame", "CompoundMaster.TFrame", "CompoundMain.TFrame"):
        style.configure(name, background=COLORS["bg"])
    style.configure("CompoundEditor.TFrame", background=COLORS["panel"])
    style.configure("CalcHint.TLabel", background=COLORS["panel"], foreground=COLORS["muted"], font=("Segoe UI", 9))
    style.configure("Section.TLabel", background=COLORS["panel"], foreground=COLORS["text"], font=("Segoe UI", 10, "bold"))
    style.configure("Status.TLabel", background=COLORS["panel"], foreground=COLORS["muted"], padding=(10, 5), font=("Segoe UI", 9))
    style.configure("ChemRegion.Compact.TCheckbutton", background=COLORS["panel"], foreground=COLORS["text"], font=("Segoe UI", 9), padding=(0, 2))
    style.map("ChemRegion.Compact.TCheckbutton", background=[("disabled", COLORS["panel"]), ("active", COLORS["panel"])], foreground=[("disabled", COLORS["muted"])])

    secondary = ("TButton", "CompoundToolbar.TButton", "FileAction.TButton", "RowAction.TButton")
    primary = ("ChemAction.TButton", "Accent.TButton", "DrawReaction.TButton", "Blue.TButton", "Violet.TButton")
    for name in (*secondary, *primary, "Danger.TButton"):
        fill = COLORS["accent"] if name in primary else COLORS["panel_alt"]
        ink = "#ffffff" if name in primary else COLORS["danger"] if name == "Danger.TButton" else COLORS["text"]
        hover = "#2c70aa" if name in primary else "#fff1f1" if name == "Danger.TButton" else COLORS["button_active"]
        pressed = COLORS["accent_dark"] if name in primary else COLORS["danger_light"] if name == "Danger.TButton" else "#dce7ee"
        style.configure(name, background=fill, foreground=ink, bordercolor=COLORS["accent"] if name in primary else COLORS["line"],
                        lightcolor=fill if name in primary else COLORS["line"], darkcolor=fill if name in primary else COLORS["line"],
                        padding=(10, 5), relief="flat" if name in primary else "solid", borderwidth=1,
                        focusthickness=1, focuscolor=COLORS["accent_mid"])
        style.map(name, background=[("disabled", COLORS["panel_alt"]), ("pressed", pressed), ("active", hover)],
                  foreground=[("disabled", COLORS["muted"]), ("!disabled", ink)],
                  bordercolor=[("focus", COLORS["accent"]), ("active", COLORS["accent_mid"])],
                  relief=[("pressed", "sunken"), ("!pressed", "flat" if name in primary else "solid")])
    style.configure("Toolkit.TMenubutton", background=COLORS["panel"], foreground=COLORS["text"],
                    arrowcolor=COLORS["text"], bordercolor=COLORS["line"], padding=(10, 5), relief="flat")
    style.map("Toolkit.TMenubutton", background=[("pressed", "#dce7ee"), ("active", COLORS["button_active"])],
              foreground=[("disabled", COLORS["muted"])], bordercolor=[("focus", COLORS["accent"])])
    style.configure("ChemAction.TCheckbutton", background=COLORS["select"], foreground=COLORS["accent_dark"], padding=(8, 4))
    style.map("ChemAction.TCheckbutton", background=[("active", COLORS["select"])])
    for name in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(name, background=COLORS["panel"], fieldbackground=COLORS["panel"], foreground=COLORS["text"],
                        bordercolor=COLORS["line"], lightcolor=COLORS["line"], darkcolor=COLORS["line"],
                        arrowcolor=COLORS["muted"], padding=(6, 4), selectbackground=COLORS["select"], selectforeground=COLORS["text"])
        style.map(name, bordercolor=[("focus", COLORS["accent"])],
                  fieldbackground=[("disabled", COLORS["panel_alt"]), ("readonly", COLORS["panel"])],
                  foreground=[("disabled", COLORS["muted"])],
                  selectbackground=[("readonly", COLORS["panel"])], selectforeground=[("readonly", COLORS["text"])])
    style.configure("Treeview", background=COLORS["panel"], fieldbackground=COLORS["panel"], foreground=COLORS["text"],
                    bordercolor=COLORS["line"], rowheight=28, relief="flat", font=("Segoe UI", 10))
    style.configure("Treeview.Heading", background=COLORS["blue_light"], foreground=COLORS["accent_dark"],
                    bordercolor=COLORS["blue_light"], lightcolor=COLORS["blue_light"], darkcolor=COLORS["blue_light"],
                    relief="flat", font=("Segoe UI", 9, "bold"), padding=(8, 7))
    style.map("Treeview", background=[("selected", COLORS["select"])], foreground=[("selected", COLORS["accent_dark"])])
    style.map("Treeview.Heading", background=[("active", "#e0ebf1")])
    for notebook, padding, font_size in (("TNotebook", (10, 5), 10), ("Main.TNotebook", (6, 4), 9),
                                        ("Chem.TNotebook", (18, 7), 10), ("CompactChem.TNotebook", (10, 7), 10)):
        style.configure(notebook, background=COLORS["bg"], borderwidth=0, tabmargins=(0, 4, 0, 0))
        style.configure(notebook + ".Tab", background=COLORS["panel_alt"], foreground=COLORS["muted"],
                        bordercolor=COLORS["line"], lightcolor=COLORS["panel_alt"], darkcolor=COLORS["line"],
                        padding=padding, font=("Segoe UI", font_size, "bold"))
        style.map(notebook + ".Tab", background=[("selected", COLORS["select"]), ("active", COLORS["button_active"])],
                  foreground=[("selected", COLORS["accent_dark"]), ("active", COLORS["text"])], relief=[("!pressed", "flat")])
    # Keep native tab elements, but let inactive main tabs blend into one strip.
    style.configure("Main.TNotebook.Tab", background=COLORS["bg"], bordercolor=COLORS["bg"],
                    lightcolor=COLORS["bg"], darkcolor=COLORS["bg"])
    style.map("Main.TNotebook.Tab",
              bordercolor=[("selected", COLORS["accent_mid"]), ("active", COLORS["button_active"])],
              lightcolor=[("selected", COLORS["accent_mid"]), ("active", COLORS["button_active"])],
              darkcolor=[("selected", COLORS["accent_mid"]), ("active", COLORS["button_active"])])
    for orientation in ("Horizontal", "Vertical"):
        style.configure(orientation + ".TScrollbar", background=COLORS["line"], troughcolor=COLORS["panel_alt"],
                        bordercolor=COLORS["panel_alt"], arrowcolor=COLORS["muted"], relief="flat")
        style.map(orientation + ".TScrollbar", background=[("active", COLORS["accent_mid"])])
    root._xinpilot_controls_styled = True


def configure_table_tags(tree):
    tree.tag_configure("even", background=COLORS["panel"])
    tree.tag_configure("odd", background=COLORS["stripe"])


def stripe_tag(index):
    return "odd" if index % 2 else "even"
