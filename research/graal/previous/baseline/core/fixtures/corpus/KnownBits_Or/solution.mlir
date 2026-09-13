builtin.module {
  func.func @solution(%a: !transfer.abs_value<[!transfer.integer,!transfer.integer]>, %b: !transfer.abs_value<[!transfer.integer,!transfer.integer]>) -> !transfer.abs_value<[!transfer.integer,!transfer.integer]> {
    %v0 = "transfer.get"(%a) {index = 0 : index} : (!transfer.abs_value<[!transfer.integer,!transfer.integer]>) -> !transfer.integer
    %v1 = "transfer.get"(%a) {index = 1 : index} : (!transfer.abs_value<[!transfer.integer,!transfer.integer]>) -> !transfer.integer
    %v2 = "transfer.get"(%b) {index = 0 : index} : (!transfer.abs_value<[!transfer.integer,!transfer.integer]>) -> !transfer.integer
    %v3 = "transfer.get"(%b) {index = 1 : index} : (!transfer.abs_value<[!transfer.integer,!transfer.integer]>) -> !transfer.integer
    %v4 = "transfer.and"(%v0, %v1) : (!transfer.integer, !transfer.integer) -> !transfer.integer
    %v5 = "transfer.constant"(%v0) {value = 0 : index} : (!transfer.integer) -> !transfer.integer
    %v6 = "transfer.cmp"(%v4, %v5) {predicate = 1 : index} : (!transfer.integer, !transfer.integer) -> i1
    %v7 = "transfer.constant"(%v0) {value = -1 : index} : (!transfer.integer) -> !transfer.integer
    %v8 = "transfer.and"(%v2, %v3) : (!transfer.integer, !transfer.integer) -> !transfer.integer
    %v9 = "transfer.cmp"(%v8, %v5) {predicate = 1 : index} : (!transfer.integer, !transfer.integer) -> i1
    %v10 = "transfer.or"(%v1, %v3) : (!transfer.integer, !transfer.integer) -> !transfer.integer
    %v11 = "transfer.neg"(%v0) : (!transfer.integer) -> !transfer.integer
    %v12 = "transfer.and"(%v11, %v7) : (!transfer.integer, !transfer.integer) -> !transfer.integer
    %v13 = "transfer.neg"(%v2) : (!transfer.integer) -> !transfer.integer
    %v14 = "transfer.and"(%v13, %v7) : (!transfer.integer, !transfer.integer) -> !transfer.integer
    %v15 = "transfer.or"(%v12, %v14) : (!transfer.integer, !transfer.integer) -> !transfer.integer
    %v16 = "transfer.neg"(%v15) : (!transfer.integer) -> !transfer.integer
    %v17 = "transfer.and"(%v10, %v16) : (!transfer.integer, !transfer.integer) -> !transfer.integer
    %v18 = "transfer.cmp"(%v17, %v5) {predicate = 1 : index} : (!transfer.integer, !transfer.integer) -> i1
    %v19 = "transfer.select"(%v18, %v7, %v16) : (i1, !transfer.integer, !transfer.integer) -> !transfer.integer
    %v20 = "transfer.select"(%v9, %v7, %v19) : (i1, !transfer.integer, !transfer.integer) -> !transfer.integer
    %v21 = "transfer.select"(%v6, %v7, %v20) : (i1, !transfer.integer, !transfer.integer) -> !transfer.integer
    %v22 = "transfer.select"(%v18, %v7, %v10) : (i1, !transfer.integer, !transfer.integer) -> !transfer.integer
    %v23 = "transfer.select"(%v9, %v7, %v22) : (i1, !transfer.integer, !transfer.integer) -> !transfer.integer
    %v24 = "transfer.select"(%v6, %v7, %v23) : (i1, !transfer.integer, !transfer.integer) -> !transfer.integer
    %v25 = "transfer.make"(%v21, %v24) : (!transfer.integer, !transfer.integer) -> !transfer.abs_value<[!transfer.integer,!transfer.integer]>
    func.return %v25 : !transfer.abs_value<[!transfer.integer,!transfer.integer]>
  }
}
