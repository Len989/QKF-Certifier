"""Independent proof replay. Telemetry consistency is diagnostic, not evidence of execution."""
import hashlib
import importlib.abc
from pathlib import Path
import sys


class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {'subprocess', 'platform', 'z3', 'cvc5', 'research.semantic_work.meter',
                        'research.semantic_work.experiment'} or (
            fullname.startswith('research.') and fullname.rsplit('.',1)[-1].startswith('producer')):
            raise ImportError('forbidden during semantic replay: '+fullname)


def replay(root):
    from .contract import load_json, canonical, digest, need
    from .run import check
    root = Path(root)
    manifest=load_json(root/'MANIFEST.json')
    files={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}-{'MANIFEST.json'}
    need(files==set(manifest),'artifact file set')
    for name, sha in manifest.items():
        rel=Path(name)
        need(not rel.is_absolute() and '..' not in rel.parts and not (root/rel).is_symlink(),'safe artifact path')
        need(hashlib.sha256((root/rel).read_bytes()).hexdigest()==sha,'artifact integrity')
    registration=load_json(root/'REGISTRATION.json')
    need(canonical(registration)==canonical(load_json(Path(__file__).with_name('REGISTRATION.json'))),'registered requests')
    summary=load_json(root/'SUMMARY.json');statuses=[];proofs=0
    for i, entry in enumerate(registration['cases']):
        directory=root/('case-%02d'%i);r=load_json(directory/'request.json')
        need(digest(r)==entry['request_sha256'],'request identity')
        direct=load_json(directory/'direct.json');observed={'direct':direct['status']}
        for arm,req_file in (('covered','request.json'),('mixed','mixed-request.json')):
            req=load_json(directory/req_file)
            expected=load_json(directory/'request.json')
            if arm=='mixed':expected['strategy']='witness_then_covered'
            need(req==expected,'only registered strategy may change')
            saved=load_json(directory/(arm+'.json'));observed[arm]=saved['result']['status']
            if saved['proof'] is not None:
                verified=check(req,saved['proof'])
                need(verified==saved['result'],'semantic outcome replay')
                need(load_json(directory/(arm+'-proof.json'))==saved['proof'],'standalone proof identity')
                if arm=='covered':
                    need(digest(saved['proof']['legacy'])==direct['legacy_proof_sha256'],'direct legacy proof')
                proofs+=1
            else:
                need(saved['result']['status'] not in ('certified','refuted'),'no unverified success')
            totals={}
            for stage in saved['work']['phases']:
                for k,v in stage['counts'].items():totals[k]=totals.get(k,0)+v
            need(totals==saved['work']['counts'],'work phase sum')
            need(saved['certificate_bytes']==(0 if saved['proof'] is None else len(canonical(saved['proof']).encode())),
                 'complete certificate byte size')
        statuses.append({'name':entry['name'],'statuses':observed})
    need(statuses==summary['cases'],'summary consistency')
    need(summary['status']=='passed' and not load_json(root/'FAILURES.json'),'recorded full run')
    return {'schema':'qkf-semantic-replay-result-v1','status':'passed','cases':len(statuses),
            'proofs_checked':proofs,'summary_sha256':digest(summary),
            'measurement_execution_proven':False,'unresolved_absence_certified':False}


if __name__ == '__main__':
    if len(sys.argv)!=2:raise ValueError('one experiment directory')
    sys.meta_path.insert(0,Guard())
    from .contract import canonical
    print(canonical(replay(sys.argv[1])))
