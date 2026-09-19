# Единый исследовательский запуск целей

Этот слой объединяет уже принятые исследовательские профили, не меняя их математические ядра и внутренние форматы доказательств. Он намеренно находится в `research/`, а не в устанавливаемом `src/qkf_certifier`: публичный пакет пока не обещает поддержку всех исследовательских Java-профилей.

## Один внешний формат

`qkf-target-v1` выбирает один из четырёх существующих маршрутов:

- `word_result` — выбранный `static long -> long` метод из `research.wordexpr`;
- `boolean_predicate` — выбранный `static int/long -> boolean` метод;
- `successor` — опубликованный восходящий Graal-профиль и общий язык наблюдений;
- `masked_bound` — опубликованный нисходящий профиль и общий язык наблюдений.

Для первых двух видов `source.entry` задаёт класс и метод, а `source.word_type` задаёт `long` либо `int/long` соответственно. Для двух Graal-профилей source равен `{"profile":"ascending"}` или `{"profile":"descending"}`. `goal` компилируется в существующую внешнюю спецификацию соответствующего профиля. Сертификат не может выбрать другой движок или ослабить цель.

## Единый proof envelope

`qkf-unified-proof-v1` хранит точный kind/engine, SHA-256 исходного текста, хеш внешней цели и скомпилированной спецификации, неизменённый внутренний сертификат/пакет и сохранённый результат.

Команда `check` заново компилирует внешнюю цель и запускает прежний независимый checker. Она не импортирует producer, не выполняет Java и не запускает SMT. Внутренние форматы `qkf-word-expression-certificate-v1`, `qkf-word-predicate-certificate-v1` и `qkf-research-package-v2` не меняются.

## CLI

```sh
python -m research.unified.run prove Source.java --target target.json --proof proof.json
python -O -m research.unified.run check Source.java --target target.json --proof proof.json
```

Путь proof при `prove` должен быть новым. Статусы сохраняют смысл существующих движков: `certified`, `refuted`, `unsupported`, `budget_exhausted`, `invalid_certificate`, `input_error`, `internal_error`.

Этот runner не является новым доказательным алгоритмом и не увеличивает внешнее покрытие. Его задача — дать одну точку входа, единый binding и единый replay поверх уже проверенных профилей. Lean-теоремы и публичный PyPI API этим этапом не расширяются.

## Проверка

```sh
python -m unittest research.unified.test_unified -v
python -O -m unittest research.unified.test_unified -v
python -m research.unified.experiment
```

Smoke-experiment содержит пять случаев: положительный word-result, положительный Boolean predicate, положительный successor, положительный masked maximum и сохранённый строгий descending-вариант, который должен быть `refuted`. Это регрессия существующих результатов, а не новая выборка.
