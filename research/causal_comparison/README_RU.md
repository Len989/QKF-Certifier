# PR46: причинное сравнение блока A

Цель — установить, какую работу устраняют source-факты, выбор вопросов,
Paper II, межцелевые леммы и локальная вынужденность Paper I, и сопоставить
экономию с полной стоимостью проверяемого результата.

Это исследовательский эксперимент на принятом PR45. Он не меняет алгоритмы,
правила checker, SDK defaults, installed `qkf` или принятые научные утверждения.
Глобальная цель остаётся прежней: **QKF Semantic Compiler**, локальный SDK/CI,
компилирующий поддержанный IR в достаточные проверенные семантические сводки.

Протокол и точные cases опубликованы отдельным коммитом
`3919c6ccee028cab428c3f185b52a4383d22519c` **до сравнительных запусков**.
Локальный registration commit `a8ba03e` имеет то же дерево.
Это регистрация constructed development-эксперимента, не внешний holdout.
Перед полным прогоном опубликована [поправка к измерению](MEASUREMENT_ADJUSTMENT_RU.md):
трассировка и учёт памяти разделены, все case hashes сохранены.

## Что сравнивается

32 случая, 122 зарегистрированные пары case/route. Шесть пар заранее
помечены `contract_not_supported`: старый signed-control не имеет нужного
условного/fixed-width контракта или бюджета native-вопросов. Они остаются
в таблице покрытия. Выполняются 116 пар, каждая с отдельными call-audit и
memory процессами и тремя холодными повторениями построения и проверки.
Полный журнал содержит 1044 попытки.

| Группа | Маршруты и причинный вопрос |
|---|---|
| Equality/mask и arithmetic/low bits | Retained PR38/39; PR41 ordinary/query; PR43 adaptive/eager; три SDK-маршрута. Отделяем новое локальное правило, выбор фактов и CC-backend. |
| Холодные серии 1/4/16 | `sdk_default`, `sdk_reuse`, `sdk_direct`. Native и exact-goal caches разрешены каждому; ordinary control получает те же проверенные леммы. |
| Негативные и открытые случаи | Ошибочный source/guard, fixed alias, пустой G, нехватка представления, unsupported и бюджет. Проверенный `unresolved` не считается опровержением source. |
| Physical phase cell | Forcing, generated-only ablation, direct от тех же seed и direct от физических ветвей. Самостоятельный профиль с собственной гарантией. |

В signed-профиле I уже выключен по A1. Дополнительный идентичный
`without_forcing` запуск не создаёт нового причинного свидетельства.
В фазовом профиле `no_saturation` может не закрыть исходную цель; рядом
стоят два равноценных прямых способа её доказательства.

## Воспроизведение

Из корня репозитория, в Python 3.10 или 3.12:

```bash
python -m research.causal_comparison.preserve
python -m research.causal_comparison.experiment reproduction/causal_comparison/my_run
python -m research.causal_comparison.replay reproduction/causal_comparison/my_run
python -O -m research.causal_comparison.replay reproduction/causal_comparison/my_run
python -m research.regression.run
```

Каждый запуск требует нового output-каталога. Неудачные попытки сохраняются;
автоматического retry и выбора лучшего запуска нет. Эксперимент выполняется
последовательно. Во время замера не следует запускать рядом регрессии.
Current CI делает полный эксперимент на Python 3.10/3.12, проверяет сохранение
принятой базы, выполняет оба replay и сохраняет `reproduction/context/`
как artifact, включая точный source archive. Числа разных CI runners
не объединяются с локальным замером в одну временную выборку.

## Пакет данных

| Файл | Назначение |
|---|---|
| `PROTOCOL.json`, `REGISTRATION.json`, `ENGINE.json` | Условия замера, hashes source/query/limits/outcome и состояние кода. |
| `case.json`, `audit.json` | Независимый запрос, полный proof, backend trace, native attempts, E/E+, historical obligations и общие actual-call counters. |
| `memory.json` | Отдельный tracemalloc-only child и peak Python allocations, с той же identity полного proof/result. |
| `timing-N.json` | Холодное построение без дополнительной PR46 трассировки/tracemalloc. Bytes identity proof/result должна совпасть с audit. Встроенная инструментализация backends сохраняется. |
| `*-check.json`, `*.process.json` | Свежая проверка, проверенное применение, времена API и всего дочернего процесса, stdout/stderr, таймауты. |
| `ATTEMPTS.json`, `FAILURES.json`, `INTERRUPTION.json` | Полный журнал, ошибки и при наличии незавершённый запуск. |
| `CAUSAL.json` | Совпадение native preparation, реально не запрошенные факты, использование лемм, проверенные D/S и прямые контроли. |
| `COSTS.json`, `DECISION.json`, `SUMMARY.json` | Все измерения, min/median/max, measured-prefix crossings и отдельные решения. |
| `MANIFEST.json` | Точные байты и множество файлов. Идентичность не заменяет семантическую проверку. |

Audit использует общий call/return tracer рядом с существующими эксклюзивными
profilers. Он учитывает построение, built-in replay и SDK extraction/packing.
Память измеряется другим процессом. Их времена не смешиваются с тремя временными повторениями. `research_calls`
не является числом инструкций; `tracemalloc` не является RSS. Размеры proof,
source, request и диагностик приводятся отдельно.

Построение включает все внутренние проверки. Cold check измеряется новым
процессом; warm apply — 64 повторения заранее заданной последовательности
входов только для certified SDK. Маршрут без runtime получает
`not_applicable`, а не нулевую стоимость применения. Proof-only сценарий
и build/check/apply сценарий имеют разные столбцы.

Phase names backends сохраняются в данных. Смешанная фаза
`pure_row_saturation_and_builtin_checks` не выдаётся за чистый поиск.
Исторические lower models проверяются на собственных E/E+ отдельно от
основного cold-check времени. По этим инструментированным development
повторениям не заявляется коэффициент ускорения production-инструмента.

Итоги и следующий шаг: [REPORT_RU.md](REPORT_RU.md).
Граница математических утверждений: [CLAIMS_RU.md](CLAIMS_RU.md).
SDK: [PR45 README](../applicable_summary/README_RU.md).
