# PR34 — конкретное опровержение без полного фактора

Цель roadmap v0.2: отрицательному доказательству не нужен полный носитель положительного
доказательства. Новый маршрут проверяет **конкретное слово на его конечной ширине** по
повторно разобранному источнику и независимо переданной цели. Он не строит residual
carrier, не выводит наблюдения, не запускает source reduction и не требует строк.
Это не новый алгоритм наблюдений или общий слой вынужденности Paper I.

## Проверяемое утверждение

Для допустимого исходника `s`, цели `g`, ширины `w >= 1` и сырого слова `x < 2**w`
checker устанавливает `evaluate(s,x,w) != target(g,x,w)` в неизменённом контракте
`modular-lsb-signed-word-predicates-v1`. Такой свидетель опровергает равенство на
**всех** положительных ширинах. Он не доказывает свойства остальных слов,
достаточности интерфейса, минимальности ширины или переноса ошибки на 32/64 бита.

Доверены restricted frontend, whole-word IR evaluator, target compiler/evaluator,
JSON и новый checker. Producer и checker разделены, но используют одну принятую
семантику. Это не Lean-теорема и не верификация произвольного Java compiler.
Новый checker использует ранее реализованный whole-word путь проверки, не старый
монитор с предварительной загрузкой полного observation пакета.

`qkf-signed-concrete-witness-v1` содержит binding источника, выбранного объявления,
исходного IR, цели, спецификации и контракта. Свидетель хранит `width`, `raw`,
LSB-first `word`, Boolean `source_result`/`target_result`. Избыточные поля независимо
пересчитываются. Слово с плохим префиксом, но правильным **конечным** ответом не
принимается. Пересчёт хешей после подмены цели/источника не заменяет реальное расхождение.

Результат: `refuted`, `claim: concrete_source_target_mismatch`, `target_checked: true`,
`refutes_all_positive_widths: true`, **`source_interface_verified: false`**,
`all_positive_widths: false`, `lean_checked: false`. All-positive флаг означает
отсутствие положительного универсального сертификата. `minimum_width_checked: false`:
replay не ищет меньшие свидетели. Предъявленные слова допускают ширины 1..4096.

`witness_at_native_width` сообщает только совпадение ширины с int/long профилем.
`native_execution_checked` всегда false: checker не запускает Java. Он не создаёт
автоматические native-witnesses из малого слова. Java-исполнение в эксперименте
хранится отдельно и не является предпосылкой сертификата.

## Ограниченный поиск

`producer.probe` перебирает ширины 1..`max_width`, затем raw по возрастанию.
По умолчанию `max_width=8`, `max_evaluations=510` (все слова ширин 1..8); допустимы
0..20 и 0..1000000. Нулевые лимиты поддержаны. Потенциально большое окно всё равно
ограничено числом вычислений. Ширина поиска отделена от ширины предъявленного слова.

API возвращает `(certificate_or_None, result, diagnostics)`; `search` — первые два
значения. Диагностика содержит число проверок, завершённые ширины и следующего
кандидата при cutoff. Она **не сертификат** полноты, отсутствия ошибки или минимальности.
Без свидетеля: `not_refuted` после окна, `budget_exhausted` при candidate cutoff,
`unsupported` при неподдерживаемом источнике. Первые два не означают правильность.
Весь выбранный body разбирается до поиска: dead shifts/calls/division остаются
unsupported. Грамматика и ограничения исходника не расширяются.

## Unified v5 и неизменённый fallback

`research.unified.v5` — отдельная исследовательская точка входа; v4 не меняется.
Для signed-запроса `prove` сначала запускает probe; без опровержения (включая cutoff)
переходит к v4. Unsupported не скрывается сменой профиля, а ошибка checker не
считается «не найдено». Факторные результаты сохраняют **старые схемы, engine и result**.

`tautology_31` с правильной целью пока всё ещё даёт budget в этом fallback: source
reduction PR33 не подключается к target-доказательству неявно. Нужна отдельная
проверяемая интеграция. `x==256 && x>0` против false проходит окно 1..8 без найденной
ошибки, затем v4 получает контрпример ширины 10.

Новое envelope: `qkf-unified-proof-v4`; результат: `qkf-unified-result-v4`.
Unified-v1/v2/v3 проверяются прежними checkers. Новый пакет не может выдаваться
за source-observation или positive proof. `check/explain` concrete-пакета не
импортируют факторные профили; это проверено отдельным свежим процессом.

`prove` возвращает `(result, proof_or_None)`; `prove_with_diagnostics` добавляет
третий объект, не входящий в проверяемый verdict. Budgets v5 имеют явную оболочку:

```json
{"search":{"max_width":8,"max_evaluations":510},"fallback":{"max_states":64}}
```

Signed fallback options проверяет прежний валидатор даже при раннем refuted (без
построения модели). Не-signed виды идут прямо по v4/v3/v1; search options для них
запрещены, а `fallback` сохраняет прежние бюджеты. CLI `search` принимает только
объект поисковых лимитов, без общей оболочки.

```sh
python -m research.unified.v5 prove source.java --target target.json --proof proof.json --diagnostics search.json
python -O -m research.unified.v5 check source.java --target target.json --proof proof.json
python -O -m research.unified.v5 explain source.java --target target.json --proof proof.json
python -m research.unified.v5 search source.java --target target.json --proof witness.json
python -m research.unified.v5 witness source.java --target target.json --raw 0 --width 1 --proof witness.json
```

`witness` проверяет переданный кандидат, не ищет. Новые файлы создаются исключительно;
duplicate/nonfinite JSON отвергается. Exit codes: certified=0; refuted=1;
not_refuted/unsupported/budget_exhausted=2; invalid_certificate=3; input_error=64;
internal_error=70. Установленный `qkf` CLI не меняется.

## Приёмка и конечные проверки

Точные source/target bytes `delayed_31` сверяются с PR32 registration. Первый кандидат
`(w=1,x=0)` — контрпример в модульном расширении, где константа 2147483648L равна нулю.
Ни одно состояние 65-state carrier не строится; тест запрещает residual
`initial/cell/terminal/model`. Синтаксический DAG строится и учитывается в стоимости.
Cap 64 не повышен; сокращение исходника не требуется этому отрицательному маршруту.

42 теста покрывают hostile proofs, final-width sign, прямой 4096-битный witness,
независимую интерпретацию target atoms, 48 seeded expressions, точность fallback,
старые форматы, CLI и normal/optimized replay с запретом producers/SMT/subprocess.
Свежий процесс для concrete proof дополнительно запрещает импорт bridge,
reduction, observations, runtime, signed_targets, inference и unified.v4.

Эксперимент: 12 автоматических случаев + два явно заданных native-width свидетеля;
отдельные controls. Main: 4 certified, 9 refuted, 1 budget. Из 13 proof пакетов восемь
concrete, пять прежнего row-route; disabled-search control сохраняет дополнительный
positive proof. Сохранены все исходники, цели, proofs, результаты, explanations,
диагностики поиска, отдельные v4-control records и timings. Это не новый holdout,
исторические 1/15, 2/33 и результаты Run32 не пересчитываются.

```sh
python -m unittest research.signed_witness.test_witness -v
python -O -m unittest research.signed_witness.test_witness -v
python -m research.signed_witness.experiment reproduction/witness/fresh --java
python -O -m research.signed_witness.experiment reproduction/witness/fresh --replay
```

Fresh `--java`: 3664 входа на 14 constructed случаях. Дополнительные 1764 point-regressions
проверяют один принятый whole-word evaluator: это **не независимая верификация frontend**
и не row-runtime benchmark. Настоящие native outputs сверяются с IR отдельно. На
small-width-only примере native mismatches нет; конечная выборка не доказывает их
всеобщее отсутствие. Прямые 32/64-битные свидетели входят в Java population.

Replay проверяет 14 имеющихся proof пакетов (13 main + 1 control), но не запускает
поиск, старые контрольные построения или Java. No-proof diagnostics остаются данными,
не доказательством отсутствия ошибки. Полная стоимость precheck не скрывается: на
верной программе он добавляет работу. Нет общего ускорения, Paper II visibility
измерения или новой Lean-теоремы. Далее PR35 — проверяемое условное покрытие остаточных
зависимостей; интеграцию reduction/coverage с целью надо выполнять явно.
