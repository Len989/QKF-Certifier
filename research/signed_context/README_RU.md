# PR36: повторно используемый проверенный контекст

Задача roadmap v0.2: одна полная проверка **источника → reduction → guarded coverage
→ наблюдений → атомных строк** обслуживает несколько независимых целей, объяснений
и исполнений. Строитель наблюдений и математические правила PR35 не меняются.

## Две разные единицы работы

`load(source, selection, observations)` проверяет весь переданный source-bound пакет
через неизменённый loader PR35 **один раз**. После этого объект `CheckedContext`
держит неизменяемый Runner, точный source request, проверенный исходный IR и полную
зависимость source proof как неизменяемые JSON-строки. Цель не участвует в загрузке.

`context.prove(target)`, `check(target, proof)` и `explain(target, proof)` строят или
проверяют только новое целевое обязательство. Парсер, полный или covered carrier,
source-reduction replay и generic atomic checker повторно не вызываются. Положительный
путь использует неизменённый PR31 `check_product` и действия строк PR30. Отрицательный
путь повторяет все проверки PR31 на **уже проверенном исходном IR**, в том числе
совпадение результата строк и whole-word evaluation и дополнительные native-width
IR-кандидаты. Это не запуск Java и не автоматический подъём малого свидетеля на 64 бита.

`build(source, selection)` сначала запускает прежний PR35 producer, включая его
внутренние проверки, затем `load`. Поэтому тезис «одна проверка» относится к загрузке
предъявленного пакета и последующей сессии, **не к нулевой стоимости поиска или всем
внутренним проверкам старого producer**. Discovery учитывается отдельно.

## Пример API

```python
from research.signed_bridge.model import request
from research.signed_context.session import build, load

source = "class Demo { public static boolean f(long x) { return x > 0; } }"
selection = request({"class": "Demo", "method": "f"}, "long")
context, outcome = build(source, selection)
if context is None:
    raise RuntimeError(outcome)  # unsupported или исчерпание бюджета, не доказательство

def target(goal):
    return {"schema": "qkf-target-v2", "kind": "signed_boolean_predicate",
            "source": {"entry": {"class": "Demo", "method": "f"}, "word_type": "long"},
            "goal": goal}

positive = target(["positive"])
wrong = target(["negative"])
for specification in (positive, wrong):
    result, proof = context.prove(specification)
    if proof is not None:
        assert context.check(specification, proof) == result
        explanation = context.explain(specification, proof)

assert context.value(1, 64)
source_proof = context.export_source_proof()  # отсоединённая копия для передачи
# В другом процессе нужно вновь вызвать load с исходником, а не доверять receipt.
```

В примере `assert` — только пользовательские демонстрационные проверки. Реальные
checkers не используют `assert` для обязательств и работают под `python -O`.

`prove_many` принимает 1–64 отдельно заданные цели одного метода/типа. Все selections
проверяются до начала целевой работы. В пределах загруженного контекста доступны
только `max_target_states` (1–8192) и `max_witness_bits` (0–4096); остальные лимиты
относятся к построению источника и остаются лимитами PR35. Исчерпание одного
целевого бюджета не повреждает контекст и не выдаёт частичного сертификата.

## Форматы и переносимость

Нового целевого proof format нет: каждый пакет остаётся
`qkf-unified-proof-v5` / `qkf-signed-guarded-target-v1`, с engine
`signed-guarded-observation-target-v1` и **точно прежними полями результата**.
И положительные, и отрицательные пакеты принимаются неизменённым `unified.v6.check`.
`unified.v7.check` для этого формата создаёт новый проверенный контекст и проверяет цель.

Тёплый `context.check` требует точного совпадения вложенного source proof с проверенным
снимком, а не только предъявленного хеша/receipt. Затем заново проверяет source/target
binding, весь target product или конкретный witness и сохранённый результат. Другая
корректная структура интерфейса того же источника требует отдельной загрузки: это
кеш проверенной **точной зависимости**, не доказанная семантическая эквивалентность
произвольных кеш-ключей. Стоимость сравнения/сериализации пакета не скрывается.

`describe()` имеет `kind: inspection-only-not-a-certificate` и `target_checked: false`.
Обычный пользователь не может создать проверенный контекст из Runner или receipt;
сериализация контекста через pickle запрещена. Все наружные словари — отсоединённые
копии. Изменения caller-owned source request, certificate, result и explanation не
меняют загруженное действие. Враждебная Python-reflection, monkeypatching и конкурентное
изменение аргументов во время snapshot не входят в гарантию обычного API.

В отличие от самого Runner, **контекст сохраняет полное доказательство и исходный IR
как неизменяемые данные**. Это нужно для переноса и отрицательных проверок. Он не
является компактным DAG формата будущего PR37 и не обещает уменьшения общего размера
самодостаточных сертификатов. В памяти не остаётся изменяемый Model, используемый
вместо действия строк.

## Исследовательский CLI

```sh
python -m research.unified.v7 prove source.java --target target.json --proof proof.json
python -O -m research.unified.v7 check source.java --target target.json --proof proof.json
python -O -m research.unified.v7 explain source.java --target target.json --proof proof.json
python -m research.unified.v7 batch source.java --target targets.json --proof NEW_DIRECTORY
```

`targets.json` для batch — массив независимых `qkf-target-v2` запросов. Можно подать
`--observations source-proof.json`, чтобы загрузить существующий пакет без нового
поиска. `--budget` при batch/prove использует прежние полные лимиты PR35; при наличии
готового пакета source-discovery лимиты валидируются, но не ограничивают повторную
проверку уже предъявленного сертификата. Целевые лимиты применяются всегда.

Каталог batch содержит отдельные target/result/proof файлы. SUMMARY — диагностический
индекс, не агрегированный сертификат; незавершённые случаи не имеют proof файла.
Повторное использование пути запрещено. Ошибка файловой системы во время записи
может оставить явно неполный каталог; атомарная транзакция каталога не заявляется.

V7 не запускает bounded precheck V5. Старые форматы и не-signed запросы делегируются
старым маршрутам с прежними именами и результатами. При signed-проверке не загружаются
Graal/KnownBits/inference profiles, `unified.run` и `observations.run_package`.
Некоторые необходимые прежние checker-модули импортируются loader-ом PR35; отсутствие
всех модулей предыдущих PR не заявляется. Установленный публичный `qkf` CLI не меняется.

## Математическая и доверенная граница

Проверка исходного интерфейса устанавливает одно и то же остаточное действие для
любого продолжения в контракте PR35. Для каждой независимо заданной цели отдельно
проверяется полное произведение или конкретный конечный witness. Общая посылка не
доказывается заново в каждом употреблении, но **не исчезает из переносимого proof**.
Это организация переиспользования установленного интерфейса, не новый алгоритм
вывода наблюдений или новая общая теорема Papers I/II. Native labels, guards, область
применимости и source binding не заменяются кешированным Boolean.

Trusted: ограниченный frontend, исходная/целевая семантика, coverage/row checkers,
новый snapshot/session/witness adapter и Python runtime. `lean_checked` остаётся false.
Общий исходный лимит — 64 covered descriptions; incomplete coverage не принимается.
Другой источник, тип, контракт или цель не могут быть незаметно подставлены. Старые
1/15, 2/33 и эксперимент PR32 не изменены.

## Воспроизведение и измерение

```sh
python -m research.regression.run --group new
python -O -m research.regression.run --group new
python -m research.regression.run --group prior
python -O -m research.regression.run --group prior
python -m research.signed_context.experiment reproduction/context/fresh --java
python -O -m research.signed_context.replay reproduction/context/fresh
```

Восемь прежних constructed-источников, по четыре целевых запроса на каждый. Некоторые
цели логически эквивалентны; это тест переиспользования, а не 32 новых программы или
семейства. Полные старые пакеты проверяются неизменённым V6. Отдельный счётчик
подтверждает один parse / covered rebuild / atomic check при load и отсутствие их
повторов после четырёх целей и объяснений. Счётчик не входит в timing-измерения.

Сохраняются source discovery, additional-target discovery, три парных измерения
четырёх прежних проверок против одной загрузки и четырёх новых проверок, а также три
cold-process check для каждого маршрута. Время холодного процесса включает импорт
и запуск; это не подменяется временем API. Ускорение малой части не выдаётся за
общий результат. Финальная зависимость и размеры proof не сжимаются.

Replay проверяет все сохранённые доказательства, объяснения и native outputs,
но не запускает поиск, Java, старый поисковый контроль или timing-эксперименты.
Manifest audit — проверка байтов, не семантическая проверка. Численные времена —
описательные измерения на выбранных примерах, не SMT-рейтинг или новая внешняя оценка.
