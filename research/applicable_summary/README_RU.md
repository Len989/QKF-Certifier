# PR45 — применимая проверенная сводка

Экспериментальный SDK объединяет выпуск, независимую проверку, применение и
объяснение достаточной сводки. Нужны полный checkout и Python 3.10+; новых
зависимостей нет. Установленный `qkf` сохраняет свой прежний контракт.

```bash
python -m research.applicable_summary.example
```

Пример строит условную Boolean-сводку, проверяет переносимый пакет, применяет
его к трём словам и проверяет новую, отдельно заданную формулу потребителя.
Исполнение исходника при `apply` отсутствует. Формат и доверенная часть
описаны в [FORMAT_TRUST_RU.md](FORMAT_TRUST_RU.md), результаты — в
[VALIDATION_RU.md](VALIDATION_RU.md).

## Поддержанные задачи

| Профиль | Доказанная связь и применимая область | Выбор по умолчанию |
|---|---|---|
| `modular-lsb-signed-word-predicates-v1` | На точных `G` и ширине Boolean-источник равен независимому target; target использует знак, popcount 0..3 и Boolean-связки | Общий native-контекст PR43/44, `no_lemmas` |
| `graal-ascending-physical-phases-v1` | Запрошенные прообразы подмножеств трёх физических фаз в одной `(m,a,g,y)` ячейке | `direct_cell` |
| Импорт PR41/43/44 | Полная проверка исходного consumer-сертификата в его прежнем формате | Явный `from_certificate` |
| Импорт coverage | Проверка уже имеющегося covered-сертификата и его условного потребителя | Только явный импорт; новый `build` не строит legacy-модель |

Профили не смешиваются. Фазовый результат не является утверждением о целом
слове или Java-методе. Boolean-сводка не описывает поведение вне `G`, и не
является полным интерфейсом всех свойств программы. All-positive и fixed-width
обязательства различаются. Runtime принимает ширины 1..4096; математическая
all-positive гарантия исходного сертификата сохраняется.

Решения A1/A2 действуют: `reuse` и `direct_cache` для signed-профиля включаются
явно; `forcing`, `direct_seeds`, `no_saturation` — явные варианты локального
фазового профиля. PR45 не устанавливает окупаемость этих механизмов. Новая
полная причинная оценка остаётся PR46.

## SDK

```python
from research.applicable_summary import build, check, refine
from research.applicable_summary.contract import signed_request

source = '''class Demo { static boolean f(long x) {
    return (x<0) && (((x+x)&1)==0);
} }'''
target = {
    "schema": "qkf-target-v2", "kind": "signed_boolean_predicate",
    "source": {"entry": {"class": "Demo", "method": "f"}, "word_type": "long"},
    "goal": ["negative"],
}
request = signed_request(target, guards=[["popcount_le", 1]])
packet, result, work = build(source, request)
if packet is not None:
    summary = check(source, request, packet)
    if summary.result()["applicable"]:
        value = summary.apply(128, width=8)  # True; unsigned encoding of -128
        dependencies = summary.explain()
```

`signed_request` принимает один target или список до 64 независимых targets.
`width=8` выбирает fixed width; без `width` — все положительные ширины.
Для фазового профиля используется `phase_request(label, goals)`.

- `build(source, request, route=None, limits=None)` возвращает packet или `None`,
  результат и оплаченный backend/work отчёт. Все новые стадии экспорта и
  проверки измерены отдельно. `max_work` и остальные `limits` относятся к
  выбранному backend; сериализация/checker также имеют фиксированные
  структурные ограничения. Это не общий wall-time лимит всего SDK.
- `check(source, independent_request, packet)` повторяет проверку оснований
  и выдаёт immutable `CheckedSummary`. Источник передаётся отдельно; изменение
  даже его текстовой идентичности требует новой проверки. Receipt не принимается.
- `summary.apply(unsigned_word, width=w)` возвращает Boolean. Точный guard,
  диапазон входа и ширина проверяются до выдачи значения. Для phase-профиля
  `summary.apply(subset)` возвращает только уже доказанный прообраз.
- `summary.assess(new_request)` проверяет достаточность для нового потребителя.
  Signed-формула сравнивается с проверенным действием на точном конечном
  пространстве capped-popcount/sign. Это target-семантика, без запуска source.
  Иные `G`, width, selection/profile, неподтверждённая цель или неизвестная
  phase-ячейка не получают положительный ответ.
- `summary.explain(goal=0, consumer=None)` возвращает проверенные основания
  выбранной цели; для новой достаточной цели добавляет ссылку на исходную
  доказанную цель и проверку классов. Минимальность объяснения глобально не
  заявляется. Импортированные старые форматы сохраняют свой полный basis.
- `refine(source, summary, new_request, ...)` явно запускает новый build для
  того же текста source. Он не обещает incremental search и не переносит
  основания между изменёнными программами. Старый объект остаётся проверенным
  только для своего контракта.

`result()`/`interface()`/`export()` возвращают отделённые JSON-копии. Объект
нельзя восстановить из pickle; новый процесс получает packet и проверяет его.
Это граница обычного Python API, без защиты от reflection/monkeypatching
внутри доверенного процесса.

## Прямое доказательство

Основной signed-route получает source/native-факты PR43/44 и экспортирует
только зависимости завершённых доказательств. В новом DAG есть checked native
facts и выведенные равенства; каждая ссылка ведёт строго назад. При наличии
общей леммы новая цель явно использует transitivity через её правую часть.

Неиспользованные native facts, proof events и леммы удаляются. Термы и ссылки
перенумеровываются, после чего независимый checker повторно проверяет каждый
шаг. Если нужный промежуточный congruence-терм теряет первоначальное объявление
в удалённом равенстве, его синтаксис удерживает рефлексивный структурный запрос
`t=t`. Он не добавляет аксиому или пользовательскую гарантию.

В процессе построения всё ещё используется минимальный native-пакет PR44,
который разбирается перед экспортом нового DAG. Поэтому это прямой путь от
потребительских доказательств, а не утверждение об отсутствии временных копий
или единственной сериализации. Полная legacy-модель и её pair separators
на новом пути не строятся. Цена промежуточной упаковки и повторных проверок
остаётся в отчёте; ускорение этого пути не заявляется.

Если batch содержит unresolved lower model, сохраняется исходная scoped
презентация PR44. Удаление предпосылок из отрицательной модели могло бы изменить
её смысл. Такой пакет проверяется, но не создаёт недоказанную исполняемую
сводку. Если в mixed batch есть отдельная доказанная цель, только она может
служить основанием применимого действия.

## Исходы и отказы

`certified`, `refuted`, `unresolved`, `unsupported`, `verified_empty_domain`
различаются. Для budget возвращается `unresolved / resource_budget`, без
частичного packet. Нижняя модель и исчерпание policy не становятся source
контрпримером. Пустой `G` явно вакуозен и не даёт полезного runtime-входа.

Положительный checker допускает source parsing и проверку локальных правил,
но не выполняет исходную программу целиком. Конкретное signed-опровержение
заново вычисляет source на указанном word, проверяет `G` и width. Фазовое
опровержение относится только к локальному множеству физических фаз.

`apply` вне проверенного guard/width вызывает `OutsideDomain`; неизвестная
ячейка или отсутствие положительного основания — `NotApplicable`.
Несовпадение нового target с доступной сводкой даёт `refinement_required`,
без выдачи абстрактного разделителя за конкретный source-контрпример.

## CLI и воспроизведение

```bash
python -m research.applicable_summary build source.java --request request.json --proof packet.json --work work.json
python -O -m research.applicable_summary check source.java --request request.json --proof packet.json
python -m research.applicable_summary apply source.java --request request.json --proof packet.json --input 128 --width 8
python -m research.applicable_summary assess source.java --request request.json --proof packet.json --consumer new-request.json
python -m research.applicable_summary explain source.java --request request.json --proof packet.json --goal 0
```

CLI каждый раз загружает и проверяет packet. Для warm application используется
SDK-объект. Output paths должны быть новыми. Exit codes: 0 — certified/empty
или успешное apply/explain; 1 — refuted/unresolved/unsupported либо выход за
область применения; 2 — некорректный ввод, сертификат или файловая операция.
Malformed JSON/типизированный запрос не является семантическим опровержением.

```bash
python -m research.regression.run
python -O -m research.regression.run
python -m research.applicable_summary.preserve
python -m research.applicable_summary.experiment reproduction/applicable_summary/fresh
python -m research.applicable_summary.replay reproduction/applicable_summary/fresh
python -O -m research.applicable_summary.replay reproduction/applicable_summary/fresh
```

`fresh` должен отсутствовать. Replay ставит запрет planner/producers/SMT до
импорта checker; actual-call guard запрещает Java/subprocess, скрытую legacy
сборку и полное source-исполнение при положительной проверке и применении.
Диагностика budget, время и поиск не объявляются математическим сертификатом.
