# Карта «математическое утверждение → код → проверяемая граница» после PR46

PR46 проверяет работу и стоимость принятых механизмов. Он не вводит новую
математическую теорему и не изменяет старые статьи. Следствие из конечной
презентации, свойство source, экспериментальная экономия и продуктовая
полезность имеют разные основания.

| Утверждение | Проверяющий код | Основание и точная граница |
|---|---|---|
| Ground-равенство следует из конечных типизированных E | `ground_query/checker.py::check`, `check_model` | Хронологические axiom/congruence events и проверяемые конечные модели. Python checker; F1 Lean soundness для этого формата ещё не выполнена. Не универсальное source-тождество. |
| Query-subterm engine не добавляет произвольные термы | `ground_query/producer.py::search`, `prove` | Producer сопоставляет фактические nodes с разобранным запросом; trace содержит `input_nodes`, `added_terms`, horizon. Это факт данного алгоритма/запуска, не доказательство выигрыша над ordinary CC. |
| Source-факт связывает G, width, source/IR и нативное равенство | `source_query/rules.py::check_fact`; `source_lemmas/terms.py::check_native` | Локальные правила equality/mask, low-bit arithmetic и target/guard algebra. Frontend и Python semantics остаются доверенными. Доступны также простому контролю. |
| Требование потребителя доказано из source-фактов | `source_query/checker.py`; `source_planner/checker.py`; `applicable_summary/direct.py::check` | Конечные E связываются с точным source-to-target обязательством. Желаемый target не принимается как аксиома. Не доказательство всех свойств функции. |
| Проверенная лемма допустима в следующей презентации | `source_lemmas/checker.py::CheckedPresentation`, `load_presentation` | Проверка прежнего основания, scope, chronology и `via_lemma`. Не глобальная lemma schema и не перенос между source-версиями. F1 должен покрыть импорт такой леммы. |
| Вынужденное значение на D\S относится к actual phase cell | `source_forcing/bridge.py`; `source_forcing/checker.py::_check`; `pure_rows/checker.py` | Восемь подмножеств трёх физических фаз, проверенные branches/seeds, union/intersection и identity descent. Отдельный локальный guard; whole-word и signed гарантии из него не следуют. |
| SDK исполняет доказанное наблюдаемое действие | `applicable_summary/contract.py::interface`; `checker.py::check`; `runtime.py::CheckedSummary` | Checker заново выводит finite interface; immutable capability проверяет область применения. При apply source не исполняется. Не полная реконструкция source outputs за пределами объявленного класса. |
| Signed refutation — конкретное нарушение | `source_query/checker.py` и retained signed checkers | Проверяются width, G и исполнение modular IR. Abstract nonconsequence не превращается в source refutation. Java/SMT в fresh replay не запускаются. |
| Выбор вопросов действительно устранил запросы | `source_planner/audit.py`; `causal_comparison/analysis.py::causal_checks` | Все выбранные и неудачные candidates сохранены, eager/adaptive используют прежние правила. Весь поиск и replay оплачены. Trace — диагностика фактических вызовов, не криптографическая аттестация исполнения. |
| Межцелевой вывод действительно переиспользован | `source_lemmas/producer.py`; PR46 historical replay | Проверяются `via_lemma` успешных последующих obligations и основания леммы. Доступность леммы или exact-cache hit отдельно не доказывает устранение нетривиального вывода. |
| Новый путь имеет меньшую полную стоимость | `PROTOCOL.json`; `COSTS.json`; `DECISION.json` | Только конкретные сопоставимые case/profile/width, три cold samples, все проигрыши и бюджеты. Структурная экономия, меньший JSON и отдельный быстрый повтор не устанавливают общий speedup. |

## Что уже формализовано и что ещё нужно

Существующие Lean результаты сохраняются: например,
`research/lean/QKF/Checked.lean::forced_rows_correct`,
`SourceBridge.lean::source_step_factor`, `source_word_factor`,
`Gluing.lean::run_simulation`, `closed_certificate_sound`.
Они касаются своих декодированных моделей, данных и мостов. Их наличие
не покрывает автоматически PR40 ground-DAG, PR44 импорт лемм, PR45 JSON
transport, новый SDK или весь Java frontend.

**F1 остаётся незакрытой приёмкой блока A:** soundness типизированного
хронологического ground-DAG в каждой модели E, затем soundness импорта
проверенного предыдущего вывода. Нужны исполняемые отрицательные примеры,
axiom audit и точная карта сериализованных events к Lean-объекту.
JSON decoding/frontend перечисляются как отдельные оставшиеся мосты.

PR46 не переименовывает development-корпус во внешний benchmark. Поддержка
широкого языка, MLIR/xDSL adapter, source-version transport, whole transformers
и независимые продуктовые пилоты остаются будущими задачами roadmap v0.4.
