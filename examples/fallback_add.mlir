// A deliberately residual cross-bit example. No full target proof is claimed.
builtin.module {
  func.func @solution(%a: !transfer.abs_value<[!transfer.integer, !transfer.integer]>, %b: !transfer.abs_value<[!transfer.integer, !transfer.integer]>) -> !transfer.abs_value<[!transfer.integer, !transfer.integer]> {
    %x = "transfer.get"(%a) {index=0:index} : (!transfer.abs_value<[!transfer.integer, !transfer.integer]>) -> !transfer.integer
    %y = "transfer.get"(%b) {index=0:index} : (!transfer.abs_value<[!transfer.integer, !transfer.integer]>) -> !transfer.integer
    %sum = "transfer.add"(%x, %y) : (!transfer.integer, !transfer.integer) -> !transfer.integer
    %zero = "transfer.constant"(%x) {value=0:index} : (!transfer.integer) -> !transfer.integer
    %r = "transfer.make"(%sum, %zero) : (!transfer.integer, !transfer.integer) -> !transfer.abs_value<[!transfer.integer, !transfer.integer]>
    func.return %r : !transfer.abs_value<[!transfer.integer, !transfer.integer]>
  }
}
