"""Source-bound Lucene predicate study; constructed controls are a separate set."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile

from research.external.frozen_v1.experiment import check_blob, check_engine
from research.observations.model import digest, require
from .cli import save
from .frontend import select
from .predicate_checker import check, prepare
from .predicate_frontend import CONTRACT, GOAL_SCHEMA, target_value
from .predicate_producer import derive
from .predicate_semantics import evaluate

ROOT = Path(__file__).resolve().parents[2]


def specification(entry, target=None, word_type='int'):
    return {'schema': GOAL_SCHEMA, 'contract': CONTRACT, 'entry': entry, 'word_type': word_type,
            'target': ['popcount_le', 1] if target is None else target}


def cases():
    return [
        ('alternate', 'return (x & -x)==x;', ['popcount_le',1], 'int', 'certified'),
        ('one_hot', 'return x!=0 && ((x & (x-1))==0);', ['popcount_eq',1], 'int', 'certified'),
        ('at_most_two', 'int t=x & (x-1); return (t & (t-1))==0;', ['popcount_le',2], 'int', 'certified'),
        ('at_most_three', 'int t=x & (x-1); t=t & (t-1); return (t & (t-1))==0;', ['popcount_le',3], 'int', 'certified'),
        ('zero', 'return x==0;', ['popcount_eq',0], 'int', 'certified'),
        ('local_boolean', 'boolean b=(x & (x-1))==0; return b;', ['popcount_le',1], 'int', 'certified'),
        ('long_predicate', 'return (x & (x-1L))==0L;', ['popcount_le',1], 'long', 'certified'),
        ('wrong_true', 'return true;', ['popcount_le',1], 'int', 'refuted'),
        ('wrong_false', 'return false;', ['popcount_le',1], 'int', 'refuted'),
        ('wrong_zero', 'return x==0;', ['popcount_le',1], 'int', 'refuted'),
        ('wrong_increment', 'return (x & (x+1))==0;', ['popcount_le',1], 'int', 'refuted'),
        ('small_width_only', 'return 2!=0;', ['or',['popcount_le',1],['not',['popcount_le',1]]], 'int', 'refuted'),
    ]


def population():
    # Fixed development sample, not a blind external selection.
    xs = set(range(1 << 16))
    rng = random.Random(20260916017)
    xs.update(rng.getrandbits(32) for _ in range(4096))
    for k in range(32):
        xs.update({1<<k, (1<<k)-1, ((1<<k)+1)&0xffffffff, 0xffffffff^(1<<k)})
    xs.update({0x7fffffff,0x80000000,0x80000001,0xffffffff})
    return sorted(xs)


def replay_all(output):
    output = Path(output)
    results = []
    for p in sorted(output.glob('*.certificate.json')):
        prefix = p.name.removesuffix('.certificate.json')
        source = (output/(prefix+'.java')).read_bytes().decode('utf-8')
        spec = json.loads((output/(prefix+'.goal.json')).read_text())
        cert = json.loads(p.read_text())
        actual = check(source, spec, cert)
        expected = json.loads((output/(prefix+'.result.json')).read_text())
        require(actual == expected, 'independent replay '+prefix)
        results.append({'id':prefix,'status':actual['status'],'certificate_sha256':digest(cert)})
    require(len(results)==13, 'complete predicate replay population')
    return results


def run(inputs, output):
    inputs, output = Path(inputs), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    check_engine(ROOT)
    corpus = json.loads((ROOT/'research/external/frozen_v1/CORPUS.json').read_text())
    raw = (inputs/'lucene_bits.java').read_bytes()
    identity = check_blob(raw, corpus['sources']['lucene_bits'])
    source = raw.decode('utf-8')
    spec = specification({'class':'BitUtil','method':'isZeroOrPowerOfTwo'})
    cert, result = derive(source,spec)
    require(result['status']=='certified', 'original Lucene independent count proof')
    (output/'lucene.java').write_bytes(raw)
    save(output/'lucene.identity.json',identity)
    save(output/'lucene.goal.json',spec)
    save(output/'lucene.certificate.json',cert)
    save(output/'lucene.result.json',result)
    declaration = select(source, spec['entry'], word_type='int', result_type='boolean')
    save(output/'lucene.selection.json',{'span':declaration[4], 'declaration':declaration[3]})
    designed = []
    for name, body, target, typ, expected in cases():
        text='class Example { public static boolean f('+typ+' x) {'+body+'} }'
        g=specification({'class':'Example','method':'f'},target,typ)
        c,r=derive(text,g)
        require(r['status']==expected and check(text,g,c)==r, 'constructed predicate '+name)
        (output/(name+'.java')).write_text(text,encoding='utf-8')
        save(output/(name+'.goal.json'),g);save(output/(name+'.certificate.json'),c)
        save(output/(name+'.result.json'),r)
        designed.append({'id':name,'status':r['status'],'states':r['source']['native_states'],
                         'classes':r['source']['classes'],'certificate_sha256':digest(c)})
    xs=population()
    driver=('public class PredicateProbe { public static void main(String[] a) throws Exception {\n'
            'java.io.BufferedReader r=new java.io.BufferedReader(new java.io.InputStreamReader(System.in));\n'
            'for(String s;(s=r.readLine())!=null;) System.out.println(\n'
            'org.apache.lucene.util.BitUtil.isZeroOrPowerOfTwo(Integer.parseInt(s)));\n}}\n')
    ip='\n'.join(str(x if x<2**31 else x-2**32) for x in xs)+'\n'
    with tempfile.TemporaryDirectory(prefix='qkf-predicate-') as d:
        d=Path(d)
        # Compile the full, unmodified original class, not a retyped method body.
        (d/'BitUtil.java').write_bytes(raw)
        (d/'PredicateProbe.java').write_text(driver,encoding='utf-8')
        cp=subprocess.run(['javac','--release','17','-d',str(d),str(d/'BitUtil.java'),str(d/'PredicateProbe.java')],
                          capture_output=True,text=True,timeout=30)
        require(cp.returncode==0,'full BitUtil compilation: '+cp.stderr)
        run_java=subprocess.run(['java','-cp',str(d),'PredicateProbe'],input=ip,
                                capture_output=True,text=True,timeout=30)
        require(run_java.returncode==0,'original class invocation: '+run_java.stderr)
    ys=run_java.stdout.splitlines()
    require(len(ys)==len(xs) and all(y in {'true','false'} for y in ys),'native Boolean population')
    _, ir, _, table, terminals, start=prepare(source,spec,cert['source'])
    for x,y in zip(xs,ys):
        q=start[0]
        for k in range(32):q=table[q,str((x>>k)&1)]
        expected=target_value(spec['target'],x.bit_count())
        require((y=='true')==evaluate(ir,x,32)==terminals[q]==expected,'Java/DAG/QKF/count agreement')
    (output/'PredicateProbe.java').write_text(driver,encoding='utf-8')
    (output/'native-input.txt').write_text(ip,encoding='utf-8')
    (output/'native-output.txt').write_text(run_java.stdout,encoding='utf-8')
    save(output/'REPLAY.json',replay_all(output))
    summary={'development_not_blind':True,'new_external_methods':1,'new_external_certified':1,
             'new_external_refuted':0,'old_twelve_method_population_unchanged':True,
             'constructed_certified':7,'constructed_refuted':5,'native_inputs':len(xs),
             'native_width':32,'native_mismatches':0,'native_full_original_class':True,
             'source_states':result['source']['native_states'],'classes':result['source']['classes'],
             'product_states':result['product_states'],'checked_edges':result['checked_edges'],
             'original_certificate_sha256':digest(cert),'constructed':designed,
             'new_lean_theorem':False,'frozen_v1_unchanged':True}
    save(output/'SUMMARY.json',summary)
    save(output/'MANIFEST.json',{str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted(output.rglob('*')) if p.is_file()})
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs');parser.add_argument('output');parser.add_argument('--replay',action='store_true')
    a=parser.parse_args()
    if a.replay:print(json.dumps(replay_all(a.output),sort_keys=True))
    else:print(json.dumps(run(Path(a.inputs).resolve(),Path(a.output).resolve()),sort_keys=True))
