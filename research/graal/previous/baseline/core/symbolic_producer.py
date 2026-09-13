from environment import save
from qkf_certifier.kernel import children,at,replace,digest
import symbolic_bridge as bridge
from producer_v6 import produce as symbolic_produce
from producer import Incomplete

MAX_TRIALS=12

def candidates(initial):
 found=[];seen=set()
 def walk(e,path):
  d=bridge.descriptor(e)
  if d is not None and digest(e) not in seen:seen.add(digest(e));found.append(path);return
  for index in children(e):walk(e[index],path+[index])
 walk(initial,[]);return found[:MAX_TRIALS]

def produce(initial,checkpoint=lambda x:None):
 cur=initial;trace=[];attempts=[];spent={'search_nodes':0,'fm_constructed_rows':0}
 # Paths refer to the original shape; no candidate has a candidate ancestor.
 # After replacement, recompute the next unmatched expression to avoid stale paths.
 tried=set()
 while len(attempts)<MAX_TRIALS and len(trace)<bridge.MAX_LEMMAS:
  paths=[p for p in candidates(cur) if digest(at(cur,p)) not in tried]
  if not paths:break
  path=paths[0];tried.add(digest(at(cur,path)))
  source,d,captures=bridge.specification(cur,path)
  try:cert,record=symbolic_produce(source)
  except Incomplete as e:cert=None;record=e.record
  except (ValueError,TypeError) as e:cert=None;record=dict(status='unsupported_translation',reason=str(e),totals={})
  for k in spent:spent[k]+=record.get('totals',{}).get(k,0)
  attempts.append(dict(path=path,descriptor=d,obligation=source,captures=captures,record=record));checkpoint(dict(attempts=attempts,totals=spent))
  if cert is not None:
   new=replace(cur,path,d['after'])
   trace.append(dict(schema=bridge.SCHEMA,path=path,descriptor=d,captures=captures,obligation=source,
                     certificate=cert,before_hash=digest(cur),after_hash=digest(new)))
   cur=new
 return cur,trace,dict(attempts=attempts,totals=spent)
