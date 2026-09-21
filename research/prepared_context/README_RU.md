# PR48 — подготовленный проверенный контекст

Новый исследовательский путь `research.prepared_context` сохраняет прежние
native rules, политику вопросов PR43, schema пакета PR44 и экспорт SDK PR45.
Default существующего SDK не меняется. Загрузка внешнего пакета по-прежнему
проходит через прежний независимый checker.

```python
from research.prepared_context.sdk import build
packet, result, work = build(source, request,
                            backend='ordinary', policy='no_lemmas', limits=limits)
```

`backend` независимо принимает `ordinary` или `query`, `policy` — `no_lemmas`
или `reuse`. Четыре конфигурации используют один `State/derive`, кеш native
вопросов, кеш точных завершённых целей, критерий promotion и упаковку.
Поддерживается signed profile; phase-путь остаётся в прежнем SDK.

## Область доверия

Один admission допускает source целиком, точный IR, profile, selection, guards,
width и фиксированную native algebra. Вложенные значения хранятся в immutable
последовательностях и отображениях; контексты разных целей разделяют один IR.
Изменение входного dict или возвращённой JSON-копии не меняет внутреннее состояние.
Отдельные Python capabilities нельзя получить из поля `checked` или pickle.
Защита от произвольной Python reflection не заявляется.

Каждое новое native-основание полностью проверяется при вставке. E и E+ —
раздельные неизменяемые префиксы. Проверенный consumer, подготовленный ground
input и lower model привязаны к объекту presentation, запросу, basis и epoch.
Promotion требует текущего положительного ground-вывода; более поздний E/E+
или другой build такой capability не принимает. Lower model остаётся
диагностикой текущего ground-запроса и никогда не кешируется как source-вердикт.

Ground DAG один раз проходит прежний strict parser. Producer и внутренний
checker используют неизменяемое разобранное значение. Сохранённые алгоритмы
и ограниченные изменения входных адаптеров перечислены в `ALGORITHMS.json`.
Новый internal checker не заменяет внешний cold checker: весь итоговый пакет
повторно проверяется старым кодом, включая все native и derived основания.
Все промежуточные checkpoint сохраняются в audit и повторяются при replay.

## Horizon и остановка

Ordinary делает обычный CC над узлами и уравнениями, активными при
`min(full_horizon, max_horizon)`, без activation layers и скрытого query fallback.
При полном horizon алгоритм, proof и статистика совпадают с PR41.
Query начинает с глубины endpoints, ограниченной cap, и при `not_visible`
доходит до cap. Неактивный endpoint даёт `unresolved/insufficient_horizon`.
Native-вопросы задаются только после окончательного `not_entailed` текущей
presentation. Разница числа checkpoints относится к backend, а не к reuse.

## Что измеряется

Регистрация опубликована отдельным commit до сравнительного запуска.
Пять строк, 38 пар case/route, 646 попыток на Python: семь свежих timing
build/check, отдельные audit build/check и tracemalloc build. Тайминги
последовательны внутри runner; результаты разных runner/Python не объединяются.
Стоимость включает build, delivery encoding, внешний cold check, assess и
export/explain. Apply измеряется отдельно; память — Python peak только build.
Все встроенные budget/guard profiler остаются включены.

Прежние byte-preserved controls из PR47: `sdk_ordinary`, `once_ordinary`,
`each_ordinary`. Полная матрица выполняется для одинаковых контрактов поставки.
Independent certificates не разделяют состояние между build; отдельный кеш
пакетов для exact repeats здесь не исследуется и выигрыш над ним не заявляется.

```sh
python -m unittest research.prepared_context.test_prepared
python -O -m unittest research.prepared_context.test_prepared
python -m research.prepared_context.preserve
python -m research.prepared_context.experiment reproduction/prepared/run --shard mask
python -m research.prepared_context.replay reproduction/prepared/run
python -O -m research.prepared_context.replay reproduction/prepared/run
```

Старый PR44 packet, `extract → components → package → check` намеренно сохранены:
их устранение относится к PR49. Снижение budgeted Python calls меняет ресурсное
поведение при `max_work`, но само по себе не расширяет семантическое покрытие.
Экономический итог, default и формальное обязательство F1 здесь не закрываются.
