# QKF: карта механизмов и утверждений после PR #25

Исходная точка: main `c8c7b4eeaf848d31c8c324a4316ffec8aac81cda`, дерево
`4838b8badbb3a56f8a7d2a197ce6c0d3d6b3a77d`. Карта добавлена в PR #26.
Это актуальное дополнение, а не новая редакция статьи или переинтерпретация K1–K10.
Старая [карта статьи](CLAIMS.md), статьи и исторические результаты сохранены побайтно.
План следующих изменений: [roadmap v0.1](QKF_ROADMAP_v0.1_RU.md).

## Математический ориентир и необходимые различия

Цель — автоматически строить достаточный наблюдательный интерфейс действия и
проверять его связь с исходной семантикой, метками, областью и независимой целью.
Не только «проверить ещё один метод», но уменьшить ручное задание доказательной
конструкции. Объём автоматизации и стоимость обнаружения учитываются отдельно.

Paper I (13.09.2026): Theorems 3.4, 4.1, 5.2 и 7.1 разделяют защиту носителя,
вынужденный фактор, насыщение ядра и достройку. Paper II (13.09.2026), §4:
хронологические ground-доказательства и конечные модели нижнего горизонта; §7:
граница с universal/rewrite-режимом. Paper III v2.0 (13.09.2026), §§7,9,12:
consumer/domain/labels, атомные строки, склейка, ограниченный Lean-пилот и общий
вызов вывода наблюдений. Это основания и границы, а не утверждение, что вся серия
уже реализована в public CLI. Полные определения сохраняются в соответствующих
редакциях статей; документы более ранней даты не обновляются задним числом.

Не отождествляем:

- вынужденное равенство carrier-имён, достаточное наблюдательное отождествление и
  выбор значения при достройке;
- правильную структуру ядра и правильную разметку его классов;
- source-model equivalence и выполнение независимо заданного target;
- глубину ground-доказательства, длину разделяющего продолжения, число итераций,
  минимальность конечного фактора и single-deletion irredundancy вопросов;
- конечные Java-прогоны, all-positive-width сертификат и Lean-теорему.

## Уже существующие механизмы: не изобретать заново

| Механизм | Реализация на baseline | Сертификат / проверка | Граница |
|---|---|---|---|
| Публичный source-to-verdict и девять строк | `src/qkf_certifier/frontend.py`, `kernel.py`, `certificate.py` | `qkf-rewrite-v3`, пакетные `tests/` | Отдельный устанавливаемый CLI; не получает research-возможности автоматически. |
| Конечное замыкание вопросов обратным переносом | `research/observations/producer.py:synthesize`, `model.py` | `checker.py:check`; `tests/test_inference.py` | Выводится фактор конечной модели и объявленного consumer. Generic JSON model — доверенный вход, не доказательство связи с Java. |
| Полные и атомные вынужденные строки | `research/observations/producer.py:_row/_atomic_row`, `atomic_rows.py` | `qkf-derived-observation-v1` / `qkf-derived-observation-atomic-v1`; `checker.py` | Атомы и labels проверяются; затем rows восстанавливают переходы. В этом powerset-профиле нет нового расширения D за пределы S. |
| Общий контекст и его consumer-фактор | `research/observations/context_checker.py`, `context_factor.py:Runner`, `factor_producer.py` | `qkf-context-consumer-factor-v1`; `tests/test_context.py`, `test_factor.py` | Нельзя заменять один общий свидетель независимыми свидетелями на каждом шаге. Минимальность — относительно заданной конечной модели/consumer. |
| Source-derived словарь и остаточная семантика отдельных Java-регионов | `research/observations/java_words.py`, `ascending_source.py`, `ascending_kernel.py`, `source_cli.py` | source/region certificates; `tests/test_source_words.py`, `test_ascending.py` | Принятые шаблоны и арифметические правила заданы заранее; конкретные исходные тела проверяются. Не произвольный Java. |
| Независимые target и композиция | `research/observations/target_rules.py`, `target_syntax.py`, `run_package.py`, `context_factor.py` | `qkf-research-package-v2`; `tests/test_target_integration.py`, `test_composition_integration.py` | Отдельные source и target обязательства, typed/shared input constraints; не новый автоматический общий язык целей. |
| Inference v1/v2 | `research/inference/adapters.py`, `v2_adapters.py`, `v2_checker.py` | `qkf-observation-inference-v1/v2`; `test_inference.py`, `test_inference_v2.py` | Source-derived координатные equality/order/relational вопросы; конечное перечисление residual carrier. |
| Signed terminal profile | `research/signed_predicates/frontend.py`, `semantics.py`, `checker.py` | `test_signed_predicates.py`, PR #24 dedicated workflow | Один int/long→boolean; знак определяется terminal-битом. Нет calls/shifts/branches и общего signed word-to-word order. |
| Inference v3 | `research/inference/v3_adapters.py`, `v3_producer.py`, `v3_checker.py`, `v3_target_checker.py` | `qkf-observation-inference-v3`; `test_inference_v3.py`; PR #25 run 35463665595 | Продолжения 0–2 бита плюс residual-библиотека. Проверяется single-deletion irredundancy; не произвольный observation-language synthesis. |
| Единый research v3 | `research/unified/v3.py`, `v3_schema.py` | `qkf-unified-proof-v2/result-v2`; normal/-O replay | Signed/word/predicate/ascending идут через v3; masked bounds делегируются legacy. Старые envelope проверяются старым checker. |
| Более поздний Graal caller-carrier | `research/create_joint/create_kernel.py`, `create_source.py`, `create_math.py` | `README_RU.md`, `test_create_joint.py`, dedicated workflow | Существует после снимка Paper III: точный закреплённый caller для поддержанных ширин 1,8,16,32,64. Не general Java и не blanket all-width claim. |
| Lean-фрагменты | `research/lean/QKF/`, `research/lean_targets/QKFTarget/` | `Audit.lean`, `CreateAudit.lean`, `CI_SCOPE.md`, `CREATE_CALLER_RU.md`; соответствующие CI | Проверять точные theorem/source bindings; новый Python inference-v3 не становится Lean-теоремой из-за соседства с этими файлами. |

Файлы в таблице принадлежат зафиксированному baseline. Общий finite Model имеет
лимит 64 состояния, полный row-format — 8 классов, атомный — до 64 классов.
Residual-inference v3 допускает до 512 исходных состояний, 256 кандидатов,
128 выбранных вопросов по умолчанию, 8192 target states с отдельными inherited
caps. Эти несовпадающие границы нельзя молча устранить урезанием модели.

## Что именно сделал PR #25, а что пока запланировано

PR #25 подключил signed terminal profile к source-derived выбору вопросов и
независимому target-product через unified v3. Он не подключил signed-модель к
общему `observations.producer.synthesize` и не сделал atomic rows источником
переходов этого нового маршрута: `v3_target_checker.SignedTarget` сейчас строит
table из `inference.adapters.quotient_cells`. Общая row-based инфраструктура
уже работает в других observation-профилях.

Это и есть интеграционный разрыв блока A, а не отсутствие в проекте backward
closure или atomic encoding. PR #28 должен дать source-bound bridge; #29 —
подключить имеющийся вывод вопросов; #30 — использовать проверенные rows в
исполнении; #31 — связать цепочку с отдельным target; #32 — измерить её цену.
Ни один из этих пунктов не считается реализованным данным PR #26.

## Утверждения и доказательные границы baseline

**R-OBS.** Конечный observation-checker проверяет принадлежность и происхождение
вопросов, стабильность partition, protected labels, row completion и separating
contexts. Для generic-модели вывод относится к переданным переходам. Source-bound
режим дополнительно нуждается в проверенном восстановлении модели из исходника.

**R-INF3.** V3 заново проверяет source/target/IR/library bindings, refinement и
pruning, стабильность partition и необходимость каждого выбранного вопроса
отдельно. Это не доказательство минимального количества вопросов среди всех
возможных языков и не общая минимизация произвольного Java.

**R-TARGET3.** Signed product проверяет обязательства после каждого перехода,
то есть для положительных ширин. Контрпример должен нарушать цель на своей
последней ширине. Native-width candidates проверяются отдельно; положительный
source-interface сам по себе не подтверждает target.

**R-TRUST.** Producer не импортируется при независимом replay; это не устраняет
доверие к Python-checker, исходному frontend, семантике, runtime и источнику
спецификации. Хеш не является доказательством эквивалентности Java и IR. SMT/Java
отключены при replay, но конечная native-валидация хранится как отдельное evidence.

**R-BASE26.** Новая регистрация фиксирует все 1837 baseline files посредством
Git tree и SHA-256 inventory. Это доказательство идентичности snapshot при
проверке, не новый verdict программы, математический результат или holdout.

## Evidence populations: не складывать знаменатели

| Срез | Статус и смысл | Опорная запись |
|---|---|---|
| Frozen inference v2 / PR #23 | Исторический 1/15; остальные — пробелы поддержки, не 14 upstream bugs | `research/external/frozen_v2/PROTOCOL.md`, `ENGINE.json`, PR #23 |
| Signed v1 / PR #24 | Три повторно использованных gap-метода; post-holdout development | `research/signed_predicates/README_RU.md`, PR #24 |
| Inference v3 / PR #25 | Те же три development-метода; 3 certified, 3 constructed refuted, 1 unsupported, 1 exhausted-budget | `research/inference/V3_RU.md`, `v3_experiment.py`, PR #25 |
| Конечная Java-проверка PR #25 | 209389 входов внешних development-методов, ноль расхождений; не число доказательств | Run 35463665595, SUMMARY SHA-256 в ENGINE.json |
| PR #26 | Только baseline/protocol freeze, никакого нового знаменателя или результата | `research/external/frozen_v3/REGISTRATION.json` |

Baseline unit/regression reruns в новых CI не превращаются в новое внешнее
исследование. Известные source blobs и их копии учитываются в exposure ledger
будущего корпуса. После использования нового holdout при разработке v4 он будет
reference/development для v4, а не повторно независимой выборкой.

## Как оценивать дальнейшее продвижение

Для каждого изменения записывать: что перестало задаваться вручную; какой source,
consumer и domain охвачены; какой сертификат и каким checker принимается; как
сохраняются labels/shared context; что доказывает положительный и отрицательный
результат. Измерять всю стоимость discovery, включая неудачи, отдельно от replay,
размера конечного сертификата, native-валидации и proof-assistant coverage.

Статьи I/II сохраняют собственные mathematical scope. Третья v2.0 — исторический
снимок; поздние Graal caller и inference результаты не следует ни стирать, ни
задним числом приписывать той редакции. Обновление manuscript запланировано
отдельно; эта карта фиксирует связь текущего кода с будущей редакцией.
