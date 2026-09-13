# Сравнение SMT: ширина 32, 1000 мс, одно повторение

| Контракт | Кодирование | Решатель | UNSAT | SAT | Не решено | Время процессов, с |
|---|---|---|---|---|---|---|
| historical | prefix | z3 | 8 | 9 | 22 | 34.25 |
| historical | prefix | bitwuzla | 10 | 18 | 11 | 21.11 |
| historical | prefix | cvc5 | 3 | 3 | 33 | 49.97 |
| historical | balanced | z3 | 12 | 16 | 11 | 27.12 |
| historical | balanced | bitwuzla | 12 | 20 | 7 | 15.34 |
| historical | balanced | cvc5 | 3 | 6 | 30 | 45.24 |
| artifact | prefix | z3 | 13 | 0 | 26 | 38.38 |
| artifact | prefix | bitwuzla | 13 | 0 | 26 | 33.53 |
| artifact | prefix | cvc5 | 4 | 0 | 35 | 52.12 |
| artifact | balanced | z3 | 19 | 0 | 20 | 32.74 |
| artifact | balanced | bitwuzla | 18 | 0 | 21 | 28.51 |
| artifact | balanced | cvc5 | 5 | 0 | 34 | 47.71 |
| llvm | prefix | z3 | 15 | 0 | 24 | 36.79 |
| llvm | prefix | bitwuzla | 13 | 0 | 26 | 33.62 |
| llvm | prefix | cvc5 | 5 | 0 | 34 | 52.22 |
| llvm | balanced | z3 | 19 | 0 | 20 | 30.32 |
| llvm | balanced | bitwuzla | 17 | 0 | 22 | 28.43 |
| llvm | balanced | cvc5 | 6 | 0 | 33 | 46.88 |

Время — полные процессы. Создание запросов учтено отдельно. SAT проверен на исходном SSA; UNSAT не распространяется на другие ширины.
