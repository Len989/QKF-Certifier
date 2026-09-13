"""Scoped forced relations and their finite count observation.

This checker imports no producer. Contract authority is supplied only by the
outer source checker; the default, authority=None, means arbitrary input words.
Bit tables are local consequences of actual positive path equalities and the
explicitly bound KnownBits input pairs. Equality routes are replayed, not searched.
"""
from functools import lru_cache
import collections
import itertools
from qkf_certifier.frontend import parse_bundle, expression
from qkf_certifier.kernel import CONTRACT, Z, T, digest, hashes, at, replace
from regular_interfaces import tree, order
from symbolic_bridge import path_guards
from semantic_view import context, constant, LEAVES
import boundary_v2_kernel as PREVIOUS
import observation_kernel as NATIVE_ROWS
import action_kernel

SCHEMA = 'qkf-scoped-count-observation-v1'
SCOPE_SCHEMA = 'qkf-source-mask-authority-v1'
ONE = ('const', 1)
COUNTS = {'countl_one', 'countr_one'}
CONSUMERS = PREVIOUS.ACTIONS | {'mul', 'udiv', 'sdiv', 'urem', 'srem'} | COUNTS | {'countl_zero', 'countr_zero'}
MAX_GUARDS = 64
MAX_ROUTE = 8
MAX_BITS = 8


@lru_cache(maxsize=20000)
def native(e):
    return PREVIOUS.native(e)


def source_authority(bundle, entry):
    """Reconstruct authority from actual parsed argument positions, never a cert."""
    fs = parse_bundle(bundle)
    initial = expression(fs, entry)
    args = fs[entry]['args']
    if len(args) != 2:
        raise ValueError('source authority requires the declared two-input entry')
    return dict(schema=SCOPE_SCHEMA, semantics=CONTRACT, sources=hashes(bundle),
                entry=entry, initial_hash=digest(initial),
                inputs=[dict(argument=args[i], position=i, zero=('var', 2*i),
                             one=('var', 2*i+1)) for i in range(2)],
                premise='each original nonbottom KnownBits input has disjoint zero and one masks')


def facts(guards):
    g = context([(native(tree(p)), t) for p, t in guards])
    if len(g) > MAX_GUARDS:
        raise ValueError('context guard budget')
    return g


def linear(e):
    """Exact additive word identity, coefficients are integers modulo 2^w."""
    out, steps = PREVIOUS.normalize(e)
    coefficients = collections.Counter()
    integer = 0
    def walk(t, sign):
        nonlocal integer
        if t[0] == 'add':
            walk(t[1], sign); walk(t[2], sign)
        elif t[0] == 'sub':
            walk(t[1], sign); walk(t[2], -sign)
        elif t == Z:
            pass
        elif t == T:
            integer -= sign
        elif t[0] == 'const':
            integer += sign*t[1]
        else:
            coefficients[t] += sign
    walk(out, 1)
    coefficients = {k: v for k, v in coefficients.items() if v}
    return coefficients, integer, dict(normal_form=out, steps=steps,
        coefficients=[dict(term=k, coefficient=v) for k,v in sorted(coefficients.items(), key=repr)], integer=integer)


def equality_edges(g):
    edges = []
    for i, (p, truth) in enumerate(g):
        if not truth or p[0] != 'cmp0':
            continue
        cs, integer, bridge = linear(('sub', p[1], p[2]))
        if len(cs) != 2 or sorted(cs.values()) != [-1, 1]:
            continue
        a = next(k for k,v in cs.items() if v == 1)
        b = next(k for k,v in cs.items() if v == -1)
        # a - b = -integer, modulo the native word modulus.
        edges.append(dict(guard=i, left=a, right=b, difference=-integer, bridge=bridge))
    return edges


def verify_predecessor(y, x, route, g):
    if route == 'definition':
        expected = native(('sub', y, ONE))
        if x != expected:
            raise ValueError('predecessor definition mismatch')
        return dict(rule='native-predecessor-definition', word=y, predecessor=x)
    if not isinstance(route, list) or not 1 <= len(route) <= MAX_ROUTE:
        raise ValueError('equality route budget')
    edges = {r['guard']: r for r in equality_edges(g)}
    current = y; offset = 0; steps = []
    for r in route:
        if set(r) != {'guard', 'from', 'to'} or type(r['guard']) is not int:
            raise ValueError('equality route entry')
        edge = edges.get(r['guard'])
        a, b = tree(r['from']), tree(r['to'])
        if edge is None or a != current:
            raise ValueError('equality route source')
        if (a, b) == (edge['left'], edge['right']):
            delta = edge['difference']
        elif (a, b) == (edge['right'], edge['left']):
            delta = -edge['difference']
        else:
            raise ValueError('equality route operands')
        offset += delta; current = b
        steps.append(dict(edge=edge, direction=[a,b], accumulated_difference=offset))
    if current != x or offset != 1:
        raise ValueError('route does not prove predecessor relation')
    return dict(rule='additive-equality-transport', word=y, predecessor=x, steps=steps,
                conclusion='word = predecessor + 1 modulo 2^w')


def coordinate(e):
    return e[0] in {'var','zero','ones','not','and','or','xor'} and all(
        coordinate(c) for c in (() if e[0] in LEAVES else e[1:]))


def bit(e, values):
    if e == Z: return 0
    if e == T: return 1
    if e[0] == 'var': return values[e[1]]
    if e[0] == 'not': return 1 ^ bit(e[1], values)
    a,b = (bit(t, values) for t in e[1:])
    return a & b if e[0] == 'and' else a | b if e[0] == 'or' else a ^ b


def disjoint(a, b, g, authority):
    conjunction = native(('and', a, b))
    for i, (p, truth) in enumerate(g):
        if truth and p[0] == 'cmp0' and {p[1],p[2]} == {conjunction,Z}:
            return dict(rule='positive-path-disjointness', guard=i, equality=p)
    if a==Z or b==Z:
        return dict(rule='zero-word-disjointness')
    if a==native(('not',b)) or b==native(('not',a)):
        return dict(rule='word-complement-disjointness',left=a,right=b)
    for side,term,other in [(1,a,b),(2,b,a)]:
        if term[0]=='and':
            for i in (1,2):
                try:premise=disjoint(term[i],other,g,authority)
                except ValueError:continue
                return dict(rule='and-factor-disjointness',side=side,factor=i,premise=premise)
    if not coordinate(a) or not coordinate(b):
        raise ValueError('no checked disjointness for these words')
    equations = [(i,p) for i,(p,t) in enumerate(g)
                 if t and p[0]=='cmp0' and coordinate(p[1]) and coordinate(p[2])]
    variables = sorted({t[1] for e in [a,b]+[p for _,p in equations] for t in order(e) if t[0]=='var'})
    if len(variables) > MAX_BITS:
        raise ValueError('coordinate context bit budget')
    pairs = [] if authority is None else [(2*i,2*i+1) for i in range(2)]
    rows = []
    for values in itertools.product((0,1), repeat=len(variables)):
        v = dict(zip(variables, values))
        if any(v.get(z,0) & v.get(o,0) for z,o in pairs):
            continue
        if any(bit(p[1],v) != bit(p[2],v) for _,p in equations):
            continue
        av, bv = bit(a,v), bit(b,v)
        if av & bv:
            raise ValueError('compatible coordinate cell has overlapping bits')
        rows.append(dict(values=values, left=av, right=bv))
    return dict(rule='forced-coordinate-cells', variables=variables,
                contract_pairs=pairs, authority_hash=None if authority is None else digest(authority),
                positive_equalities=[dict(guard=i, equality=p) for i,p in equations],
                surviving_rows=rows, protected_values=[0,1],
                conclusion='no compatible coordinate has left=right=1')


def word_cover(y, guards, authority, parameter):
    """One protected sparse carrier, with independent checked origins."""
    y=native(tree(y));g=facts(guards)
    if set(parameter)=={'boundary_count'}:
        n=native(tree(parameter['boundary_count']))
        if n[0] not in {'countr_zero','countr_one'}:
            raise ValueError('not a lower boundary observation')
        source=('shl',ONE,n)
        arithmetic,proof=NATIVE_ROWS.boundary(source,'carry')
        if native(arithmetic)!=y:
            raise ValueError('arithmetic word is not the proved boundary')
        evidence=dict(origin='existing-run-carry-boundary',boundary_source=source,
                      arithmetic=arithmetic,carry_proof=proof,
                      sparse_lemma='shifting the unit word gives zero or one set bit, including saturated shifts')
    elif set(parameter)=={'unit_shift'}:
        if tree(parameter['unit_shift'])!=y or y[0]!='shl' or y[1]!=ONE:
            raise ValueError('unit shift source mismatch')
        evidence=dict(origin='unit-word-shift',source=y,
                      sparse_lemma='shifting the unit word gives zero or one set bit, including saturated shifts')
    elif set(parameter)=={'predecessor','route'}:
        x = native(tree(parameter['predecessor']))
        predecessor = verify_predecessor(y, x, parameter['route'], g)
        separation = disjoint(y, x, g, authority)
        evidence=dict(origin='scoped-predecessor',predecessor=predecessor,disjointness=separation)
    else:
        raise ValueError('sparse premise parameters')
    # If y!=0, write y=2^k*(2*t+1). Then y&(y-1) contains all set
    # bits except the lowest one. Disjointness forces t=0. y=0 is retained.
    return dict(kind='protected-sparse-word-cover',minimum_width=2,word=y,
        source_hash=digest(y),guards_hash=digest(guards),canonical_guards=g,
        authority_hash=None if authority is None else digest(authority),
        **evidence,
        forced_carrier=dict(labels=['zero','one-set-bit'], word=y,
                           lemma='y & (y-1) = 0 iff y is zero or has exactly one set bit'))


def count_cover(n, guards, authority, parameter):
    n = native(tree(n))
    if n[0] not in COUNTS:
        raise ValueError('no sparse binary cover for this run count')
    y=n[1];cover=word_cover(y,guards,authority,parameter)
    predicate = ('cmp2', y, Z) if n[0]=='countl_one' else ('cmp1', ('and',y,ONE), Z)
    return predicate, dict(cover,kind='scoped-sparse-count-cover',count=n,count_hash=digest(n),
        observation=dict(predicate=predicate, labels=[0,1],
                         cells=[dict(edge_bit=0,count=0),dict(edge_bit=1,count=1)],
                         justification='two consecutive one bits are excluded; width is at least two'))


def substitute(e, old, new):
    if e == old: return new
    if e[0] in LEAVES: return e
    return native((e[0], *(substitute(t,old,new) for t in e[1:])))


def cell_view(e):
    """Existing universal cell identities, with no KnownBits assumptions."""
    if e[0] in LEAVES:return e
    t=native((e[0],*(cell_view(c) for c in e[1:])))
    if t[0] in {'urem','srem'} and t[1]==Z:return Z
    if t[0] in action_kernel.SHIFTS and t[2]==Z:return t[1]
    if t[0] in action_kernel.MASKS and t[2]==Z:return t[1]
    try:out,_=action_kernel.elementary(t)
    except ValueError:return t
    return native(out)


def derive(e, guards, authority, parameter):
    e = tree(e); v = native(e)
    if v[0] not in CONSUMERS:
        raise ValueError('unsupported finite-observation consumer')
    if parameter=={'observed_action':'lowest-set-bit-erasure'}:
        if v[0]!='lshr' or v[2][0]!='countr_one':
            raise ValueError('not the lower-run erasure action')
        payload=v[1];word=v[2][1];g=facts(guards)
        below=disjoint(payload,native(('sub',word,ONE)),g,authority)
        inside=disjoint(payload,native(('not',word)),g,authority)
        # Payload is contained in word & ~(word-1), the lowest set bit.
        # If word is odd that is bit zero, erased by every positive run length.
        # If word is even, its trailing-one count is zero and the action is identity.
        predicate=('cmp0',('and',word,ONE),Z)
        after=native(('select',predicate,payload,Z))
        return after,dict(kind='scoped-payload-action-row',minimum_width=2,source_hash=digest(e),
            view=v,guards_hash=digest(guards),authority_hash=None if authority is None else digest(authority),
            payload_in_word=inside,payload_disjoint_predecessor=below,
            forced_carrier='payload is contained in the lowest set bit of the counted word',
            supplied_cells=[dict(low_bit=0,count=0,effect='identity'),
                            dict(low_bit=1,count='at least one',payload='zero or unit word',effect='zero')],
            after_hash=digest(after))
    if set(parameter)=={'selector'}:
        selector=native(tree(parameter['selector']))
        if selector[0]!='select' or selector not in order(v):
            raise ValueError('selector is not a named source-view subterm')
        cells=[dict(label=truth,after=cell_view(substitute(v,selector,selector[2 if truth else 3])))
               for truth in (False,True)]
        after=native(('select',selector[1],cells[1]['after'],cells[0]['after']))
        return after,dict(kind='scoped-source-choice-row',minimum_width=2,source_hash=digest(e),
            view=v,guards_hash=digest(guards),selector=selector,supplied_cells=cells,
            cell_bridges='native identities and the existing total elementary action rules',
            binding='all occurrences of the same source selector share one branch',after_hash=digest(after))
    if set(parameter)=={'sparse_divisor'}:
        if v[0]!='urem':raise ValueError('sparse remainder consumer')
        cover=word_cover(v[2],guards,authority,parameter['sparse_divisor'])
        after=native(('and',v[1],('sub',v[2],ONE)))
        return after,dict(kind='scoped-sparse-remainder-row',minimum_width=2,source_hash=digest(e),
            view=v,guards_hash=digest(guards),cover=cover,
            supplied_cells=[dict(divisor='zero',remainder='dividend',mask='all ones'),
                            dict(divisor='2^k, 0<=k<w',remainder='lowest k bits of dividend',mask='2^k-1')],
            after_hash=digest(after))
    if set(parameter) != {'count','premises'}:
        raise ValueError('consumer parameters')
    n = native(tree(parameter['count']))
    if n not in order(v):
        raise ValueError('count is not a named source-view subterm')
    predicate, cover = count_cover(n, guards, authority, parameter['premises'])
    cells = [dict(label=k, after=cell_view(substitute(v,n,constant(k)))) for k in (0,1)]
    after = native(('select', predicate, cells[1]['after'], cells[0]['after']))
    return after, dict(kind='scoped-finite-consumer-row', minimum_width=2,
        source_hash=digest(e), view=v, guards_hash=digest(guards), cover=cover,
        supplied_cells=cells, binding='all occurrences of this named count share one label',
        after_hash=digest(after))


def proof_steps(proof):
    if proof['kind'] not in {'scoped-finite-consumer-row','scoped-source-choice-row','scoped-sparse-remainder-row','scoped-payload-action-row'}:
        return PREVIOUS.proof_steps(proof)
    def count(v):
        if isinstance(v,dict):return 1+sum(count(t) for t in v.values())
        if isinstance(v,(list,tuple)):return sum(count(t) for t in v)
        return 0
    return count(proof)


def replay(initial, trace, expected, authority=None):
    root = tree(initial); steps = 0
    if not isinstance(trace,list) or len(trace) > 1000:
        raise ValueError('scoped observation trace budget')
    for t in trace:
        if t['schema'] != SCHEMA:
            nxt = replace(root,t['path'],tree(t['after']))
            root,n = PREVIOUS.replay(root,[t],nxt); steps += n
            continue
        if t['minimum_width'] != 2 or t['before_hash'] != digest(root):
            raise ValueError('scoped observation source binding')
        if t['policy'] not in {'guards','context'}:
            raise ValueError('context policy')
        scope = None if t['policy']=='guards' else authority
        if t['policy']=='context' and scope is None:
            raise ValueError('source contract authority is absent')
        guards = path_guards(root,t['path'])
        after,proof = derive(at(root,t['path']),guards,scope,t['parameter'])
        if digest(guards)!=digest(t['guards']) or digest(proof)!=digest(t['proof']) or after!=tree(t['after']):
            raise ValueError('scoped observation derivation mismatch')
        root = replace(root,t['path'],after); steps += proof_steps(proof)
        if digest(root)!=t['after_hash']:
            raise ValueError('scoped observation result binding')
    if root != tree(expected):
        raise ValueError('scoped observation final expression')
    return root,steps
