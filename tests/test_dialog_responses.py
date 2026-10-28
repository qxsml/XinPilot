import tempfile
import threading
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

from desktop.live_engine import Controller
from desktop.live_app import LiveBridge
from tecan_frame import TecanFrame


class DialogResponseTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.controller = Controller.__new__(Controller)
        self.controller.app = self.root
        self.controller.pending = {}
        self.controller.dialog = None

    def tearDown(self):
        self.root.destroy()

    def answer(self, token, value):
        self.controller.event({'action': 'answer', 'id': token, 'value': value})

    def test_duplicate_and_stale_answers_cannot_cross_dialogs(self):
        c = self.controller
        tokens = []
        def first():
            tokens.append(c.dialog['id'])
            self.answer(tokens[0], 'demo')
            self.answer(tokens[0], 'unwanted second answer')
        self.root.after(0, first)
        with patch('desktop.live_engine.id', return_value=123, create=True):
            self.assertEqual(c.prompt({'kind': 'askstring'}), 'demo')
            def second():
                tokens.append(c.dialog['id'])
                self.answer(tokens[0], 'demo')
                self.assertFalse(c.pending[tokens[1]]['answered'])
                self.answer(tokens[1], 'confirmed full path')
            self.root.after(0, second)
            self.assertEqual(c.prompt({'kind': 'asksaveasfilename'}), 'confirmed full path')
        self.assertNotEqual(*tokens)
        self.assertFalse(c.pending)
        self.assertIsNone(c.dialog)

    def test_nested_prompt_restores_parent(self):
        c = self.controller
        def nested():
            parent = c.dialog['id']
            def child_answer():
                self.answer(parent, 'stale parent click')
                self.assertFalse(c.pending[parent]['answered'])
                self.answer(c.dialog['id'], 'child')
            self.root.after(0, child_answer)
            self.assertEqual(c.prompt({'kind': 'showinfo'}), 'child')
            self.assertEqual(c.dialog['id'], parent)
            self.answer(parent, 'parent')
        self.root.after(0, nested)
        self.assertEqual(c.prompt({'kind': 'askstring'}), 'parent')

    def test_relative_new_gwl_is_rejected_without_mutation(self):
        probe = SimpleNamespace(_confirm_gwl_switch_if_dirty=lambda *a, **k: True,
                                _default_gwl_directory=lambda: None,
                                winfo_toplevel=lambda: self.root)
        with patch('tecan_frame.simpledialog.askstring', return_value='demo'), \
             patch('tecan_frame.filedialog.asksaveasfilename', return_value='demo.gwl'), \
             patch('tecan_frame.messagebox.showerror') as error:
            TecanFrame._new_blank_gwl(probe)
            error.assert_called_once()
        with patch('tecan_frame.simpledialog.askstring', return_value='demo'), \
             patch('tecan_frame.filedialog.asksaveasfilename', return_value=''), \
             patch('tecan_frame.messagebox.showerror') as error:
            TecanFrame._new_blank_gwl(probe)
            error.assert_not_called()


class NativeDialogTests(unittest.TestCase):
    def test_existing_relative_gwl_requires_save_as(self):
        entry = {'path': 'demo.gwl', 'name': 'demo.gwl'}
        probe = SimpleNamespace(exported_gwl_files=[entry], _default_gwl_directory=lambda: None)
        with patch('tecan_frame.filedialog.asksaveasfilename', return_value='') as chooser:
            self.assertFalse(TecanFrame._save_gwl_entry_edits(probe, 0))
            chooser.assert_called_once()
        self.assertEqual(entry['path'], 'demo.gwl')

    def bridge(self, result):
        b = LiveBridge.__new__(LiveBridge)
        b._file_dialog_lock = threading.Lock()
        b._file_dialog_tokens = set()
        b._dialog = {'id': 'unique', 'kind': 'asksaveasfilename', 'defaultextension': '.gwl'}
        b._window = SimpleNamespace(create_file_dialog=Mock(return_value=result))
        b.event = Mock()
        return b

    def test_native_dialog_is_opened_once_and_cancel_is_preserved(self):
        b = self.bridge(None)
        b.file_dialog('unique')
        b.file_dialog('unique')
        b._window.create_file_dialog.assert_called_once()
        self.assertFalse(b.event.call_args.args[0]['value'])

    def test_relative_path_is_rejected_and_full_path_is_returned(self):
        b = self.bridge(('demo.gwl',))
        with self.assertRaises(ValueError):
            b.file_dialog('unique')
        self.assertIsNone(b.event.call_args.args[0]['value'])
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'demo')
            b = self.bridge((path,))
            b.file_dialog('unique')
            self.assertEqual(b.event.call_args.args[0]['value'], path + '.gwl')


if __name__ == '__main__':
    unittest.main()
