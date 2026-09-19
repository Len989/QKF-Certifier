# Signed terminal predicates v1

Этот профиль появился **после** frozen_v2 holdout из PR #23 и закрывает один
из измеренных классов отказов: positive-only power-of-two predicates.

Он не меняет \`predicate-v1\` и не пересчитывает frozen_v2. Исторический результат
holdout остаётся 1/15. Три метода Guava/Commons ниже используются только как
post-holdout development regression.

## Source profile

Поддерживается один выбранный \`static boolean f(int x)\` или
\`static boolean f(long x)\` с одним homogeneous word type.

Словные операции: unary +, -, ~; binary +, -, &, |, ^; ==, !=; signed
comparisons с нулём <, <=, >, >= и симметричные формы 0 < x и т. п.

Boolean operations: !, &&, ||, а также pure Boolean &, |, ^.

Поскольку calls, assignments inside expressions и другие side effects запрещены,
для разрешённого профиля eager Boolean & имеет тот же truth result, что и
соответствующая логическая conjunction. Это не утверждение об общем Java.

Разрешены leading method annotations. Они не входят в semantic declaration hash,
но полный source_sha256 по-прежнему связывает весь исходный файл.

Для long разрешён обычный Java widening положительных unsuffixed int literals
0..2^31-1, например x - 1. Произвольные numeric conversions не добавлены.

По-прежнему отвергаются shifts, calls, fields, casts, branches, loops, несколько
аргументов и arbitrary word-to-word signed order.

## Signed terminal observation

Сканирование идёт от младших битов к старшим. Для equality atom сохраняется
прежний mismatch_seen. Для comparison word > 0 и других zero-order atoms
сохраняются: был ли встречен хотя бы один установленный bit и последний
прочитанный bit.

После чтения w>0 bits последний bit является sign bit w-битного two's-complement
слова. Поэтому positive = nonzero и sign=0; nonnegative = sign=0;
negative = sign=1; nonpositive = sign=1 или zero.

## Independent target

Schema: \`qkf-signed-word-predicate-goal-v1\`.

Count atoms: popcount_le(k), popcount_eq(k), k=0..3.
Signed atoms: positive, nonnegative, negative, nonpositive.
Разрешены not, and, or, xor.

Positive power of two задаётся независимо от source formula как
\`["and", ["positive"], ["popcount_eq", 1]]\`.

Это существенно отличается от unsigned popcount_eq(1): sign-bit-only negative
value имеет popcount 1, но не является положительной степенью двойки.

## Development cases

После завершённого frozen_v2 используются:
- Guava LongMath.isPowerOfTwo(long);
- Guava IntMath.isPowerOfTwo(int);
- Apache Commons Numbers ArithmeticUtils.isPowerOfTwo(long).

Все исходные blobs остаются теми же, что были заморожены до PR #23.
Их успешность в №24 не меняет frozen denominator и не является новым holdout.

## Trust boundary

Это новый Python-checked mathematical profile, не новая Lean theorem. Replay
заново парсит source, строит terminal source factor, проверяет QKF observation
certificate и closed product с независимым count/sign target. Replay не запускает
producer, Java или SMT. Native Java используется только как отдельная
implementation validation на исходной Java width 32/64.
