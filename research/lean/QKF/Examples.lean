import QKF.SourceBridge

namespace QKF

/- Four-bit signed word, lower mask 0011: successor of 0 is 1. -/
example : let s := run wordStep wordStart [2, 1, 0]
    s.width = 3 ∧ s.g = 0 ∧ s.x = 1 ∧ s.t = 1 ∧ s.carry = false := by decide

/- Three-bit signed word, all bits optional: -1 advances to 0. -/
example : let s := run wordStep wordStart [3, 3]
    signed s.g (2 ^ s.width) true = -1 ∧
    signed s.t (2 ^ s.width) (bxor true s.carry) = 0 := by decide

/- The smallest mathematical width has just a sign bit. -/
example : let s := run wordStep wordStart []
    signed s.g (2 ^ s.width) true = -1 ∧
    signed s.t (2 ^ s.width) (bxor true s.carry) = 0 := by decide

end QKF
