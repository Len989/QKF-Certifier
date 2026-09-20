"""Fresh semantic replay with pre-import guards; manifests establish only integrity."""
from __future__ import annotations
import argparse
import hashlib
import importlib.abc
import json
from pathlib import Path
import sys


class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        forbidden=('research.pure_rows.producer','research.pure_rows.reference','research.pure_rows.experiment',
                   'research.signed_', 'research.inference', 'papers', 'z3', 'cvc5', 'subprocess', 'platform')
        if any(fullname==p or fullname.startswith(p if p.endswith('_') else p+'.') for p in forbidden):
            raise ImportError('forbidden during pure-row replay: '+fullname)


def run(root: Path):
    sys.meta_path.insert(0,Guard())
    from .common import encoded, read_json, need, digest
    from .checker import check, check_completion, explain
    manifest=read_json(root/'MANIFEST.json')
    need(type(manifest) is dict,'manifest shape')
    actual={str(f.relative_to(root)) for f in root.rglob('*') if f.is_file()}-{'MANIFEST.json'}
    need(actual==set(manifest),'artifact file set differs')
    for name,sha in manifest.items():
        rel=Path(name)
        need(not rel.is_absolute() and '..' not in rel.parts and not (root/rel).is_symlink(),'unsafe artifact path')
        need(hashlib.sha256((root/rel).read_bytes()).hexdigest()==sha,'artifact hash differs: '+name)
    index=read_json(root/'INDEX.json')
    need(type(index) is list and len(index)==5264,'registered population incomplete')
    counts={};named={};pairs=0;protected=0;external=0;rounds=0
    for i,entry in enumerate(index):
        path=entry['path'];need(path==f'cases/case-{i:05d}.json','case ordering/path')
        data=read_json(root/path);family,name=data['family'],data['name']
        need(family==entry['family'] and name==entry['name'] and digest(data['input'])==entry['input_sha256'],'index binding')
        result=check(data['input'],data['proof']);size=len(encoded(data['proof']))
        need(size==entry['certificate_bytes'],'certificate byte count')
        counts[family]=counts.get(family,0)+1
        length=sum(len(xs) for xs in result['interface']['horizon2_partition'])
        pairs+=length*(length-1)//2;protected+=int(result['carrier_protected'])
        external+=sum(row['external_count'] for row in result['rows']);rounds+=result['strict_feedback_rounds']
        if family=='named':
            named[name]=dict(carrier_partition=result['carrier_partition'],strict_feedback_rounds=result['strict_feedback_rounds'],
                            N1=result['interface']['N1'],N2=result['interface']['N2'],rows=result['rows'],certificate_bytes=size)
    expected=dict(schema='qkf-pure-row-development-summary-v1',status='passed',presentations=sum(counts.values()),families=counts,
                  unordered_interface_pairs_per_horizon=pairs,horizons_checked=[1,2],protected_presentations=protected,
                  external_row_classes_total=external,strict_feedback_rounds_total=rounds,named_cases=named,
                  semantic_scope='exact named interface; completion witnesses checked separately',
                  new_java_execution=False,new_smt_execution=False,lean_checked=False)
    need(encoded(expected)==encoded(read_json(root/'SUMMARY.json')),'saved summary not reproduced')
    for item in read_json(root/'COMPLETIONS.json'):
        need(encoded(check_completion(item['input'],item['witness']))==encoded(item['result']),'completion witness replay differs')
    record=read_json(root/'cases/case-00001.json')
    for item in read_json(root/'QUERIES.json'):
        result=explain(record['input'],record['proof'],item['left'],item['right'],item['horizon'])
        need(encoded(result)==encoded(item),'query replay differs')
    return expected


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path)
    args=parser.parse_args();print(json.dumps(run(args.root),sort_keys=True))
