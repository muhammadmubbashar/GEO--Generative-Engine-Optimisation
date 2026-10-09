"""Recompute the published citation statistics; no API calls or private corpus needed."""
import csv
import json
from pathlib import Path
import numpy as np


def calculate():
    folder = Path(__file__).resolve().parent
    with (folder / 'citation_outcomes.csv').open(encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    ids = sorted({r['query_id'] for r in rows})
    assert len(ids) == 29 and len(rows) == 580
    assert len({(r['query_id'], r['seed'], r['repeat'], r['condition']) for r in rows}) == 580
    counts = {}
    means = {}
    for condition in ('baseline', 'optimised'):
        selected = [r for r in rows if r['condition'] == condition]
        assert len(selected) == 290
        counts[condition] = sum(int(r['citation_inclusion']) for r in selected)
        means[condition] = []
        for qid in ids:
            group = [r for r in selected if r['query_id'] == qid]
            assert len(group) == 10
            assert {(r['seed'], r['repeat']) for r in group} == {(str(s), str(t)) for s in (1, 2) for t in range(1, 6)}
            assert all(r['citation_inclusion'] in ('0', '1') for r in group)
            means[condition].append(sum(int(r['citation_inclusion']) for r in group) / 10)
    d = np.asarray(means['optimised']) - np.asarray(means['baseline'])
    rng = np.random.default_rng(20261009)
    boot = rng.choice(d, (50000, len(d)), replace=True).mean(axis=1)
    null = (rng.choice([-1, 1], (100000, len(d))) * d).mean(axis=1)
    return {
        'queries': 29, 'answers_per_condition': 290, 'citing_answers': counts,
        'baseline_rate': counts['baseline'] / 290,
        'optimised_rate': counts['optimised'] / 290,
        'difference_percentage_points': float(d.mean() * 100),
        'relative_uplift_percent': (counts['optimised'] / counts['baseline'] - 1) * 100,
        'query_bootstrap_95_percentage_points': (np.quantile(boot, [.025, .975]) * 100).tolist(),
        'two_sided_query_sign_flip_p': (1 + int(np.sum(np.abs(null) >= abs(d.mean()) - 1e-12))) / 100001,
        'improved_declined_unchanged': [int(sum(d > 0)), int(sum(d < 0)), int(sum(d == 0))],
    }


if __name__ == '__main__':
    print(json.dumps(calculate(), indent=2))
