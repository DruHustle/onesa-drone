"""Strict numeric observations shared by the planner and independent supervisor."""

from math import isfinite


def finite_number(value):
    # Strings and booleans are not observations. NaN comparisons cannot establish
    # safety, and very large integers cannot be represented by the simulator.
    if type(value) not in (int, float):
        return False
    try:
        return isfinite(value)
    except OverflowError:
        return False


def valid_battery(value):
    return finite_number(value) and 0 <= value <= 100


def positive_number(value):
    return finite_number(value) and value > 0
