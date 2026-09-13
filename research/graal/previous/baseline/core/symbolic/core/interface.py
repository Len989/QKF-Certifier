"""Source-derived visibility layers for primitive count rows.

No claim-name rules, candidate model, search call, or supplied extra axiom.
The compiler uses only the already registered base-word count observations.
"""
def observation_plan(count_names, level):
    if type(level) is not int or level not in (0, 1, 2):
        raise ValueError('interface level')
    if not level:
        return []
    by_word = {}
    for (kind, word), variable in count_names.items():
        by_word.setdefault(word, {})[kind] = variable
    result = {}
    def insert(word, index, reason):
        key = (word, tuple(sorted((k, v) for k, v in index.items() if v)))
        result.setdefault(key, []).append(reason)
    for word, kinds in sorted(by_word.items()):
        if {'clz', 'clo'} <= set(kinds):
            insert(word, {'w': 1, '#': -1}, 'shared-leading-end')
        if {'ctz', 'cto'} <= set(kinds):
            insert(word, {}, 'shared-trailing-end')
        if level == 2 and len(kinds) >= 2:
            for kind, variable in sorted(kinds.items()):
                if kind.startswith('cl'):
                    insert(word, {'w': 1, variable: -1}, kind + '-run-start')
                    insert(word, {'w': 1, variable: -1, '#': -1}, kind + '-stop-start')
                else:
                    insert(word, {}, kind + '-run-start')
                    insert(word, {variable: 1}, kind + '-stop-start')
    return [dict(word=word, index=list(index), reasons=reasons)
            for (word, index), reasons in sorted(result.items())]
