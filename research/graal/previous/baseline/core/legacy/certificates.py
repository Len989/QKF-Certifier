"""Source-bound all-positive-width certificate checker; no producer imports."""
import json
from qkf_certifier.kernel import replay as replay_public,digest,CONTRACT,hashes
from qkf_certifier.frontend import parse_bundle
from regular_interfaces import tree
from guard_kernel import replay as replay_guards
from observer_kernel import replay as replay_observers,EXTENSION as OLD_EXTENSION
from mask_observers import replay as replay_masks,EXTENSION as MASK_EXTENSION
from branch_kernel import verify_tree,EXTENSION as COMPOSITION_EXTENSION
from prefix_masks import BACKEND
from prove_umin import one_bit
from word_oracle import evaluate

SCHEMA='qkf-bounded-mask-case-certificate-v2'
def verify(bundle,cert,expected_target):
    if cert['schema']!=SCHEMA or cert['backend']!=BACKEND:raise ValueError('schema/backend')
    if cert['target']!=expected_target or cert['entry']!='solution':raise ValueError('target/entry')
    if cert['semantics']!=CONTRACT or cert['min_rewrite_width']!=2:raise ValueError('semantics/width partition')
    if cert['legacy_extension']!=OLD_EXTENSION or cert['mask_extension']!=MASK_EXTENSION or cert['composition_extension']!=COMPOSITION_EXTENSION:raise ValueError('extension binding')
    if cert['sources']!=hashes(bundle):raise ValueError('source binding')
    if cert['normalization']['entry']!='solution':raise ValueError('normalization entry')
    nf=replay_public(bundle,'solution',cert['normalization'])
    simple=tree(cert['simplified']);replay_guards(nf,cert['guard_trace'],simple,2)
    old=tree(cert['old_observed']);replay_observers(simple,cert['observer_trace'],old,2)
    new=tree(cert['observed']);replay_masks(old,cert['mask_trace'],new,2)
    if digest(new)!=cert['observed_hash']:raise ValueError('mask-normal result')
    rows,bad=one_bit(parse_bundle(bundle),'solution',expected_target,evaluate)
    if bad is not None or json.loads(json.dumps(rows))!=cert['width_one']:raise ValueError('width one')
    return verify_tree(new,expected_target,cert['proof'])
