# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs
root=Path(SPECPATH).parent
import sys
sys.path.insert(0,str(root/".desktop-deps"))
resources=[]
for directory in ('PyParse','Modified PyParse','toolkit','Cheminformatic_Super_Advance','ketcher_bridge/dist','desktop/live_ui'):
    for path in (root/directory).rglob('*'):
        if path.is_file() and not any(part in ('__pycache__','tests','node_modules','.git') for part in path.relative_to(root).parts) and path.suffix not in ('.pyc','.log'):
            resources.append((str(path),str(path.relative_to(root).parent)))
resources += [(str(root/'tests/fixtures/peak-inspection-portable.zip'),'tests/fixtures')]
resources += [(str(root/'xinpilot_logo.ico'),'.')]
resources += [(str(root/'THIRD_PARTY_NOTICES.md'),'.')]
resources += collect_data_files('rdkit')+collect_data_files('webview')+collect_data_files('pythonnet')+collect_data_files('clr_loader')
hidden=['desktop.live_app','desktop.live_engine','desktop.packaged_check','integrated_full_software','webview.platforms.winforms','webview.platforms.edgechromium','clr','pythonnet','clr_loader']
resources += collect_data_files('opentrons') + collect_data_files('opentrons_shared_data')
resources += [(str(p),str(p.relative_to(root).parent)) for p in (root/'third_party').rglob('*') if p.is_file()]
for package in ('rdkit','PIL','openpyxl','pandas','numpy','matplotlib','seaborn','jinja2','opentrons','opentrons_shared_data'):
    hidden+=collect_submodules(package)
a=Analysis([str(root/'desktop/frozen_entry.py')],pathex=[str(root),str(root/'.desktop-deps')],binaries=collect_dynamic_libs('webview')+collect_dynamic_libs('clr_loader'),datas=resources,hiddenimports=hidden,hookspath=[str(root/'.desktop-deps/webview/__pyinstaller')],hooksconfig={'matplotlib':{'backends':['TkAgg','Agg']}},excludes=['PyQt5','PyQt6','PySide2','PySide6'],noarchive=False)
# A venv over Miniforge needs its base runtime DLLs explicitly collected.
# Resolve only their dependency closure, rather than copying the entire environment.
import pefile
library=Path(sys.base_prefix)/'Library/bin'
queue=['libcrypto-3-x64.dll','libssl-3-x64.dll','liblzma.dll','libbz2.dll','libexpat.dll','tcl86t.dll','tk86t.dll','ffi-8.dll','sqlite3.dll']
seen={Path(item[0]).name.lower() for item in a.binaries}
while queue:
    name=queue.pop()
    if name.lower() in seen:continue
    path=library/name
    if not path.is_file():continue
    seen.add(name.lower());a.binaries.append((name,str(path),'BINARY'))
    with pefile.PE(str(path),fast_load=True) as pe:
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
        for item in getattr(pe,'DIRECTORY_ENTRY_IMPORT',[]):
            queue.append(item.dll.decode())
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='XinPilot-v1.2.3-Windows-x64',version=str(root/'packaging/version_info.txt'),console=False,icon=str(root/'xinpilot_logo.ico'),upx=False)
