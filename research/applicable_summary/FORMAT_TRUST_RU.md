# Формат достаточной сводки и карта доверия

Запрос `qkf-summary-request-v1` имеет точные поля `schema`, `profile`, `query`.
Signed query — batch PR44; phase query — локальный запрос PR42. Бюджеты и
стратегия не являются семантическими предпосылками.

На wire используется bounded PR37 `qkf-json-proof-dag-v1`. Его раскрытый корень:

| Поле | Проверяемое значение |
|---|---|
| `schema` | `qkf-applicable-summary-v1` |
| `request` | Точное совпадение с независимым запросом вызывающего |
| `source_sha256` | Идентичность отдельно переданного source; затем проверяется сама связь |
| `kind` | `native_direct`, `native_batch`, `source_query`, `source_plan`, `phase_cell` |
| `evidence` | Нативное доказательство выбранной семьи; результат/receipt не принимается |
| `interface` | Исполняемая форма, заново вычисленная из проверенных consumer claims |

Неизвестные поля/версии отвергаются. Данные — bounded acyclic integer-only
JSON; bool и int различаются, повторные ключи запрещены. DAG проверяет глубину,
размер раскрытия и достижимость до выделения раскрытых контейнеров.

## Native direct

`qkf-direct-consumer-dependencies-v1` содержит `scope`, `nodes`, `goals`.
Scope повторяет точную PR44 привязку source/IR/selection, semantic profile,
G, width, native algebra, ruleset и силу замкнутой гарантии.

Node `native` содержит исходный native entry с claim и проверяемыми evidence.
Node `equality` содержит замкнутое равенство, IDs ранее проверенных premises,
необязательную ссылку `via`, ground request и хронологический proof PR40.
Новый `E` точно совпадает с перечисленными доказанными равенствами. `via`
проверяет точный левый endpoint и транзитивно заменяет его правой частью
ранее доказанного равенства. Это не универсальная схема и не инстанцирование.

Checker проверяет основной ground query и только рефлексивные дополнительные
объявления нужных proof terms. Все нерефлексивные равенства требуют прежних
оснований. Удалённые native facts нельзя вернуть голыми аксиомами.
Все proof events должны вести к основному выводу; каждое premise использовано,
каждый node достижим из consumer roots. Это dependency slicing выбранного
доказательства, без обещания минимального доказательства среди всех возможных.

Цель ссылается на точное source-to-consumer равенство либо содержит explicit
empty-domain/concrete-witness proof. Exact cache ссылается на строго прежний
тождественный запрос. Неизвестный consumer не принимается по наличию похожего
узла или совпадению одного хеша.

## Применение и достаточность

Из `G ⇒ source=C` и точной конечной target-семантики checker компилирует
Boolean-таблицу по `(min(4,popcount), sign)` в объявленной области ширин.
Эта target-абстракция фиксирована и source-free; она не является построением
source residual carrier. Guard и все поддержанные targets постоянны внутри
её классов. Runtime проверяет unsigned encoding/width, вычисляет класс и
возвращает проверенное значение. Source/IR/evaluator в runtime не используются.

Новый потребитель допускается, когда его значения совпадают с этой таблицей
на всех допустимых классах при той же selection/G/width. Область не ослабляется
автоматически. Для локального профиля применимы только запрошенные проверенные
phase cells; существование forced domain не превращается в таблицу иных ячеек.

## Теорема / код / доверенная граница

| Утверждение | Проверяющий код | Что остаётся доверенным |
|---|---|---|
| Source принят целиком в поддержанном профиле | PR41 `context.prepare`, PR42 `context.prepare` | Restricted parser/compiler и описание modular/physical семантики |
| Native-факт верен в точных G/width | PR41 `rules.check_fact`, PR44 `terms.check_native` | Локальные Python rule schemas, low-bit arithmetic и input bridge |
| Выведенное равенство следует из оснований | PR40 `ground_query.checker`, PR45 `direct.check` | Python-декодирование/типизация/проверка пути; F1 Lean theorem ещё отдельная задача |
| Фазовая вынужденность относится к actual cell | PR42 `bridge` + PR38 `pure_rows.checker` | Локальный source bridge и проверка finite pure-row evidence; не whole-word gluing |
| Импортированная coverage достаточна | PR41/43 checker + `signed_coverage` local replay | Сохранённые source-reduction, local coverage и consumer-product правила |
| Исполняемая форма соответствует доказанной цели | PR45 `contract.interface` и `checker.check` | Точная target-domain семантика, проверка JSON equality и классификация runtime-входа |
| Runtime применяет именно выданную сводку | PR45 immutable `CheckedSummary` | Обычный Python process/API boundary; не sandbox от враждебного Python-кода |
| Signed source-опровержение конкретно | PR41 `checker.witness` | Конкретная modular IR-семантика, проверка guard/width; Java runtime не вызывается |

Полный replay не доверяет хешу или сохранённому verdict. Хеши связывают данные;
каждое положительное основание проверяется по своим правилам. Тайминги,
счётчики, trace и сообщения о budget остаются диагностикой.

Новых Lean-теорем в PR45 нет. Существующие формализации не переименовываются
в доказательство этого Python SDK, сериализации или полного frontend. Малое
ядро F1 и итоговое причинное сравнение PR46 остаются отдельными обязательствами.
