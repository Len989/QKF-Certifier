# PR32: приёмка блока A

Сначала прочитать [протокол](PROTOCOL.md), затем [отчёт](REPORT_RU.md).
Это development-сравнение, не новый внешний holdout и не обновление показателя 2/33.

В `LOCK.json` закреплены до первого измерения код исполнителя опыта, фиксированный
генератор, полные идентичности 28 случаев и протокол. Протокол опубликован коммитом
`dd79ffe2831584748305ed96fb8acd04fd0a9025`; SHA-закрепление — следующим коммитом
`d32da80c44469fb89f8513e9e0a9bc959eb0383d`. Полные байты стенда опубликованы затем,
с теми же хешами. Предварительно выполнялись только constructed unit/smoke проверки
стенда, не полный сравнительный прогон. Измеренные движки не изменяются.

## Воспроизведение

Требуются Linux/POSIX, Python 3.10+ и Git с указанными объектами. В измерительном
стенде Java и SMT не используются. Удалённое скачивание требует доступ к закреплённым
raw GitHub blobs. Выходные каталоги должны отсутствовать.

```sh
mkdir -p reproduction/acceptance/engines/{v3,pr31}
git archive c8c7b4eeaf848d31c8c324a4316ffec8aac81cda | tar -x -C reproduction/acceptance/engines/v3
git archive eb2e68023e272c51710a25cdfe0a0ff8dd5642ac | tar -x -C reproduction/acceptance/engines/pr31
python -m research.external.frozen_v2.download_sources reproduction/acceptance/input
python -m unittest research.acceptance.test_acceptance -v
python -O -m unittest research.acceptance.test_acceptance -v
python -m research.acceptance.run run reproduction/acceptance/experiment --old reproduction/acceptance/engines/v3 --new reproduction/acceptance/engines/pr31 --inputs reproduction/acceptance/input
python -O -m research.acceptance.run audit reproduction/acceptance/experiment
python -m research.acceptance.report reproduction/acceptance/experiment reproduction/acceptance/ANALYSIS.json
```

`run` запускает все discovery и checker-процессы, а затем отдельную фазовую диагностику.
`audit` повторно сверяет сохранённые байты, происхождение импортов, все попытки и
результаты; он **не запускает checkers ещё раз**. Полные новые replay уже выполняются
самим `run`: три обычных и один `-O` для первого сертификата каждой конфигурации.
Для нового ручного replay одного сохранённого пакета:

```sh
python -I -B -O research/acceptance/worker.py --root reproduction/acceptance/engines/pr31 --case reproduction/acceptance/experiment/cases/guava_long --mode closure_rows --operation check --budget '{}' --proof reproduction/acceptance/experiment/attempts/guava_long/closure_rows/discovery-0/proof.json --output reproduction/acceptance/manual-replay
```

Для A выбрать `--mode frozen_v3` и соответствующий export; для B — `closure_cells`.
Режим B — явно отдельный сравнительный формат; production `unified.v4` его отвергает.
Он сохраняет весь атомный сертификат, проверку и загрузку, заменяя только источник
переходов в произведении. Это не измерение полного удаления row-доказательств.

`EXPECTED.json` содержит хеш детерминированной сводки первого локального прогона,
а не ожидаемые timings. Все численные измерения хранятся в отдельных RECORD/PROCESS
и PHASES. Установленный `qkf` CLI и production engines этот пакет не используют.

## Артефакты

Сохраняются исходники/цели, все 252 discovery-попытки, все 268 replay, реальные
сертификаты и результаты, origins модулей, wall/CPU/RSS, точные engine inventories,
окружение, самостоятельная phase-диагностика и полный SHA-256-манифест. Отдельные
процессные отказы запрещают успешную приёмку; математические budget/unsupported
исходы остаются в знаменателях. Временные отношения описательны: три повтора не
являются доказательством статистически устойчивого общего превосходства.
