import QKFTarget.Create

namespace QKFTarget.Create.Controls

def idKey (z : Nat) := z
theorem idKey_mono : MonotoneKey idKey := by
  intro a b h
  exact h

def interval2to5 (z : Nat) : Prop := 2 ≤ z ∧ z ≤ 5

theorem interval_bounds : Covers interval2to5 2 5 := by
  intro z hz
  exact hz

def bucketOrderGood : Bool :=
  decide (signedWord 4 8 4 ≤ signedWord 4 8 7)

def mixedBucketOrderAgrees : Bool :=
  decide ((signedWord 4 8 7 ≤ signedWord 4 8 1) ↔ (7 ≤ 1))

def commonPrefixPositive : Bool :=
  decide ((fun z => z / 4) 8 = (fun z => z / 4) 11)

def commonPrefixBroken : Bool :=
  decide ((fun z => z / 4) 8 = (fun z => z / 4) 12)

def emptyExact : Bool :=
  decide (¬ ∃ z : Nat, z < 0)

def unstableStep (n : Nat) : Nat := n + 1
def stableStep (n : Nat) : Nat := if n < 2 then n + 1 else n

def thirdPassPositive : Bool :=
  decide (stableStep (stableStep (stableStep 0)) = stableStep (stableStep 0))
def thirdPassWithoutNormality : Bool :=
  decide (unstableStep (unstableStep (unstableStep 0)) = unstableStep (unstableStep 0))

def positiveExamples : Bool :=
  bucketOrderGood &&
  !mixedBucketOrderAgrees &&
  commonPrefixPositive &&
  !commonPrefixBroken &&
  emptyExact &&
  thirdPassPositive &&
  !thirdPassWithoutNormality

theorem positive : positiveExamples = true := by decide

end QKFTarget.Create.Controls
