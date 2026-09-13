"""Source-bound semantic bridge from native word ASTs to unchanged v6.

Arbitrary native subexpressions can be captured as independent words or
nonnegative integer values. Forgetting their dependencies is an overapproximation.
Only proven symbolic equalities permit a native replacement.
"""
import copy
from environment import ROOT
from qkf_certifier.kernel import children,at,replace,digest,Z,W
from regular_interfaces import tree
import kernel,prefix,reconstruction
COUNTS={'countl_zero':'clz','countl_one':'clo','countr_zero':'ctz','countr_one':'cto'}
SCHEMA='qkf-native-symbolic-bridge-v1'
MAX_LEMMAS=12

class Translation:
 def __init__(self):self.words={};self.numbers={}
 def word(self,e):
  if e==('zero',):return ['zero']
  if e==('ones',):return ['ones']
  if e[0] in {'not'}:return [e[0],self.word(e[1])]
  if e[0] in {'and','or','xor'}:return [e[0],self.word(e[1]),self.word(e[2])]
  if e[0] in {'shl','lshr'}:return [e[0],self.word(e[1]),self.scalar(e[2])]
  if e[0] in {'set_low_bits','set_high_bits','clear_low_bits','clear_high_bits'}:
   mask=['lowmask' if 'low' in e[0] else 'highmask',self.scalar(e[2])]
   return ['or',self.word(e[1]),mask] if e[0].startswith('set') else ['and',self.word(e[1]),['not',mask]]
  if e not in self.words:self.words[e]='a'+str(len(self.words))
  return ['input',self.words[e]]
 def scalar(self,e):
  if e==('width',):return 'w'
  if e==('zero',):return 0
  # Only literals 0 and 1 are represented by the same nonnegative integer at
  # EVERY positive width. Larger / negative literals remain captured words.
  if e==('const',1):return 1
  if e[0] in COUNTS:return [COUNTS[e[0]],self.word(e[1])]
  if e[0] in {'umin','umax'}:return ['min' if e[0]=='umin' else 'max',self.scalar(e[1]),self.scalar(e[2])]
  if e[0]=='sub' and e[1]==W and e[2][0] in COUNTS:return ['sub','w',self.scalar(e[2])]
  if e not in self.numbers:self.numbers[e]='p'+str(len(self.numbers))
  return self.numbers[e]
 def guard(self,e):
  if e==('true',):return True
  if e==('false',):return False
  if e[0] in {'booland','boolor','boolxor'}:
   a,b=self.guard(e[1]),self.guard(e[2])
   if e[0]=='boolxor':return ['or',['and',a,['not',b]],['and',['not',a],b]]
   return ['and' if e[0]=='booland' else 'or',a,b]
  if e[0] in {'cmp0','cmp1','cmp6','cmp7','cmp8','cmp9'}:
   # Word zero/nonzero can be observed exactly by a full leading-zero count.
   if e[2]==Z and e[0] in {'cmp0','cmp1'}:
    q=['eq',['clz',self.word(e[1])],'w'];return q if e[0]=='cmp0' else ['not',q]
   a,b=self.scalar(e[1]),self.scalar(e[2]);op=e[0]
   return {'cmp0':lambda:['eq',a,b],'cmp1':lambda:['not',['eq',a,b]],'cmp6':lambda:['lt',a,b],
           'cmp7':lambda:['le',a,b],'cmp8':lambda:['lt',b,a],'cmp9':lambda:['le',b,a]}[op]()
  # Omit a guard we cannot translate; this strengthens the proposed theorem.
  raise ValueError('guard outside symbolic interface')
 def manifest(self):
  return dict(word_captures=[dict(name=n,expression=e) for e,n in self.words.items()],
              scalar_captures=[dict(name=n,expression=e,interpretation='unsigned_native_word_value') for e,n in self.numbers.items()],
              environment='current_native_source_before_this_rewrite')

def descriptor(e):
 if e[0] in {'shl','lshr'} and e[1][0] in {'shl','lshr'} and e[0]!=e[1][0] and e[2]==e[1][2]:
  return dict(kind='whole_word',before=e,after=e[1][1])
 if e[0] in COUNTS:
  view=e[1];flip=False
  while view[0]=='not':flip=not flip;view=view[1]
  kind=COUNTS[e[0]]
  if flip:kind={'clz':'clo','clo':'clz','ctz':'cto','cto':'ctz'}[kind]
  if (kind,view[0]) in {('clz','lshr'),('ctz','shl')}:
   native_count=('countl_zero' if kind=='clz' else 'countr_zero',view[1]);s=view[2]
   # Bounded sum using native modular words. The addition is observed only
   # under n < w-s and s < w, hence n+s < w <= 2**w-1 at every width.
   capped=('select',('cmp9',s,W),W,('select',('cmp9',native_count,('sub',W,s)),W,('add',native_count,s)))
   return dict(kind='count_observation',before=e,after=capped,native_count=native_count,amount=s)
 return None

def path_guards(initial,path):
 e=initial;guards=[]
 for index in path:
  if e[0]=='select' and index in (2,3):guards.append((e[1],index==2))
  e=e[index]
 return guards

def specification(initial,path):
 e=at(initial,path);d=descriptor(e)
 if d is None:raise ValueError('native candidate')
 tr=Translation()
 if d['kind']=='whole_word':claims=[['word_eq',tr.word(e),tr.word(d['after'])]]
 else:
  scalar=[COUNTS[e[0]],tr.word(e[1])];n=tr.scalar(d['native_count']);s=tr.scalar(d['amount'])
  claims=[['scalar',['eq',scalar,['min','w',['add',n,s]]]]]
 guards=[];used=[]
 for index,(g,truth) in enumerate(path_guards(initial,path)):
  try:q=tr.guard(g)
  except ValueError:continue
  guards.append(q if truth else ['not',q]);used.append(index)
 assume=['and',*[['le',0,n] for n in tr.numbers.values()],*guards]
 source=dict(schema=kernel.DSL,name='native_word_bridge',inputs=list(tr.words.values()),parameters=list(tr.numbers.values()),
             assume=assume,claims=claims,origin=dict(native_hash=digest(initial),path=list(path),descriptor=d,
                                                   capture_manifest=tr.manifest(),used_path_guards=used))
 return source,d,tr.manifest()

def verify_symbolic(source,cert):
 if cert['schema']==reconstruction.SCHEMA:return reconstruction.verify(source,cert)
 if cert['schema']==prefix.SCHEMA:return prefix.verify(source,cert)
 if cert['schema']==kernel.SCHEMA:return kernel.verify(source,cert)
 raise ValueError('symbolic schema')

def replay(initial,trace):
 cur=initial
 if len(trace)>MAX_LEMMAS:raise ValueError('symbolic trace length')
 for entry in trace:
  if entry['schema']!=SCHEMA or entry['before_hash']!=digest(cur):raise ValueError('native bridge source')
  source,d,captures=specification(cur,entry['path'])
  # JSON round trips change tuples to lists; canonical digests compare shapes.
  if digest(entry['descriptor'])!=digest(d) or digest(entry['captures'])!=digest(captures):raise ValueError('native capture binding')
  if entry['obligation']!=source and digest(entry['obligation'])!=digest(source):raise ValueError('native obligation binding')
  verify_symbolic(source,entry['certificate'])
  cur=replace(cur,entry['path'],d['after'])
  if entry['after_hash']!=digest(cur):raise ValueError('native rewrite result')
 return cur
