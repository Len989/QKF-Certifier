#!/usr/bin/env python3
"""Rebuild all source traces, check semantics, and certify the corpus."""
import argparse
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--repo',type=Path,required=True)
    ap.add_argument('--out',type=Path,default=ROOT/'rerun_results');args=ap.parse_args()
    repo=str(args.repo.resolve());out=str(args.out.resolve())
    subprocess.run(['git','diff','--quiet','HEAD','--','src','tests/word_oracle.py'],cwd=repo,check=True)
    commands=[
        ['audit_fixed.py','--repo',repo,'--corpus',str(ROOT/'fixtures/corpus'),'--helpers',str(ROOT/'fixtures/helpers'),'--out',out],
        ['audit_observers.py','--repo',repo,'--results',out],
        ['check_observers.py','--repo',repo,'--results',out],
        ['prove_umin.py','--repo',repo,'--results',out],
        ['analyze_umin.py','--repo',repo,'--results',out],
    ]
    for cmd in commands:
        print('Running',cmd[0],flush=True)
        subprocess.run([sys.executable,str(ROOT/cmd[0]),*cmd[1:]],check=True)
    print('Completed:',out)


if __name__=='__main__':main()
