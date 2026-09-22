# PR49 — прямой выпуск графа зависимостей

Прямой выпуск сохраняет канонические proof/result bytes и все фактически выполненные промежуточные обязательства. Положительный signed-путь больше не строит PR44 native packet для последующего извлечения; финальный envelope принимает прежний независимый checker. Открытые обязательства сохраняют прежний scoped-model fallback.

## Исполнение и данные

- Протокол до замеров: `1a152ed9ec277b7371d8fdba071787a675cb2690`.
- Engine: `0be531350f1e062b04a26fd51915e443765026d5`; tree: `a011e838dcf2c7058adce294ebb989557eba7674`.
- [Полный cost CI](https://github.com/Len989/QKF-Certifier/actions/runs/35670602199): шесть shard × Python 3.10/3.12. На каждой версии — 48 пар case/route и **816/816 попыток**; всего 1632. Ни одна не исключена; неуспешных попыток нет.
- На пару: семь свежих timing build/check, отдельные audit build/check и отдельный tracemalloc build. 64 серии apply измерены отдельно от основной lifecycle.
- Проверены ZIP digests, manifests, полный source tar против `git archive` engine, clean tree, hashes кода и повторный расчёт SUMMARY из raw samples. Все 2196 сохраняемых файлов PR48 совпадают до и после.
- [RESULTS.json](RESULTS.json) содержит все среды, samples/min/median/max, call maps, Python peaks и artifact identities. Полные пакеты, histories и журналы находятся в CI artifacts; [README](README_RU.md) содержит команды воспроизведения.

Это development population. Числа разных runner/Python не объединяются. Таблицы показывают Python 3.12; Python 3.10 полностью сохранён в RESULTS. Локальные функциональные smoke-пробы не включены в экономические оценки.

## Полная стоимость одинаковой поставки

Медианы в ms. Lifecycle = build с кодированием delivery + внешний cold check + assessment всех сервисных целей + export/explain. В колонках PR48/49 одинаковый query/no_lemmas; ordinary-контроль выбран протоколом заранее.

| Поставка | PR48 lifecycle | PR49 lifecycle | PR48 build+cold | PR49 build+cold | Ordinary SDK контроль |
| --- | ---: | ---: | ---: | ---: | ---: |
| mask, одна цель | 835.98 | 578.97 | 800.14 | 543.02 | 347.75 |
| mask, all-width, 4 цели | 3482.99 | 2165.81 | 3382.96 | 2066.95 | 434.58 |
| parity, fixed8, 4 цели | 3477.76 | 2156.00 | 3374.09 | 2053.29 | 409.86 |
| 16 точных повторов | 2942.70 | 2119.99 | 2770.16 | 1949.58 | 505.14 |
| mask, 4 отдельных пакета | 6478.41 | 4080.38 | 6210.11 | 3810.04 | 1439.30 |
| power_open, scoped fallback | 629.47 | 634.19 | 604.01 | 609.03 | 361.84 |

Диапазон относительного сокращения медианы query/no_lemmas по десяти положительным средам: 27.96% … 38.80% для lifecycle и 29.62% … 39.98% для build+cold. Это диапазон отдельных сравнений, не объединённая оценка или доверительный интервал.

Четыре фактора PR49, lifecycle ms:

| Поставка | ordinary/no_lemmas | ordinary/reuse | query/no_lemmas | query/reuse |
| --- | ---: | ---: | ---: | ---: |
| mask, одна цель | 555.71 | 552.82 | 578.97 | 578.27 |
| mask, all-width, 4 цели | 2100.47 | 2062.54 | 2165.81 | 2164.22 |
| parity, fixed8, 4 цели | 2113.00 | 2058.26 | 2156.00 | 2169.79 |
| 16 точных повторов | 2085.29 | 2112.34 | 2119.99 | 2116.94 |
| mask, 4 отдельных пакета | 3995.42 | 4079.42 | 4080.38 | 4147.77 |

Простой зарегистрированный контроль дешевле всех четырёх новых факторов в 10/10 положительных средах. Попарные случаи, где новый путь дешевле контроля: нет. Сравнения касаются одинаковых заявленных поставок; PR52, holdout и переключение default этим не закрываются.

## Реальная работа и память

Полный build audit, mask/all-width/N=4, Python 3.12, query/no_lemmas:

| Вызов | PR48 | PR49 |
| --- | ---: | ---: |
| ground parse | 74 | 26 |
| context from JSON | 43 | 0 |
| target_context | 40 | 12 |
| native external replay | 38 | 9 |
| dependency extract | 1 | 0 |
| components replay | 2 | 1 |
| final public check | 1 | 1 |
| Все DAG pack | 2 | 1 |
| Все DAG unpack | 6 | 2 |
| Все research Python calls | 1273278 | 662483 |

Все новые native-основания по-прежнему проходят проверку при добавлении в PR48 Presentation; все оставленные основания независимо проверяются при приёме финального пакета. Снижение повторных вызовов не заменяет эти обязательства внутренним receipt. Экономия каноникализации не объявляется единственным encode: вызовы для digest/identity остаются в audit и стоимости.

Память и промежуточные пакеты, query/no_lemmas, Python 3.12. Peak — отдельный tracemalloc build, включая retained work и кодирование результата; это не RSS.

| Поставка | PR48 peak bytes | PR49 peak bytes | Итоговый packet bytes | Native output producer PR48 / PR49 |
| --- | ---: | ---: | ---: | ---: |
| mask, одна цель | 3475738 | 3387836 | 5815 | 1 / 0 |
| mask, all-width, 4 цели | 5728292 | 5243224 | 13895 | 1 / 0 |
| parity, fixed8, 4 цели | 5883080 | 5330872 | 14639 | 1 / 0 |
| 16 точных повторов | 8020007 | 5937066 | 8221 | 1 / 0 |
| mask, 4 отдельных пакета | 5376490 | 5236369 | 33907 | 4 / 0 |
| power_open, scoped fallback | 3366544 | 3293870 | 4670 | 1 / 1 |

Изменение Python peak по 40 положительным matched сравнениям: -28.83% … 0.45%. Знак плюс означает рост. Native промежуточные пакеты отсутствуют во всех положительных PR49-парах; итоговые packet bytes совпадают с PR48. Колонка native output и счётчик work.backend.emission.intermediate_native_packets относятся к выходу producer. Это не число всех временных упаковок: fallback дополнительно дважды перепаковывает native evidence внутри прежнего components/checker. В его полном build остаются 4 DAG pack (3 native + финальный envelope) и 10 unpack у PR48 и PR49. На положительном одиночном/service пути pack снизился 2 → 1, unpack 6 → 2; для отдельных пакетов значения суммируются. Все эти вызовы учитываются trace, lifecycle и peak. Полные packing_audit, созданные/оставленные nodes/events, вспомогательные queries и diagnostic bytes доступны в каждой строке RESULTS.

## Незавершённый результат и проверка

- `power_open`, Python 3.10: сокращение lifecycle -0.40%; изменение peak 1.30%. Native batch, lower models и исходные результаты сохранены побайтово; fallback и уже выполненная сборка полностью включены в стоимость.
- `power_open`, Python 3.12: сокращение lifecycle -0.75%; изменение peak -2.16%. Native batch, lower models и исходные результаты сохранены побайтово; fallback и уже выполненная сборка полностью включены в стоимость.

Совпали все 42 matched пары PR48/49 (40 положительных и две fallback): delivery/result bytes, native attempts, основания и checkpoint identities. Новые checkpoint-обязательства не заменяются старым сокращённым журналом; прежний checker проверяет каждый фактически выполненный вывод.

- На Python 3.10 normal и `-O` независимо приняли 75 пакетов, 590 checkpoints и 27072 apply-вызовов. Search imports = 0; positive source execution запрещено.
- На Python 3.12 normal и `-O` независимо приняли 75 пакетов, 590 checkpoints и 27072 apply-вызовов. Search imports = 0; positive source execution запрещено.

Локально прошли 36 новых тестов в normal и `-O`: 27 signed cases × 4 конфигурации, fake/missing native proof, orphan/cycle/forward dependency, lemma endpoint/residual, guard/width binding, вспомогательные terms, mixed positive/inactive fallback и порча финальной сериализации. Общий CI сохраняет 1077 прежних тестов и выполняет новые 36 на Python 3.10/3.12, normal/`-O`.

## Статус и дальнейший шаг

PR49 закрывает прямой выпуск DAG в границах зарегистрированных случаев. Публичная schema и независимый checker сохранены. Алгоритмы поиска и default не менялись. Soundness в Lean остаётся задачей PR50/F1a; экономическая продуктовая гипотеза и PR52 остаются открытыми.

Исторические длительные PR46–48 timings не запускались для добавленного PR49 engine. Обычный current-research workflow и прежние semantic checks сохранены. Полные исторические timings доступны через workflow_dispatch.

Этот отчёт закреплён за указанным engine. Его публикация отдельно от engine не меняет измеренный код и не требует повторять весь CI только ради числового отчёта.
