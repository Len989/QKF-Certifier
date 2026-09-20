"""Post-measurement descriptive statistics. Not part of any proof engine."""
from collections import Counter
from pathlib import Path
import argparse
import json
import statistics

from .cases import MODES,load,save
from .run import verify


def analyze(root):
    root=Path(root); summary=verify(root); cases=summary['cases']; records={}
    for name,row in cases.items():
        records[name]={}
        for mode,metrics in row['modes'].items():
            d=root/'attempts'/name/mode
            discovery=[load(d/('discovery-'+str(i))/'RECORD.json') for i in range(3)]
            process=[load(d/('discovery-'+str(i))/'PROCESS.json') for i in range(3)]
            replay=[load(p/'RECORD.json') for p in sorted(d.glob('replay-*'))]
            normal=[r for r in replay if not r['optimized']]
            records[name][mode]={'metrics':metrics,
                'discovery_operation_median_s':statistics.median(r['operation_wall_seconds'] for r in discovery),
                'discovery_process_median_s':statistics.median(r['wall_seconds'] for r in process),
                'discovery_all_attempts_s':sum(r['operation_wall_seconds'] for r in discovery),
                'discovery_all_processes_s':sum(r['wall_seconds'] for r in process),
                'discovery_peak_rss_kib':max(r['process_peak_rss_kib'] for r in discovery),
                'replay_operation_median_s':statistics.median(r['operation_wall_seconds'] for r in normal) if normal else None}
    main=[n for n,r in cases.items() if not r['group'].endswith('_control')]
    controls=[n for n in cases if n not in main]
    common=[n for n in main if all(cases[n]['modes'][m]['status'] in ('certified','refuted') for m in MODES)]
    aggregates={}
    for mode in MODES:
        aggregates[mode]={'main_statuses':dict(Counter(cases[n]['modes'][mode]['status'] for n in main)),
            'control_statuses':dict(Counter(cases[n]['modes'][mode]['status'] for n in controls)),
            'all_discovery_operation_seconds':sum(r[mode]['discovery_all_attempts_s'] for r in records.values()),
            'all_discovery_process_seconds':sum(r[mode]['discovery_all_processes_s'] for r in records.values()),
            'main_proof_bytes':sum(cases[n]['modes'][mode]['proof_bytes'] for n in main),
            'common_proof_bytes':sum(cases[n]['modes'][mode]['proof_bytes'] for n in common)}
    phases=load(root/'PHASES.json')
    ratios={}
    for name,p in phases['cases'].items():
        rs=p['timings']
        ratios[name]={'checked_load_median_s':statistics.median(r['checked_load_seconds'] for r in rs),
                     'row_product_discovery_median_s':statistics.median(r['rows_product_discovery_seconds'] for r in rs),
                     'row_product_replay_median_s':statistics.median(r['rows_product_replay_seconds'] for r in rs),
                     'rows_over_cells_warm':statistics.median(r['rows_warm_seconds'] for r in rs)/statistics.median(r['cells_warm_seconds'] for r in rs)}
    return {'schema':'qkf-run32-descriptive-analysis-v1','environment':load(root/'ENVIRONMENT.json'),
            'aggregates':aggregates,'main_cases':len(main),'controls':len(controls),
            'common_completed_cases':len(common),'records':records,'phases':ratios,
            'finite_ir_cell_row_comparisons':phases['finite_comparisons'],
            'timing_is_descriptive':True,'new_holdout':False}


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('experiment',type=Path)
    p.add_argument('output',type=Path); a=p.parse_args(); result=analyze(a.experiment)
    save(a.output,result); print(json.dumps(result['aggregates'],sort_keys=True))


if __name__=='__main__': main()
