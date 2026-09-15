import QKFTarget.Masked

/-! Finite semantic controls for the new bridge, not replacements for its proofs.
The driver checks each defective gate is false, then attempts the false claim
in another Lean invocation and requires an actual decision-proof rejection. -/
namespace QKFTarget.MaskedWords.Controls

def smallColumn (c : Fin 5) : Column := ⟨c.val, Nat.lt_trans c.isLt (by decide)⟩

def completeAlphabet : Bool := decide (∀ (i : Input) (b : Bool),
  allowed (inputMust i) (inputMay i) b = true →
  ∃ c : Column, project c = i ∧ rivalBit c = b)

def incompleteAlphabet : Bool := decide (∀ (i : Input) (b : Bool),
  allowed (inputMust i) (inputMay i) b = true →
  ∃ c : Fin 5, project (smallColumn c) = i ∧ rivalBit (smallColumn c) = b)

def rivalReplacedBySeed : Bool := decide (∀ (i : Input) (b : Bool),
  allowed (inputMust i) (inputMay i) b = true →
  ∃ c : Column, project c = i ∧ seedBit c = b)

def outputLeaksRival : Bool := decide (∀ c d : Column,
  project c = project d → rivalBit c = rivalBit d)

def inputProjectionChanged : Bool := decide (∀ c : Column,
  inputSeed (if c.val == 4 then 1 else project c) = seedBit c)

def reversedBitOrder : Bool := value [true, false] == digit true * 2 + digit false

def wrapReturnsMaximum : Bool :=
  value (emitted Original.machine Original.machine.initial [2]) == value ([2].map inputMay)

def membershipSuffices : Bool := decide (∀ (i : Input) (b : Bool),
  allowed (inputMust i) (inputMay i) b = true →
  inputSeed i ≠ inputMay i → digit (inputSeed i) < digit b)

def missingLengthConstraint : Bool := decide (value [false, true] < 2 ^ (1 : Nat))

def positiveExamples : Bool :=
  (value (emitted Original.machine Original.machine.initial [2, 0, 1]) == 4) &&
  (value (emitted Original.machine Original.machine.initial [2, 0, 2]) == 0) &&
  (value (emitted Original.machine Original.machine.initial [3, 0, 3]) == 5) &&
  (value (emitted Original.machine Original.machine.initial [0]) == 0) &&
  (value (emitted Original.machine Original.machine.initial [1]) == 1) &&
  completeAlphabet

-- Compiler-checked controls for gap, wrap, singleton masks and minimum width.
theorem positive : positiveExamples = true := by decide

end QKFTarget.MaskedWords.Controls
