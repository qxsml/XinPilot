"""Exercise local previews and the consent popup in the real TypeScript renderer."""
import json
from pathlib import Path
import sys
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from openpyxl import Workbook
from desktop.live_app import LiveBridge, html
import webview

work = tempfile.TemporaryDirectory(prefix='xinpilot-privacy-')
path = Path(work.name) / 'synthetic-stocks.xlsx'
book = Workbook()
sheet = book.active
sheet.append(['ID', 'SMILES'])
sheet.append(['VALID_LOCAL', 'CCO'])
sheet.append(['INVALID_LOCAL', 'not-a-smiles'])
book.save(path)
book.close()


class FixtureBridge(LiveBridge):
    def file_dialog(self, token):
        return self.event({'action': 'answer', 'id': token, 'value': str(path)})


bridge = FixtureBridge()
window = webview.create_window('XinPilot privacy regression', html=html(), js_api=bridge, width=1280, height=850)
bridge._window = window
report = {}


def wait(expression):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        result = window.evaluate_js(expression)
        if result:
            return result
        time.sleep(.15)
    raise AssertionError(expression)


def click(label):
    selector = '[...document.querySelectorAll("button")].find(b=>b.textContent===' + json.dumps(label) + ' && b.getAttribute("aria-busy")!=="true")'
    wait('!!(' + selector + ')')
    window.evaluate_js(selector + '.click()')


def select(identifier):
    selector = '[...document.querySelectorAll(".tree tbody tr")].find(r=>r.textContent.includes(' + json.dumps(identifier) + '))'
    wait('!!(' + selector + ')')
    window.evaluate_js(selector + '.click()')


def check():
    try:
        click('Load Excel')
        wait('document.body.textContent.includes("VALID_LOCAL")')
        select('VALID_LOCAL')
        click('From SMILES')
        wait('document.querySelector("#prompt").textContent.includes("calculated locally")')
        click('OK')
        select('INVALID_LOCAL')
        wait('[...document.querySelectorAll(".toplevel button")].some(b=>b.textContent==="Fetch preview from PubChem")')
        text = window.evaluate_js('[...document.querySelectorAll(".toplevel")].map(w=>w.textContent).join(" ")')
        assert 'SMILES online' in text, text
        assert window.evaluate_js('[...document.querySelectorAll("button")].filter(b=>b.textContent==="Fetch preview from PubChem").every(b=>!!b.closest(".toplevel"))')
        click('Cancel')
        wait('document.querySelectorAll(".toplevel").length===0')
        wait('document.body.textContent.includes("Structure preview unavailable")')
        select('VALID_LOCAL')
        report.update(status='PASS', local_smiles_action=True, popup_only_fetch_button=True, cancelled_preview=True)
    except Exception:
        report.update(status='FAIL', error=traceback.format_exc())
    finally:
        window.evaluate_js('ready=false')
        bridge._shutdown()
        window.destroy()


webview.start(check, gui='edgechromium')
work.cleanup()
out = ROOT / 'artifacts/tests/compound-privacy-window.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report))
raise SystemExit(report.get('status') != 'PASS')
