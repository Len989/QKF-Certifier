"""Constructed reduction study, not a holdout or a target-coverage measurement.

Fresh runs optionally execute Java on eight cases. Replay never invokes Java,
producer search or old-model enumeration; it checks saved source-bound packages
and outputs. Previous-path counts remain explicitly retained diagnostics.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
from research.observations.model import digest, require
from research.signed_bridge.cli import load
from research.signed_bridge.model import CapacityExceeded, request, word_value
from research.signed_predicates import semantics
from . import bridge

ROOT = Path(__file__).resolve().parents[2]


def cases():
    templates = (
        ("complement", "(x==16) || !(x==16)", ""),
        ("contradiction", "(x<0) && !(x<0)", ""),
        ("absorption", "(x<0) || ((x<0) && x==16)", ""),
        ("alias", "(x==16) || !(16==x)", ""),
        ("dead_local", "x<0", "WORD unused=x+16; boolean b=x==7; "),
        ("assignment", "b", "boolean b=x<0; b=true; "),
        ("reflexive", "(x+3)==(x+3)", ""),
        ("not_and_literal", "!!(x>0) && true", ""),
        ("power", "x>0 && (x & (x-1))==0", ""),
        ("signed_literal", "16>0", ""),
    )
    for typ in ("int", "long"):
        for name, expression, prefix in templates:
            text = f"class Demo {{ public static boolean f({typ} x) {{ {prefix.replace('WORD',typ)}return {expression}; }} }}"
            yield name+"_"+typ, text, request({"class":"Demo","method":"f"},typ), name in {"complement","absorption","dead_local","signed_literal"}
    for name, expression in (
        ("tautology_31", "x == 2147483648L || x != 2147483648L"),
        ("contradiction_62", "(x == 4611686018427387904L) && !(x == 4611686018427387904L)"),
        ("dead_31", "x<0"),
        ("nested_31", "!(!(x == 2147483648L || x != 2147483648L))"),
    ):
        prefix = "long ignored=x+2147483648L; " if name=="dead_31" else ""
        text = f"class Demo {{ public static boolean f(long x) {{ {prefix}return {expression}; }} }}"
        yield name, text, request({"class":"Demo","method":"f"},"long"), False


def save(path, value):
    with Path(path).open("x", encoding="utf-8") as f:
        f.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+"\n")


def factor_value(model, proof, x, width):
    edges = {(r["state"],r["symbol"]):r["next"] for r in proof["cells"]}
    state = proof["initial"]
    for i in range(width): state=edges[state,str((x>>i)&1)]
    return model.terminal[proof["blocks"][state][0]]=="true"


def run(output, *, replay=False, java=False):
    output=Path(output)
    require(not (replay and java), "replay cannot run Java")
    if replay:
        manifest=load(output/"MANIFEST.json")
        files={p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
        require(set(manifest)==files-{"MANIFEST.json"}, "exact experiment file set")
        for name, expected in manifest.items():
            require(hashlib.sha256((output/name).read_bytes()).hexdigest()==expected, "experiment bytes: "+name)
        original_summary=load(output/"SUMMARY.json")
        java=original_summary["java_executed_in_original_run"]
    else:
        require(not output.exists(), "new experiment directory")
        output.mkdir(parents=True)
    outcomes, performance = {}, {}
    for name, text, selection, native_case in cases():
        d=output/name
        if replay:
            require((d/"source.java").read_text()==text and load(d/"request.json")==selection,"source/request")
            c=load(d/"certificate.json")
        else:
            d.mkdir(); (d/"source.java").write_text(text,encoding="utf-8"); save(d/"request.json",selection)
            start=time.perf_counter(); c, result=bridge.infer(text,selection)
            require(c is not None,"constructed reduction failed: "+name)
            performance[name]={"full_infer_including_check_seconds":time.perf_counter()-start}
            save(d/"certificate.json",c)
            # This independent reference enumeration is NOT part of the new route.
            from research.signed_bridge.producer import derive as old
            start=time.perf_counter()
            try:
                _, old_result=old(text,selection)
                reference={"status":"source_model_verified","model_states":old_result["model_states"]}
            except CapacityExceeded:
                reference={"status":"budget_exhausted","stage":"original_source_model","limit":64}
            performance[name]["separate_old_reference_seconds"]=time.perf_counter()-start
            save(d/"old_reference.json",reference)
        start=time.perf_counter(); result=bridge.check_observations(text,selection,c)
        original,reduced,model=bridge.rebuild_model(text,selection,c["source_model"])
        if not replay: performance[name]["separate_replay_and_rebuild_seconds"]=time.perf_counter()-start
        small=wide=native_count=0
        for w in range(1,9):
            for x in range(1<<w):
                expected=semantics.evaluate(original,x,w)
                require(expected==semantics.evaluate(reduced,x,w)==word_value(model,x,w)
                        ==factor_value(model,c["observations"],x,w),"finite original/reduced/model/factor agreement")
                small+=1
        for w in (31,32,33,63,64,65,127,4096):
            for x in (0,1,(1<<w)-1,1<<(w-1)):
                require(semantics.evaluate(original,x,w)==semantics.evaluate(reduced,x,w)
                        ==word_value(model,x,w),"wide agreement")
                wide+=1
        if java and native_case:
            width=32 if selection["word_type"]=="int" else 64
            xs=sorted(set(range(256))|{(1<<width)-1,1<<(width-1),(1<<(width-1))-1})
            if replay:
                record=load(d/"native.json")
                require(record["inputs"]==xs and record["width"]==width,"native population")
                require(record["source_sha256"]==original["source_sha256"],"native source binding")
                ys=record["outputs"]
            else:
                from research.signed_predicates.frontend import select
                from research.signed_predicates.experiment import native
                _,_,_,declaration,_=select(text,selection["entry"],word_type=selection["word_type"])
                start=time.perf_counter(); ys=native(declaration,"f",selection["word_type"],width,xs)
                performance[name]["native_seconds"]=time.perf_counter()-start
                save(d/"native.json",{"inputs":xs,"outputs":ys,"width":width,"source_sha256":original["source_sha256"]})
            require(type(ys) is list and len(ys)==len(xs) and all(type(y) is bool for y in ys),"native outputs")
            for x,y in zip(xs,ys):
                require(y==semantics.evaluate(original,x,width)==semantics.evaluate(reduced,x,width)
                        ==word_value(model,x,width),"Java/source/reduced/model agreement")
            native_count=len(xs)
        if replay:
            require(load(d/"result.json")==result,"replayed source result")
        else: save(d/"result.json",result)
        reduction=c["source_model"]["reduction"]
        outcomes[name]={"model_states":len(model.states),"classes":result["classes"],
                       "nodes_before":len(original["nodes"]),"nodes_after":len(reduced["nodes"]),
                       "atoms_before":len(original["atoms"]),"atoms_after":len(reduced["atoms"]),
                       "steps":len(reduction["steps"]),"certificate_sha256":digest(c),
                       "small_word_comparisons":small,"wide_comparisons":wide,"native_inputs":native_count}
    if not replay:
        from .producer import derive, ReductionLimit
        from research.wordexpr.frontend import Unsupported
        controls={}
        delayed="class Demo { public static boolean f(long x) { return x == 2147483648L; } }"
        _, controls["delayed_31"]=bridge.infer(delayed,selection)
        require(controls["delayed_31"]["stage"]=="reduced_source_model","honest retained limitation")
        for name,kwargs in (("reduction_budget",{"max_steps":0}), ("model_budget",{"max_states":1}),
                            ("observation_budget",{"max_observations":0})):
            s=next(t for n,t,_,_ in cases() if n=="tautology_31")
            c,r=bridge.infer(s,selection,**kwargs);require(c is None,"no partial certificate");controls[name]=r
        try:
            derive("class Demo { public static boolean f(long x) { long dead=x>>1; return true; } }",selection)
            raise RuntimeError("dead unsupported source accepted")
        except Unsupported as exc: controls["dead_unsupported"]={"status":"unsupported","reason":str(exc)}
        save(output/"CONTROLS.json",controls)
    summary={"schema":"qkf-signed-reduction-development-v1","cases":outcomes,"verified":len(outcomes),
             "small_word_comparisons":sum(x["small_word_comparisons"] for x in outcomes.values()),
             "wide_comparisons":sum(x["wide_comparisons"] for x in outcomes.values()),
             "native_inputs":sum(x["native_inputs"] for x in outcomes.values()),"mismatches":0,
             "java_executed_in_original_run":java,"target_checked":False,"new_holdout":False,
             "scope":"constructed source equivalence; no new target or revised Run32/Run27 verdicts"}
    if replay: require(summary==original_summary,"reconstructed summary")
    else:
        save(output/"SUMMARY.json",summary);save(output/"PERFORMANCE.json",performance)
        save(output/"MANIFEST.json",{p.relative_to(output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in sorted(output.rglob("*")) if p.is_file()})
    return summary


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("output",type=Path)
    p.add_argument("--replay",action="store_true");p.add_argument("--java",action="store_true");a=p.parse_args()
    print(json.dumps(run(a.output,replay=a.replay,java=a.java),sort_keys=True))
