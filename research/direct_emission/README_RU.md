# PR49: прямой выпуск проверенных зависимостей

Экспериментальный `research.direct_emission.sdk.build` принимает тот же signed
summary request и возвращает `(packet, result, work)`. Независимые параметры:
`backend='ordinary'|'query'`, `policy='no_lemmas'|'reuse'`. Это дополнительный
путь; default SDK, алгоритмы поиска, native rules и прежние checker не изменены.

```python
from research.direct_emission.sdk import build
from research.applicable_summary.checker import check

packet, result, work = build(source, request, backend='ordinary', policy='reuse')
if packet is not None:
    summary = check(source, request, packet)
```

`Assembler` получает только внутренние неизменяемые значения PR48. Native node
создаётся после проверки нового основания; equality node — из проверенного
вывода, включая импортируемую лемму. При экспорте используются уже разобранные
ground nodes. Повторных восстановления контекста и сборки исходного ground
request для slicing нет. Использованные события остаются в хронологическом
порядке; axiom indices и пути перенумеровываются вместе. Вспомогательные
congruence terms объявляются рефлексивными queries, без новых аксиом.

Финальный граф содержит достижимые зависимости всех целей. Порядок обхода
совпадает с PR45; минимальность DAG не заявляется. Форматы
`qkf-direct-consumer-dependencies-v1` и `qkf-applicable-summary-v1` сохранены.
Положительный путь упаковывает один финальный envelope и вызывает прежний
public checker. Только этот checker выдаёт применимый `CheckedSummary`.
Предварительная сборка interface из проверенных результатов не является
выдачей capability. Повреждённый результат сериализации должен быть отклонён.
Каноникализация и digest выполняются неоднократно и учитываются в полной
стоимости; обещания одного JSON encode на весь build нет.

Если хотя бы одна цель `unresolved`, сохраняется весь native batch с его
scoped lower models. Тогда остаётся прежняя цепочка pack/check/extract/package.
Уже выполненная сборка direct nodes тоже включена в стоимость fallback.
`empty` и конкретное опровержение сохраняют собственные проверенные основания.

`work.backend` хранит все фактически выполненные checkpoints, native attempts,
E/E+ и результаты. Независимый receiver заново проверяет каждый из этих
checkpoints прежним checker. `work.backend.emission` отдельно показывает
созданные/оставленные nodes и events, вспомогательные queries, число и байты
промежуточных native packets. Полные delivery/diagnostic bytes, отдельный Python
peak, build, cold check, assessment, export/explain и apply записывает стенд.
Процессная память RSS не измеряется. Внутренние capabilities — граница обычного
API; защиты от враждебной Python reflection здесь нет.

Протокол и шесть случаев зафиксированы коммитом
`1a152ed9ec277b7371d8fdba071787a675cb2690` до сравнительных замеров. Пять
положительных строк PR48 сравнивают все четыре одинаковые конфигурации, а
`power_open` отдельно измеряет fallback. Простой ordinary-контроль получает
полноценный проверенный SDK-интерфейс. Это development population; PR52 и
переключение default не заявляются. Предыдущие полные результаты PR48 включены
без изменений из ветки `research/pr48-results-dac33a1`.

```sh
python -m unittest research.direct_emission.test_emission
python -O -m unittest research.direct_emission.test_emission
python -m research.direct_emission.preserve
python -m research.direct_emission.experiment reproduction/emitted-run --shard mask
python -m research.direct_emission.replay reproduction/emitted-run
python -O -m research.direct_emission.replay reproduction/emitted-run
```

Новый workflow измеряет шесть case shards на Python 3.10/3.12. Внутри runner
timing runs последовательны; результаты разных runner и Python не объединяются.
Каждая пара имеет семь свежих timing build/check, отдельные audit build/check
и memory build: 48 пар и 816 попыток на Python. Все попытки, включая неудачные,
остаются в журнале, без скрытого перезапуска.

Длительные исторические PR46–48 timing workflows автоматически запускаются при
изменениях прежнего кода, но пропускают добавления в новый пакет, отчёты и
перестановку regression registry. `workflow_dispatch` сохраняет полный ручной
запуск. Обычный `current-research.yml` со всеми прежними тестами, normal/`-O`
и semantic replay остался побайтово прежним. Workflow-only правки проверяются
тестом, разрешающим только path filters и замену preservation entry point.

Новый preservation gate сохраняет 2196 принятых файлов PR48. Три явных
исключения: аддитивный `SUITES.json` и два исторических measurement workflow.
PR48 workflow теперь использует этот gate, поскольку его старый снимок
включал изменяемый PR47 workflow. Старые preservation scripts и зарегистрированные
протоколы сохранены; для точного воспроизведения исторического workflow доступен
соответствующий старый commit. `ADAPTATION.json` содержит исходный SHA256 и полный
diff producer, чтобы изменение выпуска было отделено от алгоритмов поиска.
