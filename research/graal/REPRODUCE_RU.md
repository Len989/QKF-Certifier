# Воспроизведение

## Проверка сохранённых доказательств

После распаковки ZIP, находясь в `qkf_universal_lower_2026-09-13`:

```bash
python restore_project.py
python replay_saved.py --output reproduction/check_01
python audit_step.py --output reproduction/audit_01.json
```

Восстановление проверяет размеры, SHA-256 и безопасные имена файлов,
распаковывает текущие данные и извлекает обе статьи из точной архивной
истории. Существующий файл с отличающимися байтами не перезаписывается.
Replay запускает семь свежих процессов проверки: текущий lower и всю
предыдущую цепочку universal upper, Graal source/word и теоретических
сертификатов. Поиск и SMT для проверки не требуются.

Нижний сертификат можно проверить отдельно:

```bash
python lower_kernel.py --source previous/baseline/source/IntegerStamp.java --certificate results/main/certificate.json --output reproduction/lower_only.json
```

Каталог `reproduction` сначала должен существовать. Повторно используйте
новые имена результатов. Полная проверка frozen-байтов — `python freeze_step.py`.

## Повторение разработки

Исходные результаты не перезаписывать. `validate_lower.run`, `validate_proofs.run`
и `run_step.run` создают фиксированные каталоги с `exist_ok=False`; для нового
прогона сделайте отдельную рабочую копию и осознанно выберите новые выходные
пути. Сохранённые скрипты показывают точные параметры генераторов и seed.

Java-часть использует прежние pinned JDK и ECJ. `QKF_JAVA_RUNTIME` может
указывать каталог Java runtime; по умолчанию ожидается соседний
`qkf_graal_tools/jdk/jdk4py/java-runtime`, ECJ — соседний
`qkf_graal_tools/ecj-3.42.0.jar`. Java 25.0.2, ECJ 3.42.0; SHA-256 компилятора
и исходников записаны в `native/MANIFEST.json` и в манифестах мутантов.
Полный Graal не собирался: используются прежние точные тела helpers и shims.
Запуск `-da` сохранён; явные GraalError.guarantee остаются активны.

Универсальный API проверяет ширины 1..4096; native Java — до 64. Вне условия
на знак возвращается `unsupported_source_sign_context`, не доказательство.
`joint_empty` обрабатывайте до повторной подачи `refined_spec`: пустой
исходный ответ иногда содержит нижнюю границу вне w-битного диапазона.
