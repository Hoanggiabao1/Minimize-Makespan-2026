from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import run_full_matrix  # noqa: E402
from search_support import (  # noqa: E402
    analytical_cycle_lower_bound,
    average_power_cap,
    initial_probe_horizon,
    upper_lower_power_cap,
)


class HorizonFormulaTests(unittest.TestCase):
    def test_power_cap_formulas_use_exact_integer_arithmetic(self) -> None:
        powers = [11, 7, 5, 2]
        self.assertEqual(average_power_cap(powers, 2), (2 * 25 + 4 * 11) // 8)
        self.assertEqual(upper_lower_power_cap(powers, 2), (11 + 7 + 11) // 2)

    def test_initial_horizon_uses_ceiling_and_power_aware_lower_bound(self) -> None:
        times = [2, 2, 1]
        powers = [5, 4, 3]
        cap = 5
        lower_bound = analytical_cycle_lower_bound(times, powers, 2, cap)
        self.assertEqual(lower_bound, 5)
        self.assertEqual(initial_probe_horizon(times, lower_bound, 2), 5)

    def test_all_paper_configurations_start_at_or_above_every_lower_bound(self) -> None:
        instances = [
            item
            for item in run_full_matrix.load_instances()
            if item.name in run_full_matrix.MAIN_FAMILIES
        ]
        self.assertEqual(len(instances), 72)
        for instance in instances:
            times, powers = run_full_matrix.read_instance_data(instance.name)
            for threshold_dir in run_full_matrix.THRESHOLDS.values():
                qmax = run_full_matrix.qmax_for(threshold_dir, powers, instance.m)
                lower_bound = run_full_matrix.power_aware_lower_bound(
                    times, powers, instance.m, qmax
                )
                c0 = max(run_full_matrix.c_initial(times, instance.m), lower_bound)
                with self.subTest(
                    instance=instance.name, m=instance.m, threshold=threshold_dir
                ):
                    self.assertEqual(
                        c0,
                        initial_probe_horizon(times, lower_bound, instance.m),
                    )
                    self.assertGreaterEqual(c0, lower_bound)
                    self.assertGreaterEqual(c0, max(times))

    def test_lutz2_m49_avg_uses_twenty_not_eighteen(self) -> None:
        times, powers = run_full_matrix.read_instance_data("LUTZ2")
        qmax = run_full_matrix.qmax_for("AVG_Peak", powers, 49)
        lower_bound = run_full_matrix.power_aware_lower_bound(times, powers, 49, qmax)
        c0 = max(run_full_matrix.c_initial(times, 49), lower_bound)
        self.assertEqual(qmax, 670)
        self.assertEqual(lower_bound, 19)
        self.assertEqual(c0, 20)

    def test_orchestrator_passes_initial_horizon_to_cplex_mip(self) -> None:
        instance = run_full_matrix.Instance("LUTZ2", 49, 11)
        command = run_full_matrix.solver_command(
            "AVG_Peak", "cplex_mip", instance, 20, "E"
        )
        self.assertEqual(command[-1], "20")


if __name__ == "__main__":
    unittest.main()
