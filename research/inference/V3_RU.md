# Observation inference v3: signed terminal integration

Продолжение PR #24. Отдельный signed-профиль теперь подключён к автоматическому
выбору наблюдений и единому исследовательскому CLI. Файлы inference-v1/v2,
предикатных движков, старого unified runner и frozen_v2 не изменены.

## Запуск из корня репозитория

```sh
python -m research.unified.v3 prove \
  research/inference/examples/SignedPower.java \
  --target research/inference/examples/signed-power-target.json \
  --proof signed-proof.json

python -O -m research.unified.v3 check \
  research/inference/examples/SignedPower.java \
  --target research/inference/examples/signed-power-target.json \
  --proof signed-proof.json
```

Файл proof создаётся эксклюзивно: существующий файл не перезаписывается.
Для бюджетов можно передать `--budget budget.json`, например
`{"max_features": 0}` или `{"max_target_states": 1}`.
Исчерпание бюджета возвращает `budget_exhausted`, а не опровержение или сертификат.
Коды выхода: certified = 0, refuted = 1, unsupported / budget_exhausted = 2,
invalid_certificate = 3, input_error = 64, internal_error = 70.

Это research CLI, не новый релиз установленной команды `qkf`.

## Что именно выводится автоматически

Сначала из разрешённого Java-метода получается конечная система остаточных
состояний. Затем строится source-derived библиотека вопросов:

1. Значение исходного terminal Boolean-выражения после продолжения префикса
   строкой из 0, 1 или 2 битов. Биты читаются от младшего к старшему; пустая
   строка означает текущий terminal result. Константные вопросы и вопросы с
   одинаковыми ответами на достижимом carrier удаляются.
2. Прежние вопросы v2 о координатах остаточного состояния: Boolean projections,
   integer cuts/equalities и pairwise relations.

Ни имя метода, ни библиотека происхождения, ни формула target не выбирают вопросы.
Смысл вопросов определяется исходной программой. Target используется позже,
при отдельной проверке произведения фактора с целевой семантикой.

Выбор идёт по конфликтам terminal/output/continuation. После этого удаление
избыточных вопросов повторяется до устойчивого результата. Checker независимо
проверяет каждый конфликт и то, что удаление любого одного оставшегося вопроса
нарушает устойчивость. Это **single-deletion irredundancy**, не глобально
минимальное число предикатов и не доказательство минимальности для всех программ.

Для трёх development-методов достаточно автоматически выбранных вопросов:

- terminal result сейчас;
- terminal result после суффикса `0`;
- terminal result после суффикса `10`.

Получается 4 класса из 6 исходных состояний и 5 состояний target product.
Никакой вручную составленный набор наблюдений для этих методов не передаётся.

## Версии схем и маршруты

Новый signed request имеет schema `qkf-target-v2`, kind
`signed_boolean_predicate`, поля `source.entry`, `source.word_type`, `goal`.
Независимый target positive power-of-two —
`["and", ["positive"], ["popcount_eq", 1]]`.
В этой версии target-v2 вводится только для signed kind; старые запросы не надо
переводить на новую schema.

Сертификат вывода наблюдений: `qkf-observation-inference-v3`.
Внешние envelope/result: `qkf-unified-proof-v2` / `qkf-unified-result-v2`.
Engine ID: `observation-inference-v3`.

Новый runner также принимает старые target-v1 для word result, Boolean predicate
и ascending successor, направляя их через inference-v3 с сохранённой v2 source и
target семантикой. Masked bounds остаются на прежнем unified-v1 маршруте.
Старые unified-v1 proof envelopes replay-ятся старым checker без изменения.
Старые runner и checker продолжают работать отдельно.

## Независимая проверка

Replay заново проверяет связь с исходным текстом, target, IR и библиотекой
наблюдений; trace уточнений; partition; single-deletion irredundancy; затем
полноту и достижимость target product. Он не импортирует producer, subprocess,
Java-инструменты или SMT-пакеты. Есть тест в новом процессе, где запрет импортов
установлен **до** загрузки checker.

Signed obligation проверяется после каждого перехода, а не в начальном
состоянии: гарантируются все положительные ширины в модульной семантике профиля.
Знак определяется последним прочитанным битом, не угадывается заранее.

Отрицательный witness обязан нарушать target **на своей последней ширине**.
Его вывод сравнивается с независимым whole-word IR execution. Отдельно проверяются
несколько native-width кандидатов, включая sign-bit-only word. Найденные native
witnesses — реально проверенные IR-примеры, не предположение о переносе любой
ошибки с малой ширины на 32/64 бита и не исполнение Java при replay.

## Воспроизводимый development experiment

```sh
python -m research.external.frozen_v2.download_sources reproduction/v3-input
python -m research.inference.v3_experiment reproduction/v3-input reproduction/v3-fresh
python -O -m research.inference.v3_experiment reproduction/v3-input reproduction/v3-fresh --replay
```

Для fresh experiment нужен JDK; выбранные точные объявления методов компилируются
с `--release 17`. Replay JDK не требует. Native records и boundary diagnostics при
replay сохраняются как ранее полученные результаты, **не исполняются заново**;
все шесть proof cases и три reference certificates проверяются заново.

| Development case | Source states | Observations | Classes | Product | Verdict |
|---|---:|---:|---:|---:|---|
| Guava LongMath | 6 | 3 | 4 | 5 | certified |
| Guava IntMath | 6 | 3 | 4 | 5 | certified |
| Commons ArithmeticUtils | 6 | 3 | 4 | 5 | certified |

Кроме них есть 3 constructed negative controls, 1 unsupported shift и
1 exhausted-budget control. Ожидаемые counts:
`{"certified":3,"refuted":3,"unsupported":1,"budget_exhausted":1}`.

Fresh native comparison на внешних методах: **209 389 inputs, 0 mismatches**.
Для трёх отрицательных controls по 259 inputs; каждый даёт настоящее расхождение
с target, при нулевых расхождениях между Java и whole-word source IR.

Reference certificates PR #24 создаются и replay-ятся отдельным старым signed
checker. На этих трёх методах числа классов совпадают. Это проверка сохранения
компактности, а не общее обещание оптимальности v3.

## Границы результата и следующий этап

Это post-holdout development reuse, не новый внешний holdout. Исторический
frozen_v2 результат **1/15 остаётся неизменным**, а 42 зафиксированных файла его
движка проверяются по Git blob identities.

Профиль source и его остаточная семантика по-прежнему заранее реализованы;
lookahead ограничен двумя битами, carrier — 512 состояниями, библиотека — 256
вопросами, target product — 8192 состояниями. Сохраняются ограничения PR #24:
нет произвольного Java, shifts/calls/branches, общего signed word-to-word order
или нового Lean theorem. Bounded continuation queries — расширение проверяемой
библиотеки, не автоматическое изобретение произвольного observation language.

Следующий отдельный этап: зафиксировать точный v3 engine и правила отбора **до**
запуска нового внешнего holdout на методах, не использованных здесь для разработки.
Не превращать прежние три gap-метода в якобы независимый evaluation set.
