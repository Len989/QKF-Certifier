import sys,time,json
from algebras import A3,MV3,Z2ADD,Z3ADD,Z4ADD,M2,M3,S3,ONE
from engine import Theory,build_signature,generate_equations,build_pool,synthesize,sign_table_z3,parity_table_z4
from visibility_cc import VisibilityCongruenceClosure

cases=[
 ('A3|MV3 empty',A3,MV3,{}),
 ('A3|MV3 Ann',A3,MV3,{'schemes':['Ann']}),
 ('Z2|M2 recon',Z2ADD,M2,{'ident':'neutrals','schemes':['Un','Dist']}),
 ('Z3|M3 recon',Z3ADD,M3,{'ident':'by_name','schemes':['Un','Dist']}),
 ('Z3|S3 sign',Z3ADD,S3,{'schemes':['Tab'],'tab':sign_table_z3(S3)}),
 ('Z4 parity',Z4ADD,ONE,{'schemes':['Tab'],'tab':parity_table_z4(ONE)}),
 ('flagship 11',Z2ADD,M2,{'schemes':['Ann','Comp','Tab'],'tab':{('0','0'):'1'}}),
]
rows=[]
for name,A,B,kw in cases:
 th=Theory(A=A,B=B,ident=kw.get('ident','none'),schemes=tuple(kw.get('schemes',())),merge=kw.get('merge',False),merge_op=kw.get('merge_op'),tab=kw.get('tab'))
 action,ops,CA,CB=build_signature(th);eqs=generate_equations(th,action);T1=build_pool(ops,CA+CB,1,0)
 t=time.perf_counter(); red=VisibilityCongruenceClosure(eqs,T1,horizon=2).run(); rt=time.perf_counter()-t
 t=time.perf_counter(); full=synthesize(A,B,d=2,cap=0,**kw); ft=time.perf_counter()-t
 rows.append({
   'case':name,'T2_terms':full.pool_size,'reduced_nodes':red.stats['nodes'],
   'node_reduction_x':round(full.pool_size/red.stats['nodes'],1),
   'reduced_sec':round(rt,6),'full_sec':round(ft,6),
   'runtime_speedup_x':round(ft/rt,1) if rt else None,
   'delta0':red.stabilization_horizon(CA+CB),'delta1':red.stabilization_horizon(T1)
 })
 print(rows[-1],flush=True)
open('benchmark_results.json','w').write(json.dumps(rows,indent=2))
