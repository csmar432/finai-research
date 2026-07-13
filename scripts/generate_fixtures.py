"""Generate sample data fixtures for offline testing.

T008 audit_fix_2026_07_12: This script generates synthetic data fixtures in
data/sample/ that can be used to test the paper pipeline without real MCP
calls. The fixtures are committed to the repo so users can run smoke tests
out-of-the-box.

Usage:
    python scripts/generate_fixtures.py            # regenerate all fixtures
    python scripts/generate_fixtures.py --seed 7   # change seed for variation
    python scripts/generate_fixtures.py --output /tmp/fixtures  # custom dir

Output files (in data/sample/):
    esg_panel_demo.csv       - 250 obs DID fixture (50 firms × 5 years)
    did_synthetic_panel.csv  - 300 obs staggered DID (30 firms × 10 years)
    references_demo.bib      - 5 entries BibTeX (Callaway, Sun-Abraham, etc.)

All data is SYNTHETIC (numpy RNG with seed=42 default). Do NOT use for
empirical analysis.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


# ── Fixture definitions ──────────────────────────────────────────────────────


def generate_esg_panel(seed: int = 42, n_firms: int = 50, n_years: int = 5) -> pd.DataFrame:
    """Generate ESG-style panel for DID testing.

    Design: 50 firms split into 25 treated (high ESG) + 25 control (low ESG).
    Years: 2018-2022, with treatment in 2020+.
    Treatment effect: -0.05 on leverage (i.e., high ESG firms reduce leverage).
    """
    rng = np.random.default_rng(seed)
    rows = []
    for f in range(n_firms):
        is_treated = f >= n_firms // 2
        esg_tier = "high" if is_treated else "low"
        for y in range(2018, 2018 + n_years):
            post = int(y >= 2020)
            did = int(is_treated and post)
            rows.append({
                "firm_id": f"F{f:03d}",
                "ticker": f"TEST{f:03d}",
                "year": y,
                "esg_tier": esg_tier,
                "esg_high": int(is_treated),
                "post": post,
                "did": did,
                "lev": float(np.clip(0.4 + rng.normal(0, 0.1) + (-0.05 if did else 0), 0.05, 0.95)),
                "ltd_ratio": float(np.clip(0.25 + rng.normal(0, 0.08) + (-0.03 if did else 0), 0.0, 0.8)),
                "cost_debt": float(np.clip(0.05 + rng.normal(0, 0.015) + (-0.01 if did else 0), 0.01, 0.15)),
                "ln_assets": float(8.0 + rng.normal(0, 1.0)),
                "roa": float(np.clip(0.05 + rng.normal(0, 0.03), 0.0, 0.20)),
                "tangibility": float(np.clip(0.30 + rng.normal(0, 0.1), 0.0, 0.8)),
                "mb": float(np.clip(1.5 + rng.normal(0, 0.5), 0.5, 5.0)),
                "cash_ratio": float(np.clip(0.15 + rng.normal(0, 0.05), 0.0, 0.5)),
            })
    return pd.DataFrame(rows)


def generate_did_panel(seed: int = 42, n_firms: int = 30, n_years: int = 10,
                      start_year: int = 2010, treat_year: int = 2015) -> pd.DataFrame:
    """Generate staggered DID panel for modern DID estimators.

    Half treated (treatment year 2015), half never-treated.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for f in range(n_firms):
        is_treated = f >= n_firms // 2
        unit_treat_year = treat_year if is_treated else 9999
        for y in range(start_year, start_year + n_years):
            post = int(y >= unit_treat_year and is_treated)
            rows.append({
                "firm_id": f"S{f:03d}",
                "year": y,
                "treat": int(is_treated),
                "post": post,
                "did": int(is_treated and post),
                "y": float(0.5 + 0.05 * (y - start_year) + rng.normal(0, 0.1)
                           + (0.15 if (is_treated and post) else 0)),
                "x1": float(rng.normal(0, 1)),
                "x2": float(rng.normal(0, 1)),
            })
    return pd.DataFrame(rows)


REFERENCES_DEMO = """@article{callaway2021difference,
  title={Difference-in-differences with multiple time periods},
  author={Callaway, Brantly and Sant'Anna, Pedro HC},
  journal={Journal of Econometrics},
  volume={225},
  number={2},
  pages={200--230},
  year={2021},
  doi={10.1016/j.jeconom.2020.12.001}
}

@article{sun2021event,
  title={Event-study designs with staggered treatment timing},
  author={Sun, Liyang and Abraham, Sarah},
  journal={Journal of Econometrics},
  year={2021},
  doi={10.1016/j.jeconom.2021.02.007}
}

@article{borusyak2024revisiting,
  title={Revisiting Event-Study Designs: Robust and Efficient Estimation},
  author={Borusyak, Kirill and Jaravel, Xavier and Spinks, Jann Spiess},
  journal={Review of Economic Studies},
  year={2024},
  doi={10.1093/restud/rdad070}
}

@article{abadie2010synthetic,
  title={Synthetic Control Methods for Comparative Case Studies},
  author={Abadie, Alberto and Diamond, Alexis and Hainmueller, Jens},
  journal={Journal of the American Statistical Association},
  volume={105},
  number={490},
  pages={493--505},
  year={2010}
}

@article{roth2023pretest,
  title={Pre-test with Caution: Event-Study Estimates After Testing for Parallel Trends},
  author={Roth, Jonathan and Sant'Anna, Pedro HC},
  journal={Biometrika},
  year={2023}
}
"""


# ── Main ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate sample data fixtures.")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed (default: 42)")
    parser.add_argument("--output", type=Path, default=Path("data/sample"),
                        help="Output directory (default: data/sample)")
    args = parser.parse_args(argv)

    output_dir: Path = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating fixtures (seed={args.seed}) → {output_dir}")

    # Fixture 1: ESG panel
    esg_df = generate_esg_panel(seed=args.seed)
    esg_path = output_dir / "esg_panel_demo.csv"
    esg_df.to_csv(esg_path, index=False)
    print(f"  ✓ {esg_path.name}: {len(esg_df)} obs, "
          f"{esg_df.firm_id.nunique()} firms, {esg_df.year.nunique()} years")

    # Fixture 2: DID staggered
    did_df = generate_did_panel(seed=args.seed)
    did_path = output_dir / "did_synthetic_panel.csv"
    did_df.to_csv(did_path, index=False)
    print(f"  ✓ {did_path.name}: {len(did_df)} obs, "
          f"{did_df.firm_id.nunique()} firms, {did_df.year.nunique()} years")

    # Fixture 3: BibTeX
    bib_path = output_dir / "references_demo.bib"
    bib_path.write_text(REFERENCES_DEMO)
    n_entries = REFERENCES_DEMO.count("@article{")
    print(f"  ✓ {bib_path.name}: {n_entries} BibTeX entries")

    print("\nAll fixtures generated. To test:")
    print("  python scripts/generate_fixtures.py")
    print("  python notebooks/00_quickstart.ipynb")
    return 0


if __name__ == "__main__":
    sys.exit(main())
