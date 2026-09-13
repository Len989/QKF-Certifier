"""Declared equivalent action representations and deliberate unsupported shifts.

This is a mechanism-directed metamorphic suite, not an external holdout.
No normalization or inference function is used to construct variants.
"""
X=('var',0);Y=('var',1);DATA=('var',2);Z=('zero',);T=('ones',);W=('width',);ONE=('const',1)
OPS=['countr_zero','countr_one','countl_zero','countl_one']


def flip(op):return op.replace('one','TEMP').replace('zero','one').replace('TEMP','zero')


def replace(e,old,new):
    if e==old:return new
    if e[0] in {'var','const','zero','ones','width','true','false'}:return e
    return (e[0],*(replace(x,old,new) for x in e[1:]))


def variants(e,ns):
    alias=e
    for n in ns:alias=replace(alias,n,(flip(n[0]),('not',n[1])))
    op,x,a=e
    return [e,(op,x,('add',Z,a)),alias,(op,('not',('not',x)),('sub',('add',a,ONE),ONE))]


def cases():
    rows=[]
    def add(family,e,ns,role):
        for i,v in enumerate(variants(e,ns)):
            rows.append(dict(id=family+'__'+str(i),family=family,expression=v,reference=e,role=role))
    for countop in OPS:
        n=(countop,X);side='low' if countop.startswith('countr') else 'high'
        for op in ['clear_low_bits','set_low_bits','clear_high_bits','set_high_bits']:
            same=op.endswith(side+'_bits');base=n if same else ('sub',W,n)
            for d in [-1,0,1]:
                amount=base if d==0 else ('add',base,ONE) if d==1 else ('sub',base,ONE)
                add('position_'+countop+'_'+op+'_'+str(d),(op,DATA,amount),[n],'position')
        for op in ['shl','lshr','ashr']:
            n1=(countop,X);n2=(OPS[(OPS.index(countop)+1)%4],Y)
            amount=('sub',('umin',ONE,n1),('umax',n2,('sub',W,ONE)))
            add('endpoint_'+countop+'_'+op,(op,DATA,amount),[n1,n2],'endpoints')
        # Retain unresolved cases instead of deleting them from denominators.
        for op in ['shl','lshr','ashr']:
            add('relocation_'+countop+'_'+op,(op,DATA,n),[n],'unsupported-relocation')
    # The same position observer also serves shifts of an all-ones carrier.
    for countop in OPS:
        n=(countop,X);op='shl' if countop.startswith('countr') else 'lshr'
        for d in [-1,1]:
            amount=('sub',n,ONE) if d==-1 else ('add',n,ONE)
            add('ones_shift_'+countop+'_'+str(d),(op,T,amount),[n],'position')
    return rows
