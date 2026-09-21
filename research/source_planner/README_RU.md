# PR43 — вопросы к source из независимой цели

Экспериментальный planner получает source, независимую consumer-цель, guard `G`,
width contract и бюджет. Он сам выбирает один следующий native-вопрос,
добавляет доказанный факт в `E`, проверяет достаточность и останавливается,
как только consumer proof закрыт. Пользователь не задаёт observation list.
Семантика source, guards и native-правила сохранены из PR41.

Это ограниченный механизм выбора вопросов, а не общий синтез отношений.
PR42 разрешил forcing только в отдельном physical-phase профиле и не показал
его полезности против прямого контроля. Поэтому Paper I здесь выключен.
Общие проверенные леммы для разных consumer-целей относятся к PR44;
каждый запрос PR43 начинает с нового состояния.

## Контракт и алгоритм

`request` имеет прежнюю схему `qkf-guarded-source-query-v1`: выбранный метод,
signed Boolean target, guards и `all_positive` либо фиксированную ширину.
Сначала допускается и компилируется весь выбранный source. Даже неподдержанный
оператор в неиспользуемом присваивании не обходится ранним выходом или пустым `G`.

1. Из source IR и отдельного target строятся точные корни запроса.
   Начальный `E` пуст. Проверяется текущая consumer-обязанность.
2. Если endpoints ещё не активны, сохраняется синтаксическое свидетельство
   недостаточного горизонта. Для активного запроса проверяется ground proof
   или полная конечная разделяющая модель данного `E` и горизонта.
3. При `not_visible` горизонт растёт до полного конечного `H`, если позволяет
   бюджет. Нехватка горизонта не объявляется нехваткой source-фактов.
4. При `not_entailed` на полном `H` syntax-only policy выбирает один вопрос.
   Native-правило исполняется только после выбора; неудача тоже оплачивается
   и сохраняется. Уже испробованные вопросы повторно не исполняются.
5. Новый факт немедленно инвалидирует текущую разделяющую модель.
   После расширения `E` строится и независимо проверяется новый checkpoint.
   Доказательство цели завершает native-поиск без следующих вопросов.

Положительный proof может быть достаточен ниже полного `H`: использованные
активные аксиомы уже независимо проверены как факты исходного source.
Отрицательный ответ ниже `H` остаётся только `not_visible`.

## Зарегистрированный язык вопросов

Ни имя fixture, ни ожидаемый исход не входят в planner. Все схемы native-фактов
уже были в PR41; PR43 меняет выбор конкретного вопроса и порядок проверки.

| Вопрос | Откуда берутся аргументы | Что проверяется |
|---|---|---|
| `input-bridge` | Source atom со знаком/нулём raw input; сначала совпадающий с consumer | Точное соответствие source atom и target predicate |
| `guard-truth` | Текущий pure-target term | Его постоянное значение на проверенном `G` |
| `eq-mask` | Реальная source-клауза `not(atomA) or atomB` | Условия импликации равенства константе в mask predicate |
| `low-bit` | Достижимый IR node `word & 1` | Полные parity rows всех зависимостей для обоих input bits |
| `guard-zero` | Достижимый raw input | Guard действительно ограничивает input нулём |
| `local` | Текущий term и его IR dependencies | Фиксированная локальная word/Boolean identity или target definition |

После consumer-shaped мостов и target-вопросов policy идёт по достаточным
congruence/Boolean pullbacks от текущей обязанности. Равенство аргументов
одинакового оператора достаточно для равенства результатов; обратное не
предполагается. Проверенная разделяющая модель лишь ставит различающиеся
аргументы раньше в очереди. Она не доказывает native-факт и не подставляет
желаемую истину в source. Boolean pullback тоже задаёт достаточный подзапрос,
который ещё нужно обосновать.

Существующие доказанные замены направляют обход. При схлопывании Boolean-
контекста сохраняется связь оставшейся клаузы с исходными atom/word nodes.
В `work` записаны происхождение каждого вопроса, исходные и нормализованные
term IDs, полный producer DAG, версия `E` и ID проверенного separator.
Сертификат экспортирует только точный `Sub(E) ∪ Sub(O)` и нужные native proofs.

## Остановка и остаточная обязанность

| Результат | Значение и переносимое свидетельство |
|---|---|
| `certified / consumer_closed` | Проверенные native-факты и ground equality proof для независимой цели |
| `verified_empty_domain` | Отдельно проверенная пустота `G`, после допуска source |
| `unresolved / insufficient_horizon` | Неактивные endpoints либо проверенное `not_visible`; consumer остаётся открыт |
| `unresolved / not_entailed_from_current_E` | Проверенная модель полного конечного `E`; это не контрпример source |
| `refuted / concrete_violation` | Конкретное слово и ширина, проверенные против source, target и `G` |
| `certified / explicit_covered_fallback` | Явно разрешённый старый guarded coverage proof |
| `unsupported` | Source или контракт не прошёл допуск; частичного proof нет |
| `budget_exhausted` | Исчерпан ресурс; частичный финальный proof не выпускается |

В диагностике отдельно указаны три слоя: неследование из текущего `E`,
потребность в дополнительных source-фактах и исчерпание зарегистрированной
candidate policy. Последнее воспроизводимо, но не является доказательством
глобальной невозможности или минимальности набора вопросов.

После исчерпания языка выполняется ограниченный поиск конкретного guarded
контрпримера. Отсутствие найденного слова не становится доказательством.
Только с `--fallback` допускается retained covered-source construction.
Его собственная подготовка и все предшествующие неудачные попытки остаются
в ledger. `G` и width сохраняются при каждом переходе и replay.

Каждый прежний отрицательный checkpoint остаётся доказательством только своего
`E` и горизонта. После добавления факта он не используется для нового выбора.
Если новый checkpoint не завершился из-за бюджета, старый separator нельзя
выдать за остаток расширенного `E`; финальный certificate отсутствует.

## Контроли и полная цена

`planner` использует Paper II query-subterm backend. `ordinary` получает
ту же adaptive policy и native-попытки, но применяет обычный unfiltered CC
на полном разрешённом горизонте. Если cap не допускает полный CC, он явно
использует общий bounded Paper II backend только для диагностики горизонта.
`eager` сохраняет прежний PR41 collector, затем использует тот же consumer
checker, witness и opt-in fallback. Во всех 39 зарегистрированных случаях
списки native-попыток `planner` и `ordinary` совпали дословно.

У planner меньше native-вопросов, но больше промежуточных proofs, моделей,
повторных source parses и проверок фактов. Всё это входит в actual-call ledger
и instrumented elapsed time, включая fallback и встроенные проверки.
Сериализация диагностики, CLI I/O и внешний replay вынесены за этот счётчик.
`research_calls` — входы в Python-функции, не CPU instructions и не независимая
оценка сложности. `work` и его хеш не аттестуют произвольное исполнение Python.

В финальном локальном прогоне 180 native rule executions у planner против
761 у eager, но 114 checkpoints против 34 и около 4,74 s против 1,67 s
полного инструментированного времени. Полезность выбора вопросов подтверждена;
ускорение всего пути не установлено. Различия с eager не приписываются
автоматически теоремам I/II. Полные числа и ограничения — в `VALIDATION_RU.md`.

## Использование и воспроизведение

Python 3.10 или 3.12, без новых зависимостей. Пример source:

```java
class Demo {
    public static boolean f(long x) { return ((x+x) & 1) == 0; }
}
```

Пример независимого request (цель — тождественная истина):

```json
{
  "schema": "qkf-guarded-source-query-v1",
  "width": {"kind": "all_positive"},
  "guards": [],
  "target": {
    "schema": "qkf-target-v2",
    "source": {"entry": {"class": "Demo", "method": "f"}, "word_type": "long"},
    "kind": "signed_boolean_predicate",
    "goal": ["or", ["negative"], ["nonnegative"]]
  }
}
```

```bash
python -m research.source_planner prove example.java --request request.json --proof proof.json
python -O -m research.source_planner check example.java --request request.json --proof proof.json
```

Опции `--limits limits.json`, `--route ordinary|eager`, `--fallback` явные.
Limits задают `max_work`, `max_fact_attempts`, `max_rounds`, `max_horizon`,
`max_witness_width`, `max_witness_evaluations`, `max_source_states`,
`max_product_states`; defaults и верхние границы видны в `context.py`.
`max_rounds` считает все checkpoint attempts, включая рост горизонта.
Неизвестные поля и Boolean вместо integer отвергаются.

Файл proof создаётся без перезаписи. Коды: 0 — certified/empty;
1 — unresolved/refuted/unsupported/budget; 2 — неверный ввод, proof или путь.
Это отдельная research CLI; installed `qkf` не меняется.

```bash
python -m research.regression.run
python -O -m research.regression.run
python -m research.source_planner.preserve
python -m research.source_planner.experiment reproduction/source_planner/fresh
python -m research.source_planner.replay reproduction/source_planner/fresh
python -O -m research.source_planner.replay reproduction/source_planner/fresh
```

Каталог `fresh` должен отсутствовать. Comparison сохраняет все outcomes,
расходы, failures, manifest и промежуточные checkpoints. Fresh replay ставит
запрет planner, native discovery, CC search, producers и SMT imports **до**
загрузки checker. Проверяются все финальные proofs и исторические модели
на их собственном `E`. Бюджет и исчерпание search policy не переисполняются
как часть семантической проверки.
