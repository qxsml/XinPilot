"""Schedule Tk work with cancellation tied to the owning widget's lifetime."""
import tkinter as tk


def _install_cleanup(widget):
    if widget.__dict__.get('_xinpilot_callback_cleanup'):
        return

    def cleanup(event):
        if event.widget is not widget:
            return
        # Inspect Tcl's active queue rather than retaining cancelled token IDs.
        # Only callbacks registered on this widget are cancelled, never another
        # window's timer or a worker's operation.
        commands = set(widget._tclCommands or ())
        try:
            for token in widget.tk.splitlist(widget.tk.call('after', 'info')):
                info = widget.tk.call('after', 'info', token)
                script = widget.tk.splitlist(info[0])
                if script and script[0] in commands:
                    widget.after_cancel(token)
        except tk.TclError:
            pass  # The interpreter may already be shutting down.

    widget.bind('<Destroy>', cleanup, add='+')
    widget._xinpilot_callback_cleanup = True


def after(widget, milliseconds, callback, *args):
    _install_cleanup(widget)
    return widget.after(milliseconds, callback, *args)


def after_idle(widget, callback, *args):
    _install_cleanup(widget)
    return widget.after_idle(callback, *args)
