# Lean-формализация caller-инвариантов `IntegerStamp.create`

Этот этап формализует математический остаток после source-bound прогона №19,
не меняя принятые `QKFTarget.Ceiling` и `QKFTarget.MaskedWords`.

## Что теперь проверяет Lean

Новый модуль `QKFTarget.Create` доказывает:

- совпадение signed Java order и payload order внутри фиксированного sign bucket;
- общий interval/common-prefix принцип для любого монотонного observation key;
- сохранение carrier при добавлении common-prefix факта, истинного на точных extrema;
- монотонное сужение старых корректных границ точными extrema;
- точный смысл Empty как отсутствия legal value;
- существование nonwrapping successor witness из floor < bound <= legal maximum;
- финальную третью итерацию как чистое подтверждение fixed point, если после двух
  изменяющих проходов установлен Normal и Normal-состояние является fixed point;
- прямой handoff caller-derived FloorContract/SuccessorContract в уже принятую
  теорему exact ceiling.

## Что НЕ стало Lean-теоремой

Lean всё ещё не разбирает Java и не доказывает, что конкретный текст
`IntegerStamp.create` порождает ровно premises нового модуля. Этот мост
остаётся source-bound Python слоем из PR №19.

Особенно важно: theorem `third_pass_confirmation` не доказывает из воздуха,
что два прохода конкретного Java caller всегда создают Normal. Она доказывает
последний логический шаг: если два изменяющих прохода установили Normal, а
Normal фиксирован source-step, третья итерация обязана быть только проверкой.
Получение Normal из exact extrema + prefix refinement остаётся явным внешним
обязательством.

Таким образом новый этап уменьшает trusted mathematical rules, но не заявляет
полную формальную верификацию Java frontend/source correspondence.

## Acceptance

`check_create.py` требует настоящий Lean 4.33.0, fresh build,
строгий axiom audit десяти theorem, три двухсторонних semantic controls и
изолированный `sorryAx` negative control. Дополнительно он заново проверяет
PR19 source binding и наличие пяти caller rule names, к которым относятся
новые формальные lemmas.

Никакие `sorry`, `admit`, `native_decide`, `bv_decide`, новые axioms
или unsafe declarations в принятом Lean source не допускаются.
