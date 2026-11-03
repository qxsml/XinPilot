"""Regression checks for module stacking, widget lifetime and source tooling."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
import unittest

from xinpilot.application.opentrons_modules import validate_heater_shaker_stack
from xinpilot.application.opentrons_protocol import compile_protocol
from xinpilot_callbacks import after, after_idle
from test_robot_review_fixes import request, transfer

ROOT = Path(__file__).resolve().parents[1]


def module(adapter):
    return dict(key='heater_shaker', type='Heater-Shaker', slot='D1',
                load_name='heaterShakerModuleV1', labware_alias='dest1', adapter=adapter)


class ModuleStackTests(unittest.TestCase):
    def test_supported_and_unsupported_pairs_follow_api_definitions(self):
        for api in ('2.15', '2.24', '2.27'):
            for plate, adapter in [('nest_96_wellplate_2ml_deep', 'opentrons_96_deep_well_adapter'),
                                   ('corning_96_wellplate_360ul_flat', 'opentrons_universal_flat_adapter')]:
                with self.subTest(api=api, plate=plate):
                    validate_heater_shaker_stack(module(adapter), {'load_name': plate}, api)
            with self.subTest(api=api), self.assertRaisesRegex(ValueError, 'cannot be loaded'):
                validate_heater_shaker_stack(module('opentrons_96_flat_bottom_adapter'),
                                            {'load_name': 'nest_96_wellplate_2ml_deep'}, api)

    def test_wrong_adapter_role_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'not an Opentrons adapter'):
            validate_heater_shaker_stack(module('nest_96_wellplate_2ml_deep'), None, '2.24')

    def test_compiler_rejects_initial_and_moved_incompatible_plate(self):
        req = request([transfer()])
        req.module_configs.append(module('opentrons_96_deep_well_adapter'))
        with self.assertRaisesRegex(ValueError, 'cannot be loaded'):
            compile_protocol(req)  # destination is a Corning flat-bottom plate
        req.module_configs[0]['labware_alias'] = ''
        req.rows[0].update(move_plate=True, move_labware_alias='dest1', move_to_slot='Heater-Shaker Module')
        # The module target label is the canonical compiler value.
        req.rows[0]['move_to_slot'] = 'Heater-Shaker Module @ D1'
        with self.assertRaisesRegex(ValueError, 'cannot be loaded'):
            compile_protocol(req)


class CallbackLifetimeTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.update_idletasks()
        self.addCleanup(self.root.destroy)

    def test_destroy_cancels_only_owners_callbacks(self):
        first, second = tk.Frame(self.root), tk.Frame(self.root)
        calls = []
        timer = after(first, 10000, lambda: calls.append('closed'))
        idle = after_idle(first, lambda: calls.append('closed-idle'))
        other = after(second, 10000, lambda: calls.append('open'))
        first.destroy()
        pending = self.root.tk.splitlist(self.root.tk.call('after', 'info'))
        self.assertNotIn(timer, pending)
        self.assertNotIn(idle, pending)
        self.assertIn(other, pending)
        self.root.update()
        self.assertEqual([], calls)

    def test_destroy_child_keeps_parent_timer_and_manual_cancel_works(self):
        parent = tk.Frame(self.root)
        child = tk.Frame(parent)
        pending = after(parent, 10000, lambda: None)
        cancelled = after(parent, 10000, lambda: None)
        parent.after_cancel(cancelled)
        child.destroy()
        self.assertIn(pending, self.root.tk.splitlist(self.root.tk.call('after', 'info')))
        parent.destroy()
        self.assertNotIn(pending, self.root.tk.splitlist(self.root.tk.call('after', 'info')))

    def test_callbacks_still_execute_with_arguments(self):
        frame = tk.Frame(self.root)
        calls = []
        after(frame, 0, calls.append, 'timer')
        after_idle(frame, calls.append, 'idle')
        self.root.update()
        self.assertEqual(['timer', 'idle'], calls)

    def test_runner_polling_is_cancelled_on_close(self):
        from pyparse_runner_frame import PyParseRunnerFrame
        frame = PyParseRunnerFrame(self.root, 'PyParse', ROOT/'PyParse/PyParse.py', False)
        own_commands = set(frame._tclCommands)
        frame.destroy()
        for token in self.root.tk.splitlist(self.root.tk.call('after', 'info')):
            script = self.root.tk.call('after', 'info', token)[0]
            self.assertNotIn(self.root.tk.splitlist(script)[0], own_commands)


class SourceToolTests(unittest.TestCase):
    def test_syntax_check_catches_garbled_header_without_running_code(self):
        sys.path.insert(0, str(ROOT/'scripts'))
        from check_python_syntax import syntax_errors
        with tempfile.TemporaryDirectory() as tmp:
            good, bad = Path(tmp)/'good.py', Path(tmp)/'bad.py'
            good.write_text('raise RuntimeError("must never execute")\n')
            bad.write_text('\u00ef\u00bb\u00bfimport sys\n', encoding='utf-8')
            self.assertEqual([], syntax_errors([good]))
            self.assertEqual(1, len(syntax_errors([bad])))
            self.assertFalse((Path(tmp)/'__pycache__').exists())

    def test_legacy_manifest_writer_produces_canonical_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'scripts').mkdir()
            for name in ('source_manifest.py', 'verify_source_manifest.py'):
                shutil.copyfile(ROOT/'scripts'/name, root/'scripts'/name)
            (root/'VERSION').write_text('0.0.0')
            for name in ('source_manifest.py', 'verify_source_manifest.py'):
                result = subprocess.run([sys.executable, '-B', str(root/'scripts'/name)],
                                        capture_output=True, text=True)
                self.assertEqual(0, result.returncode, result.stdout+result.stderr)


if __name__ == '__main__':
    unittest.main()
