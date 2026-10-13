# Test Output

Command: `python -m unittest discover -v`  (run 2026-10-13 16:36)

```
test_engine_matches_reference (tests.test_model.TestModel.test_engine_matches_reference) ... ok
test_sequences_exercise_the_interesting_paths (tests.test_model.TestModel.test_sequences_exercise_the_interesting_paths)
Guard against a vacuous model test: the generator must actually ... ok
test_confirm_release_idempotent (tests.test_rules.TestMisc.test_confirm_release_idempotent) ... ok
test_errors (tests.test_rules.TestMisc.test_errors) ... ok
test_invalid_args_mutate_nothing (tests.test_rules.TestMisc.test_invalid_args_mutate_nothing) ... ok
test_release_lapsed_gives_up_late_confirm (tests.test_rules.TestMisc.test_release_lapsed_gives_up_late_confirm) ... ok
test_status_values (tests.test_rules.TestMisc.test_status_values) ... ok
test_cannot_hold_sold_seat_even_same_user (tests.test_rules.TestR1.test_cannot_hold_sold_seat_even_same_user) ... ok
test_other_user_cannot_hold_held_seat (tests.test_rules.TestR1.test_other_user_cannot_hold_held_seat) ... ok
test_seat_free_after_expiry_for_others (tests.test_rules.TestR1.test_seat_free_after_expiry_for_others) ... ok
test_concurrent_holds_by_same_user_never_exceed_limit (tests.test_rules.TestR2.test_concurrent_holds_by_same_user_never_exceed_limit) ... ok
test_confirmed_seats_do_not_count (tests.test_rules.TestR2.test_confirmed_seats_do_not_count) ... ok
test_expired_holds_free_quota (tests.test_rules.TestR2.test_expired_holds_free_quota) ... ok
test_fifth_hold_rejected (tests.test_rules.TestR2.test_fifth_hold_rejected) ... ok
test_release_frees_quota (tests.test_rules.TestR2.test_release_frees_quota) ... ok
test_confirm_before_expiry (tests.test_rules.TestR3R4.test_confirm_before_expiry) ... ok
test_expires_at_never_changes (tests.test_rules.TestR3R4.test_expires_at_never_changes) ... ok
test_late_confirm_allowed_if_untouched (tests.test_rules.TestR3R4.test_late_confirm_allowed_if_untouched) ... ok
test_late_confirm_blocks_later_holders (tests.test_rules.TestR3R4.test_late_confirm_blocks_later_holders) ... ok
test_late_confirm_does_not_need_free_quota (tests.test_rules.TestR3R4.test_late_confirm_does_not_need_free_quota) ... ok
test_late_confirm_rejected_if_retaken (tests.test_rules.TestR3R4.test_late_confirm_rejected_if_retaken) ... ok
test_retaken_then_expired_still_lost (tests.test_rules.TestR3R4.test_retaken_then_expired_still_lost) ... ok
test_retaken_then_released_still_lost (tests.test_rules.TestR3R4.test_retaken_then_released_still_lost) ... ok
test_retry_after_expiry_is_new_hold (tests.test_rules.TestR5.test_retry_after_expiry_is_new_hold) ... ok
test_retry_after_expiry_loses_to_other_user (tests.test_rules.TestR5.test_retry_after_expiry_loses_to_other_user) ... ok
test_retry_at_limit_succeeds (tests.test_rules.TestR5.test_retry_at_limit_succeeds) ... ok
test_retry_does_not_consume_quota (tests.test_rules.TestR5.test_retry_does_not_consume_quota) ... ok
test_retry_returns_same_hold_ignores_ttl (tests.test_rules.TestR5.test_retry_returns_same_hold_ignores_ttl) ... ok
test_all_or_nothing_on_limit (tests.test_rules.TestR6.test_all_or_nothing_on_limit) ... ok
test_all_or_nothing_on_unavailable_seat (tests.test_rules.TestR6.test_all_or_nothing_on_unavailable_seat) ... ok
test_already_held_seats_cost_nothing (tests.test_rules.TestR6.test_already_held_seats_cost_nothing) ... ok
test_duplicates_deduped (tests.test_rules.TestR6.test_duplicates_deduped) ... ok
test_empty (tests.test_rules.TestR6.test_empty) ... ok
test_five_new_seats_always_fail (tests.test_rules.TestR6.test_five_new_seats_always_fail) ... ok
test_five_requested_but_dupes_make_it_four (tests.test_rules.TestR6.test_five_requested_but_dupes_make_it_four) ... ok
test_four_seats_ok (tests.test_rules.TestR6.test_four_seats_ok) ... ok
test_opposite_order_no_deadlock (tests.test_rules.TestR6.test_opposite_order_no_deadlock) ... ok
test_unavailable_error_wins_over_limit (tests.test_rules.TestR6.test_unavailable_error_wins_over_limit) ... ok
test_hold_many_never_partially_applied_under_contention (tests.test_stress.TestStress.test_hold_many_never_partially_applied_under_contention)
Two users repeatedly hold_many overlapping sets; at any quiescent ... ok
test_invariants_under_contention (tests.test_stress.TestStress.test_invariants_under_contention) ... ok

----------------------------------------------------------------------
Ran 40 tests in 30.365s

OK

[model] base seed=819423872 sequences=300

[stress] seed=284987864 rounds=60
```
