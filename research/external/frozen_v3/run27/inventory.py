"""Independent Java declaration inventory and lexical source-span checks.

JavacTask.parse only: candidates are never compiled, attributed or executed.
No QKF module is imported. The lexical pass preserves literals, removes comments
and confirms explicit modifiers and UTF-16-to-UTF-8 source spans.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
TOKEN = re.compile(r'\s+|//[^\r\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|'
                   r"'(?:\\.|[^'\\])*'|[A-Za-z_$][A-Za-z0-9_$]*|[0-9][A-Za-z0-9_]*|"
                   r'>>>=|>>>|>>=|<<=|>>|<<|\.\.\.|==|!=|<=|>=|&&|\|\||\+\+|--|\S')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def tokens(text):
    return [m.group() for m in TOKEN.finditer(text)
            if not m.group().isspace() and not m.group().startswith(('//', '/*'))]


def char_position(text, utf16):
    return len(text.encode('utf-16-le')[:2 * utf16].decode('utf-16-le'))


def normalize(body, variables):
    mapping = {v: 'v' + str(i) for i, v in enumerate(dict.fromkeys(variables))}
    out = []
    for token in tokens(body):
        out.append(mapping.get(token, token) if not out or out[-1] != '.' else token)
    return sha(canonical(out))


def eligible(row, header):
    words = tokens(header)
    return ('public' in words and 'static' in words and row['return_type'] in {'int','long','boolean'}
            and len(row['parameter_types']) == 1 and row['parameter_types'][0] in {'int','long'})


def inventory(data):
    data = Path(data).resolve()
    frame = json.loads((data / 'FRAME.json').read_text())
    files = [(repo, f) for repo in frame['repositories'] for f in repo['frame']]
    with tempfile.TemporaryDirectory(prefix='qkf-declarations-') as tmp:
        subprocess.run(['javac', '--release', '17', '-d', tmp, str(HERE / 'Inventory.java')],
                       check=True, capture_output=True, text=True, timeout=60)
        result = subprocess.run(['java', '-cp', tmp, 'Inventory',
                                 *[str(data / f['source_file']) for _,f in files]],
                                capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise ValueError('incomplete declaration inventory: ' + result.stderr)
    by_path = {str(data / f['source_file']): (repo, f) for repo,f in files}
    rows = []
    for line in result.stdout.splitlines():
        raw = json.loads(line)
        repo, f = by_path[raw['path']]
        text = (data / f['source_file']).read_bytes().decode('utf-8')
        a,b = (char_position(text, raw[k]) for k in ('start_utf16','end_utf16'))
        body = char_position(text, raw['body_start_utf16']) if raw['body_start_utf16'] >= 0 else None
        header = text[a:body if body is not None else b]
        before = text[:a].rstrip()
        doc_start = before.rfind('/**') if before.endswith('*/') and raw['doc'] is not None else -1
        doc_span = [doc_start,len(before)] if doc_start >= 0 else None
        reasons = []
        if not {'public','static'} <= set(tokens(header)): reasons.append('not_explicit_public_static')
        if raw['return_type'] not in {'int','long','boolean'}: reasons.append('return_outside_frame')
        if len(raw['parameter_types'])!=1 or raw['parameter_types'][0] not in {'int','long'}: reasons.append('parameter_outside_frame')
        r = {'repository': repo['repository'], 'revision': repo['revision'], 'source_file': f['source_file'],
             'source_sha256': f['sha256'], 'source_git_blob': f['git_blob'],
             'class': raw['class'], 'package': raw['package'], 'method': raw['name'],
             'return_type': raw['return_type'], 'parameter_types': raw['parameter_types'],
             'parameter_names': raw['parameter_names'], 'modifiers': raw['modifiers'],
             'span': [a,b], 'span_unit':'unicode_codepoint', 'line_span':[text.count('\n',0,a)+1,text.count('\n',0,b)+1],
             'declaration_sha256': sha(text[a:b].encode()), 'body_span': None if body is None else [body,b],
             'body_sha256': None if body is None else sha(text[body:b].encode()),
             'normalized_body_sha256': None if body is None else normalize(text[body:b], raw['parameter_names']+raw['local_names']),
             'doc': raw['doc'], 'doc_span': doc_span,
             'doc_sha256': None if doc_span is None else sha(text[doc_span[0]:doc_span[1]].encode()),
             'eligible': not reasons, 'exclusions': reasons}
        if eligible(raw,header) != r['eligible']: raise ValueError('lexical/AST eligibility mismatch')
        rows.append(r)
    return rows, result.stderr


if __name__ == '__main__':
    import sys
    rows, diagnostics = inventory(sys.argv[1])
    print(json.dumps({'declarations':rows,'diagnostics':diagnostics},sort_keys=True,indent=2))
