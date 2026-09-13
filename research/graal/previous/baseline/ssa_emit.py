"""Unchanged SSA emitter from the previous LLVM adapter; no proof rules."""
def emit(expr):
    A='!transfer.abs_value<[!transfer.integer,!transfer.integer]>';I='!transfer.integer'
    lines=['builtin.module {',f'  func.func @solution(%a: {A}, %b: {A}) -> {A} {{']
    cache={};counter=0
    def instruction(op,args,ins,out,attrs=''):
        nonlocal counter
        name=f'%v{counter}';counter+=1
        at=' {'+attrs+'}' if attrs else ''
        lines.append(f'    {name} = "transfer.{op}"('+', '.join(args)+')'+at+' : ('+', '.join(ins)+') -> '+out)
        return name
    for i in range(4):
        cache[('var',i)]=instruction('get',['%a' if i<2 else '%b'],[A],I,f'index = {i%2} : index')
    def visit(e):
        if e in cache:return cache[e]
        op=e[0]
        if op in {'zero','ones','const'}:
            value=0 if op=='zero' else -1 if op=='ones' else e[1]
            v=instruction('constant',[cache[('var',0)]],[I],I,f'value = {value} : index')
        elif op=='width':v=instruction('get_bit_width',[cache[('var',0)]],[I],I)
        elif op.startswith('bool'):
            xs=[visit(c) for c in e[1:]]
            nonlocal counter
            v=f'%v{counter}';counter+=1
            lines.append(f'    {v} = arith.{op[4:]}i {xs[0]}, {xs[1]} : i1')
        else:
            xs=[visit(c) for c in e[1:]]
            if op.startswith('cmp'):v=instruction('cmp',xs,[I,I],'i1',f'predicate = {int(op[3:])} : index')
            elif op=='pair':v=instruction('make',xs,[I,I],A)
            else:v=instruction('neg' if op=='not' else op,xs,['i1',I,I] if op=='select' else [I]*len(xs),I)
        cache[e]=v;return v
    result=visit(expr);lines.extend([f'    func.return {result} : {A}','  }','}'])
    return '\n'.join(lines)+'\n'
