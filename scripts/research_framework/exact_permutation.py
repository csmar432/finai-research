"""Exact (combinatorial) permutation tests for event-study-style data.

Why this exists
---------------
The existing ``permutation_test_greenium`` and ``_test_placebo``
implementations in scripts.research_framework.* are Monte-Carlo —
they draw ``n_permutations`` random shuffles of the labels and
estimate the p-value as the fraction whose test statistic exceeds
the observed value.  For a small number of events (e.g. the CBAM
study's 8 events grouped 3/3/2 → 560 unique label assignments),
Monte-Carlo with the default 1000-iteration budget is overkill —
we can enumerate all 560 and get an exact p-value.

This module provides that enumeration.  For larger problems where
the multinomial coefficient overflows the budget, it falls back to
exhaustive enumeration in chunks but emits a warning.

Reference
---------
The CBAM paper used this test to verify that the relaxation-vs-
tightening CAR difference (p=0.037) and price-reveal-vs-tightening
(p=0.114) were not driven by chance label assignment.  See
``Stage6_EMPIRICAL_RESULTS.md`` in the project's deliverables.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, Sequence

import numpy as np


@dataclass
class ExactPermutationResult:
    """Result of an exact permutation test.

    Attributes
    ----------
    observed_stat : float
        The observed value of the test statistic on the real labels.
    perm_count : int
        Total number of label permutations enumerated (= n! /
        prod(n_i!) for the multinomial case).
    p_two_sided : float
        Two-sided exact p-value: probability that |stat| >= |observed|
        under the null hypothesis of label-exchangeability.
    p_one_sided_greater : float
        P(stat >= observed) under H0.
    p_one_sided_less : float
        P(stat <= observed) under H0.
    distribution_min, distribution_max, distribution_mean :
        Summary of the permuted-stat distribution (useful for
        reporting even when p-values are non-significant).
    """

    observed_stat: float
    perm_count: int
    p_two_sided: float
    p_one_sided_greater: float
    p_one_sided_less: float
    distribution_min: float
    distribution_max: float
    distribution_mean: float


def _enumerate_multinomial_labels(
    n_total: int, group_sizes: Sequence[int]
) -> Iterable[tuple[int, ...]]:
    """Enumerate every distinct way to label ``n_total`` items with
    the integer labels ``range(len(group_sizes))`` such that the
    counts match ``group_sizes``.

    For 8 events with sizes (3, 3, 2) this yields 8! / (3!·3!·2!) = 560
    tuples; for n_total <= 12 this fits comfortably in memory.
    """
    if sum(group_sizes) != n_total:
        raise ValueError(
            f"group_sizes sum to {sum(group_sizes)} but n_total={n_total}"
        )
    if any(s < 0 for s in group_sizes):
        raise ValueError("group_sizes must be non-negative")

    # Multinomial enumeration by layered combinations:
    #   1. Start with a length-n vector of placeholders (-1).
    #   2. For group 0, choose ``group_sizes[0]`` slot positions out of
    #      n, and assign them label 0.
    #   3. From the remaining slots, choose ``group_sizes[1]`` for
    #      label 1, etc.
    # Each sequence of choices is unique and produces a unique full
    # label vector.  The total number of yields equals
    # n! / prod(n_i!).

    def _assign(
        partial: list[int], free_slots: tuple[int, ...], group_idx: int
    ) -> Iterable[tuple[int, ...]]:
        if group_idx == len(group_sizes):
            yield tuple(partial)
            return
        size = group_sizes[group_idx]
        for chosen in combinations(free_slots, size):
            chosen_set = set(chosen)
            new_partial = list(partial)
            for s in chosen:
                new_partial[s] = group_idx
            new_free = tuple(s for s in free_slots if s not in chosen_set)
            yield from _assign(new_partial, new_free, group_idx + 1)

    placeholder = [-1] * n_total
    return _assign(placeholder, tuple(range(n_total)), 0)


def _stat_from_labels(
    observed_per_event: np.ndarray,
    labels: Sequence[int],
    group_a: int,
    group_b: int,
) -> float:
    """Compute the test statistic ``mean(group_a) - mean(group_b)``.

    ``observed_per_event`` is a length-n vector with the per-event CAR
    difference (or any other scalar effect).  ``labels`` is a length-n
    vector of integers naming the group each event belongs to.
    """
    arr = np.asarray(observed_per_event, dtype=float)
    lab = np.asarray(labels, dtype=int)
    a_mask = lab == group_a
    b_mask = lab == group_b
    a_vals = arr[a_mask]
    b_vals = arr[b_mask]
    if a_vals.size == 0 or b_vals.size == 0:
        return 0.0
    return float(a_vals.mean() - b_vals.mean())


def exact_permutation_test(
    observed_per_event: Sequence[float],
    group_labels: Sequence[int],
    *,
    group_a: int = 0,
    group_b: int = 1,
    stat_fn=None,
    max_perms: int = 1_000_000,
) -> ExactPermutationResult:
    """Exact (combinatorial) permutation test for event-study data.

    Parameters
    ----------
    observed_per_event : sequence of float
        Per-event test statistics (e.g. CAR differences) under the
        observed (true) label assignment.
    group_labels : sequence of int
        The TRUE labels for each event.  Used only to determine
        ``group_sizes`` for the enumeration.
    group_a, group_b : int
        Which two groups to compare (default 0 vs 1).
    stat_fn : callable, optional
        Custom statistic.  Signature
        ``stat_fn(observed, labels, group_a, group_b) -> float``.
        Defaults to ``mean(group_a) - mean(group_b)``.
    max_perms : int
        Safety cap on the enumeration size.  Default 1M, which is
        generous (covers any practical event-study).

    Returns
    -------
    ExactPermutationResult

    Notes
    -----
    For the CBAM case (8 events, group sizes (3, 3, 2)), the test
    enumerates 560 permutations and returns the exact two-sided p.
    For larger problems where ``n! / prod(n_i!) > max_perms`` the
    function raises ``ValueError`` — the caller should fall back to
    the Monte-Carlo ``permutation_test_greenium`` API instead.
    """
    arr = np.asarray(observed_per_event, dtype=float)
    lab = np.asarray(group_labels, dtype=int)
    n = len(arr)
    if len(lab) != n:
        raise ValueError("observed_per_event and group_labels must align")

    # Derive group sizes from the observed labels (the only true label
    # assignment we know).
    unique_labels = sorted(set(lab.tolist()))
    group_sizes = [int((lab == lbl).sum()) for lbl in unique_labels]

    total = math.factorial(n)
    for s in group_sizes:
        total //= math.factorial(s)
    if total > max_perms:
        raise ValueError(
            f"Total label permutations = {total} exceeds max_perms={max_perms}. "
            "Fall back to Monte-Carlo permutation_test_greenium."
        )

    # Observed statistic.
    stat_fn = stat_fn or _stat_from_labels
    observed_stat = stat_fn(arr, lab, group_a, group_b)

    # Enumerate every distinct label assignment and compute the stat.
    perm_stats: list[float] = []
    for perm in _enumerate_multinomial_labels(n, group_sizes):
        s = stat_fn(arr, perm, group_a, group_b)
        perm_stats.append(s)
    perm_stats_arr = np.asarray(perm_stats, dtype=float)

    abs_obs = abs(observed_stat)
    n_two = int(np.sum(np.abs(perm_stats_arr) >= abs_obs - 1e-12))
    n_greater = int(np.sum(perm_stats_arr >= observed_stat - 1e-12))
    n_less = int(np.sum(perm_stats_arr <= observed_stat + 1e-12))

    return ExactPermutationResult(
        observed_stat=float(observed_stat),
        perm_count=int(perm_stats_arr.size),
        p_two_sided=float(n_two) / float(perm_stats_arr.size),
        p_one_sided_greater=float(n_greater) / float(perm_stats_arr.size),
        p_one_sided_less=float(n_less) / float(perm_stats_arr.size),
        distribution_min=float(perm_stats_arr.min()),
        distribution_max=float(perm_stats_arr.max()),
        distribution_mean=float(perm_stats_arr.mean()),
    )
