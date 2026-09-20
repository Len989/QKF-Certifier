# PR31: независимая цель над исполнением атомных строк

Этот этап соединяет PR28–30: source-bound модель, замыкание наблюдений и
проверенный row-runtime теперь служат доказательству отдельно заданной цели.
Это исследовательский маршрут, не изменение установленной команды `qkf`.

## Запуск

Из полного репозитория на Python 3.10+:

```sh
python -m research.unified.v4 prove research/inference/examples/SignedPower.java \
  --target research/inference/examples/signed-power-target.json --proof target-proof.json
python -O -m research.unified.v4 check research/inference/examples/SignedPower.java \
  --target research/inference/examples/signed-power-target.json --proof target-proof.json
python -O -m research.unified.v4 explain research/inference/examples/SignedPower.java \
  --target research/inference/examples/signed-power-target.json --proof target-proof.json
```

`prove` строит и независимо проверяет весь пакет. `check` не импортирует
генераторы; `explain` сначала проверяет цель и затем объясняет интерфейс.
Существующий файл доказательства не перезаписывается. Источник и цель всегда
передаются проверяющему извне, а не извлекаются из предложенного сертификата.

В API `research.unified.v4.prove(source, target, budgets=...)` возвращает
`(result, envelope)`; для unresolved-результата envelope равен None.
`check(source, target, envelope)` возвращает заново вычисленный результат.

## Язык цели и совместимость

Без расширения используется `qkf-target-v2`, kind `signed_boolean_predicate`.
Сохраняются атомы positive/nonnegative/negative/nonpositive, popcount_eq/le с
порогами 0..3 и Boolean not/and/or/xor. Семантика — прежний контракт
`modular-lsb-signed-word-predicates-v1`. Независимая спецификация не угадывается
по имени метода и не ослабляется после неудачи.

Новый движок: `signed-observation-row-target-v1`.
Внутренний сертификат: `qkf-signed-row-target-v1`.
Новый unified envelope/result: `qkf-unified-proof-v3` / `qkf-unified-result-v3`.
Пакеты source-модели и наблюдений PR28/29 вложены без смены их схем.

Старые unified-v1/v2 envelopes проверяются исходными checkers, с исходными
метками движков и результатами. Новое построение для НЕ-signed kinds
делегируется неизменённому v3/v1; эти результаты не называются row-proof.
Бюджеты делегированного маршрута остаются его прежними бюджетами.

## Что проверяет произведение

Сначала PR30 loader заново проверяет связь источника, IR, полной достижимой
модели, наблюдений, меток и атомных строк. Полученный immutable Runner не
содержит исходника, IR, остаточных состояний или прямой таблицы `cells`.

Состояние цели: `(source_class, capped_popcount, last_bit)`.
Порог насыщения равен max(1, 1 + максимальный порог popcount-атома), поэтому
все разрешённые целевые атомы сохраняют значение после насыщения. Для ширины
w>0 count есть min(limit,popcount(raw)), а last_bit — знаковый бит слова.
Начальная метка `not-a-word` не считается Boolean-результатом.

Сертификат содержит initial, типизированные состояния и строго более раннего
родителя каждого неначального состояния. Checker восстанавливает каждый
переход через `runner.machine.step`, то есть через атомные прообразы PR30,
проверяет достижимость, отсутствие дубликатов, замкнутость под ОБОИМИ битами и
совпадение с целью ПОСЛЕ КАЖДОГО перехода. Выбор состояния без проверяемого
родителя не принимается. Полнота не заменяется конечным тестированием слов.

Локальная симуляция PR28/29, восстановление того же действия PR30 и индукция
по битам дают совпадение источника и цели для всех положительных ширин
принятого математического профиля. Ограничение API на исполнение конкретных
слов не ограничивает это индуктивное утверждение. Начало при ширине 0
исключено явно, а не замаскировано удобным значением цели.

Положительное произведение не вызывает whole-word IR evaluator или старую
inference-v3 таблицу. Последняя не используется как способ получить переходы
нового proof. Producer и checker разделяют Monitor и доверенную семантику
цели; независимость означает replay без поиска, а не отсутствие общего кода.

## Контрпримеры и неверные сертификаты

Отрицательный пакет содержит непустое LSB-first слово. Оно обязано нарушать
цель НА СВОЕЙ ПОСЛЕДНЕЙ ширине. Whole-word IR независимо проверяет реальный
результат, сравниваемый с row-runtime и целевой Boolean-функцией.

Дополнительно проверяются несколько кандидатов на физической Java-ширине.
Это не автоматическое продолжение малого witness и не исполнение Java при
replay. Пустой список native-width witnesses не доказывает отсутствие ошибок
на этой ширине. Development-контроль `x>0 || (x==2 && x<0)` нарушает цель
positive при ширине 2, но дополнительные native-проверки ошибки не находят.

Подмена цели, source-only пакет вместо target-proof, неполное произведение,
повреждённая строка или ложный сохранённый verdict отвергаются. Корректный
source-interface ошибочной программы не гарантирует её целевое свойство.
Вычисленное source false и статус refuted также не тождественны.

## Бюджеты и коды

Signed-бюджеты в JSON для `--budget`:
`max_states` 1..64 (по умолчанию 64), `max_observations` 0..63 (63),
`max_pullbacks` 0..100000 (4096), `max_classes` 1..64 (64),
`max_target_states` 1..8192 (8192), `max_witness_bits` 0..4096 (4096).
Boolean вместо целочисленного бюджета не принимается. Истощение различает
source_model, observation_closure и target_product; полного proof нет.
Неподдерживаемый исходник не считается опровержением.

Коды: certified=0, refuted=1, unsupported/budget_exhausted=2,
invalid_certificate=3, input_error=64, internal_error=70. Лимиты JSON и
исходного текста — прежние 5 MB и 2 MB unified CLI. Произвольная malformed
цель не превращается в новую поддержанную спецификацию.

## Development experiment

```sh
python -m research.external.frozen_v2.download_sources reproduction/pr31-input
python -m research.signed_targets.experiment reproduction/pr31-input reproduction/pr31-fresh
python -O -m research.signed_targets.experiment reproduction/pr31-input reproduction/pr31-fresh --replay
python -m unittest research.signed_targets.test_targets -v
python -O -m unittest research.signed_targets.test_targets -v
```

Три прежних PR24 метода и восемь constructed sources: ожидаются 7 certified
и 4 refuted. Пять отдельных диагностических controls: 1 unsupported и
4 budget_exhausted. Java/IR/row сравниваются на 209389 внешних development
входах и 2072 constructed-входах, без смешивания знаменателей. Для трёх
constructed native-ошибок ожидаются расхождения с target при совпадении
Java/IR/row. Малый-only witness записывается отдельно.

Fresh требует JDK 17+. Replay проверяет все 11 доказательств, объяснения и
сохранённые native outputs, но НЕ повторяет Java, генерацию или неудачные
поисковые controls; последние — сохранённые диагностические записи.
PERFORMANCE учитывает полное построение/встроенные проверки, отдельно
check/explain, native-вызовы и неудачные попытки. Сравнение скорости с v3,
прямой таблицей или SMT в этом этапе не выполняется.

## Границы и следующий этап

Frontend, остаточная и целевая семантика, Python checker и runtime остаются
доверенными реализациями; `lean_checked` false. Модель по-прежнему полностью
строится в пределах 64 состояний. Нет новой грамматики Java, изобретения
произвольного языка наблюдений, Lean-теоремы или внешнего holdout. Frozen_v2
1/15 и Run27 2/33 неизменны. Этот этап — атомно порождённые строки III,
не реализация общей задачи достройки или роста forced domain из I.

Следующий №32 — приёмочное сравнение трёх конфигураций и обновление научной
карты, с учётом всей стоимости обнаружения, а не только конечного сертификата.
