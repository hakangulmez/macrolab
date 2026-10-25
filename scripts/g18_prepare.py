"""Prepare the local UI-v3 preview from accepted G17 payloads, without a candidate.

Run from the repository root. No network, model execution, publication, or Git
mutation. The accepted runs/g17/site is required and remains read-only.
"""
from pathlib import Path
import json,os,shutil,subprocess,sys
ROOT=Path.cwd();sys.path.insert(0,str(ROOT/'scripts'))
from g9_export import inventory
OUT=ROOT/'runs/g18'
records=[]
for suffix,accepted in [('',ROOT/'runs/g17/site')]:
 target=OUT/suffix;public=target/'public';public.mkdir(exist_ok=True,parents=True)
 for folder in ['data','runtime','licences','schemas','validation']:
  shutil.copytree(accepted/folder,public/folder,dirs_exist_ok=True)
 shutil.copy2(accepted/'.nojekyll',public/'.nojekyll')
 shutil.copy2(ROOT/'runs/g17/runtime_wheel.json',target/'runtime_wheel.json')
 wheel=json.loads((target/'runtime_wheel.json').read_text());shutil.copy2(public/'runtime'/wheel['wheel_file'],target/wheel['wheel_file'])
 shutil.copytree(ROOT/'third_party/fonts/jetbrains-mono',public/'licences/fonts/jetbrains-mono',dirs_exist_ok=True)
 from ui_snapshot import create
 create(accepted,public/'ui/inflation.json')
 with (target/'build.log').open('w') as log:
  subprocess.run(['npm','run','build','--','--emptyOutDir'],cwd=ROOT/'web',env={**os.environ,'MACROLAB_BASE_PATH':'/macrolab/','MACROLAB_PUBLIC_DIR':str(public),'MACROLAB_BUILD_DIR':str(target/'site')},stdout=log,stderr=subprocess.STDOUT,check=True)
 baseline=inventory(accepted);fresh=inventory(target/'site');shipped={r['path']:r for r in fresh['files']}
 fixed=[r for r in baseline['files'] if not r['path'].startswith('assets/') and r['path']!='index.html']
 for row in fixed:assert shipped[row['path']]==row,row['path']
 assert max(f['bytes'] for f in fresh['files'] if f['path'].endswith('.js'))<500000
 (target/'site-inventory.json').write_text(json.dumps(fresh,indent=2)+'\n')
 records.append({'snapshot':json.loads((public/'data/manifest.json').read_text())['snapshot_id'],'all_data_runtime_licences_schemas_validation_exact':True,'byte_identical_files':len(fixed),'file_count':fresh['file_count'],'total_bytes':fresh['total_bytes'],'tree_sha256':fresh['tree_sha256']})
 print(records[-1],flush=True)
(OUT/'preparation.json').write_text(json.dumps({'passed':True,'web_version':'2.0.1','runtime_version':'2.0.0','network_requests':0,'builds':records},indent=2)+'\n')
