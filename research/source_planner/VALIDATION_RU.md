# PR43 — зарегистрированная проверка planner

База: принятый PR42, commit `01541ee22fd59dfe8be2d0453f942984c833d445`,
tree `b83554662418adf052846803b48d25dde9e76d59`.
Локальная регистрация протокола, точных cases, budgets и ожидаемых outcomes:
commit `ba72ed69c10e9387488a83b251ee83d0fa7986f5`, до сравнительных запусков.
Серверная публикация происходит позже; это development registration,
не внешняя пререгистрация и не holdout.
Protocol SHA-256: `db79e6855899e06dc1d8fe95b5ee74ed444c753dbeec4c81d0eea5e636cd721f`.

## Полный знаменатель

Все 32 запроса PR41 сохранены без изменения source, guards, width и target.
Добавлены семь заранее зарегистрированных случаев: две цели для одного
source/G, mask/parity short-circuit, неиспользуемая local dependency и два
ограничения горизонта. 39 случаев × 3 маршрута = **117 исходов**.
Проверены **108** финальных переносимых сертификатов и **262** промежуточных
checkpoints. Исторические модели проверены каждая на собственном `E`.

| Маршрут | Certified | Refuted | Unresolved | Empty G | Unsupported | Budget |
|---|---:|---:|---:|---:|---:|---:|
| planner | 24 | 6 | 4 | 2 | 2 | 1 |
| ordinary | 24 | 6 | 4 | 2 | 2 | 1 |
| eager | 24 | 6 | 4 | 2 | 2 | 1 |

В 24 certified каждого маршрута включены два явно запрошенных fallback.
Из четырёх unresolved два показывают исчерпание ограниченного native-языка
(`power_open`, `late_open`), два — недостаточный горизонт. Это разные причины;
ни один abstract separator не выдаётся за source counterexample.
Ошибочные source/guards дают шесть конкретных проверенных нарушений.
Unsupported и budget сохранены в знаменателе, частичного финального proof нет.

Во всех 39 случаях native attempt logs planner и ordinary совпадают дословно,
включая неудачи и остановку по бюджету. Одинаковые исходы не доказывают
эквивалентность стратегий на всех возможных программах.

## Выбор вопросов и ранняя остановка

Числа включают успешные и неуспешные исполненные native-вопросы:

| Случай | planner / ordinary | eager |
|---|---:|---:|
| mask_31 | 2 | 20 |
| double_even | 5 | 19 |
| mask_short_circuit | 4 | 42 |
| parity_short_circuit | 8 | 36 |
| irrelevant_local | 1 | 10 |
| goal_true | 8 | 25 |
| goal_negative | 3 | 20 |

В двух последних строках одинаковые source и `G`: `((x+x)&1)==0 || x<0`
при отрицательном input. Для consumer TRUE planner выбирает parity projection;
для consumer negative сначала связывает source sign atom с target, затем
использует `G`. Исходная программа/guard не менялись, последовательности
вопросов различаются. Неиспользуемая local parity dependency не вычисляется.

Тест остановки перехватывает успешную независимую проверку и запрещает любой
последующий native-вызов. Отдельно проверяется runtime closed guard.
В тесте достаточного same-head pullback порядок дочерних обязанностей
действительно использует значения проверенной модели; желаемая истина не
подставляется как premise. Подмена native conclusion отвергается checker.

Каждое из 79 расширений `E` adaptive-маршрута инвалидирует прежний separator.
Подмена исторического model input hash новым `E` не заменяет проверку новых
аксиом. Бюджет следующего checkpoint не позволяет экспортировать старую
модель как остаточную обязанность нового `E`.

## Полная стоимость

Финальный пакет: `reproduction/source_planner/pr43_04`.
SHA-256 `SUMMARY.json`:
`5ddbb12b6070aeda0ad5d6c4f182dcdc4aa8414320f35ccf332df76d728e7cfd`.
Генерируемые пакеты не коммитятся. Current CI повторяет experiment, normal/`-O`
replay и сохраняет source snapshot, cases, proofs, costs, failures и manifest.

Суммы по всем 39 запросам, включая refuted/unresolved/budget/unsupported:

| Счётчик | planner | ordinary | eager |
|---|---:|---:|---:|
| Запрошено native-попыток | 181 | 181 | 762 |
| Native rules исполнено | 180 | 180 | 761 |
| Неуспешных native executions | 101 | 101 | 610 |
| Выпущено нерефлексивных фактов | 79 | 79 | 117 |
| Ground checkpoints | 114 | 114 | 34 |
| Guard-domain builds, включая встроенный replay | 171 | 171 | 91 |
| Research Python calls | 3 181 730 | 3 157 306 | 1 046 739 |
| Все финальные proofs, B | 109 029 | 108 959 | 115 270 |
| Все checkpoint proofs, B | 465 341 | 465 271 | 125 877 |
| Полная work-диагностика, B | 1 188 595 | 1 120 195 | 643 549 |
| Instrumented elapsed, ms | 4744,52 | 4616,45 | 1672,04 |

Разница на одну попытку — общий `fact_budget`: лимит останавливает исполнение,
но запрос уже записан. Checkpoint proofs входят в work-диагностику; эти строки
нельзя складывать как непересекающиеся размеры. Финальный proof иногда также
является последним checkpoint. Source и request передаются отдельно и одинаковы
для всех маршрутов одного случая; они не включены в байты certificate.

Во всех трёх маршрутах 1024 bounded source evaluations и два fallback attempts
с восемью coverage classes и 24 product states. Planner не сокращает эту часть.
К его затратам добавлены 580 syntax proposals, 871 syntax visits, все
промежуточные closure/model searches, повторные admissions и native checking.
Legacy builder calls разрешены только внутри explicit fallback; вызовы
вне этого участка запрещены actual-call guard.

Примеры полного elapsed для planner / ordinary / eager, ms:
`mask_31`: 138,66 / 110,61 / 38,58;
`parity_short_circuit`: 211,89 / 199,28 / 49,12.
Это один последовательный инструментированный запуск без одновременных
регрессионных тестов. Process/module caches между случаями сохраняются,
импорт первого случая не выровнен. Внешний replay и diagnostic serialization
не входят в эти времена. Более ранние запуски сохранены; лучший не выбирался.

Вывод этого development run ограничен: planner сокращает купленные вопросы
и останавливается при достаточности, но повторные checkpoints делают весь путь
дороже eager. Ускорение I/II не установлено. Для дальнейшей оптимизации есть
конкретная цена repeated checking; перенос проверенных лемм между целями
в этом PR отсутствует. A1 не расширяет разрешение на source forcing.

## Проверки и сохранение базы

54 новых теста охватывают goal change, обе зарегистрированные relational
семьи, неиспользуемые IR dependencies, остановку после доказательства,
syntax-only ranking, model-guided sufficient pullback, invalidation при росте
`E`, inactive/not_visible/full-H различия, бюджет после нового факта,
fallback и concrete witnesses под `G`, source/guard/width rebinding,
повреждение native rows и ground proofs, ложную provenance, отсутствие search
imports в fresh checker, строгие limits/JSON и CLI без перезаписи.

Полный current реестр: **826 предыдущих + 54 новых = 880 тестов**.
Normal и `python -O` проходят весь реестр. Fresh normal/optimized replay
проверяет все 108 certificates и 262 historical checkpoints с запретом
planner/search imports до загрузки checker. Current CI запускает это на
Python 3.10 и 3.12. Новых Lean-утверждений нет.

Сохранены байты и режимы **2074** файлов принятой базы. Исключения — только
два заранее разрешённых infrastructure-файла: `current-research.yml` и
`research/regression/SUITES.json`; изменения в них добавляют PR43 к текущим
проверкам. Inventory SHA-256:
`1b95db150dfe90e19c4c316a8ecdb1617517bbf23949d1815b12b941a4aba2d4`.

## Исправления до публикации

`pr43_01` сохранён с failure и исходным результатом `mask_two/planner`:
после упрощения outer Boolean context обход потерял происхождение оставшейся
source-клаузы. Получен ложный unresolved вместо ожидаемого certified;
ложного положительного сертификата не было. Обход теперь рассматривает
исходный и нормализованный term и восстанавливает actual atom/word IDs.
Регистрация, source, outcomes и native-правила не менялись.

`pr43_02` полностью прошёл сравнение. При review уточнены только diagnostics:
`required_horizon` для inactive query отделён от полного `H`, eager помечен
как неадаптивный, native exhaustion выделен по стадии, записан outcome fallback
и сохранён origin pullback. `pr43_03` повторил сравнение после этих уточнений;
одновременно шли unit tests, поэтому его времена не используются в таблице.
`pr43_04` выполнен последовательно после завершения тестов на том же коде.

Первый вызов нового test module не импортировался из-за отсутствующих скобок
в многострочном `with`. Синтаксис исправлен; лог сохранён отдельно. Второй
вызов прошёл все 54 теста. Неудачные запуски и их случаи не исключались
задним числом, ранняя остановка не оправдывается изменением ожидаемого исхода.
