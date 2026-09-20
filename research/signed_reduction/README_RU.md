# PR33 — проверяемое сокращение до раскрытия остаточного носителя

Новая исследовательская ветка `research.signed_reduction` реализует первый пункт
roadmap v0.2 после принятого PR32. Она не меняет frozen v3, старые PR28–31, installed
CLI, языки источника/цели и результаты 1/15, 2/33 или 23-case comparison PR32.

## Что уже существовало и что добавлено

Signed frontend уже строит hash-consed word DAG, переиспользует одинаковые атомы
и разворачивает локальные присваивания в выражение действительного return.
Однако его `nodes` и `atoms` сохраняют вычисления, ставшие ненужными возвращаемой
формуле. PR28 перечисляет остатки всех таких координат до факторизации.

Устанавливаемый KnownBits/MLIR certifier уже имеет локальный rule/path replay
(см. III §6), но его термы и контракт не совпадают с signed Java IR. Его правила
не импортируются как автоматически доказанные правила нового профиля и не меняются.
Общие DAG и signed-семантика, источник/selection из PR28, finite Model и generic
observation producer/checker переиспользуются без изменения. Здесь добавлены
отдельный типизированный каталог, trace replay, точная проекция живых зависимостей
и явно versioned reduced bridge. Это не новый общий congruence-closure алгоритм.

Вход — source и прежний `qkf-signed-source-request-v1`. Никакой target, partition,
список наблюдений или желаемая семантика не используется при сокращении.
**Весь выбранный source body сначала проверяется старым frontend**, даже когда
его return константен. Неподдерживаемый shift/call/division в неиспользуемом локальном
вычислении не пропускается. Существующие синтаксические бюджеты (64 word nodes,
12 atoms и ограничения formula/body) действуют до нового сокращения.

## Сертификат сокращения и девять семейств правил

`qkf-signed-source-reduction-v1` хранит оригинальный IR, source/request/contract
binding, шаги `{path,rule}`, итоговую формулу, проекции new-index→old-index и reduced
IR. Checker сам заново разбирает source, повторяет каждый шаг и заново вычисляет
ровно нужные зависимости. Доверять присланному reduced IR или его хешу нельзя.

| Идентификатор | Разрешённое равенство |
|---|---|
| atom-alias | Одинаковые атомы или симметрия word equality; ссылка только на более ранний атом. |
| eq-reflexive | Равенство одного и того же word DAG node самому себе. |
| signed-zero | Signed-сравнение нулевого literal node с нулём. |
| not-literal | Boolean отрицание константы. |
| double-not | Двойное Boolean отрицание. |
| bool-literal | Две константы, нейтральный/поглощающий операнд AND/OR, XOR с false/true. |
| idempotent | Повторный Boolean операнд AND/OR; self-XOR даёт false. |
| complement | p и !p в Boolean AND/OR/XOR. |
| absorption | p OR (p AND q), p AND (p OR q), обе позиции. |

Это чистые двухзначные тождества после независимой интерпретации атомов.
`atom-alias` отдельно использует равенство word-значений, а не считает реальные
атомы независимыми. **Ненулевые literal comparisons не вычисляются как обычные
математические константы:** например, 2147483648L > 0 ложно на ширине 32 и истинно
на ширине 33 в данном модульном расширении. Никакое правило signed-order между
разными выражениями или новое word-арифметическое правило не добавлено.

Любой принятый trace доказывает эквивалентность, не максимальность упрощения.
Пустой корректный trace допустим; producer использует детерминированный обход,
ограниченный 512 шагами, с явным исчерпанием вместо частичного результата.
Boolean правила уменьшают число узлов, либо число atom occurrences/их индексы
при неизменном размере; canonical/minimum-normal-form claim отсутствует.

## Почему проекция сохраняет поведение на всех положительных ширинах

1. Каждый local rule — равенство при любой допустимой интерпретации word atoms.
   Контекстная подстановка и транзитивность сохраняют возвращаемую формулу.
2. Из её оставшихся атомов вычисляется транзитивное множество word dependencies.
   На нём сохраняются исходные операции и literals, меняются только индексы.
   Индукция по word DAG сохраняет каждое нужное значение при любой ширине.
3. Вычисления поддержанного профиля чистые и тотальные. Поэтому удаление остальных
   координат не меняет ни нужные значения, ни исключения/эффекты: таких эффектов
   в принятом профиле нет. Это не разрешение оптимизировать произвольную Java.
4. Всегда сохраняется старый input node 0 как stateless anchor: текущая bit-semantics
   требует непустой word-вектор даже для константной формулы. У константы остаётся
   одна word-координата и ни одного predicate atom.
5. На reduced IR применяются прежние initial/cell/terminal и положительно-ширинное
   completion из PR28. Никакого перечисления исходного carrier в новом пути нет.

Это проверяемая реализация ограниченных правил и условный математический аргумент,
**не новая Lean-теорема**. Доверенная часть: существующий restricted parser,
whole-word/residual semantics, новое правило/проекция, Python checkers.
Это не реализация общего forced quotient или D=S^kappa из Paper I, не измерение
lambda_E из Paper II, не символическое покрытие нераскрытых состояний из PR35.

## Новый bridge и observation mode

`qkf-signed-reduced-source-model-v1` содержит reduction и полный достижимый carrier
**сокращённого** IR. Связь хранит hashes original IR, reduced IR и reduction proof.
Checker проверяет typed earlier-parent witnesses и пересчитывает каждый переход
и terminal; наличие initial и полная closure доказывают полноту reduced carrier.
Один лишь хеш таблицы не принимается. Лимит остаётся **64 вместе с initial**.

`qkf-signed-reduced-observations-v1` поверх этого вызывает неизменный generic atomic
observation checker. Producer выводит вопросы прежним backward closure. Пустая
трасса — `not-a-word`, всегда отдельно от непустых Boolean результатов.
Для постоянной функции получается **2 model states / 2 classes / 1 question**.
Это не one-class результат на consumer, различающем пустой и непустой вход.

Оригинальный `tautology_31` из PR32 теперь даёт такой двухсостоянийный интерфейс
после одного `complement` шага; его source hash сверяется с регистрацией PR32.
Положительно заданной цели у этого опыта нет: **это source equivalence, не новый
`certified` target verdict старого unified.v4**. Старый default route намеренно
не переключён. Его own certificates продолжают проверяться старыми checkers;
новый формат ими отвергается. Подключение будущего сокращённого carrier к общему
целевому пути должно быть отдельным явным, проверяемым изменением.

`delayed_31` (x == 2147483648L) не сокращается этими правилами и всё ещё получает
`budget_exhausted` на построении reduced source model. Короткое опровержение без
полного carrier остаётся задачей PR34. Этот отказ сохраняется как контроль.

## Команды

```sh
python -m research.signed_reduction.cli reduce source.java --class Demo --method f --word-type long --certificate reduction.json
python -m research.signed_reduction.cli build source.java --class Demo --method f --word-type long --certificate model.json
python -m research.signed_reduction.cli infer source.java --class Demo --method f --word-type long --certificate observations.json
python -O -m research.signed_reduction.cli check source.java --class Demo --method f --word-type long --certificate observations.json
```

`check` распознаёт только три новых схемы. Исходник и selection передаются снова.
Файлы создаются эксклюзивно; существующие пути и symlinks не перезаписываются.
Повторяется строгий duplicate/nonfinite JSON reader PR28 и 8 MiB лимит.
Exit 0: source equivalence checked; 2: unsupported/budget; 3: invalid certificate;
64: input error. Во всех результатах `target_checked` и `lean_checked` — false.
На API `infer` стадии budget разделены: source_reduction, reduced_source_model,
observation_closure. Бюджет не означает опровержение и не выдаёт partial proof.

## Проверки и развитие, не новый holdout

41 новый тест: все девять правил с source witnesses; независимые Boolean truth
tables; полные малые слова для 16 выражений в двух типах; 48 seeded generated
контекстов; переименования/вложенность; stepwise commutation projection; широкие
границы до 4096; старая и новая схемы; typed/path/hash/source/atom/row/closure
corruptions; budget/output controls. Guard при построении `tautology_31` запрещает
старый enumerator и проверяет, что каждый cell получает только reduced IR.
Fresh normal/-O replay блокирует producer/subprocess/SMT импорты до checker import.

```sh
python -m unittest research.signed_reduction.test_reduction -v
python -O -m unittest research.signed_reduction.test_reduction -v
python -m research.signed_reduction.experiment reproduction/reduction/fresh --java
python -O -m research.signed_reduction.experiment reproduction/reduction/fresh --replay
```

Опыт содержит 24 сконструированных случая, 12 240 малых word comparisons, 768
широких сравнений и (с --java) 2072 inputs на восьми source-файлах. Они сравнивают
original/reduced/model/factor semantics; Java дополнительно сравнивается с первыми
тремя. Никаких новых external methods или target verdicts к покрытию не прибавляется.
Сохраняются все source/request/proof/result/native records, отдельные timings и
полный file/hash manifest. Replay действительно проверяет source proofs и stored
outputs; old-reference enumeration и failed searches сохраняет как diagnostics,
не повторяет. Время native/reference не входит в full-infer timing; все три
затраты записаны отдельно. Ускорение относительно SMT не заявляется.

Все 297 выбранных прежних тестов выполняются на текущем дереве отдельно от новых.
Исторический строгий snapshot workflow PR32 закреплён на его принятом commit и
явно называется archived. Новый workflow сохраняет **полный source tarball**,
поэтому исключение hidden loose files при передаче не повреждает snapshot.
Ни один замок эксперимента не ослабляется, прошлые статьи и roadmap не меняются.
