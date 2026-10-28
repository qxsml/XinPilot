# Windows setup

## Run from source

Install 64-bit Python 3.12 with Tk and the Python launcher, and Microsoft Edge
WebView2 Runtime. Extract/clone the full repository into a writable directory.
Run `Setup_TypeScript.bat`, then `Launch_XinPilot.bat`.

Setup creates `.venv` and installs `requirements.txt` from the internet. The
Opentrons simulator runs from its included Python source; a separate simulator
EXE is not required. The compiled TypeScript interface and Ketcher assets are
included, so normal launch does not require Node or an internet connection.
Optional compound lookups and FASTSOLV installation require their own connection.

Interpreter priority: `XINPILOT_PYTHON`, private `xinpilot.local.bat`, this
folder's `.venv\Scripts\python.exe`, then `python` on PATH. A private override
is optional and must not be uploaded. The example file contains no local path.

## Development

Install `requirements-dev.txt` into the same environment. To rebuild TypeScript,
use either the isolated Windows toolchain:

```bat
python scripts/setup_toolchain.py
python scripts/setup_renderer_bundler.py
Build_TypeScript.bat
```

or an installed Node/npm environment:

```bat
cd desktop\live_ui
npm install
npm run build
```

Pinned renderer dependencies are in `desktop/live_ui/package.json`. Toolchain
downloads require internet access. Commit the rebuilt `desktop/live_ui/dist/app.js`
after changing renderer source. Run the checks in [testing](testing.md).

## Executables

The repository does not contain an EXE. Build with the [packaging instructions](../packaging/README.md)
or use an executable separately attached by the maintainer to a matching release.
EXE users do not need Python/Node, but do need WebView2 and a writable folder.
FASTSOLV remains external. Independent clean-PC installation testing is still
outstanding; development-machine checks are not a substitute.
