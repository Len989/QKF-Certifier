# Observation Inference v1

Этот этап впервые выбирает конечный source-interface автоматически из исходной
семантики, а не получает готовый набор наблюдений от исследователя.

## Кандидатная библиотека

После существующего source frontend строится достижимый residual carrier.
Библиотека вопросов выводится из типов его координат:

- arithmetic carry / constant tail: `residual[i] == k`;
- accumulated equality mismatch: Boolean projection;
- persistent Boolean register: Boolean projection;
- ascending arithmetic offset: `offset == k`.

Имя Java-метода не выбирает таблицу состояний или готовый профиль наблюдений.
Библиотека пока намеренно конечная и ограниченная equality-проекциями. Это v1,
а не синтез произвольного языка наблюдений.

## CEGAR

Поиск начинается с пустого интерфейса. Если два residual states попали в один
класс, checker требует одинаковые:

1. terminal observations;
2. output для каждого входного символа;
3. quotient-класс продолжения.

При первом нарушении producer выбирает первый library-question, который
разделяет конкретную конфликтующую пару. После достижения стабильности идёт
deletion pruning: наблюдение удаляется, если quotient остаётся стабильным.

Сертификат хранит каждый conflict witness, выбранную проекцию, pruning trace и
финальный partition. Независимый checker заново строит source residual semantics
и library, проверяет весь trace и финальную стабильность. Producer ему не нужен.

## Связь с целью

Для `word_result` inferred quotient напрямую замыкается в product с
независимой word target machine.

Для `boolean_predicate` product использует независимо заданную saturated
popcount target semantics и проверяет terminal agreement.

Для `successor` v1 пока выдаёт только source-interface certificate.
Существующий independent ascending successor proof должен отдельно быть
`certified`. Это явно записывается как
`successor_target_checker_not_connected_v1`; отсутствие нового target bridge
не маскируется статусом certified.

## Пиннинг эксперимента

CI скачивает неизменённые:

- OpenJDK `Long.java` и проверяет `lowestOneBit`;
- Lucene `BitUtil.java` и проверяет `isZeroOrPowerOfTwo`;
- retained source-identical Graal `IntegerStamp.java` для ascending region.

OpenJDK/Lucene проверяются по старым frozen Git blob ID. Сам frozen-v1 engine
не меняется: новый код находится в `research/inference/`, вне его roots.

Это не новый blind benchmark. Те же методы уже использовались ранее; цель
прогона — проверить автоматический выбор интерфейса, а не увеличить внешний
denominator.

## Что считается успехом

- lowbit: inferred stable interface + direct independent target closure;
- terminal predicate: inferred stable interface + direct independent count target closure;
- Graal successor: inferred stable source interface + отдельный прежний
  independent successor certificate;
- irrelevant residual control должен свестись к 1 классу и 0 выбранным
  observations;
- неправильная identity-реализация против lowbit должна дать проверяемое
  `refuted`, а не `unsupported`.

## Граница

Не заявляются:

- произвольные predicates/relations над residual state;
- автоматический вывод новой арифметической абстракции;
- arbitrary Java;
- доказанная минимальность по всем возможным observation languages;
- новый Lean theorem;
- новый frozen external denominator.

Это первый CEGAR-слой над фиксированной source-derived observation library.
Следующий этап может расширять library и учиться предлагать новые типы
наблюдений по failed conflicts.
