# Hearing Is Not Verifying: Remote ID Position Verifiability from Existing Cell Sites

Code and frozen numbers for the paper *Hearing Is Not Verifying: Bounding Remote ID Position Checks from Existing Cell Sites* (SBRC 2027).

![Pitch](public/pitch.gif)

## In short

Remote ID makes every drone broadcast its position. Nothing proves the position is true. Cell sites could check it.
We do not build a verifier. We bound what any signal-strength verifier could do, using a Cramér-Rao condition along real flight tracks.

Data: 89 flights of 20 drones at the 2025 São Paulo Grand Prix (Interlagos), and the licensed cell sites of three operators.

| Result | Value |
|---|---|
| Flight time heard by the sites together | 99% |
| Drones verifiable for less than half of their flight time | half of them |
| Share of flight time verifiable by 2 of the 3 operators alone | under 4% |
| Distance within which 3 sites must lie to catch a 100 m lie | about 138 m |

Geometry, not sensitivity, is the limit. Position checks on existing sites need operators to pool their sites.
All numbers are upper bounds: reception is modelled, not measured.

## Layout

```text
src/drs/        cleaning, geometry, channel and observation model
analysis/       observability, verifiability bound, hypotheses, statistics, figures
experiments/    one runner per stage, and configs
tests/          pytest (synthetic data only)
data/           how to get the inputs (data/README.md) and the event geometry
figures/        figures of the paper
results/freeze/ every number in the paper, with its source
```

## Reproduce

Python 3.11 or newer.

```bash
pip install -e .
python -m pytest -q
```

Three levels:

1. **Check the numbers.** Open `results/freeze/numbers.csv`. `results_freeze.md` gives the source file, row and sha256 of each number. No raw data needed.
2. **Re-run the simulation.** Needs the cleaned tracks (see `data/README.md`).
3. **From raw data.** Only for the maintainers: the raw tracks are personal data.

Operator names map to Operator A/B/C through a private file. Create it before steps D to G:

```yaml
# experiments/configs/local/presentation.yaml  (git-ignored)
presentation:
  operator_alias: {<operator name in the site inventory>: A, ...}
```

| Step | Command |
|---|---|
| A. Clean raw tracks (maintainers) | `python experiments/run_stage_a.py` |
| B. Simulation | `python experiments/run_blocks.py --out results/stage_b/blockO --seeds 0-19` |
| C. Hypotheses | `python experiments/run_hypotheses.py --blocks results/stage_b/blockO` |
| D. Summary and figures | `python experiments/run_summary.py --blocks results/stage_b/blockO` |
| E. Maps | `python experiments/run_map.py --out results/stage_b/map --scenario consortium --seeds 0-4` |
| F. Mechanism | `python experiments/run_mechanism.py --blocks results/stage_b/blockO --out results/stage_b/mechanism` |
| G. Freeze | `python experiments/run_freeze.py --blockO results/stage_b/blockO --mechanism results/stage_b/mechanism --map results/stage_b/map --out results/freeze` |

Step G also takes `--interim`, `--anatel` and `--f3-dir` for the descriptive keys. Run `python experiments/run_freeze.py --help`.
Robustness variants (block S) re-run step B with `--sample-filter`, `--agl` or `--override`, and pass `--blockS label=dir` to step G.

## Data and privacy

| Data | Status |
|---|---|
| Raw drone tracks (with pilot, home, serial numbers) | Not published. Personal data |
| Pseudonymisation key | Never stored. Read from an environment variable |
| Cell site records | Public ANATEL records. Operators shown as A/B/C |
| Frozen numbers | Published. Aggregates only |

Pilot and home positions never leave the private pipeline. A/B/C hides names, but public data can still re-identify operators.

## Cite

See `CITATION.cff`.

## License

Code: MIT (`LICENSE`). Data files are not covered by it.

## Contact

Flavio L. S. Souza, ITA. flavioluiz.ssouza@gmail.com