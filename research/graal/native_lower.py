"""Execute the exact Graal upper helper with a new command in its old Java harness."""
import hashlib,json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent


def java():
    runtime=Path(os.environ.get('QKF_JAVA_RUNTIME',str(ROOT.parent/'qkf_graal_tools/jdk/jdk4py/java-runtime')))
    env=os.environ.copy();env['LD_LIBRARY_PATH']=str(runtime/'lib')+':'+str(runtime/'lib/server')
    return [str(runtime/'bin/java'),'-Xmx512m'],env


def build():
    out=ROOT/'native';out.mkdir(exist_ok=False)
    base=(ROOT/'previous/native/IntegerStamp.java').read_text()
    marker='if(a[0].equals("create")) {'
    extra='''if(a[0].equals("lower")) {
          long result=computeLowerBound(bits,Long.parseLong(a[2]),Long.parseUnsignedLong(a[3],16),Long.parseUnsignedLong(a[4],16),a[5].equals("1"));
          out.write("LO "+result+"\\n");continue;
        }
        '''
    if base.count(marker)!=1:raise ValueError('unique original harness dispatch')
    generated=base.replace(marker,extra+marker)
    for name in ['helper_15']:
        exact=(ROOT/'previous/baseline/native'/(name+'.inc')).read_text().rstrip('\n')
        if generated.count(exact)!=1:raise ValueError('exact native target body: '+name)
    (out/'IntegerStamp.java').write_text(generated)
    command,env=java();jar=ROOT.parent/'qkf_graal_tools/ecj-3.42.0.jar'
    expected=json.loads((ROOT/'previous/baseline/native/MANIFEST.json').read_text())['compiler_sha256']
    if hashlib.sha256(jar.read_bytes()).hexdigest()!=expected:raise ValueError('pinned ECJ')
    p=subprocess.run(command+['-jar',str(jar),'-17','-d',str(out/'classes'),str(out/'IntegerStamp.java')],env=env,text=True,capture_output=True,timeout=60)
    version=subprocess.run(command+['-version'],env=env,text=True,capture_output=True,timeout=15)
    result=dict(status='compiled' if p.returncode==0 else 'compile_failed',returncode=p.returncode,
                generated_sha256=hashlib.sha256(generated.encode()).hexdigest(),
                prior_harness_sha256=hashlib.sha256(base.encode()).hexdigest(),compiler_sha256=expected,
                runtime=version.stderr,stdout=p.stdout,stderr=p.stderr,
                difference='Only one new harness command; all original algorithm bodies remain byte-for-byte intact')
    (out/'MANIFEST.json').write_text(json.dumps(result,indent=2)+'\n')
    if p.returncode:raise RuntimeError(p.stderr)
    return result


def evaluate(specs,classes=None):
    lines=[f'lower {s["width"]} {s["lower"]} {s["must"]:x} {s["may"]:x} {int(s["can_zero"])}' for s in specs]
    command,env=java()
    p=subprocess.run(command+['-da','-cp',str(classes or ROOT/'native/classes'),'IntegerStamp'],env=env,
                     input='\n'.join(lines)+'\n',text=True,capture_output=True,timeout=60)
    if p.returncode:raise RuntimeError(p.stderr)
    output=p.stdout.splitlines()
    if len(output)!=len(specs):raise ValueError('native output cardinality')
    values=[]
    for line in output:
        if not line.startswith('LO '):raise ValueError('native source error: '+line)
        values.append(int(line[3:]))
    return values


if __name__=='__main__':print(json.dumps(build()))
