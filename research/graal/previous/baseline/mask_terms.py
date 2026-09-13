"""Small symbolic vocabulary tied to the two original KnownBits inputs."""
import itertools


def tree(x):return tuple(tree(a) for a in x) if isinstance(x,(tuple,list)) else x
V=tuple(('v',i) for i in range(4))
ZERO=('int',0)


def bit(e,row):
    e=tree(e);op=e[0]
    if op=='v':
        if len(e)!=2 or type(e[1]) is not int or not 0<=e[1]<4:raise ValueError('word variable')
        return row[e[1]]
    if op=='not':return 1-bit(e[1],row)
    if op in {'and','or','xor'}:
        a,b=bit(e[1],row),bit(e[2],row)
        return {'and':lambda:a&b,'or':lambda:a|b,'xor':lambda:a^b}[op]()
    if e==('zero',):return 0
    if e==('ones',):return 1
    raise ValueError('not a bitwise word expression: '+repr(e))


def rows():
    return [r for r in itertools.product([0,1],repeat=4) if not(r[0]&r[1]) and not(r[2]&r[3])]


def cube(must,may):return ('cube',tree(must),tree(may))
def lo(c):return ('lo',tree(c))
def hi(c):return ('hi',tree(c))


def predicate(p,row):
    p=tree(p)
    if type(p) is bool:return p
    op,a,b=p
    if a[0]=='sign' and b[0]=='int':
        x,y=bit(a[1],row),b[1]
        return {'==':lambda:x==y,'!=':lambda:x!=y,'<':lambda:x<y,'<=':lambda:x<=y,'>':lambda:x>y,'>=':lambda:x>=y}[op]()
    if b==ZERO and a[0] in {'lo','hi'} and op in {'>=','<'}:
        sign=bit(a[1][2 if a[0]=='lo' else 1],row)
        return bool(sign) if op=='<' else not sign
    raise ValueError('unsupported sign-context predicate: '+repr(p))


def sign_rows(guards):
    return [r for r in rows() if all(predicate(p,r)==truth for p,truth in guards)]


def valid_table(c):
    c=tree(c)
    if c[0]!='cube':raise ValueError('cube term')
    out=[]
    for r in rows():
        m,y=bit(c[1],r),bit(c[2],r)
        if m and not y:raise ValueError('mask carrier is not proved compatible')
        out.append([list(r),m,y])
    return out


def word_ast(e):
    e=tree(e)
    if e[0]=='v':return ('var',e[1])
    if e[0] in {'zero','ones'}:return e
    if e[0] not in {'and','or','xor','not'}:raise ValueError('word projection grammar')
    return (e[0],*(word_ast(x) for x in e[1:]))
