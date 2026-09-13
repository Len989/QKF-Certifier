"""Fresh lower production after freeze, then isolated replay of the full proof chain."""
import argparse,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def run():
    from freeze_step import verify,sha
    integrity=verify();out=ROOT/'results/main';out.mkdir(parents=True,exist_ok=False)
    start=time.perf_counter()
    from lower_producer import produce
    p=produce((ROOT/'previous/baseline/source/IntegerStamp.java').read_text())
    if p['status']!='certificate_produced':raise ValueError('Lower production failed')
    (out/'certificate.json').write_text(json.dumps(p['certificate'],indent=2)+'\n')
    producer=dict(status=p['status'],file_sha256=sha(out/'certificate.json'),certificate_bytes=(out/'certificate.json').stat().st_size,seconds=time.perf_counter()-start)
    (out/'producer.json').write_text(json.dumps(producer,indent=2)+'\n')
    subprocess.run([sys.executable,str(ROOT/'replay_saved.py'),'--output',str(out/'replay')],check=True,timeout=220)
    if verify()!=integrity:raise ValueError('Freeze changed during main run')
    replay=json.loads((out/'replay/results.json').read_text())
    record=dict(status='completed',integrity=integrity,producer=producer,replay_status=replay['status'],fresh_proof_processes=replay['fresh_proof_processes'],
                lower='universal conditional carrier preservation; universal mask successor',upper='previous universal exact upper contract replayed',
                graal='control 1/5; joint 2/5 unchanged',NiceToMeetYou='historical 11/39 whole and 104/411 components; not rerun',
                scope='No full-create theorem, new whole-program result, new benchmark or new SMT run.')
    (out/'results.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
if __name__=='__main__':run()
