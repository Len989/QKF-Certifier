import sys,time,json
from algebras import A3,MV3,Z2ADD,Z3ADD,Z4ADD,M2,M3,S3,ONE
from engine import Theory,build_signature,generate_equations,build_pool,sign_table_z3,parity_table_z4
from visibility_cc import VisibilityCongruenceClosure
from visibility_cc_fast import IncrementalVisibilityCC
cases=[
 ('A3|MV3 empty',A3,MV3,{}),('A3|MV3 Ann',A3,MV3,{'schemes':['Ann']}),
 ('Z3|M3 recon',Z3ADD,M3,{'ident':'by_name','schemes':['Un','Dist']}),
 ('Z3|S3 sign',Z3ADD,S3,{'schemes':['Tab'],'tab':sign_table_z3(S3)}),
 ('Z4 parity',Z4ADD,ONE,{'schemes':['Tab'],'tab':parity_table_z4(ONE)}),]
for name,A,B,kw in cases:
 th=Theory(A=A,B=B,ident=kw.get('ident','none'),schemes=tuple(kw.get('schemes',())),tab=kw.get('tab'))
 action,ops,CA,CB=build_signature(th);eqs=generate_equations(th,action);T1=build_pool(ops,CA+CB,1,0)
 t=time.perf_counter();a=VisibilityCongruenceClosure(eqs,T1,horizon=2).run();ta=time.perf_counter()-t
 t=time.perf_counter();b=IncrementalVisibilityCC(eqs,T1,horizon=2).run();tb=time.perf_counter()-t
 assert a.partition(T1,2)==b.partition(T1,2)
 print({'case':name,'nodes':len(b.nodes),'reference_ms':round(ta*1000,3),'worklist_ms':round(tb*1000,3),'worklist_speedup':round(ta/tb,2),'sig_reprocess':b.stats['signature_reprocess']})
