# PR30: исполнитель проверенного signed-интерфейса через атомные строки

Продолжает принятый PR29. После одной полной проверки source-bound пакета
исполнитель хранит только классы, terminal-метки, атомные прообразы и скалярные
идентификаторы связи с исходником. В исполнителе нет исходного текста, IR,
остаточных состояний, модели `Model`, объекта сертификата или прямой таблицы
`cells`. При чтении очередного бита семантика исходника больше не вызывается.

Это самостоятельный runtime, не новый алгоритм наблюдательного замыкания.
Общее ядро уже строило атомные строки и восстанавливало из них `cells` в PR29.
Старые frontend, checker, producer, сертификаты и исторические результаты
остаются неизменными. Новый независимый target относится к следующему PR31.

## API: проверка один раз, исполнение многократно

```python
from pathlib import Path
from research.signed_bridge.cli import load as load_json
from research.signed_bridge.model import request
from research.signed_runtime.runtime import load

text = Path("research/inference/examples/SignedPower.java").read_text()
selection = request({"class": "SignedPower", "method": "isPowerOfTwo"}, "long")
proof = load_json("observations.json")  # обычный source-bound пакет PR29
runner, receipt = load(text, selection, proof)

assert runner.value(1, 64) is True
assert runner.value(1 << 63, 64) is False
prefix = runner.start().feed("1")        # сначала младший бит
assert prefix.finish() is False         # одноразрядное знаковое слово -1
assert prefix.feed("0000000").finish() is True  # восьмиразрядное слово 1
```

`receipt.status == source_runtime_verified` означает
`claim: source_row_runtime_equivalence`. Всегда `target_checked: false` и
`lean_checked: false`. Программа без положительного guard получает интерфейс
своего фактического поведения, а не сертификат положительной степени двойки.

`runner.value(raw, width)` принимает **сырой неотрицательный код** слова,
`1 <= width <= 4096` и `0 <= raw < 2**width`; вне диапазона нет скрытого modulo.
`runner.run(symbols)` принимает LSB-first последовательность строковых символов
`"0"` и `"1"`, в том числе генератор. `start().feed(...)` допускает продолжения
по частям и независимые ветви от одного неизменяемого префикса. По умолчанию и
максимально — 1 048 576 битов на цепочку; `max_bits` может уменьшить бюджет.
Это предел API исполнения, не предел условного математического утверждения.

Нулевая длина имеет метку `not-a-word`, и `finish()` не возвращает Boolean для
пустого слова. Последний бит задаёт знак; промежуточные переходы выдают только
`_`. Ошибка входа или `ExecutionLimit` не меняет уже полученный immutable cursor
и не выдаёт частичный результат. Генератор входных символов может быть частично
прочитан при ошибке: его внешние побочные эффекты не откатываются.

## Почему это исполнение строк, а не доверие к сохранённому графу

Для каждой пары входного символа и выходной метки row хранит `k` масок
`h({j}) = {i: output(i)=y, next(i)=j}`. Загрузчик сначала вызывает **неизменённый**
source/observation replay PR28–29. Он проверяет нативные метки атомов, guard,
пустую ячейку, правило finite-unions, ядро, полноту и устойчивость фактора.

Затем immutable `AtomicRow` хранит только образы атомов. Для любого подмножества:

`h(P) = OR(h({j}) for j in P)`.

Непересекающиеся образы атомов обеспечивают сохранение пересечений; объединения
обеспечены конструкцией. Guard равен объединению всех атомных образов; ядро —
равенство после проекции на атомы с непустыми образами. `image` и `same_image`
предоставляют это действие без раскрытия таблицы размера `2**k`.
Для одноэлементного generic carrier пустая ячейка должна быть проверена нативно,
как в старом checker; `h(empty)=empty` не выводится из несуществующей пары атомов.

`Machine.step(i,a)` находит единственную пару `(y,j)`, для которой бит `i`
содержится в атомном прообразе `h[a,y]({j})`. При построении машины проверены
непересечение guard разных выходов и точное покрытие всех исходных классов.
В загрузчике восстановленное действие дополнительно сравнивается с уже
проверенными `cells`; эти `cells` не копируются в runtime и не используются при
последующем исполнении. Потоковый cursor хранит только номер класса и длину.

Условное обоснование: PR28 связывает исходник и остаточную модель; PR29
связывает эту модель и размеченный фактор; нативные атомы однозначно определяют
его шаг. Индукция по последовательности битов сохраняет соответствие класса.
Защищённые terminal-метки дают тот же Boolean на любой положительной ширине в
принятом модульном профиле. Это не новая Lean-теорема о Python или Java.
Связь с III — атомные строки и их реальное потребление (§7.3–7.4), не общее
увеличение вынужденной области из статьи I: здесь атомы порождают весь носитель.

## Граница доверия

Только `runtime.load(source, request, PR29_certificate)` устанавливает
соответствие источнику. Публичные конструкторы `core.AtomicRow`, `core.Machine`
и `Runner` сами по себе проверяют структуру, а не доказательство об исходнике.
`runner.describe()` выдаёт отсоединённый inspection view **не сертификат**;
загрузки такого JSON без исходного доказательства намеренно нет.
Изменение меток при одинаковом ядре требует нового source-bound доказательства.

После загрузки изменение исходных словарей/inspection view не меняет runtime.
Frozen dataclasses и tuple защищают обычный API от случайной мутации, но это
не sandbox против враждебного Python, reflection или изменения кода процесса.
Конкурентная мутация аргументов во время снимка также вне контракта.
Frontend, остаточная семантика, существующие checkers и новый код исполнения
остаются доверенными реализациями. Построение модели по-прежнему ограничено
64 состояниями; runtime не обходит и не увеличивает этот предел.

## CLI

```sh
# Создать обычный пакет существующей командой PR29:
python -m research.signed_observations.cli infer research/inference/examples/SignedPower.java --class SignedPower --method isPowerOfTwo --word-type long --certificate observations.json
# Проверить и показать исполнение:
python -m research.signed_runtime.cli inspect research/inference/examples/SignedPower.java --class SignedPower --method isPowerOfTwo --word-type long --certificate observations.json
python -m research.signed_runtime.cli run research/inference/examples/SignedPower.java --class SignedPower --method isPowerOfTwo --word-type long --certificate observations.json --raw 1 --width 64
python -O -m research.signed_runtime.cli run research/inference/examples/SignedPower.java --class SignedPower --method isPowerOfTwo --word-type long --certificate observations.json --bits 10000000
```

CLI проверяет пакет один раз на вызов. Для многих слов за одну проверку нужен
API с сохранённым `runner`. Коды: 0 — проверено/исполнено (в том числе Boolean
false), 2 — unsupported или execution_budget_exhausted, 3 — invalid_certificate,
64 — input_error, 70 — internal_error. Ни один код не является target verdict.
CLI ничего не перезаписывает и не создаёт новый формат proof.

## Тесты и development-эксперимент

```sh
python -m unittest research.signed_runtime.test_runtime -v
python -O -m unittest research.signed_runtime.test_runtime -v
python -m research.external.frozen_v2.download_sources reproduction/rows-input
python -m research.signed_observations.experiment reproduction/rows-input reproduction/rows-prior
python -m research.signed_runtime.experiment reproduction/rows-input reproduction/rows-prior reproduction/rows-runtime
python -O -m research.signed_runtime.experiment reproduction/rows-input reproduction/rows-prior reproduction/rows-runtime --replay
```

Только создание `rows-prior` запускает Java и поиск PR29. Новый experiment
проверяет существующие восемь пакетов и native records, а потом сравнивает новый
row runtime с проверенной прямой таблицей и IR. Это три прежних PR24 метода и
пять constructed случаев, **не** повтор Run27 и **не** новый внешний holdout.
Ожидается 209 389 сверок с native records, 2 550 constructed сверок и 176
отдельных wide-control сверок. Первые два числа сохраняют знаменатели PR29.

Время генерации/Java берётся из отдельной записи предыдущего этапа; время
полной загрузки, сравнительного прохода и трёх тёплых повторов по 2048 входов
измеряется отдельно. Прямая таблица — только контроль. Перебор атомов может быть
медленнее; общего ускорения и сравнения с SMT этот PR не утверждает. Replay не
переизмеряет старые timings. Полная доверенная цепочка проверяется при загрузке,
а не заменяется контрольной суммой runtime-view.

Новый workflow проверяет текущий PR и все 196 выбранных прежних тестов. Старый
live workflow замыкания явно закреплён за PR29, чтобы сохранить его строгую
проверку добавленных путей; это архивная регрессия, не тест нового кода. Остальные
файлы, замки корпуса и результаты 1/15 и 2/33 не меняются.
