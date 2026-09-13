#!/usr/bin/env python3
"""Reproduce the explicitly reported Paper II validation suite."""
from pathlib import Path
import subprocess,sys,json,ast
ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=['test_fast_vs_reference.py','test_generic_ground.py','test_certified_proofs.py','test_countermodel.py','test_optimality_countermodels.py','test_forest_stabilization.py']

def run(script,log):
    result=subprocess.run([sys.executable,str(script)],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    log.write_text(result.stdout)
    print(script.name+': '+('PASS' if result.returncode==0 else 'FAIL'),flush=True)
    if result.returncode: raise SystemExit(result.returncode)
    return result.stdout

def main():
    if not __debug__: raise SystemExit('Run without -O.')
    run(ROOT/'verification'/'verify_article.py',ROOT/'verification'/'article_check.log')
    results=[]
    for name in SCRIPTS:
        out=run(ROOT/'prototype'/name,ROOT/'verification'/name.replace('.py','.log'))
        results.append({'script':name,'result':ast.literal_eval(out.strip().splitlines()[-1])})
    (ROOT/'verification'/'regression_results.json').write_text(json.dumps({'status':'PASS','runs':results},indent=2)+'\n')
if __name__=='__main__':main()
