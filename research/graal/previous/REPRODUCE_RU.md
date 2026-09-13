# Воспроизведение универсальной верхней границы

Команды выполняются в текущем каталоге рядом с этим файлом. Нужен обычный
Python 3.12; не используйте `-O`/`-OO`. Сохранённые результаты не затираются.
Если каталог reproduction уже использован, укажите новое имя вывода.

## Восстановление и проверка доказательств

```bash
python restore_project.py
python audit_step.py --output reproduction/audit.json
python replay_saved.py --output reproduction/strict
```

restore_project.py проверяет размеры и SHA256, безопасные пути и точную
вложенную историю, восстанавливает текущие данные и 93 файла двух статей.
При повторе проверяет уже имеющиеся файлы; отличающиеся файлы не заменяет.

Аудит проверяет все 343 унаследованных и 428 зафиксированных файлов,
параметрический сертификат, две исходные вариации, 18 специализаций,
знаменатели Java/семантических проверок и прежних пяти процедур Graal.

replay_saved.py запускает 6 свежих процессов проверки: новый общий
сертификат со специализациями; три прежние связки исходник→наблюдение→SSA→
целое слово; 28 прежних совместных сертификатов; прежний двусторонний
ground-сертификат статей. Производители доказательств и SMT блокируются.
Конечное вычисление таблиц и типов порядка внутри checker остаётся частью
проверки. Сеть и Java для этих команд не нужны.

## Повторное производство и известная регрессия

```bash
python run_step.py --output reproduction/main
```

Будет заново произведён и перепроверен общий сертификат, затем все пять
Graal-слотов в обоих прежних режимах. Здесь нет нового внешнего holdout.
Ожидаемые целые результаты: control 1/5, joint 2/5. Новый helper учитывается
отдельно. Старое core-ядро и зафиксированные результаты сохраняются.

Повтор негативных и исходных вариаций:

```bash
python -c 'from pathlib import Path; from validate_certificates import run; run(Path("reproduction/certificates"))'
```

## Конкретное применение общего доказательства

```python
import json
from pathlib import Path
from universal_api import CheckedUpperContract

root = Path.cwd()
source = (root / "baseline/source/IntegerStamp.java").read_text()
certificate = json.loads(
    (root / "results/main/universal_upper/certificate.json").read_text()
)
contract = CheckedUpperContract(source, certificate)
spec = dict(width=4, must=1, may=13, lower=2, upper=7, can_zero=True)
instance = contract.refine(spec)
print(instance["answer"]["maximum"])  # 5
print(instance["joint_empty"])       # False
print(contract.verify_instance(spec, instance))
```

Объект проверяет общий сертификат перед применением. Одна проверенная
конструкция обслуживает много конкретных входов; для них не строится
новое универсальное доказательство. Runtime-лимит — 4096 бит. Входной
контракт требует совместимости масок и корректных знаковых границ.

answer.upper_query_status отличает пустой верхний запрос от настоящего
значения. joint_empty учитывает также дополнительную нижнюю границу.
В refined_spec меняется ровно upper на source_long_result, включая
minimum-sentinel. Сравнивать число с minimum для определения пустоты нельзя.

## Необязательная сверка с JVM

Установленный runtime не включён в архив. Для Linux x86_64 можно поставить
точно зафиксированные JVM и ECJ через сохранённый helper предыдущего этапа:

```bash
python baseline/reproduce_tools.py --directory ../qkf_graal_tools
```

Если установка уже существует, этот helper откажется её заменять. Для
готовой JVM по другому пути задайте `QKF_JAVA_RUNTIME` абсолютным путём
к каталогу java-runtime. native_upper.py сам задаёт пути её библиотек.
Применялись jdk4py 25.0.2.1 и ECJ 3.42.0; URL и хеши сохранены в baseline.

Классы native/classes уже включены, их исходники и хеши проверены. Для
повторения всей конечной валидации:

```bash
python -c 'from pathlib import Path; from validate_semantics import run; run(Path("reproduction/semantics"))'
```

Это 114 040 вызовов исходного верхнего helper и отдельная проверка
24 174 совместных диапазонов. Python-математическая часть также проверяет
96 sparse-word входов ширин 128,256,4096. Остальные широкие случаи относятся
к ширинам 8,16,32,64. Native-часть не исполняет Java за пределами 64 бит.

native_upper.py при запуске как основного скрипта предназначен для сборки
в новой development-копии, где каталог native ещё не существует. Он не
перезаписывает готовую сборку. Новый Java harness добавляет только команду
верхнего helper; исходные алгоритмические тела остаются неизменными.

## История и сборка полного пакета

baseline содержит неизменную рабочую копию предыдущего проекта. Для его
исторического самостоятельного восстановления используйте точный архив
в prior_stage, а не запускайте старый restore из baseline.

Точный предыдущий архив: QKF_JOINT_CARRIERS_2026-09-13.zip,
SHA256 `9e27a2fb575d4717e6b6110db0fb83a9354203f6110e34affa8ec271f7535686`.
Вся его вложенная история сохранена. Для статей проверяется цепочка
Joint Carriers → Graal Transfer → Result Observations → Context Observations.

Повторная сборка после восстановления:

```bash
python build_package.py --prior prior_stage/QKF_JOINT_CARRIERS_2026-09-13.zip --output ../QKF_UNIVERSAL_UPPER_REBUILT.zip
```

Имя результата должно быть новым. Манифесты описывают каждый байт текущего
материала и файлов статей; старый ZIP включается побайтно. Бинарный ZIP
может иметь иные метаданные времени при повторной сборке, но его содержимое
проверяется по тем же хешам. RESTORE_CHECK.json фиксирует чистую проверку
перед передачей текущего пакета.
