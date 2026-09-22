import Ground

set_option maxRecDepth 16384
set_option maxHeartbeats 8000000

namespace QKFGround.Examples

def gap_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def gap_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[0, 1]]⟩],
   [⟨[2], 2⟩]⟩
theorem gap_accepted :
    checkRaw gap_request gap_certificate = true := by decide +kernel

def flattened_nonminimal_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3), (0, 4)], [(5, 6)]⟩
def flattened_nonminimal_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[0, 1]]⟩],
   [⟨[2], 2⟩]⟩
theorem flattened_nonminimal_accepted :
    checkRaw flattened_nonminimal_request flattened_nonminimal_certificate = true := by decide +kernel

def shared_typed_request : Request :=
  ⟨2, [⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[1, 0], 0⟩, ⟨[], 1⟩, ⟨[0, 0], 0⟩],
   [⟨0, []⟩, ⟨6, [0, 0]⟩, ⟨1, []⟩, ⟨6, [0, 2]⟩, ⟨2, []⟩, ⟨6, [0, 4]⟩, ⟨3, []⟩, ⟨6, [0, 6]⟩, ⟨6, [2, 0]⟩, ⟨6, [2, 2]⟩, ⟨6, [2, 4]⟩, ⟨6, [2, 6]⟩, ⟨6, [4, 0]⟩, ⟨6, [4, 2]⟩, ⟨6, [4, 4]⟩, ⟨6, [4, 6]⟩, ⟨6, [6, 0]⟩, ⟨6, [6, 2]⟩, ⟨6, [6, 4]⟩, ⟨6, [6, 6]⟩, ⟨5, []⟩, ⟨4, [20, 0]⟩, ⟨4, [20, 4]⟩, ⟨4, [20, 6]⟩, ⟨4, [20, 1]⟩, ⟨6, [21, 21]⟩, ⟨4, [20, 3]⟩, ⟨4, [20, 2]⟩, ⟨6, [21, 27]⟩, ⟨4, [20, 5]⟩, ⟨6, [21, 22]⟩, ⟨4, [20, 7]⟩, ⟨6, [21, 23]⟩, ⟨4, [20, 8]⟩, ⟨6, [27, 21]⟩, ⟨4, [20, 9]⟩, ⟨6, [27, 27]⟩, ⟨4, [20, 10]⟩, ⟨6, [27, 22]⟩, ⟨4, [20, 11]⟩, ⟨6, [27, 23]⟩, ⟨4, [20, 12]⟩, ⟨6, [22, 21]⟩, ⟨4, [20, 13]⟩, ⟨6, [22, 27]⟩, ⟨4, [20, 14]⟩, ⟨6, [22, 22]⟩, ⟨4, [20, 15]⟩, ⟨6, [22, 23]⟩, ⟨4, [20, 16]⟩, ⟨6, [23, 21]⟩, ⟨4, [20, 17]⟩, ⟨6, [23, 27]⟩, ⟨4, [20, 18]⟩, ⟨6, [23, 22]⟩, ⟨4, [20, 19]⟩, ⟨6, [23, 23]⟩],
   [(1, 0), (3, 4), (5, 0), (7, 0), (8, 2), (9, 4), (10, 2), (11, 6), (12, 0), (13, 4), (14, 4), (15, 0), (16, 6), (17, 0), (18, 6), (19, 0), (21, 0), (22, 4), (23, 0), (24, 25), (26, 28), (29, 30), (31, 32), (33, 34), (35, 36), (37, 38), (39, 40), (41, 42), (43, 44), (45, 46), (47, 48), (49, 50), (51, 52), (53, 54), (55, 56)], [(0, 0), (0, 4), (0, 21), (0, 27), (0, 22), (0, 23), (2, 2), (4, 4), (4, 21), (4, 27), (4, 22), (4, 23), (6, 6), (21, 21), (21, 27), (21, 22), (21, 23), (27, 27), (27, 22), (27, 23), (22, 22), (22, 23), (23, 23)]⟩
def shared_typed_certificate : Certificate :=
  ⟨2,
   [⟨8, 2, 1, .axiom 4⟩, ⟨11, 6, 1, .axiom 7⟩, ⟨12, 0, 1, .axiom 8⟩, ⟨13, 4, 1, .axiom 9⟩, ⟨21, 0, 1, .axiom 16⟩, ⟨22, 4, 1, .axiom 17⟩, ⟨23, 0, 1, .axiom 18⟩, ⟨33, 34, 2, .axiom 23⟩, ⟨39, 40, 2, .axiom 26⟩, ⟨43, 44, 2, .axiom 28⟩, ⟨27, 33, 2, .congruence [[], [0]]⟩, ⟨23, 39, 2, .congruence [[], [1]]⟩, ⟨22, 43, 2, .congruence [[], [3]]⟩, ⟨34, 40, 2, .congruence [[], [4, 6]]⟩, ⟨12, 44, 2, .congruence [[5], [6, 11, 8, 13, 7, 10]]⟩],
   [⟨[], 0⟩, ⟨[2, 14, 9, 12, 5], 2⟩, ⟨[4], 1⟩, ⟨[6, 11, 8, 13, 7, 10], 2⟩, ⟨[2, 14, 9, 12], 2⟩, ⟨[6], 1⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[5, 12, 9, 14, 2, 4], 2⟩, ⟨[5, 12, 9, 14, 2, 6, 11, 8, 13, 7, 10], 2⟩, ⟨[5], 1⟩, ⟨[5, 12, 9, 14, 2, 6], 2⟩, ⟨[], 0⟩, ⟨[], 1⟩, ⟨[4, 6, 11, 8, 13, 7, 10], 2⟩, ⟨[4, 2, 14, 9, 12], 2⟩, ⟨[4, 6], 1⟩, ⟨[], 1⟩, ⟨[10, 7, 13, 8, 11, 6, 2, 14, 9, 12], 2⟩, ⟨[10, 7, 13, 8, 11], 2⟩, ⟨[], 1⟩, ⟨[12, 9, 14, 2, 6], 2⟩, ⟨[], 1⟩]⟩
theorem shared_typed_accepted :
    checkRaw shared_typed_request shared_typed_certificate = true := by decide +kernel

def typed_binary_request : Request :=
  ⟨2, [⟨[], 0⟩, ⟨[], 1⟩, ⟨[], 0⟩, ⟨[], 1⟩, ⟨[0, 1], 0⟩],
   [⟨0, []⟩, ⟨2, []⟩, ⟨1, []⟩, ⟨3, []⟩, ⟨4, [0, 2]⟩, ⟨4, [1, 3]⟩],
   [(0, 1), (2, 3)], [(4, 5), (5, 4)]⟩
def typed_binary_certificate : Certificate :=
  ⟨1,
   [⟨0, 1, 0, .axiom 0⟩, ⟨2, 3, 0, .axiom 1⟩, ⟨4, 5, 1, .congruence [[0], [1]]⟩],
   [⟨[2], 1⟩, ⟨[2], 1⟩]⟩
theorem typed_binary_accepted :
    checkRaw typed_binary_request typed_binary_certificate = true := by decide +kernel

def reflexive_request : Request :=
  ⟨1, [⟨[], 0⟩, ⟨[0], 0⟩],
   [⟨0, []⟩],
   [], [(0, 0)]⟩
def reflexive_certificate : Certificate :=
  ⟨0,
   [],
   [⟨[], 0⟩]⟩
theorem reflexive_accepted :
    checkRaw reflexive_request reflexive_certificate = true := by decide +kernel

def reverse_axioms_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reverse_axioms_certificate : Certificate :=
  ⟨2,
   [⟨3, 0, 2, .axiom 0⟩, ⟨3, 4, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[0, 1]]⟩],
   [⟨[2], 2⟩]⟩
theorem reverse_axioms_accepted :
    checkRaw reverse_axioms_request reverse_axioms_certificate = true := by decide +kernel

def active_prefix_request : Request :=
  ⟨1, [⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[0], 0⟩],
   [⟨0, []⟩, ⟨1, []⟩, ⟨2, []⟩, ⟨4, [2]⟩, ⟨4, [3]⟩, ⟨3, []⟩],
   [(0, 1), (4, 5)], [(0, 1)]⟩
def active_prefix_certificate : Certificate :=
  ⟨0,
   [⟨0, 1, 0, .axiom 0⟩],
   [⟨[0], 0⟩]⟩
theorem active_prefix_accepted :
    checkRaw active_prefix_request active_prefix_certificate = true := by decide +kernel

def empty_request : Request :=
  ⟨2, [⟨[0], 1⟩],
   [],
   [], []⟩
def empty_certificate : Certificate :=
  ⟨0,
   [],
   []⟩
theorem empty_accepted :
    checkRaw empty_request empty_certificate = true := by decide +kernel

def transitive_chain_request : Request :=
  ⟨1, [⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[0], 0⟩],
   [⟨0, []⟩, ⟨1, []⟩, ⟨2, []⟩, ⟨3, []⟩],
   [(0, 1), (1, 2), (2, 3)], [(0, 3), (3, 0)]⟩
def transitive_chain_certificate : Certificate :=
  ⟨0,
   [⟨0, 1, 0, .axiom 0⟩, ⟨1, 2, 0, .axiom 1⟩, ⟨2, 3, 0, .axiom 2⟩],
   [⟨[0, 1, 2], 0⟩, ⟨[2, 1, 0], 0⟩]⟩
theorem transitive_chain_accepted :
    checkRaw transitive_chain_request transitive_chain_certificate = true := by decide +kernel

def reject_node_self_reference_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [2]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_node_self_reference_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[0, 1]]⟩],
   [⟨[2], 2⟩]⟩
theorem reject_node_self_reference_rejected :
    checkRaw reject_node_self_reference_request reject_node_self_reference_certificate = false := by decide +kernel

def reject_node_forward_reference_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [6]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_node_forward_reference_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[0, 1]]⟩],
   [⟨[2], 2⟩]⟩
theorem reject_node_forward_reference_rejected :
    checkRaw reject_node_forward_reference_request reject_node_forward_reference_certificate = false := by decide +kernel

def reject_node_bad_reference_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [999]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_node_bad_reference_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[0, 1]]⟩],
   [⟨[2], 2⟩]⟩
theorem reject_node_bad_reference_rejected :
    checkRaw reject_node_bad_reference_request reject_node_bad_reference_certificate = false := by decide +kernel

def reject_node_wrong_arity_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, []⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_node_wrong_arity_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[0, 1]]⟩],
   [⟨[2], 2⟩]⟩
theorem reject_node_wrong_arity_rejected :
    checkRaw reject_node_wrong_arity_request reject_node_wrong_arity_certificate = false := by decide +kernel

def reject_node_wrong_sort_request : Request :=
  ⟨2, [⟨[], 0⟩, ⟨[], 1⟩, ⟨[], 0⟩, ⟨[], 1⟩, ⟨[0, 1], 0⟩],
   [⟨0, []⟩, ⟨2, []⟩, ⟨1, []⟩, ⟨3, []⟩, ⟨4, [2, 2]⟩, ⟨4, [1, 3]⟩],
   [(0, 1), (2, 3)], [(4, 5), (5, 4)]⟩
def reject_node_wrong_sort_certificate : Certificate :=
  ⟨1,
   [⟨0, 1, 0, .axiom 0⟩, ⟨2, 3, 0, .axiom 1⟩, ⟨4, 5, 1, .congruence [[0], [1]]⟩],
   [⟨[2], 1⟩, ⟨[2], 1⟩]⟩
theorem reject_node_wrong_sort_rejected :
    checkRaw reject_node_wrong_sort_request reject_node_wrong_sort_certificate = false := by decide +kernel

def reject_equation_wrong_sort_request : Request :=
  ⟨2, [⟨[], 0⟩, ⟨[], 1⟩, ⟨[], 0⟩, ⟨[], 1⟩, ⟨[0, 1], 0⟩],
   [⟨0, []⟩, ⟨2, []⟩, ⟨1, []⟩, ⟨3, []⟩, ⟨4, [0, 2]⟩, ⟨4, [1, 3]⟩],
   [(0, 2), (2, 3)], [(4, 5), (5, 4)]⟩
def reject_equation_wrong_sort_certificate : Certificate :=
  ⟨1,
   [⟨0, 1, 0, .axiom 0⟩, ⟨2, 3, 0, .axiom 1⟩, ⟨4, 5, 1, .congruence [[0], [1]]⟩],
   [⟨[2], 1⟩, ⟨[2], 1⟩]⟩
theorem reject_equation_wrong_sort_rejected :
    checkRaw reject_equation_wrong_sort_request reject_equation_wrong_sort_certificate = false := by decide +kernel

def reject_query_wrong_sort_request : Request :=
  ⟨2, [⟨[], 0⟩, ⟨[], 1⟩, ⟨[], 0⟩, ⟨[], 1⟩, ⟨[0, 1], 0⟩],
   [⟨0, []⟩, ⟨2, []⟩, ⟨1, []⟩, ⟨3, []⟩, ⟨4, [0, 2]⟩, ⟨4, [1, 3]⟩],
   [(0, 1), (2, 3)], [(4, 2), (5, 4)]⟩
def reject_query_wrong_sort_certificate : Certificate :=
  ⟨1,
   [⟨0, 1, 0, .axiom 0⟩, ⟨2, 3, 0, .axiom 1⟩, ⟨4, 5, 1, .congruence [[0], [1]]⟩],
   [⟨[2], 1⟩, ⟨[2], 1⟩]⟩
theorem reject_query_wrong_sort_rejected :
    checkRaw reject_query_wrong_sort_request reject_query_wrong_sort_certificate = false := by decide +kernel

def reject_event_wrong_sort_request : Request :=
  ⟨2, [⟨[], 0⟩, ⟨[], 1⟩, ⟨[], 0⟩, ⟨[], 1⟩, ⟨[0, 1], 0⟩],
   [⟨0, []⟩, ⟨2, []⟩, ⟨1, []⟩, ⟨3, []⟩, ⟨4, [0, 2]⟩, ⟨4, [1, 3]⟩],
   [(0, 1), (2, 3)], [(4, 5), (5, 4)]⟩
def reject_event_wrong_sort_certificate : Certificate :=
  ⟨1,
   [⟨0, 2, 0, .axiom 0⟩, ⟨2, 3, 0, .axiom 1⟩, ⟨4, 5, 1, .congruence [[0], [1]]⟩],
   [⟨[2], 1⟩, ⟨[2], 1⟩]⟩
theorem reject_event_wrong_sort_rejected :
    checkRaw reject_event_wrong_sort_request reject_event_wrong_sort_certificate = false := by decide +kernel

def reject_event_bad_endpoint_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_event_bad_endpoint_certificate : Certificate :=
  ⟨2,
   [⟨999, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[0, 1]]⟩],
   [⟨[2], 2⟩]⟩
theorem reject_event_bad_endpoint_rejected :
    checkRaw reject_event_bad_endpoint_request reject_event_bad_endpoint_certificate = false := by decide +kernel

def reject_substituted_axiom_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_substituted_axiom_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 1⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[0, 1]]⟩],
   [⟨[2], 2⟩]⟩
theorem reject_substituted_axiom_rejected :
    checkRaw reject_substituted_axiom_request reject_substituted_axiom_certificate = false := by decide +kernel

def reject_axiom_bad_index_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_axiom_bad_index_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 999⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[0, 1]]⟩],
   [⟨[2], 2⟩]⟩
theorem reject_axiom_bad_index_rejected :
    checkRaw reject_axiom_bad_index_request reject_axiom_bad_index_certificate = false := by decide +kernel

def reject_congruence_wrong_head_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_congruence_wrong_head_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 4, 2, .congruence [[0, 1]]⟩],
   [⟨[2], 2⟩]⟩
theorem reject_congruence_wrong_head_rejected :
    checkRaw reject_congruence_wrong_head_request reject_congruence_wrong_head_certificate = false := by decide +kernel

def reject_missing_premise_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_missing_premise_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence []⟩],
   [⟨[2], 2⟩]⟩
theorem reject_missing_premise_rejected :
    checkRaw reject_missing_premise_request reject_missing_premise_certificate = false := by decide +kernel

def reject_extra_premise_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_extra_premise_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[0, 1], []]⟩],
   [⟨[2], 2⟩]⟩
theorem reject_extra_premise_rejected :
    checkRaw reject_extra_premise_request reject_extra_premise_certificate = false := by decide +kernel

def reject_forward_event_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_forward_event_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[3]]⟩],
   [⟨[2], 2⟩]⟩
theorem reject_forward_event_rejected :
    checkRaw reject_forward_event_request reject_forward_event_certificate = false := by decide +kernel

def reject_self_event_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_self_event_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[2]]⟩],
   [⟨[2], 2⟩]⟩
theorem reject_self_event_rejected :
    checkRaw reject_self_event_request reject_self_event_certificate = false := by decide +kernel

def reject_bad_event_reference_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_bad_event_reference_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[999]]⟩],
   [⟨[2], 2⟩]⟩
theorem reject_bad_event_reference_rejected :
    checkRaw reject_bad_event_reference_request reject_bad_event_reference_certificate = false := by decide +kernel

def reject_broken_premise_path_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_broken_premise_path_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[1]]⟩],
   [⟨[2], 2⟩]⟩
theorem reject_broken_premise_path_rejected :
    checkRaw reject_broken_premise_path_request reject_broken_premise_path_certificate = false := by decide +kernel

def reject_broken_goal_path_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_broken_goal_path_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[0, 1]]⟩],
   [⟨[], 2⟩]⟩
theorem reject_broken_goal_path_rejected :
    checkRaw reject_broken_goal_path_request reject_broken_goal_path_certificate = false := by decide +kernel

def reject_wrong_goal_depth_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_wrong_goal_depth_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[0, 1]]⟩],
   [⟨[2], 0⟩]⟩
theorem reject_wrong_goal_depth_rejected :
    checkRaw reject_wrong_goal_depth_request reject_wrong_goal_depth_certificate = false := by decide +kernel

def reject_wrong_event_depth_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_wrong_event_depth_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 0, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[0, 1]]⟩],
   [⟨[2], 2⟩]⟩
theorem reject_wrong_event_depth_rejected :
    checkRaw reject_wrong_event_depth_request reject_wrong_event_depth_certificate = false := by decide +kernel

def reject_inactive_event_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_inactive_event_certificate : Certificate :=
  ⟨1,
   [⟨0, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[0, 1]]⟩],
   [⟨[2], 2⟩]⟩
theorem reject_inactive_event_rejected :
    checkRaw reject_inactive_event_request reject_inactive_event_certificate = false := by decide +kernel

def reject_unused_bad_event_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_unused_bad_event_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[0, 1]]⟩, ⟨0, 3, 2, .axiom 1⟩],
   [⟨[2], 2⟩]⟩
theorem reject_unused_bad_event_rejected :
    checkRaw reject_unused_bad_event_request reject_unused_bad_event_certificate = false := by decide +kernel

def reject_unknown_numeric_head_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨999, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_unknown_numeric_head_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[0, 1]]⟩],
   [⟨[2], 2⟩]⟩
theorem reject_unknown_numeric_head_rejected :
    checkRaw reject_unknown_numeric_head_request reject_unknown_numeric_head_certificate = false := by decide +kernel

def reject_missing_goal_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_missing_goal_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[0, 1]]⟩],
   []⟩
theorem reject_missing_goal_rejected :
    checkRaw reject_missing_goal_request reject_missing_goal_certificate = false := by decide +kernel

def reject_extra_goal_request : Request :=
  ⟨1, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_extra_goal_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[0, 1]]⟩],
   [⟨[2], 2⟩, ⟨[2], 2⟩]⟩
theorem reject_extra_goal_rejected :
    checkRaw reject_extra_goal_request reject_extra_goal_certificate = false := by decide +kernel

def reject_empty_sort_declaration_request : Request :=
  ⟨0, [⟨[0], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_empty_sort_declaration_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[0, 1]]⟩],
   [⟨[2], 2⟩]⟩
theorem reject_empty_sort_declaration_rejected :
    checkRaw reject_empty_sort_declaration_request reject_empty_sort_declaration_certificate = false := by decide +kernel

def reject_out_of_range_sort_request : Request :=
  ⟨1, [⟨[0], 999⟩, ⟨[], 0⟩, ⟨[], 0⟩, ⟨[], 0⟩],
   [⟨1, []⟩, ⟨3, []⟩, ⟨0, [1]⟩, ⟨0, [2]⟩, ⟨2, []⟩, ⟨0, [0]⟩, ⟨0, [4]⟩],
   [(0, 3), (4, 3)], [(5, 6)]⟩
def reject_out_of_range_sort_certificate : Certificate :=
  ⟨2,
   [⟨0, 3, 2, .axiom 0⟩, ⟨4, 3, 2, .axiom 1⟩, ⟨5, 6, 2, .congruence [[0, 1]]⟩],
   [⟨[2], 2⟩]⟩
theorem reject_out_of_range_sort_rejected :
    checkRaw reject_out_of_range_sort_request reject_out_of_range_sort_certificate = false := by decide +kernel

end QKFGround.Examples
