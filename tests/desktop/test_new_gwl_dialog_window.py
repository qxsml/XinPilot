"""Real renderer + controller: rapid OK clicks cannot skip New GWL location."""
import json
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from desktop.live_app import LiveBridge, html
import webview

if len(sys.argv) > 1:
    from unittest.mock import patch
    executable = str(Path(sys.argv[1]).resolve())
    with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', executable):
        bridge = LiveBridge()
else:
    bridge = LiveBridge()
window = webview.create_window('XinPilot New GWL regression', html=html(), js_api=bridge, width=1280, height=850)
bridge._window = window
work = tempfile.TemporaryDirectory()
chosen = str(Path(work.name) / 'rapid.gwl')
calls = []
next_result = [chosen]


def chooser(*args, **kwargs):
    calls.append(kwargs)
    return (next_result[0],) if next_result[0] else None


window.create_file_dialog = chooser
report = {'packaged_controller': len(sys.argv) > 1}


def wait(expression):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        value = window.evaluate_js(expression)
        if value:
            return value
        time.sleep(.12)
    raise AssertionError(expression)


def click(text):
    wait('[...document.querySelectorAll("button")].some(b=>b.textContent===' + json.dumps(text) + ' && b.getAttribute("aria-busy")!=="true")')
    window.evaluate_js('[...document.querySelectorAll("button")].find(b=>b.textContent===' + json.dumps(text) + ').click()')


def submit_twice():
    wait('!!document.querySelector("#prompt input")')
    window.evaluate_js('document.querySelector("#prompt input").value="rapid";const ok=[...document.querySelectorAll("#prompt button")].find(b=>b.textContent==="OK");ok.click();ok.click();')


def check():
    try:
        click('Synthesis Plan')
        click('Tecan')
        click('New GWL')
        submit_twice()
        wait('document.querySelector("#prompt").textContent.includes("Select destination format")')
        assert len(calls) == 1, calls
        click('OK')
        def list_paths():
            def flat(n):
                yield n
                for child in n.get('children', []):
                    yield from flat(child)
            return [n.get('values') for w in bridge.snapshot()['windows'] for n in flat(w) if n['kind']=='Listbox']
        before = list_paths()
        assert any('rapid.gwl' in rows for rows in before), before
        next_result[0] = None
        click('New GWL')
        submit_twice()
        wait('!document.querySelector("#prompt").textContent')
        assert len(calls) == 2
        assert before == list_paths()
        assert not Path(chosen).exists(), 'New GWL should not write before Save'
        click('Save Current GWL')
        wait('document.querySelector("#prompt").textContent.includes(' + json.dumps(chosen) + ')')
        assert Path(chosen).exists()
        click('OK')
        report.update(status='PASS', native_chooser_calls=2, full_path_preserved=True,
                      rapid_double_click=True, cancellation_keeps_list=True)
    except Exception:
        report.update(status='FAIL', error=traceback.format_exc())
    finally:
        bridge._shutdown()
        window.destroy()


webview.start(check, gui='edgechromium')
work.cleanup()
(ROOT / 'artifacts/tests').mkdir(exist_ok=True, parents=True)
(ROOT / ('artifacts/tests/new-gwl-dialog-packaged.json' if len(sys.argv) > 1 else 'artifacts/tests/new-gwl-dialog.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report))
raise SystemExit(report.get('status') != 'PASS')
