"""Run32 supervisor: all attempts retained; fixed exports; no engine monkeypatching."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time

from .cases import (BASELINE_TREE,CURRENT_TREE,MODES,REPEATS,canonical,load,population,
                    register,require,save,sha)
from .identity import snapshot

HERE=Path(__file__).resolve().parent


def limit():
    resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))


def execute(root,case,mode,operation,budget,out,proof=None,optimized=False):
    command=[sys.executable,'-I','-B']+(['-O'] if optimized else [])+[str(HERE/'worker.py'),
        '--root',str(root),'--case',str(case),'--mode',mode,'--operation',operation,
        '--budget',json.dumps(budget),'--output',str(out)]
    if proof is not None: command+=['--proof',str(proof)]
    start=time.perf_counter()
    try:
        p=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120,
                         cwd=root,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONHASHSEED':'0'},
                         preexec_fn=limit)
        code=p.returncode; stdout,stderr=p.stdout,p.stderr
    except subprocess.TimeoutExpired as exc:
        code=124; stdout,stderr=exc.stdout or b'',exc.stderr or b''
    elapsed=time.perf_counter()-start
    out.mkdir(parents=True,exist_ok=True)
    (out/'stdout.log').write_bytes(stdout); (out/'stderr.log').write_bytes(stderr)
    save(out/'PROCESS.json',{'returncode':code,'wall_seconds':elapsed,'command':command,
                            'wall_budget_seconds':120,'address_space_bytes':2*1024**3})
    return code


def seals():
    expected=load(HERE/'LOCK.json')
    require(expected['schema']=='qkf-run32-harness-lock-v1','harness lock schema')
    for path,digest in expected['sha256'].items():
        require(sha((HERE/path).read_bytes())==digest,'harness changed: '+path)
    return expected


def run(old,new,inputs,out):
    old,new,inputs,out=map(lambda p:Path(p).resolve(),(old,new,inputs,out))
    lock=seals(); out.mkdir(parents=True,exist_ok=False)
    before={'frozen_v3':snapshot(old),'current':snapshot(new)}
    require(before['frozen_v3']['tree']==BASELINE_TREE,'exact frozen engine tree')
    require(before['current']['tree']==CURRENT_TREE,'exact accepted PR31 tree')
    save(out/'ENGINE_SNAPSHOTS.json',before); save(out/'HARNESS_LOCK.json',lock)
    prepared=time.perf_counter(); entries=register(inputs,out/'cases',new)
    require(entries==load(HERE/'REGISTERED_CASES.json'),'registered case/budget identities')
    save(out/'ENVIRONMENT.json',{'python':sys.version,'executable':sys.executable,
        'platform':platform.platform(),'machine':platform.machine(),'processor':platform.processor(),
        'cpu_count':os.cpu_count(),'cpuinfo':Path('/proc/cpuinfo').read_text().split('\n\n')[0],
        'preparation_seconds':time.perf_counter()-prepared,'new_holdout':False})
    failures=[]
    for repeat in range(REPEATS):
        for i,e in enumerate(entries):
            offset=(i+repeat)%3
            for mode in MODES[offset:]+MODES[:offset]:
                root=old if mode=='frozen_v3' else new
                d=out/'attempts'/e['id']/mode/('discovery-'+str(repeat))
                if execute(root,out/'cases'/e['id'],mode,'discover',e['budgets'][mode],d):
                    failures.append(d.relative_to(out).as_posix())
    # Replay the first proof, not the fastest attempt. Keep each discovered proof.
    for e in entries:
        for mode in MODES:
            root=old if mode=='frozen_v3' else new
            d=out/'attempts'/e['id']/mode; proof=d/'discovery-0'/'proof.json'
            if proof.exists():
                for r in range(REPEATS+1):
                    q=d/('replay-'+str(r))
                    if execute(root,out/'cases'/e['id'],mode,'check',e['budgets'][mode],q,
                               proof=proof,optimized=r==REPEATS):
                        failures.append(q.relative_to(out).as_posix())
    after={'frozen_v3':snapshot(old),'current':snapshot(new)}
    require(after==before,'engine modified during evaluation')
    save(out/'POSTFLIGHT.json',{'engine_snapshots_sha256':sha(canonical(after)),
                              'failures':failures})
    require(not failures,'failed processes retained: '+repr(failures))
    # Verify result determinism, every origin, all cases and comparative packages.
    summary=audit(out)
    phase=subprocess.run([sys.executable,'-I','-B',str(HERE/'phases.py'),str(out),
                          str(out/'PHASES.json'),'--root',str(new)],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=240,cwd=new)
    (out/'phases-stdout.log').write_bytes(phase.stdout)
    (out/'phases-stderr.log').write_bytes(phase.stderr)
    require(phase.returncode==0,'separate phase diagnostics failed; logs retained')
    require(snapshot(old)==before['frozen_v3'] and snapshot(new)==before['current'],
            'engine changed during phase diagnostics')
    save(out/'SUMMARY.json',summary)
    save(out/'MANIFEST.json',{p.relative_to(out).as_posix():sha(p.read_bytes())
                             for p in sorted(out.rglob('*')) if p.is_file()})
    return summary


def audit(out):
    out=Path(out); entries=load(out/'cases'/'CASES.json')['cases']
    snapshots=load(out/'ENGINE_SNAPSHOTS.json')
    require(entries==load(HERE/'REGISTERED_CASES.json'),'complete registered population')
    rows={}; totals={m:Counter() for m in MODES}
    for e in entries:
        case=out/'cases'/e['id']; require(sha((case/'source.java').read_bytes())==e['source_sha256'],'source hash')
        require(sha(canonical(load(case/'target.json')))==e['target_sha256'],'target hash')
        rows[e['id']]={'group':e['group'],'comparison':e['comparison'],'modes':{}}
        for mode in MODES:
            d=out/'attempts'/e['id']/mode; discoveries=[d/('discovery-'+str(r)) for r in range(REPEATS)]
            records=[load(p/'RECORD.json') for p in discoveries]
            require(all(load(p/'PROCESS.json')['returncode']==0 for p in discoveries),'discovery process success')
            first=records[0]
            require(all(r['metrics']==first['metrics'] and r['result_sha256']==first['result_sha256']
                        for r in records),'deterministic verdict and metrics across all attempts')
            proof=discoveries[0]/'proof.json'
            status=first['metrics']['status']
            for p,r in zip(discoveries,records):
                require(sha(canonical(load(p/'result.json')))==r['result_sha256'],'raw discovery result hash')
            require(proof.exists()==(status in {'certified','refuted'}),'proof/status distinction')
            require(status in {'certified','refuted','unsupported','budget_exhausted'},'unexpected outcome')
            if status in {'certified','refuted'}:
                require(status==e['expected_semantics'],'contradiction with registered case semantics')
                for p in discoveries: require((p/'proof.json').read_bytes()==proof.read_bytes(),'deterministic proof bytes')
                replays=[d/('replay-'+str(r)) for r in range(REPEATS+1)]
                for p in replays:
                    rr=load(p/'RECORD.json')
                    require(load(p/'PROCESS.json')['returncode']==0 and rr['guard_active'],'replay guard/process')
                    require(rr['result_sha256']==first['result_sha256']
                            and sha(canonical(load(p/'result.json')))==rr['result_sha256'],
                            'fresh replay equals discovery result')
                records += [load(p/'RECORD.json') for p in replays]
            else: replays=[]
            require({p.name for p in d.iterdir()}=={p.name for p in discoveries+replays},
                    'unreported or missing attempts')
            origin_files=snapshots['frozen_v3' if mode=='frozen_v3' else 'current']['files']
            for p in discoveries+replays:
                for o in load(p/'IMPORTS.json').values():
                    require(o['path'] in origin_files and o['sha256']==origin_files[o['path']]['sha256'],
                            'module does not belong to its locked engine')
            rows[e['id']]['modes'][mode]=first['metrics']
            totals[mode][status]+=1
        b,c=(rows[e['id']]['modes'][m] for m in ('closure_cells','closure_rows'))
        require({k:v for k,v in b.items() if k!='proof_bytes'}=={k:v for k,v in c.items() if k!='proof_bytes'},
                'direct/row status, interfaces, obligations and structure differ')
    return {'schema':'qkf-run32-acceptance-summary-v1','cases':rows,'case_count':28,
            'main_cases':23,'controls':5,'totals':{m:dict(sorted(c.items())) for m,c in totals.items()},
            'discovery_processes':28*3*REPEATS,'replay_processes':sum(
                4 for e in rows.values() for m in e['modes'].values() if m['status'] in {'certified','refuted'}),
            'new_holdout':False,'frozen_v2_unchanged':'1/15','run27_unchanged':'2/33'}


def verify(out):
    out=Path(out); manifest=load(out/'MANIFEST.json')
    actual={p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file()}-{'MANIFEST.json'}
    require(actual==set(manifest),'artifact file set')
    for p,h in manifest.items(): require(sha((out/p).read_bytes())==h,'artifact hash: '+p)
    summary=audit(out); require(summary==load(out/'SUMMARY.json'),'summary reconstructed from all attempts')
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('command',choices=('run','audit'))
    p.add_argument('output',type=Path); p.add_argument('--old',type=Path); p.add_argument('--new',type=Path)
    p.add_argument('--inputs',type=Path); a=p.parse_args()
    result=verify(a.output) if a.command=='audit' else run(a.old,a.new,a.inputs,a.output)
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__': main()
