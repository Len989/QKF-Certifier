# Observation Inference v2

V2 развивает принятый в PR #21 CEGAR-слой, не меняя его сертификаты.

## Что добавлено

### Более богатая source-derived библиотека

Для достижимых residual coordinates автоматически строятся:

- Boolean projections;
- integer cuts `slot <= k`;
- integer equalities `slot == k`;
- pairwise relations `slot_i <= slot_j`;
- pairwise equalities `slot_i == slot_j`.

Вопрос включается только если он не константен на достижимом residual carrier.
Имена методов не выбирают эти наблюдения.

V2 предпочитает broad order cuts перед singleton equalities, но окончательный
набор всё равно определяется conflict refinement + deletion pruning.

### Прямой successor target

PR #21 для Graal останавливался на source-interface и отдельно replay-ил старый
successor package. V2 закрывает этот разрыв.

Новый target checker использует тот же generic `target_rules`:

- independent legal alternative;
- subset obligations;
- unsigned order;
- wrap-to-minimum;
- least greater legal result.

Inferred quotient заменяет только source-factor runner. Target monitor,
typed target specification и concrete whole-integer checker остаются прежними.

Для отрицательного witness replay дополнительно требует:

1. нарушение generic target formula;
2. то же нарушение через independent whole-integer target interpretation;
3. совпадение output с прямым integer execution extracted ascending region.

## Regression population

Свежий experiment проверяет:

- pinned OpenJDK `Long.lowestOneBit`;
- pinned Lucene `BitUtil.isZeroOrPowerOfTwo`;
- retained Graal original successor — direct certified;
- retained Graal irrelevant-register variant — direct certified, лишние registers не выбираются;
- retained Graal `clear_repair` — direct refuted;
- constructed `x + 3` control — richer order cut должен реально быть выбран.

Старые v1 certificates используют отдельную schema
`qkf-observation-inference-v1` и старый checker; v2 имеет
`qkf-observation-inference-v2`.

## Что НЕ утверждается

V2 всё ещё не синтезирует произвольный observation language. Candidate families
заранее определены, хотя конкретные координаты, cut values и pairwise relations
выводятся из source residual semantics.

Не заявляются:

- arbitrary Java;
- автоматическое изобретение source residual semantics;
- глобальная минимальность относительно всех predicates;
- новый frozen external benchmark;
- новый Lean theorem;
- support для descending inference target в этом PR.

Следующий этап может использовать unresolved conflicts для генерации новых
семейств наблюдений и затем перейти к frozen holdout benchmark.
