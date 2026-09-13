"""Seven fresh proof processes, with all original evidence kept at its own path."""
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def run(out):
    out=out.resolve();out.mkdir(parents=True,exist_ok=False)
    subprocess.run([sys.executable,str(ROOT/'lower_kernel.py'),'--source',str(ROOT/'previous/baseline/source/IntegerStamp.java'),
                    '--certificate',str(ROOT/'results/main/certificate.json'),'--output',str(out/'lower_replay.json')],check=True,timeout=60)
    subprocess.run([sys.executable,str(ROOT/'previous/replay_saved.py'),'--output',str(out/'preceding')],check=True,timeout=180)
    lower=json.loads((out/'lower_replay.json').read_text());old=json.loads((out/'preceding/results.json').read_text())
    if lower['status']!='proved_universal_conditional_lower_contract' or lower['search_modules_loaded'] or old['status']!='passed':raise ValueError('Strict replay failed')
    result=dict(status='passed',fresh_proof_processes=1+old['fresh_proof_processes'],lower_certificate_sha256=lower['certificate_sha256'],
                previous_universal_upper='passed',graal_whole_programs='control 1/5; joint 2/5, unchanged',
                historical_NiceToMeetYou='11/39 whole; 104/411 components; not rerun',
                full_create='not yet proved',preceding=old)
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=run(a.output)
    print(json.dumps({k:v for k,v in r.items() if k!='preceding'}))
