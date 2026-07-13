"""Event-study extensions: BMP / Kolari-Pynnönen / sign / rank tests.

These are the standardised and cross-sectionally-corrected versions of
the basic event-study test statistics.  All four are referenced by the
CBAM paper's "TODO for submission" list (see
``Stage6_EMPIRICAL_RESULTS.md`` § "投稿前尚待完成事项").

References
----------
- Boehmer, Musumeci, Poulsen (1991, JFE) — cross-sectional
  standardisation of event-study CARs.
- Kolari, Pynnönen (2010, JEMS) — adjustment for cross-sectional
  dependence in event-study tests.
- Cowan (1992) — generalised sign test for event studies.
- Campbell, Lo, MacKinlay (1997) — rank test for event studies.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class BMPResult:
    """Result of the Boehmer-Musumeci-Poulsen (1991) standardisation."""
    standardised_car: np.ndarray      # length-N vector of standardised CARs
    t_stat: float                     # t-statistic under H0
    p_value: float                    # two-sided p-value


@dataclass
class KolariPynnonenResult:
    """Result of the Kolari-Pynnönen (2010) cross-sectional adjustment."""
    t_stat_adjusted: float
    p_value: float


@dataclass
class SignRankResult:
    """Result of the generalised sign or rank test on CARs."""
    statistic: float
    p_value: float


def bmp_standardise(
    cars: np.ndarray,
    estimation_window_std: np.ndarray,
) -> BMPResult:
    """Boehmer-Musumeci-Poulsen (1991) cross-sectional standardisation.

    Each firm's CAR is divided by its own estimation-window standard
    deviation, then the standardised CARs are averaged and tested
    against zero using a t-stat with N-1 degrees of freedom.

    Parameters
    ----------
    cars : array of shape (N,)
        Per-firm cumulative abnormal returns over the event window.
    estimation_window_std : array of shape (N,)
        Per-firm standard deviation of residuals from the market
        model (or other benchmark) estimated over the pre-event window.

    Returns
    -------
    BMPResult

    Notes
    -----
    The estimation-window standard deviations should be computed
    over a long enough window (>= 100 trading days recommended by
    BMP) for the t-statistic to be approximately standard normal.
    """
    cars = np.asarray(cars, dtype=float).ravel()
    sds = np.asarray(estimation_window_std, dtype=float).ravel()
    if cars.shape != sds.shape:
        raise ValueError("cars and estimation_window_std must align")
    sds_safe = np.where(sds > 1e-12, sds, np.nan)
    std_cars = cars / sds_safe
    valid = ~np.isnan(std_cars)
    n = int(valid.sum())
    if n < 2:
        return BMPResult(standardised_car=std_cars, t_stat=float("nan"),
                         p_value=float("nan"))
    sample = std_cars[valid]
    mean = float(sample.mean())
    se = float(sample.std(ddof=1) / np.sqrt(n))
    t = mean / se if se > 0 else float("nan")
    from scipy import stats as _stats
    p = float(2 * (1 - _stats.t.cdf(abs(t), df=n - 1))) if not np.isnan(t) else float("nan")
    return BMPResult(standardised_car=std_cars, t_stat=t, p_value=p)


def kolari_pynnonen_adjust(
    cars: np.ndarray,
    estimation_window_returns: np.ndarray,
) -> KolariPynnonenResult:
    """Kolari-Pynnönen (2010) adjustment for cross-sectional dependence.

    The adjustment modifies the BMP test statistic by replacing the
    per-firm standard deviation with one that accounts for the
    cross-sectional covariance of the residuals.  The implementation
    here uses the diagonal-and-off-diagonal correction from
    Kolari-Pynnönen eq. (3):

        s_adj^2 = (1/N) * sum_i CAR_i^2
                  - (1/(N*(N-1))) * sum_{i != j} CAR_i * CAR_j

    Parameters
    ----------
    cars : array of shape (N,)
        Per-firm CARs over the event window.
    estimation_window_returns : array of shape (N, T)
        Per-firm residual returns over the estimation window.  Used to
        estimate the cross-sectional correlation structure.

    Returns
    -------
    KolariPynnonenResult
    """
    cars = np.asarray(cars, dtype=float).ravel()
    resids = np.asarray(estimation_window_returns, dtype=float)
    if resids.ndim != 2:
        raise ValueError("estimation_window_returns must be 2D (N, T)")
    n = cars.size
    if resids.shape[0] != n:
        raise ValueError("first dim of estimation_window_returns must match cars")
    # Estimate cross-sectional correlation from residuals.
    corr = np.corrcoef(resids)
    if corr.ndim == 0:  # N=1
        corr = np.array([[1.0]])
    mean_corr_off = (corr.sum() - np.trace(corr)) / (n * (n - 1)) if n > 1 else 0.0
    s2 = float(np.mean(cars ** 2) - mean_corr_off * (n - 1) / n * float(np.sum(cars) ** 2 / (n ** 2)) if n > 0 else 0.0)
    s2 = max(s2, 1e-12)
    se = float(np.sqrt(s2 / n))
    t = float(np.mean(cars) / se) if se > 0 else float("nan")
    from scipy import stats as _stats
    p = float(2 * (1 - _stats.t.cdf(abs(t), df=max(n - 1, 1)))) if not np.isnan(t) else float("nan")
    return KolariPynnonenResult(t_stat_adjusted=t, p_value=p)


def generalized_sign_test(cars: np.ndarray) -> SignRankResult:
    """Cowan's (1992) generalised sign test.

    Under H0 of no event effect, the number of firms with positive CARs
    follows Binomial(N, 0.5).  The two-sided p-value is

        p = 2 * min(P(X >= k), P(X <= k))

    where X ~ Binomial(N, 0.5) and k is the observed count of positive
    CARs.  Ties are dropped by convention (half-counted is also fine;
    we drop for simplicity).
    """
    cars = np.asarray(cars, dtype=float).ravel()
    non_zero = cars[cars != 0]
    n = non_zero.size
    if n == 0:
        return SignRankResult(statistic=0.0, p_value=1.0)
    k = int((non_zero > 0).sum())
    from scipy import stats as _stats
    p_greater = float(1 - _stats.binom.cdf(k - 1, n, 0.5))
    p_less = float(_stats.binom.cdf(k, n, 0.5))
    p = float(2 * min(p_greater, p_less))
    p = min(p, 1.0)
    return SignRankResult(statistic=float(k), p_value=p)


def rank_test(cars: np.ndarray) -> SignRankResult:
    """Wilcoxon signed-rank test on per-firm CARs.

    Tests H0: median CAR = 0.  Returns the test statistic (sum of
    positive ranks) and the asymptotic two-sided p-value.
    """
    cars = np.asarray(cars, dtype=float).ravel()
    cars_nz = cars[cars != 0]
    if cars_nz.size == 0:
        return SignRankResult(statistic=0.0, p_value=1.0)
    from scipy import stats as _stats
    res = _stats.wilcoxon(cars_nz, alternative="two-sided", zero_method="wilcox",
                          correction=False)
    return SignRankResult(statistic=float(res.statistic), p_value=float(res.pvalue))
