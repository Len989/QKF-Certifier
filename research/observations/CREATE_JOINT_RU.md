# Полный caller-carrier для `IntegerStamp.create`

Этот этап связывает ранее проверенные нисходящий и восходящий helper-профили с
реальным шестипараметрическим `IntegerStamp.create`. Он не вводит новый
универсальный Java frontend: принимается ровно закреплённая форма caller,
конструкторов, фабрик и используемых примитивов.

## Что утверждается

Для поддержанных Graal ширин 1, 8, 16, 32 и 64 рассматривается множество значений,
которые одновременно:

- лежат между входными signed lower/upper;
- содержат все биты `mustBeSet`;
- не содержат битов вне `mayBeSet`;
- исключают ноль, если `canBeZero == false`.

Сертификат утверждает для точного pinned caller:

1. `Empty` возвращается тогда и только тогда, когда это множество пусто;
2. непустой результат задаёт то же множество;
3. его lower/upper — точные signed extrema;
4. предусловия обоих helper-контрактов выводятся из состояния caller;
5. гарантии монотонности цикла выполняются;
6. не более двух проходов могут изменить состояние, третий — проверка fixed point.

Последнее соответствует фактическому `ITERATION_LIMIT = 3`, но не принимается
из комментария исходника как доказательство.

## Joint carrier

Checker использует четыре смысловые фазы:

```
entry
  ↓
exact_extrema
  ↓
prefix_closed_extrema
  ↓
stable
```

Первый существенный проход сохраняет денотацию и получает точные допустимые
границы. Следующий common-prefix refinement добавляет только масочные факты,
истинные для каждого значения между уже точными extrema, поэтому множество не
меняется. Повторное получение extrema после этого ничего не меняет; следующий
проход подтверждает fixed point.

Это логические фазы доказательства, а не утверждение, что каждый конкретный
вызов обязательно выполняет ровно три Java-итерации. Ранний `Empty`,
unrestricted delegate и fixed point после первого прохода сохраняются.

## Как получаются helper premises

Нисходящий dependency — уже проверенный exact maximum для `setOptionalBits`.
Восходящий dependency — уже проверенный exact cyclic successor для выбранного
региона `computeLowerBound`.

Caller обязан установить условия их применения. В частности:

- маски helper-вызова совпадают с текущими caller masks;
- descending seed является минимумом соответствующего sign bucket;
- seed не больше bound;
- floor-result восходящего этапа принадлежит тому же carrier;
- если нужен successor, из `floor < bound <= bucket maximum` следует
  существование большего legal word, поэтому cyclic wrap невозможен.

Особенно важна **sign condition**. Helper certificates организованы по unsigned
nonsign payload. Перед использованием order-результата caller clamp и
common-prefix masks фиксируют sign bit. В одном sign bucket Java signed order и
порядок nonsign payload совпадают. Эта связь является отдельным правилом
caller-checker и не подменяется предположением «helper обычно работает».

## Source binding

`create_source.py` заново токенизирует внешний исходник и требует точного
совпадения выбранных тел с retained source-identical fixture:

- six-argument `create`;
- three-argument range create и constant factory;
- четыре используемых конструктора;
- `contains` с zero-hole special case;
- `isEmpty`;
- `minValueForMasks`, `maxValueForMasks`;
- `computeUpperBound`, `setOptionalBits`, `computeLowerBound`.

Отдельно связываются `ITERATION_LIMIT = 3`, CodeUtil `minValue`,
`maxValue`, `signExtend` и две допустимые реализации empty factory:
retained direct fixture либо настоящий Graal cache вместе с точной
инициализацией cache.

Те же внешние байты снова разбираются существующими descending/ascending
frontends; SHA служат идентификаторами, а не заменой обязательств.

## Независимая проверка реализации

`create_math.py` — транскрипция caller, включая Java long overflow временных
сумм. Её не используют как единственный oracle.

`create_validation.py` сравнивает её с тремя независимыми источниками:

1. полным перечислением точного множества на малых ширинах;
2. отдельным signed-order digit-DP, который решает существование/extrema и
   эквивалентность interval+mask множеств без исполнения caller;
3. нативным выполнением source-identical Java fixture на физических ширинах.

Эти конечные проверки ловят ошибки реализации, но сами по себе не превращаются
в all-input theorem.

## Доверенная граница

Новый Python checker доверяет явно версионированным caller rules:
common-prefix preservation, signed-bucket bridge, адаптацию exact extrema и
двухобновленческую стабилизацию. Helper certificates при этом независимо
replay-ятся прежними checker'ами.

Это **не новая Lean-теорема**. Следующий формальный этап должен перенести
descending/caller bridge и stabilization argument в Lean. Также не заявляются:

- произвольный Java control flow;
- корректность всего класса `IntegerStamp`;
- все возможные Graal callers;
- новый внешний benchmark;
- расширение публичного `qkf`/PyPI API.

## Воспроизведение

Workflow скачивает точные pinned Graal/OpenJDK файлы и проверяет Git blob identity.

```sh
python -m unittest research.observations.tests.test_create_joint -v
python -O -m unittest research.observations.tests.test_create_joint -v

python -m research.observations.run_create_experiment \
  reproduction/create/input reproduction/create/fresh \
  --native --small-bits 4 --samples 300

python -O -m research.observations.run_create_experiment \
  reproduction/create/input reproduction/create/fresh --replay
```

Пути нового fresh output должны не существовать. Search используется только в
fresh mode; replay заново связывает внешний source/spec и проверяет оба
вложенных helper package без producer, Java или SMT.
