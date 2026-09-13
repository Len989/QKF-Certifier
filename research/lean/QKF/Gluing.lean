import Std

/-! A generic induction principle. Finite certificates supply a closed carrier;
the theorem below is about every list length, not a bounded unrolling. -/
namespace QKF

def run {S A : Type} (step : S → A → S) (initial : S) : List A → S
  | [] => initial
  | a :: rest => run step (step initial a) rest

theorem run_simulation {S T A : Type} (stepS : S → A → S) (stepT : T → A → T)
    (f : S → T) (commute : ∀ s a, f (stepS s a) = stepT (f s) a)
    (xs : List A) (s : S) : f (run stepS s xs) = run stepT (f s) xs := by
  induction xs generalizing s with
  | nil => rfl
  | cons a rest ih => simpa only [run, commute] using ih (stepS s a)

theorem run_relation {S T A : Type} (stepS : S → A → S) (stepT : T → A → T)
    (R : S → T → Prop)
    (preserves : ∀ s t, R s t → ∀ a, R (stepS s a) (stepT t a))
    {s : S} {t : T} (initial : R s t) (xs : List A) :
    R (run stepS s xs) (run stepT t xs) := by
  induction xs generalizing s t with
  | nil => exact initial
  | cons a rest ih => exact ih (preserves s t initial a)

theorem closed_certificate_sound {S A : Type} {n : Nat}
    (step : S → A → S) (states : Fin n → S) (edges : Fin n → A → Fin n)
    (initial : Fin n) (good : S → Prop)
    (closed : ∀ i a, step (states i) a = states (edges i a))
    (ends : ∀ i, good (states i)) (xs : List A) :
    good (run step (states initial) xs) := by
  have simulation := run_simulation edges step states
    (fun i a => (closed i a).symm) xs initial
  rw [← simulation]
  exact ends _

end QKF
