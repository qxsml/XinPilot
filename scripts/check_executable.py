"""Validate the packaged application from an isolated folder with synthetic data."""
import hashlib,json,os,shutil,subprocess,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
source=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT/'release/XinPilot-v1.2.3-Windows-x64.exe'
work=ROOT/'artifacts'/('pkg-'+uuid.uuid4().hex[:6])
work.mkdir(parents=True)
exe=work/'XinPilot.exe';shutil.copy2(source,exe)
env=os.environ.copy()
for name in ('PYTHONPATH','PYTHONHOME','XINPILOT_PYTHON'):env.pop(name,None)
windows=Path(os.environ.get('SystemRoot',r'C:\Windows'))
env['PATH']=str(windows/'System32')+os.pathsep+str(windows)
report={'sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'size_bytes':exe.stat().st_size}
for kind in ('standard','modified'):
    process=subprocess.run([str(exe),'--oneclick-run-pyparse',kind,'--help'],cwd=work,env=env,capture_output=True,text=True,timeout=120)
    report[kind]={'exit_code':process.returncode,'help_available':'usage:' in process.stdout.lower(),'stderr':process.stderr}
    (work/(kind+'-help.txt')).write_text(process.stdout+process.stderr,encoding='utf-8')
    if process.returncode or not report[kind]['help_available']:
        (work/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        raise RuntimeError(f'Packaged {kind} analysis startup failed: {work}')
process=subprocess.run([str(exe),'--desktop-check',str(work/'desktop-check.json')],cwd=work,env=env,timeout=180)
report['desktop_exit_code']=process.returncode
if (work/'desktop-check.json').exists():report['desktop']=json.loads((work/'desktop-check.json').read_text(encoding='utf-8'))
report['status']='PASS' if process.returncode==0 and report.get('desktop',{}).get('status')=='PASS' else 'FAIL'
(work/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'report':str(work/'summary.json'),'size_bytes':report['size_bytes']}))
raise SystemExit(report['status']!='PASS')
