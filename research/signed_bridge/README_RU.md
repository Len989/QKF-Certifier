# Run 28: самостоятельный source-bound signed-мост

Этот PR реализует шаг #28 согласованного roadmap: исходник → точная достижимая
остаточная модель → вход существующего `research.observations.Model/checker`.
**Независимый target здесь не проверяется.** Успех обозначается
`source_model_verified`, не `certified` для свойства программы.

## Что новое, а что уже существовало

PR #24 (`research/signed_predicates`) **уже** строит source-bound signed-сертификат
и вызывает `research.observations.producer/checker` внутри связанного с целью
маршрута. В PR #25 `research/inference/v3_*` использует ту же остаточную семантику,
но отдельную библиотеку ограниченных terminal-продолжений и residual-вопросов.

Run 28 не объявляет первую связь signed-семантики с observation-ядром. Он выделяет
самостоятельный, не зависящий от цели интерфейс модели; явно представляет
допустимость завершения; проверяет источник, достижимость и полноту до передачи
модели общему checker. Старые файлы frontend, signed, inference и observations
не изменены. Никакой новый алгоритм вывода наблюдений здесь не заявляется.

## Использование

Из корня полного репозитория, Python 3.10+:

```sh
python -m research.signed_bridge.cli build \
  research/inference/examples/SignedPower.java \
  --class SignedPower --method isPowerOfTwo --word-type long \
  --certificate signed-model.json

python -O -m research.signed_bridge.cli check \
  research/inference/examples/SignedPower.java \
  --class SignedPower --method isPowerOfTwo --word-type long \
  --certificate signed-model.json
```

Имена класса и метода должны соответствовать выбранному объявлению (см. сам
пример). Existing certificate-файл не перезаписывается. `--max-states N` задаёт
бюджет 1..64. Это ограничение модели **включает** состояние инициализации.
`budget_exhausted`/`unsupported` возвращают код 2 без нового сертификата;
invalid_certificate — 3; ошибка входа — 64; успешная проверка модели — 0.
Это исследовательский CLI, не расширение устанавливаемого `qkf`.

Python API:

```python
from research.signed_bridge.model import request, word_value
from research.signed_bridge.producer import derive
from research.signed_bridge.checker import check, rebuild

selection = request({"class": "Example", "method": "predicate"}, "long")
certificate, result = derive(source_text, selection)
ir, finite_model = rebuild(source_text, selection, certificate)
value = word_value(finite_model, 8, 64)  # отдельное конечное выполнение
```

Request schema — `qkf-signed-source-request-v1`; certificate schema —
`qkf-signed-source-model-v1`; model schema остаётся прежней
`qkf-finite-observation-model-v1`. Request не принимает target или partition.
Бюджет не входит в семантический request: любой успешно завершённый build выдаёт
полный носитель, а не зависящую от бюджета неполную модель.

`check_observations(source, selection, certificate, observation_certificate)`
сначала восстанавливает модель из исходника, затем передаёт её **существующему**
общему observation-checker. CLI `check --observations other.json` проверяет такой
отдельно полученный proof. Run 28 не создаёт его автоматически. В тестах вызов
старого producer используется только для проверки совместимости и отрицательного
контроля с настоящим generic-доказательством подменённой таблицы. Интеграция
вывода вопросов и исполнитель строк остаются следующими шагами #29–30.

## Контракт и точная граница пустой трассы

Сохраняется `modular-lsb-signed-word-predicates-v1` из PR #24: выбранный статический
unary int/long → boolean метод, модульные выражения, equality, signed-сравнения с
нулём и чистые Boolean-операции. Знак определяется последним прочитанным битом.
Calls/shifts/branches/casts и общий signed word-to-word order не добавляются.

Пусть `r0 = signed.initial(ir)` и `T(r,b) = signed.cell(ir,r,b)`. Мост использует
состояния `(h,r)`, где `h` указывает, прочитан ли хотя бы один бит:

- начальное состояние `(False,r0)`;
- переход `(h,r) --b--> (True,T(r,b))` для каждого `b` из `{0,1}`;
- выход каждого перехода `_` (нет преждевременного Boolean-ответа);
- terminal `(False,r0)` равен **`not-a-word`**, не `false` и не `true`;
- terminal `(True,r)` равен `signed.terminal(ir,r)`.

Все состояния после положительного числа переходов допускают завершение. Это
семантика семейства **положительных** ширин, а не Java-слова нулевой длины.
Если остаточный вектор возвращается в `r0` после чтения битов, `(True,r0)` и
`(False,r0)` всё равно различны. Например, постоянный предикат имеет одну
остаточную векторную конфигурацию, но два состояния этого completion-контракта.

Поэтому последующее число классов нельзя без оговорок сравнивать с фактором
старой модели, где terminal начальной точки был обычным Boolean. Новый consumer
наблюдает дополнительно допустимость завершения. У трёх retained PR24 методов
получилось по 6 состояний: 1 initialization-only + 5 положительных residual.
Для иных методов добавленное различение может увеличить число состояний/классов.

## Что проверяет checker и почему носитель точен

Certificate хранит IR, carrier со строго ранними parent-свидетелями и inspection
копию полной модели. Checker заново разбирает **переданный пользователем** source
и selection; проверяет точный IR и source/request/contract/completion bindings.
Для каждой записи проверяются типы и границы residual-координат; Python `bool`
не принимается вместо integer. Начальное состояние должно быть ровно `(False,r0)`.
Каждое следующее состояние имеет реального более раннего родителя и символ.

Затем **все** model-переходы и terminal-метки восстанавливаются из source-семантики.
Отсутствие любого successor отвергается. Полная сериализованная таблица должна
совпасть с восстановленной, включая алфавит, начальную точку и binding.
Пересчитанный хеш произвольной таблицы не проходит это требование.

Аргумент точности относительно принятой остаточной семантики:

1. Индукция по ранним parent-ссылкам: каждое представленное состояние достижимо.
2. Начальная точка представлена; замкнутость под обоими символами даёт по индукции
   представление любой конечной трассы. Значит, ничего достижимого не пропущено.
3. Локальная модель использует ровно `T`; та же индукция сохраняет пару `(h,r)`.
4. Для непустой трассы `h=True`, и её terminal совпадает с принятой
   `signed.terminal`. В модульной cut-семантике последняя прочитанная позиция — знак;
   арифметические carry и atom-регистры имеют прежний смысл.

Это не новый Lean theorem и не формализация корректности Python parser.
Связь с Java зависит от неизменного принятого frontend и residual-контракта;
finite Java-валидация ниже проверяет реализацию на физических ширинах отдельно.

Носитель общего `Model` ограничен 64 состояниями. Мост не принимает 512 состояний
только потому, что старый inference-v3 способен их перечислить. Есть тест на
ровно 64 состояния и отдельное исчерпание для большего residual-носителя.
Проверка не синтезирует partition и не импортирует producer, subprocess или SMT.
Она проверяет сертификат полного носителя, а не запускает поиск наблюдений.

## Development-валидация и регрессии

```sh
python -m unittest research.signed_bridge.test_bridge -v
python -O -m unittest research.signed_bridge.test_bridge -v
python -m research.external.frozen_v2.download_sources reproduction/bridge-input
python -m research.signed_bridge.experiment reproduction/bridge-input reproduction/bridge-fresh
python -O -m research.signed_bridge.experiment reproduction/bridge-input reproduction/bridge-fresh --replay
```

Fresh-режим требует JDK и компилирует выбранные точные объявления с `--release 17`.
Повторно используются только три прежних development-метода PR #24 (Guava int,
Guava long, Commons long), а **не** 33 holdout-метода PR #27. Сохраняются полные
source, request, certificate, model, result, native-входы/выходы и manifest.
Native-популяция прежняя: 69,711 + 69,839 + 69,839 = 209,389 входов. Сравниваются
Java, whole-word IR и исполнение bridge-модели. Target здесь не передаётся.

Replay заново проверяет source-model proofs, saved file identities и соответствие
сохранённых native-выходов IR/модели. Он не запускает Java и не превращает запись
о предыдущем исполнении в новое независимое native-измерение. Fresh-process тест
ставит запрет producer/native/SMT импортов **до** загрузки bridge-checker.

Новые тесты охватывают rehashed-подмены всех частей модели, пропуски/дублирование
состояний и переходов, циклы parent, типы, источник/overload/contract, завершения,
неподдерживаемую грамматику, budgets и отказ от перезаписи. Проверяются все входы
ширин 1..7 для 16 выражений в int и long, 20 дополнительных выражений с фиксированным
seed, boundary-слова вплоть до 4096 бит и сохранение старых signed/v3 сертификатов.

## Исторические замки и CI

Полный snapshot-lock PR #26 намеренно отвергает новые модули в изменённом checkout.
Его ограничения не расширяются, ENGINE/REGISTRATION/PROTOCOL и corpus-lock PR #27
не переписываются. Live workflow `frozen-v3-baseline.yml` теперь запускает прежние
исторические проверки на точном принятом PR27 head
`4314dc9d6cae00e52b8262f3653d6f72d31d87e1` (та же tree, что merged PR #27).
Этот workflow-harness не является новым измеряемым evaluator; зарегистрированная
его версия остаётся в истории и в архивном checkout. На новых PR внешняя оценка
не повторяется. Статусы этих jobs относятся к **архивному** снимку.

Новый dedicated workflow проверяет **текущий head**: новые tests, актуальные
регрессии, retained development-эксперимент и независимый replay. Перед/после
проверок он сверяет байты и executable modes всех старых файлов с merged PR #27;
единственное разрешённое изменение старого файла — live archival workflow.
Новые пути перечислены явно. Исторические frozen_v2 1/15 и Run27 2/33 неизменны.

PR #28 не утверждает выигрыш в покрытии, минимальность интерфейса, новый внешний
holdout, универсальный Java frontend, новую Lean-формализацию или готовый v4.
