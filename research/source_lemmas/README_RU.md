# PR44 — проверенные леммы для серии независимых целей

PR43 выбирает source-факты для одной цели. PR44 добавляет один проверенный
контекст для серии целей, раздельные `E` и `E+` и переносимое доказательство
общего вывода. Повторная цель получает проверенную общую часть и собственную
остаточную обязанность. Ни verdict receipt, ни один хеш не заменяют proof.

Это исследовательский batch API. По умолчанию работает `no_lemmas`: общий
source/native-контекст и обычный кеш сохраняются, межцелевые выведенные леммы
включаются явно через `--route reuse` или `direct_cache`. Решение A2 и полная
цена серий 1/4/16 опубликованы в `VALIDATION_RU.md` и генерируемом `A2.json`.

## Область и независимые цели

Batch содержит от 1 до 64 запросов прежнего вида `qkf-guarded-source-query-v1`.
У них один source, выбранная функция/word type, profile, точные guards и width.
Сами consumer expressions задаются отдельно от source и planner. Смешивание
областей отвергается; автоматического ослабления `G` или переноса на другую
ширину здесь нет.

Весь выбранный source допускается до ранней остановки и проверки пустоты `G`.
Для native target algebra используется постоянный capped-popcount domain с
cap 4 и прежними predicates 0..3. Поэтому область фактов не зависит от того,
какая цель в batch оказалась первой. Native-правила и syntax-only выбор
вопросов сохранены из PR41/43; нового семантического oracle нет.

Scope включает source/IR identities, selection, semantic profile, width,
guards, полное описание native algebra, область положительных слов и силу
гарантии `conditional_closed_ground_equality`. При загрузке source заново
компилируется, native-факты заново проверяются. Структуры сравниваются как
строгие JSON snapshots: `true` не становится integer `1`.

## E, E+ и доказательство потребителя

| Слой | Содержимое | Основание проверки |
|---|---|---|
| `E` | Native-факт, его закрытые semantic terms и native evidence | PR41 rule replay на фактическом IR, `G` и width |
| `E+` | Закрытое равенство, предыдущая презентация, зависимости и ground proof | Положительный checked proof из native prefix и строго более ранних лемм |
| Consumer | Точная независимо заданная цель и остаточное равенство | Проверенная общая лемма плюс свой ground proof |
| Exact cache | Ссылка на прежнюю проверенную source-гарантию | Строго тот же запрос и раньше проверенный certified/refuted/empty результат |

Лемма не является универсальной схемой. Нет подстановки новых переменных,
нового source или guard по совпадению формы терма. IDs обозначают содержимое;
checker всё равно проверяет математические основания. `native_count` и
`prior_lemmas` задают предшествующую презентацию, а ссылки образуют DAG.
Self/forward dependencies, искусственная аксиома и подмена вывода отвергаются.

Policy сохраняет только первый подходящий нетривиальный source-to-consumer
вывод: он должен реально использовать несколько premises и congruence,
не совпадать с уже купленным native-фактом. Отказы eligibility записываются.
Положительная проверка выдаёт process-local `CheckedGoal`; promotion принимает
только этот объект из точной прежней презентации, поэтому не повторяет поиск
или проверку уже принятого вывода. При холодной загрузке raw lemma проверяется
заново, без доверия к process-local объекту.

Пусть сохранена лемма `source = p`, а новая цель — `source = c`. Checker
проверяет точный левый endpoint и заменяет новую поисковую обязанность на
`p = c`. Поле `via_lemma` делает эту композицию явной. Снять ссылку и выдать
короткий residual proof за доказательство исходной программы нельзя.
Оба backend используют один и тот же приём; прямой контроль не лишён лемм.

Native premises первоначального вывода можно убрать из активного residual
basis. Если они нужны самой новой цели, policy восстанавливает их перед
окончательной диагностикой. Например, простая identity `p AND true = p`
может понадобиться повторно. Это не повторный поиск общего source-вывода:
следующая цель всё ещё обязана использовать `via_lemma`. Все дополнительные
checkpoints и восстановление basis оплачиваются.

## Проверенный контекст и транспорт

Из PR36 непосредственно используются строгие `freeze/thaw/source_text`
границы и тот же принцип неизменяемого process-local контекста, выдаваемого
после проверки оснований. `CheckedPresentation` адаптирует этот lifecycle
к native ground-профилю. Старый covered-source `CheckedContext` не принимает
новые данные как якобы проверенную полную source-модель; его код не изменён.

Сериализация прямо использует PR37 `signed_compact.dag`: строго более ранние
ссылки, проверка достижимости, типов, depth и expanded-size до выделения
декодированных контейнеров. Это точное структурное sharing JSON, не отдельная
теорема о семантическом равенстве. Packet сам содержит все `E`, `E+` и
обязательства целей. Whole-source quotient, legacy coverage и все pair
separators ради упаковки не строятся.

Холодный `load` проверяет общие основания один раз, затем все consumer proofs.
Первый consumer может ссылаться прямо на сохранённую лемму, поэтому её proof
не проверяется второй раз ради той же цели. Проверенный контекст возвращает
копии данных, не восстанавливается из receipt и не допускает pickle.
Как и в PR36, это обычная Python API boundary, не защита от reflection или
monkeypatching внутри самого доверенного процесса.

## Неуспех, модели и бюджеты

Разделяющая модель относится к точной конечной residual obligation, её basis
и горизонту. Она не опровергает source. Любое расширение активной презентации
инвалидирует старую модель для следующего решения. Исторические checkpoints
сохраняют собственные premises и независимо перепроверяются.

`insufficient_horizon`, неследование из текущего finite basis и исчерпание
ограниченной candidate policy разделены. Последнее — воспроизводимая
диагностика, не доказательство глобальной невозможности. Конкретный witness
перепроверяет исходный IR, target, `G` и width. Пустой `G` маркируется явно.

Exact cache хранит только устойчивые source-результаты: certified, конкретный
refuted или verified empty domain. `unresolved` с lower model туда не попадает,
даже при повторе текста запроса. Это исключает перенос отрицательной модели
после роста `E/E+`; правило одинаково для всех сравнительных маршрутов.

При budget/unsupported batch не выпускает частичный финальный packet.
Ранее завершённые checkpoints и уже проверенные основания остаются в `work`
только как scoped diagnostics. Full-source builders запрещены runtime guard.
Covered fallback в этом PR не включён; он остаётся явной возможностью PR43.

## Контроли и измерения

- `reuse`: общий native-контекст, допустимая проверенная лемма и Paper II backend;
- `direct_cache`: те же native-вопросы, лемма, residual composition и ordinary
  exact cache, обычный unfiltered CC; bounded horizon diagnostic общий;
- `no_lemmas`: тот же shared native-контекст, failed-question memo и exact cache,
  Paper II backend без добавления `E+`.

Общий source-checking, native cache, derived lemma и backend — разные причины
экономии. Удача, доступная прямому контролю с той же леммой, не называется
исключительным эффектом II. Paper I в этом signed-профиле остаётся выключен
согласно A1; physical-phase механизм PR42 не переносится сюда автоматически.

Ledger включает source/target admission, неудачные вопросы, все поиски и
checkpoints, eligibility/promotion, упаковку и встроенный холодный replay.
Внешний replay измеряется отдельно. `research_calls` — входы в Python-функции,
не CPU instructions. Диагностический JSON I/O не включён в route elapsed.
Время инструментировано; module caches сохраняются между случаями.
Ни timing, ни хеш runtime trace не являются семантическим сертификатом.

## Использование

```python
from research.source_lemmas.producer import prove
from research.source_lemmas.checker import check

source = '''class Demo { static boolean f(long x) {
  return (x<0) && (((x+x)&1)==0);
} }'''
goals = [["negative"], ["not", ["nonnegative"]],
         ["and", ["negative"], ["popcount_le", 1]]]
requests = [{
    "schema": "qkf-guarded-source-query-v1",
    "guards": [["popcount_le", 1]], "width": {"kind": "all_positive"},
    "target": {"schema": "qkf-target-v2", "kind": "signed_boolean_predicate",
        "source": {"entry": {"class": "Demo", "method": "f"}, "word_type": "long"},
        "goal": goal}
} for goal in goals]
batch = {"schema": "qkf-source-lemma-batch-v1", "requests": requests}
packet, result, work = prove(source, batch, route="reuse")
if packet is not None:
    assert check(source, batch, packet) == result["goals"]
```

```bash
python -m research.source_lemmas prove source.java --request batch.json --proof packet.json --route reuse
python -O -m research.source_lemmas check source.java --request batch.json --proof packet.json
```

Без `--route` выбирается `no_lemmas`. `--limits` принимает прежние PR43 budgets
и `max_lemmas`; нулевой storage limit отключает promotion, сохраняя возможность
доказать цель. Output-файл не перезаписывается. Exit codes: 0 — все цели
certified/empty; 1 — refuted/unresolved/unsupported/budget; 2 — неверный
ввод или proof. Installed `qkf` не переключается.

```bash
python -m research.regression.run
python -O -m research.regression.run
python -m research.source_lemmas.preserve
python -m research.source_lemmas.experiment reproduction/source_lemmas/fresh
python -m research.source_lemmas.replay reproduction/source_lemmas/fresh
python -O -m research.source_lemmas.replay reproduction/source_lemmas/fresh
```

`fresh` должен отсутствовать. Replay устанавливает запрет producers, planner,
native discovery и SMT до импорта checker; проверяет полные packets и все
исторические residual proofs. Поиск, бюджет и A2 timing заново не исполняются
как часть математического replay. Новых Lean-теорем нет; единый продуктовый
контракт применимой сводки остаётся задачей PR45.
