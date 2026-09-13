"""Repeat the delivered experiment in a new directory; preserve observations."""
from pathlib import Path
import argparse,json,shutil,subprocess,sys
from common import ROOT,setup,check_baseline

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();repo=setup(a.repo);check_baseline(repo);out=a.output.resolve()
    if out.exists() or out==ROOT or ROOT in out.parents:raise ValueError('output must be new and outside this package')
    def ignore(directory,names):
        excluded={n for n in names if n=='__pycache__' or Path(n).suffix in {'.pyc','.pkl','.so','.tmp'}}
        if Path(directory).resolve()==ROOT:excluded|={n for n in names if n=='results' or n.endswith('.log') or n=='SHA256SUMS.txt'}
        return excluded
    shutil.copytree(ROOT,out,ignore=ignore)
    def run(script,*args):
        subprocess.run([sys.executable,str(out/script),*args],check=True)
    for mode in ['composed','monolithic']:run('run_stage.py','--repo',str(repo),'--mode',mode)
    for script in ['check_semantics.py','check_refinements.py','verify_stage.py']:run(script,'--repo',str(repo))
    run('check_boundary.py','--repo',str(repo))
    statuses={mode:json.loads((out/'results'/mode/'summary.json').read_text())['summary'] for mode in ['composed','monolithic']}
    print(json.dumps({'output':str(out),'summary':statuses},indent=2))

if __name__=='__main__':main()
