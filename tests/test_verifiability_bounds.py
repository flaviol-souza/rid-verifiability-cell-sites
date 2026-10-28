import numpy as np
import pytest

from analysis.verifiability import (
    fisher_information_v3,
    inventory_bounded_decision,
    minimum_external_sites,
    sigma_h_from_information,
)


def test_exact_known_omitted_information_matches_untruncated_geometry():
    dxy = np.array([[100.0, 0.0], [-50.0, 86.6025404], [-50.0, -86.6025404]])
    d3 = np.full(3, 100.0)
    full = fisher_information_v3(dxy, d3, eta=2.2, sigma_db=6.0)
    inside = fisher_information_v3(dxy[:1], d3[:1], eta=2.2, sigma_db=6.0)
    omitted = fisher_information_v3(dxy[1:], d3[1:], eta=2.2, sigma_db=6.0)
    assert inside + omitted == pytest.approx(full)
    result = inventory_bounded_decision(inside, omitted, n_in=1, n_omitted=2, scale_m=200.0)
    assert result["sigma_h_opt_m"] == pytest.approx(sigma_h_from_information(full))
    assert result["upper"] >= result["lower"]


def test_optimistic_decision_never_below_truncated_decision():
    good = np.eye(2) / 100.0**2
    for omitted in (np.zeros((2, 2)), np.eye(2) / 200.0**2):
        result = inventory_bounded_decision(good, omitted, n_in=3, n_omitted=4, scale_m=200.0)
        assert result["upper"] >= result["lower"]


def test_minimum_external_sites_matches_trace_inverse_and_count_floor():
    J = np.diag([1 / 300.0**2, 1 / 400.0**2])
    n = minimum_external_sites(J, d_edge_m=1300.0, fisher_b=2.0, scale_m=100.0, n_possible=1)
    assert n >= 2
    c = n * 2.0**2 / 1300.0**2
    assert sigma_h_from_information(J + c * np.eye(2)) <= 100.0
    if n > 2:
        c_prev = (n - 1) * 2.0**2 / 1300.0**2
        assert sigma_h_from_information(J + c_prev * np.eye(2)) > 100.0
    assert minimum_external_sites(np.eye(2), 1300.0, 2.0, 100.0, 3) == 0


def test_unresolved_optimistic_case_is_explicit_and_upper_one():
    result = inventory_bounded_decision(np.zeros((2, 2)), np.zeros((2, 2)), 0, 3, 100.0)
    assert result["upper"] == 1
    assert result["diagnostic"] == "unresolved_optimistic"
