"""Execute exact selected Graal Java bodies with small documented dependencies.

The compiler/runtime dependencies are optional, pinned external tools. This is
not a complete Graal build. IntegerStamp operation and refinement bodies are
copied byte-for-byte; only operation method declarations receive unique names.
"""
import hashlib,json,os,subprocess,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SOURCE_SHA='7a4b84d92654ef22c911dab503efd829b48a72156ff0de51129e767589ad0010'
DEFAULT_JAVA=ROOT.parent/'qkf_graal_tools/jdk/jdk4py/java-runtime'


def java_command():
    runtime=Path(os.environ.get('QKF_JAVA_RUNTIME',str(DEFAULT_JAVA)))
    env=os.environ.copy();env['LD_LIBRARY_PATH']=str(runtime/'lib')+':'+str(runtime/'lib/server')
    return [str(runtime/'bin/java'),'-Xmx512m'],env


def block_end(s,start):
    depth=0;i=start;state='code'
    while i<len(s):
        c=s[i];n=s[i:i+2]
        if state=='line':
            if c=='\n':state='code'
        elif state=='comment':
            if n=='*/':state='code';i+=1
        elif state in {'"',"'"}:
            if c=='\\':i+=1
            elif c==state:state='code'
        elif n=='//':state='line';i+=1
        elif n=='/*':state='comment';i+=1
        elif c in {'"',"'"}:state=c
        elif c=='{':depth+=1
        elif c=='}':
            depth-=1
            if depth==0:return i+1
        i+=1
    raise ValueError('unterminated Java source block')


PRELUDE=r'''
// Local dependency shims, not upstream Graal runtime classes.
import java.io.*;
abstract class Stamp { abstract boolean hasValues(); final boolean isEmpty(){return !hasValues();} }
abstract class PrimitiveStamp extends Stamp {
  private final int bits; PrimitiveStamp(int bits,Object ops){this.bits=bits;}
  int getBits(){return bits;}
}
class CodeUtil {
  static long mask(int bits){return bits==64 ? -1L : (1L<<bits)-1;}
  static long minValue(int bits){return bits==64 ? Long.MIN_VALUE : -(1L<<(bits-1));}
  static long maxValue(int bits){return bits==64 ? Long.MAX_VALUE : (1L<<(bits-1))-1;}
  static long signExtend(long v,int bits){return bits==64 ? v : (v<<(64-bits))>>(64-bits);}
  static long convert(long v,int bits,boolean unsigned){return unsigned ? v&mask(bits) : signExtend(v,bits);}
  static boolean isPowerOf2(long v){return v>0 && (v&(v-1))==0;}
}
class Assertions { static String errorMessageContext(Object... args){return java.util.Arrays.toString(args);} }
class GraalError {
  static void guarantee(boolean p,String message,Object... args){if(!p)throw new IllegalStateException(String.format(message,args));}
  static RuntimeException shouldNotReachHere(String s){return new IllegalStateException(s);}
}
class IntegerStamp extends PrimitiveStamp {
  private final long lowerBound,upperBound,mustBeSet,mayBeSet;
  private final boolean canBeZero;
  static final int ITERATION_LIMIT=3;
  static final Ops OPS=new Ops();
  static IntegerStamp create(int bits){return new IntegerStamp(bits,false);}
  static IntegerStamp createEmptyStamp(int bits){return new IntegerStamp(bits,true);}
  static boolean isPowerOf2(long v){return CodeUtil.isPowerOf2(v);}
  static class Ops {
    Op getAdd(){return new Op("add");} Op getNeg(){return new Op("neg");} Op getNot(){return new Op("not");}
  }
  static class Op {
    final String name; Op(String n){name=n;}
    Stamp foldStamp(Stamp a,Stamp b){return foldAdd(a,b);}
    Stamp foldStamp(Stamp a){return name.equals("neg") ? foldNeg(a) : foldNot(a);}
  }
'''

MAIN=r'''
  static IntegerStamp call(String op,IntegerStamp a,IntegerStamp b){
    return (IntegerStamp)switch(op){case "and"->foldAnd(a,b);case "or"->foldOr(a,b);
      case "xor"->foldXor(a,b);case "add"->foldAdd(a,b);case "sub"->foldSub(a,b);
      default->throw new IllegalArgumentException(op);};
  }
  public static void main(String[] args) throws Exception {
    BufferedReader in=new BufferedReader(new InputStreamReader(System.in));
    BufferedWriter out=new BufferedWriter(new OutputStreamWriter(System.out));String line;
    while((line=in.readLine())!=null){
      try {
        String[] a=line.split(" ");int bits=Integer.parseInt(a[1]);long mask=CodeUtil.mask(bits);IntegerStamp r;
        if(a[0].equals("create")) {
          r=create(bits,Long.parseLong(a[2]),Long.parseLong(a[3]),Long.parseUnsignedLong(a[4],16),Long.parseUnsignedLong(a[5],16),a[6].equals("1"));
        } else {
          long za=Long.parseUnsignedLong(a[2],16),oa=Long.parseUnsignedLong(a[3],16),zb=Long.parseUnsignedLong(a[4],16),ob=Long.parseUnsignedLong(a[5],16);
          if((za&oa)!=0 || (zb&ob)!=0 || ((za|oa|zb|ob)&~mask)!=0)throw new IllegalArgumentException("input contract");
          IntegerStamp x=stampForMask(bits,oa,(~za)&mask),y=stampForMask(bits,ob,(~zb)&mask);
          r=call(a[0],x,y);
        }
        out.write("OK "+r.lowerBound+" "+r.upperBound+" "+Long.toUnsignedString(r.mustBeSet,16)+" "+Long.toUnsignedString(r.mayBeSet,16)+" "+(r.canBeZero?1:0)+"\n");
      } catch(Throwable e){out.write("ERROR "+e.getClass().getSimpleName()+" "+e.getMessage()+"\n");}
    }
    out.flush();
  }
}
'''


def build():
    raw=(ROOT/'source/IntegerStamp.java').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_SHA
    s=raw.decode();out=ROOT/'native';out.mkdir(exist_ok=True);parts=[];records=[]
    def extract(marker,label,start=0,rename=None):
        a=s.index(marker,start);brace=s.index('{',a);b=block_end(s,brace)
        original=s[a:b];body=s[brace:b]
        (out/(label+'.inc')).write_text(original+'\n')
        records.append(dict(name=label,byte_start=len(s[:a].encode()),byte_end=len(s[:b].encode()),
                            line=s[:a].count('\n')+1,sha256=hashlib.sha256(original.encode()).hexdigest(),
                            body_sha256=hashlib.sha256(body.encode()).hexdigest(),declaration_renamed=rename is not None))
        parts.append(original if rename is None else rename+body)
    for i,marker in enumerate([
        'private IntegerStamp(int bits, boolean empty)',
        'private IntegerStamp(int bits, long constant)',
        'private IntegerStamp(int bits, long lowerBound, long upperBound)',
        'private IntegerStamp(int bits, long lowerBound, long upperBound, long mustBeSet, long mayBeSet, boolean canBeZero)',
        'private boolean checkInvariants()',
        'public static IntegerStamp createConstant(int bits, long value)',
        'public static IntegerStamp create(int bits, long lowerBoundInput, long upperBoundInput)',
        'public static IntegerStamp create(int bits, long lowerBoundInput, long upperBoundInput, long mustBeSet, long mayBeSet)',
        'public static IntegerStamp create(int bits, long lowerBoundInput, long upperBoundInput, long mustBeSetInput, long mayBeSetInput, boolean canBeZero)',
        'private static boolean isEmpty(long lowerBound, long upperBound, long mustBeSet, long mayBeSet)',
        'private static long significantBit(long bits, long value)',
        'private static long minValueForMasks(int bits, long mustBeSet, long mayBeSet)',
        'private static long maxValueForMasks(int bits, long mustBeSet, long mayBeSet)',
        'private static long computeUpperBound(int bits, long upperBound, long mustBeSet, long mayBeSet, boolean canBeZero)',
        'private static long setOptionalBits(int bits, long bound, long mustBeSet, long mayBeSet, long initialValue)',
        'private static long computeLowerBound(int bits, long lowerBound, long mustBeSet, long mayBeSet, boolean canBeZero)',
        'public static IntegerStamp stampForMask(int bits, long mustBeSet, long mayBeSet)',
        'public boolean hasValues()',
        'public long lowerBound()', 'public long upperBound()', 'public long mustBeSet()', 'public long mayBeSet()',
        'public boolean isUnrestricted()',
        'public boolean contains(long value)', 'private boolean contains(long value, boolean isCanBeZero)',
        'public static boolean addOverflowsPositively(long x, long y, int bits)',
        'public static boolean addOverflowsNegatively(long x, long y, int bits)',
        'public static long carryBits(long x, long y)']):extract(marker,'helper_'+str(i))
    for op in ['Neg','Add','Sub','Not','And','Or','Xor']:
        prefix='new UnaryOp.Not()' if op=='Not' else 'new ArithmeticOpTable.'+('UnaryOp.' if op=='Neg' else 'BinaryOp.')+op+'('
        start=s.index(prefix);a=s.index('protected Stamp foldStampImpl(',start);brace=s.index('{',a)
        declaration=s[a:brace].replace('protected Stamp foldStampImpl','static Stamp fold'+op)
        extract('protected Stamp foldStampImpl(',op,start,rename=declaration)
    header=s[:s.index('package ')]
    generated=header+PRELUDE+'\n\n'.join(parts)+'\n'+MAIN
    (out/'IntegerStamp.java').write_text(generated)
    tools_dir=ROOT.parent/'qkf_graal_tools';tools_dir.mkdir(exist_ok=True)
    jar=tools_dir/'ecj-3.42.0.jar';url='https://repo.maven.apache.org/maven2/org/eclipse/jdt/ecj/3.42.0/ecj-3.42.0.jar'
    if not jar.exists():
        with urllib.request.urlopen(url,timeout=30) as response:jar.write_bytes(response.read())
    java,env=java_command()
    version=subprocess.run(java+['-version'],env=env,text=True,capture_output=True)
    result=subprocess.run(java+['-jar',str(jar),'-17','-d',str(out/'classes'),str(out/'IntegerStamp.java')],env=env,text=True,capture_output=True)
    manifest=dict(source_sha256=SOURCE_SHA,extracted=records,generated_sha256=hashlib.sha256(generated.encode()).hexdigest(),
                  compiler_url=url,compiler_sha256=hashlib.sha256(jar.read_bytes()).hexdigest(),
                  runtime=version.stderr,compile_returncode=result.returncode,stdout=result.stdout,stderr=result.stderr,
                  trust_boundary='Exact operation/refinement bodies on JVM; local CodeUtil, base classes, dispatch and equivalent uncached factories; assertions disabled. Not a full Graal build.')
    (out/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    if result.returncode:raise RuntimeError(result.stderr)
    return dict(status='compiled',source_bodies=len(records))


def evaluate(lines):
    java,env=java_command()
    p=subprocess.run(java+['-da','-cp',str(ROOT/'native/classes'),'IntegerStamp'],input='\n'.join(lines)+'\n',text=True,capture_output=True,env=env,timeout=60)
    if p.returncode:raise RuntimeError(p.stderr)
    rows=p.stdout.splitlines()
    if len(rows)!=len(lines):raise ValueError('Java output cardinality')
    return rows


if __name__=='__main__':print(json.dumps(build()))
