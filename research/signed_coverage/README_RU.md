# PR35: условное остаточное описание с проверяемым покрытием

Новый маршрут строит **остаточные программы**, а не сначала весь исходный carrier.
Он использует прежнюю signed-семантику, проверенное сокращение PR33, observation/atomic
ядро и строковый runtime. Основное новое правило: после обнаруженного несовпадения
равенство необратимо ложно на каждом продолжении. Под этим проверенным условием его
можно заменить false, упростить Boolean-потребителя и удалить ставшие ненужными
арифметические зависимости. Ни одна цель не используется как предпосылка сокращения.

## Что представляет состояние

Состояние содержит `has_bits`, текущую формулу с индексами атомов исходного reduced IR,
точную проекцию её живых узлов/атомов и только их остаточные координаты. Все индексы
проекции независимо пересчитываются по транзитивному замыканию зависимостей. Нулевой
input-узел остаётся stateless anchor принятой семантики. Опущенным координатам **не
приписывается ноль или выбранный представитель**. Они не нужны текущей формуле и
её дальнейшему действию. Их допустимые значения покрываются аргументом зависимости.

После каждого бита проверяемый edge:

1. Вычисляет точную производную по биту на живом DAG, используя прежний `signed.cell`.
2. Предъявляет каждый активный equality-атом с накопленным mismatch=1. Checker
   пересчитывает этот guard из предыдущего описания и бита. Текущее ложное знаковое
   сравнение не является таким guard: его знак может измениться на следующем бите.
3. Заменяет только эти equality-атомы на false, воспроизводит объявленные Boolean
   шаги и заново вычисляет зависимостную проекцию. Нельзя вернуть ранее забытый узел.
4. Проверяет полученное описание следующего состояния, конечную метку и полный
   набор ветвей для обоих битов.

Используются лишь шесть **пропозициональных** семейств PR33: not-literal, double-not,
bool-literal, idempotent, complement, absorption. Правила о нативных атомах PR33
не являются безусловными правилами на произвольном промежуточном остатке и в edge
не разрешены. Начальное source-to-reduced доказательство PR33 проверяется отдельно.

## Почему это покрытие, а не проверка представителей

Для остаточной формулы F с остатками r рассмотрим её поведение на любом конечном
продолжении v, включая пустое. Однобитный derivative соответствует прежней семантике
на живых координатах. Транзитивная зависимостная замкнутость доказывает коммутирование
этого вычисления с любой допустимой достройкой опущенных координат: ни их значение,
ни их будущий перенос не входят в вычисление сохранённых узлов и атомов.

Для equality-флага обновление имеет вид `difference' = difference OR mismatch`.
Из difference=1 следует difference=1 после любого числа следующих битов. Поэтому
его Boolean-значение false можно подставить не только в текущий terminal, но и во
всё дальнейшее остаточное действие. Затем истинные Boolean-равенства сохраняют
действие, а exact slicing сохраняет все нужные операции и их переносы индукцией
по DAG. Это три отдельных обязательства: absorbing guard, равенство потребителя,
и замкнутая проекция зависимостей.

Таким образом каждый проверенный edge задаёт равенство **поведения остаточных
программ** после данного бита для всех суффиксов. Индукция по суффиксу связывает
вычисление конечной модели с остаточной семантикой; начальное доказательство PR33
связывает её с переданным источником. Аргумент не предполагает заранее искомую
эквивалентность факторного графа. Guards не доказываются перебором полных состояний.

Это не обещание одной безусловной coordinate projection на всех произвольных
исходных остатках: формула и область её допустимого забывания меняются по пути.
Разные пути можно соединить в одинаковом остаточном описании, поскольку каждый
входящий edge независимо установил ту же семантику продолжений. Хранение полной
истории потерянных координат для этого не требуется.

Checker проверяет корень, строго более раннего parent каждого другого описания,
отсутствие дубликатов, каждую бинарную ветвь и каждую метку. Непустой путь никогда
не возвращается в `not-a-word`. Представленная модель полна; непокрытая ветвь,
потерянный guard или исчерпание бюджета не дают сертификата.

Эта прикладная конструкция реализует локальную simulation/склейку в смысле Paper III
§7.4 при явных source-мостах и областях §7.1. Она не является общим pure-row алгоритмом
Paper I, не измеряет term-depth visibility Paper II и не формализована новой Lean-теоремой.
Сохранены прежние ограничения грамматики, total/pure modular contract и доверие
к Python frontend, residual semantics, локальным правилам, проекции и checkers.

## Форматы и команды

Source-request остаётся `qkf-signed-source-request-v1`.
Новые форматы: `qkf-signed-guarded-source-model-v1`,
`qkf-signed-guarded-observations-v1`, `qkf-signed-guarded-target-v1`.
Старые proof schemas не переиспользуются для новых смыслов.

Source-only API: `producer.build/infer`, `checker.rebuild/check_model/check_observations`,
`checker.explain`, `runtime.load`. Производитель импортируется только для построения.
Replay никогда не вызывает старый полный source carrier или поиск наблюдений.

```sh
python -m research.signed_coverage.cli infer example.java --class Demo --method f --word-type long --certificate covered.json
python -O -m research.signed_coverage.cli check example.java --class Demo --method f --word-type long --certificate covered.json
python -O -m research.signed_coverage.cli explain example.java --class Demo --method f --word-type long --certificate covered.json
```

`source_model_verified` и `source_observation_verified` остаются source-only, с
`target_checked: false`, `lean_checked: false`. `explain` сначала проверяет весь
пакет, затем показывает именно проверенные guards и удалённые зависимости.

## Явная интеграция с независимой целью

Новый `research.unified.v6 prove/check/explain` подключает covered source-interface
к цели. Loader проверяет reduction, coverage и generic atomic proof, затем извлекает
неизменяемый Runner PR30. Переходы целевого произведения берутся из атомных строк.
Общий Monitor, positive `check_product` и concrete `check_witness` PR31 переиспользуются
без изменения. Источник и старые forward cells не управляют положительным product.

Unified envelope/result: `qkf-unified-proof-v5` / `qkf-unified-result-v5`;
engine `signed-guarded-observation-target-v1`. Положительный результат означает
`certified`, `target_checked: true`, `all_positive_widths: true` в объявленном
контракте, но `lean_checked: false`. Отрицательный product-свидетель перепроверяется
на whole-word IR исходника при его конечной ширине по прежнему PR31 checker.
Source-only proof нельзя предъявить вместо целевого доказательства.

```sh
python -m research.unified.v6 prove example.java --target target.json --proof proof.json
python -O -m research.unified.v6 check example.java --target target.json --proof proof.json
python -O -m research.unified.v6 explain example.java --target target.json --proof proof.json
```

V6 выбирает covered route напрямую: **он не запускает предварительный перебор v5**.
Быстрый negative witness-first v5 остаётся доступен без изменений. Все старые
unified-v1..v4 envelopes replay вызывают свои прежние checkers; новые non-signed
запросы направляются прежнему маршруту и не переименовываются в guarded proofs.
Ни default v4/v5, ни установленный публичный qkf CLI не изменены.

Source-only budgets: max_states 1..64, max_steps 0..512 (начальная reduction),
max_local_steps 0..4096 суммарно для edges (не более 512 на один edge),
max_observations 0..63, max_pullbacks 0..100000, max_classes 1..64.
Target добавляет прежние max_target_states 1..8192 и max_witness_bits 0..4096.
Никаких частичных proof при исчерпании. Стадии отказа разделены: source_reduction,
guarded_coverage, observation_closure, target_product. Модель по-прежнему максимум
64 состояния. Ordinary integer inputs/stream limits у извлечённого Runner прежние.

## Результат и оставшиеся ограничения

На точных source/target bytes PR32:

- `tautology_31` получает 2 model states и теперь также положительный target proof.
- `delayed_31` получает 34 остаточных описания вместо недоступного 65-state полного
  carrier. Цель false опровергается. Для такого отрицательного ответа прежний v5
  уже умеет более короткий путь вообще без модели; это не новое negative достижение.
- Нетривиальный `(x == 2147483648L) && ((x & 1) == 1)` доказывается как false после
  покрытия двух бинарных вариантов первым битом, с 2 состояниями, без полного carrier.
- Для equality с 2^k новый carrier имеет k+3 состояния: 33 при k=30, 34 при k=31,
  43 при k=40 и ровно 64 при k=61. При k=62 остаётся явный budget_exhausted.
- `x != 2147483648L || (x & 1) == 0` всё ещё раскрывает 34 описания перед получением
  двухклассового фактора. Guard-язык пока использует только необратимое ложное
  равенство и Boolean-сокращения, не любую инвариантность выражения. Нет заявления
  о минимальном поиске, оптимальном наборе guards или произвольном symbolic synthesis.

Доказательное представление теперь содержит полные локальные derivation edges.
Меньшее число исходных состояний не объявляется автоматически меньшим файлом или
меньшим временем. Все затраты построения/проверки/сравнений сохраняются отдельно;
никакого общего speedup или SMT ranking не заявляется.

## Воспроизведение development evidence

```sh
python -m unittest research.signed_coverage.test_coverage -v
python -O -m unittest research.signed_coverage.test_coverage -v
python -m research.signed_coverage.experiment reproduction/coverage/fresh --java
python -O -m research.signed_coverage.experiment reproduction/coverage/fresh --replay
```

24 constructed cases: 9 certified и 15 refuted, каждое с полным source-interface.
В каждом опыте 12 240 finite small-word, 960 wide и отдельно 2869 actual Java inputs
на 11 выбранных constructed источниках. Это сравнения original IR / covered model /
row execution, а не 24 новых независимых Java-family результата. На малых общих
случаях полный PR28 carrier сравнивается по всем достижимым парам с новым графом.
Этот reference enumeration — отдельно измеряемый контроль, не скрытый этап нового
алгоритма. Replay его не повторяет; сохранённые отказы поиска тоже не proof objects.

Семь failure controls сохраняются отдельно. При replay заново проверяются все 24
цели/интерфейса, объяснения и native records, без Java, producers или old enumeration.
50 unit tests включают произвольные достройки удалённых координат, absorbing guards
на всех малых продолжениях, атаки на сертификаты, лимит64, runtime isolation и legacy.
Все 380 выбранных прежних тестов проверяются на текущем дереве в dedicated CI.

Run32/Run27 корпусы не переоценены и не переименованы в holdout; исторические 1/15,
2/33 и сравнительные числа PR32 неизменны. Старые статьи, K1–K10 и roadmap сохранены.
Следующий акцент PR36 — повторно используемый проверенный контекст и устранение
повторной проверки общих частей, не отказ от source/coverage binding ради кеша.
