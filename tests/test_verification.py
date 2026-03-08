"""Tests for verification challenge solver."""

from contemplative_moltbook.verification import (
    VerificationTracker,
    compute,
    deobfuscate,
    parse_challenge,
    parse_number_word,
    solve_challenge,
)


class TestDeobfuscate:
    def test_basic_repeat(self):
        assert deobfuscate("ttwweennttyy") == "twenty"

    def test_triple_repeat(self):
        assert deobfuscate("fffiiivvveee") == "five"

    def test_no_repeat(self):
        assert deobfuscate("five") == "five"

    def test_empty(self):
        assert deobfuscate("") == ""

    def test_mixed_repeat(self):
        assert deobfuscate("ttwweennttyy pplluuss ffiivvee") == "twenty plus five"

    def test_single_char(self):
        assert deobfuscate("a") == "a"

    def test_all_same(self):
        # "aaaa" pair-decodes to "aa" (each pair of 'a' = one 'a')
        assert deobfuscate("aaaa") == "aa"


class TestParseNumberWord:
    def test_simple_numbers(self):
        assert parse_number_word("zero") == 0
        assert parse_number_word("one") == 1
        assert parse_number_word("twenty") == 20

    def test_compound_hyphenated(self):
        assert parse_number_word("twenty-five") == 25
        assert parse_number_word("thirty-three") == 33

    def test_compound_space(self):
        assert parse_number_word("twenty five") == 25

    def test_digit_string(self):
        assert parse_number_word("42") == 42

    def test_case_insensitive(self):
        assert parse_number_word("TWENTY") == 20

    def test_invalid(self):
        assert parse_number_word("foobar") is None

    def test_hundred(self):
        assert parse_number_word("two hundred") == 200

    def test_hundred_with_remainder(self):
        assert parse_number_word("three hundred fifty") == 350


class TestParseChallenge:
    def test_plus(self):
        result = parse_challenge("twenty plus five")
        assert result == (20.0, "+", 5.0)

    def test_minus(self):
        result = parse_challenge("ten minus three")
        assert result is not None
        assert result == (10.0, "-", 3.0)

    def test_times(self):
        result = parse_challenge("five times six")
        assert result == (5.0, "*", 6.0)

    def test_divided(self):
        result = parse_challenge("twenty divided four")
        assert result == (20.0, "/", 4.0)

    def test_gains(self):
        result = parse_challenge("ten gains five")
        assert result == (10.0, "+", 5.0)

    def test_loses(self):
        result = parse_challenge("ten loses three")
        assert result == (10.0, "-", 3.0)

    def test_invalid(self):
        assert parse_challenge("hello world") is None

    def test_invalid_numbers(self):
        assert parse_challenge("foobar plus baz") is None


class TestCompute:
    def test_add(self):
        assert compute(20.0, "+", 5.0) == 25.0

    def test_subtract(self):
        assert compute(20.0, "-", 5.0) == 15.0

    def test_multiply(self):
        assert compute(5.0, "*", 6.0) == 30.0

    def test_divide(self):
        assert compute(20.0, "/", 4.0) == 5.0

    def test_divide_by_zero(self):
        assert compute(20.0, "/", 0.0) is None

    def test_invalid_op(self):
        assert compute(1.0, "^", 2.0) is None


class TestSolveChallenge:
    def test_obfuscated_addition(self):
        assert solve_challenge("ttwweennttyy pplluuss ffiivvee") == "25.00"

    def test_obfuscated_subtraction(self):
        assert solve_challenge("tteenn mmiinnuuss tthhrreeee") == "7.00"

    def test_plain_text(self):
        assert solve_challenge("five times six") == "30.00"

    def test_division(self):
        assert solve_challenge("twenty divided four") == "5.00"

    def test_unsolvable(self):
        assert solve_challenge("random gibberish") is None


class TestVerificationTracker:
    def test_initial_state(self):
        tracker = VerificationTracker(max_failures=3)
        assert not tracker.should_stop

    def test_stop_after_max_failures(self):
        tracker = VerificationTracker(max_failures=3)
        tracker.record_failure()
        tracker.record_failure()
        assert not tracker.should_stop
        tracker.record_failure()
        assert tracker.should_stop

    def test_success_resets_count(self):
        tracker = VerificationTracker(max_failures=3)
        tracker.record_failure()
        tracker.record_failure()
        tracker.record_success()
        tracker.record_failure()
        assert not tracker.should_stop
