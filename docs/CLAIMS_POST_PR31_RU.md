# Карта утверждений после PR31 и приёмки PR32

Опорный production snapshot: `eb2e68023e272c51710a25cdfe0a0ff8dd5642ac`,
Git tree `4c1dfe4047c7bc44ca45e0dc3e73b37517859dda`, 1900 файлов.
PR32 добавляет измерение и эту карту, не изменяя движок. Сохраняются
[карта после PR25](CLAIMS_POST_PR25_RU.md), [K1–K10](CLAIMS.md) и все manuscript версии.

## Откуда берутся гарантии нового пути

| Шаг | Код / сертификат | Что проверяется | Чего не утверждает |
|---|---|---|---|
| Source → completion model / PR28 | `research/signed_bridge`, `qkf-signed-source-model-v1` | IR/source binding, достижимость, полное покрытие переходов, `not-a-word` | Не произвольный Java; source/residual semantics доверенные; 64-state cap. |
| Model → observation factor / PR29 | `research/signed_observations`, `qkf-signed-source-observations-v1` | Происхождение вопросов, stable blocks, labels, atomic completion, separation | Coarsest stable factor этого consumer, не минимум числа вопросов и не general observation-language synthesis. |
| Checked action / PR30 | `research/signed_runtime` | Source-bound load и извлечение неизменяемых атомных прообразов; recovered steps | Runtime view/receipt не заменяет исходный proof; не целевой сертификат. |
| Independent target / PR31 | `research/signed_targets`, `research/unified/v4.py` | Достижимое полное произведение через row-step, отдельная цель, непустой final-width witness | Нет новой грамматики, Lean-теоремы или произвольного language lowering. |
| Acceptance / PR32 | `research/acceptance` | Сохранность точных exports, все попытки/ошибки, fresh guarded replays, B/C equivalence | Не новый holdout, не новый production proof engine, не SMT ranking. |

Внешний verdict `certified` выдаётся только после проверки target. Source-only
статусы PR28–30 сохраняют `target_checked:false`. Все новые Python-пути сохраняют
`lean_checked:false`. Малый counterexample в modular extension не переносится
автоматически на Java int/long. Ошибочный сертификат не является upstream bug.

## Связь с математическими статьями

**Paper I, Theorems 3.4, 4.1, 5.2, 7.1.** Forced carrier equality, вынужденно
carrier-valued область и наличие completion — разные объекты. Здесь не выполнен
общий pure-row algorithm с нетривиальным ростом D за пределы S. Новый finite
source-factor — sufficient observational identification, не carrier confusion.

**Paper II, §4 и §7.** Хронологические ground proofs и threshold countermodels
касаются максимальной глубины термов. Разделяющие bit-suffixes, число итераций
closure, объём serialized proof и machine time — другие ресурсы. PR32 не измерял
lambda_E и не доказывает optimal proof horizon.

**Paper III v2.0, K6–K7, §§7.1–7.4.** Kernel sufficiency требует labels и domain.
Для h(P)=G intersect phi^{-1}(P) проверенные атомы действительно определяют действие,
а локальное соответствие и склейка поднимают его на непустые слова. Реализован
atom-generated профиль S=D=A. Утверждение об all-positive widths условно относительно
точности frontend/residual/target semantics и Python-checker; хеши фиксируют байты,
не доказывают эти semantic bridges.

PR24 уже вызывал generic observation producer/checker в goal-bound маршруте.
PR28–31 выделили reusable target-free мост, completion, самостоятельное действие и
новый unified target route. Generic closure/atomic completion не переизобретены.

Поздние Graal caller и Lean-фрагменты, описанные в карте после PR25, остаются
отдельными профилями. Их theorem names, source contracts и proof coverage нельзя
расширять результатом signed acceptance. K1–K10 исходной статьи не переименованы.

## Данные, меняющие приоритеты

Из 23 основных development-случаев A завершает 23 (15 certified / 8 refuted),
B/C — 21 (14 / 7), ещё два исчерпывают source cap. На общем наборе результаты
истинности согласны. B/C имеют одинаковые source interfaces и target obligations.
Новый factor может быть меньше, а полный proof — больше: delayed_30 61 → 33
класса, 22240 → 92017 байт. Тавтология требует 65 residual states до обнаружения
константного действия и останавливается на cap=64.

Полные численные затраты, conditional completion counts, controls и этапы
описаны в [отчёте](../research/acceptance/REPORT_RU.md). Source interface generation,
полный процесс, API после импорта, load, target product, serialized bytes,
finite correspondence и внешнее покрытие имеют разные знаменатели.

Следующие обещания являются **планом**, не принятыми утверждениями:
раннее semantic slicing, отрицательное свидетельство без полного carrier,
conditional residual simulation, reuse proof context, compact DAG certificates,
общий pure-row forced-domain checker. См. [roadmap v0.2](QKF_ROADMAP_v0.2_RU.md).
