# Source-bound observation closure — Run 29

Продолжение PR28: исходник -> проверенная completion-модель -> существующее
замыкание наблюдений -> проверенный source-bound фактор и объяснения.

Это подключение существующего алгоритма `research.observations.producer.synthesize`,
а не новый алгоритм минимизации, новая теория или первый signed-to-observation
маршрут. PR24 уже использовал это ядро внутри маршрута с целью; PR28 выделил
самостоятельный source-model мост. Здесь появился автоматический target-free
путь поверх этого моста, без передаваемой partition или библиотеки вопросов.

## Запуск

Из полного checkout, Python 3.10+; файл сертификата должен быть новым:

```sh
python -m research.signed_observations.cli infer \
  research/inference/examples/SignedPower.java \
  --class SignedPower --method isPowerOfTwo --word-type long \
  --certificate observations.json
python -O -m research.signed_observations.cli check \
  research/inference/examples/SignedPower.java \
  --class SignedPower --method isPowerOfTwo --word-type long \
  --certificate observations.json
python -m research.signed_observations.cli explain \
  research/inference/examples/SignedPower.java \
  --class SignedPower --method isPowerOfTwo --word-type long \
  --certificate observations.json
```

Python API: `producer.derive(source, request, **budgets)` возвращает
`(certificate, result)`. При исчерпании бюджета сертификат равен `None`.
`checker.check(source, request, certificate)` не запускает producer.
`explain.explain(...)` сначала проверяет весь пакет, затем объясняет его.
Запрос остаётся `qkf-signed-source-request-v1`, без внешнего target.
Схема пакета: `qkf-signed-source-observations-v1`.

Успех: `source_observation_verified`, `claim: source_observation_equivalence`,
`target_checked: false`, `lean_checked: false`. Внутренний generic-checker
сообщает `certified` только о своём конечном наблюдательном контракте; это
не доказательство внешней цели. CLI: успех 0, unsupported/budget_exhausted 2,
invalid_certificate 3, input_error 64, internal_error 70.

## Что выбирается автоматически

Начальные вопросы — равенство terminal/output наблюдаемым меткам модели.
Из вопроса P и символа a выводится обратный образ P после перехода по a.
Вопрос добавляется, только если он разделяет текущий блок. Замыкание
использует прежнее ядро без изменений и завершается устойчивостью либо бюджетом.
Нет параметра lookahead и нет заранее выписанных residual cuts в этом маршруте.
Пользователь не задаёт список предикатов, partition или желаемое число классов.

Число состояний заранее ограничено, а производный набор имеет не более n-1
разделяющих вопросов. Это конечный алгоритм над явно построенной моделью,
не синтез произвольного языка наблюдений и не обход полного раскрытия носителя.

Сертификат содержит неизменённые source-model и atomic-observation proofs.
Checker заново разбирает исходник через PR28, проверяет IR, достижимость и
полноту носителя; затем generic-checker проверяет происхождение вопросов,
точную partition, terminal/output labels, устойчивость, атомные строки,
полученные из них cells и разделяющее продолжение для каждой пары классов.
Он не повторяет поиск или построение минимальной partition.

Достаточность следует из защищённых меток и устойчивости под переходами:
отношение симуляции сохраняется индукцией по трассе. Разделяющие контексты
запрещают отождествить разные классы при сохранении этого потребителя.
Таким образом фактор — наиболее грубая стабильная partition **данной конечной
модели и данного потребителя**. Минимальное число вопросов, кратчайшие свидетели,
оптимальная стоимость или минимальность для любого другого target не заявлены.

## Положительная ширина и метки

PR28 completion не изменён. Инициализация имеет метку `not-a-word`, после
первого бита terminal равен true/false. Выход каждого перехода `_`.
Знак определяется последним прочитанным битом, а не предсказывается заранее.
Инициализация поэтому остаётся отдельным классом, даже когда остаточный вектор
повторяется после непустого слова. Константный Boolean-метод имеет два класса.

На прежних power-of-two методах: 6 source-model состояний -> 5 классов
(1 инициализация + 4 положительных), 4 вопроса, 10 разделяющих пар. Это не
ухудшение относительно 4 классов/3 вопросов inference-v3: потребители отличаются
явной меткой пустой трассы. Сравнивать числа без этой оговорки нельзя.

## Длинные продолжения и независимые проверки

На constructed-исходнике `x == 16` выводятся 7 классов из 11 состояний,
6 вопросов, свидетели до 4 битов. Для `x == 256` — 11 классов из 19,
10 вопросов, свидетели до 8 битов. В тесте независимый поиск по парам
состояний подтверждает необходимость 8 битов для выбранной пары; никакое
продолжение до 2 битов её не разделяет.

Это демонстрирует отсутствие двухбитного cutoff, но **не доказывает провал
старого v3**: его residual-вопросы также могли быть достаточными.
Длина operational continuation не равна term-depth горизонту Paper II.

`explain` восстанавливает слова вопросов из их ациклических parent-записей,
проверяет направление чтения на всех состояниях, показывает сигнатуры классов,
начальные префиксы, локальную устойчивость и уже проверенные separators.
Это объяснения эквивалентности источника и контрпримеры слияниям классов,
не контрпримеры независимому требованию к программе.

## Бюджеты и доверенная часть

`--max-states` 1..64, `--max-observations` 0..63, `--max-pullbacks`
0..100000 (по умолчанию 4096), `--max-classes` 1..64.
Классовый предел — потолок ресурса, не желаемое количество классов.
Исчерпание source-model или observation-этапа указывается отдельно; частичный
пакет не выдаётся за доказательство. По умолчанию используются только atomic
rows: полный powerset не разворачивается. Логические forced-cell counts
не называются выполненными или сохранёнными шагами.

Trust: прежний ограниченный frontend, модульная signed residual-семантика,
Python source-model/observation checkers. Отсутствие producer-импортов не означает
полную формализацию Python. Общие Java, shifts/calls/branches, новые контракты
и новая Lean-теорема здесь не добавлены. Старые схемы/движки неизменны.

## Development experiment и воспроизведение

```sh
python -m unittest research.signed_observations.test_observations -v
python -O -m unittest research.signed_observations.test_observations -v
python -m research.external.frozen_v2.download_sources reproduction/obs-input
python -m research.signed_observations.experiment reproduction/obs-input reproduction/obs-fresh
python -O -m research.signed_observations.experiment reproduction/obs-input reproduction/obs-fresh --replay
```

Три прежних PR24 метода и пять constructed-исходников дают восемь проверенных
source-observation пакетов. Native-популяция прежних методов — 209389 входов;
constructed source/IR/factor сравнения — 2550 слов ширин 1..8. Пять constructed
случаев — delayed16, delayed256, true, sign и вариант без positivity guard.
Последний тоже имеет корректный интерфейс своего поведения; требование
«positive power-of-two» в этом эксперименте не подставляется.

Fresh использует JDK с `--release 17`; replay не запускает Java и не импортирует
генераторы. Он заново проверяет восемь proof/explanation-пакетов и сравнивает
сохранённые native outputs с IR и проверенными cells. PERFORMANCE.json содержит
реальные непереносимые между машинами времена; они отделены от детерминированного
SUMMARY.json и не служат доказательными предпосылками.

35 новых тестов включают независимый попарный oracle на 16 выражениях для двух
типов и 24 детерминированных дополнительных выражениях, переименования,
эквивалентные исходники, exhaustive слова, ширины до 4096, точно 64 состояния,
budget controls и подмену корректным доказательством чужой таблицы.

## CI и дальнейшая граница

Прежний signed-source-bridge workflow теперь явно архивирует точный PR28 head:
его строгое правило новых путей нельзя ослаблять молча. Новый dedicated workflow
проверяет текущий tree, 35 новых и 161 прежний тест в двух режимах, fresh native
experiment и guarded replay. Он сверяет все 1873 прежних файла кроме одного
объявленного live-workflow изменения и точный набор девяти добавлений.
Замки PR26/27 и их архивный workflow не меняются; Run27 не перезапускается.
Исторические 1/15 и 2/33 остаются неизменными.

Атомные rows/cells уже строит и проверяет прежнее generic-ядро. Новый runtime,
самостоятельно исполняющий внешний интерфейс только через проверенные строки,
остаётся PR30. Подключение независимо заданного target/unified route — PR31.
Новый внешний holdout и измерительное сравнение версий не заявлены.
