builtin.module {
  func.func @solution(%a: !transfer.abs_value<[!transfer.integer,!transfer.integer]>, %b: !transfer.abs_value<[!transfer.integer,!transfer.integer]>) -> !transfer.abs_value<[!transfer.integer,!transfer.integer]> {
    %v0 = "transfer.get"(%a) {index = 0 : index} : (!transfer.abs_value<[!transfer.integer,!transfer.integer]>) -> !transfer.integer
    %v1 = "transfer.get"(%a) {index = 1 : index} : (!transfer.abs_value<[!transfer.integer,!transfer.integer]>) -> !transfer.integer
    %v2 = "transfer.get"(%b) {index = 0 : index} : (!transfer.abs_value<[!transfer.integer,!transfer.integer]>) -> !transfer.integer
    %v3 = "transfer.get"(%b) {index = 1 : index} : (!transfer.abs_value<[!transfer.integer,!transfer.integer]>) -> !transfer.integer
    %v4 = "transfer.neg"(%v0) : (!transfer.integer) -> !transfer.integer
    %v5 = "transfer.neg"(%v2) : (!transfer.integer) -> !transfer.integer
    %v6 = "transfer.and"(%v4, %v5) : (!transfer.integer, !transfer.integer) -> !transfer.integer
    %v7 = "transfer.neg"(%v6) : (!transfer.integer) -> !transfer.integer
    %v8 = "transfer.and"(%v1, %v3) : (!transfer.integer, !transfer.integer) -> !transfer.integer
    %v9 = "transfer.make"(%v7, %v8) : (!transfer.integer, !transfer.integer) -> !transfer.abs_value<[!transfer.integer,!transfer.integer]>
    func.return %v9 : !transfer.abs_value<[!transfer.integer,!transfer.integer]>
  }
}
