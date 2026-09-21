# PR47 — равные SDK-контракты и полная стоимость

Реализация [roadmap v0.5, PR47](../../docs/QKF_ROADMAP_v0.5_RU.md).
Алгоритмы PR41–46, SDK defaults и исторические результаты сохранены.
Регистрация опубликована до полного сравнения: commit
`bbbe8ab4bf9d0dd0f8bb2c84411eb9935f4e360e`.

Итог: [REPORT_RU.md](REPORT_RU.md), все samples и профили вызовов —
[RESULTS.json](RESULTS.json), контроли следующего сравнения —
[PR52_BASELINES.json](PR52_BASELINES.json).
Опубликованы полные CI shards на Python 3.10 и 3.12, по 2788 попыток на
каждую версию; времена разных jobs не объединены. Прерванный локальный
прогон сохранён отдельно и исключён из итоговых времён и выбора контролей.

## Что сравнивается

| Поставка | Маршруты | Что проверяет получатель |
| --- | --- | --- |
| Одна сводка | sdk_default/reuse/direct, sdk_ordinary | Один SDK packet, применимое действие, export/explain |
| Сервис серии consumer-запросов | sdk_default/reuse/direct; once_default/ordinary | Batch либо первый singleton packet, затем независимый assess всех requests |
| Отдельные сертификаты | each_default/ordinary | Каждый singleton packet проверяется без остальных |
| Proof-only | direct41 | Native доказательство; отсутствующее SDK-применение не имеет нулевой цены |
| Phase | прежние четыре локальных маршрута | Только собственный физический профиль |

`sdk_ordinary` вызывает PR41 ordinary и существующий `from_certificate`.
`sdk_direct` по-прежнему означает PR44 ordinary+reuse, а не этот простой путь.
`once_*` строит только первую сводку; её получатель загружает proof и
самостоятельно проверяет каждый новый request. Отдельный assess-ответ
не объявляется новым переносимым сертификатом.

У `each_*` нет межвызовного семантического кеша. Все независимые builds
внутри серии выполняются последовательно в одном новом процессе; импорт
модулей оплачивается первым вызовом. Это обычный SDK client, а не N новых
интерпретаторов. Холодный receiver проверяет каждый из N отдельных пакетов.

Гарантии underlying proof не ослаблены. Сервисная поставка требует
подтвердить все независимые consumers и дать тот же применимый интерфейс;
индивидуальные native derivations всех целей остаются дополнительной
возможностью batch-пакета, которую first-build/assess не заявляет.

## Команды

Из корня репозитория, свежие каталоги для каждой попытки:

```sh
python -m research.sdk_comparison.preserve
python -m unittest research.sdk_comparison.test_comparison
python -O -m unittest research.sdk_comparison.test_comparison
python -m research.sdk_comparison.experiment reproduction/sdk_comparison/run01
python -m research.sdk_comparison.replay reproduction/sdk_comparison/run01
python -O -m research.sdk_comparison.replay reproduction/sdk_comparison/run01
```

Полный локальный run имеет 33 случая, 164 пары и 2788 попыток.
CI использует непересекающиеся `--shard core|mask|parity|repeat|phase|assessment`.
Все шесть shards на каждой Python версии нужны для полного покрытия;
один зелёный shard не является полной приёмкой PR47. PR46 выполняется
целиком в собственном job. Внутри каждого job timing-маршруты последовательны.
Времена разных runners/Python не объединяются в одну выборку.

## Данные и границы

`PROTOCOL.json` и `REGISTRATION.json` фиксируют выборку до измерений.
Артефакт содержит source/request cases, полный `ENGINE.json`, журнал всех
попыток и сбоев, процессные stdout/stderr, audit-пакеты и историю оснований,
memory и все семь timing samples, независимые check records, пересчитанный
`SUMMARY.json` и manifest точных bytes. Незавершённый parent оставляет
пошаговый checkpoint; новый run не заменяет предыдущий.

Основная цена: build с native producer, SDK import и built-in checks,
кодирование поставки, cold check всех оснований, assess заданных requests,
один export/explain каждого пакета. Хеширование входной поставки и проверки
envelope включены в receiver time. Отдельно показано 64 повторения
зарегистрированных последовательностей apply и полное время дочерних
процессов. JSON I/O и запуск интерпретатора входят в процессную цену.

Call audit и tracemalloc запускаются раздельно от timing, каждый в новом
процессе. В timing сохранены встроенные профайлеры и guards. Это
инструментированные development времена; Python peak не RSS. Audit не
является доказательством исполнения, а счётчик вызовов — числом инструкций.
Python peak относится к build; память холодного receiver отдельно не измерена.

Replay не импортирует producer/planner/SMT, заново проверяет каждое
основание и E/E+ checkpoint, все последующие consumer answers, экспорт и
применение. Положительная проверка/application не выполняют source целиком.
Concrete refutation проверяется принятой семантикой. Unsupported и resource
budget без proof — явные непроверяемые поисковые диагностики; их нельзя
использовать как semantic premises или успешные proof-пакеты.

План причинной матрицы PR52, практический порог и правило выбора baseline
находятся в PROTOCOL.json. F1 открыта. Карточка следующего development
трансформера — [PILOT_RU.md](PILOT_RU.md), точные исходники — PILOT.json.
