from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from calculate_instance_bounds import (  # noqa: E402
    PEAK_TYPES,
    calculate_rows,
    select_instances,
)


class InstanceBoundCalculatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = calculate_rows(select_instances("main"), PEAK_TYPES)

    def test_produces_two_rows_for_each_paper_configuration(self) -> None:
        self.assertEqual(len(self.rows), 144)

    def test_reported_bounds_are_ordered_and_power_feasible(self) -> None:
        for row in self.rows:
            with self.subTest(
                instance=row["instance"],
                m=row["m"],
                peak_type=row["peak_type"],
            ):
                self.assertLessEqual(row["power_lb"], row["qmax"])
                self.assertLessEqual(row["qmax"], row["power_ub"])
                self.assertLessEqual(row["cycle_lb"], row["initial_horizon"])
                self.assertLessEqual(row["cycle_lb"], row["certified_cycle_ub"])

    def test_output_columns_reproduce_the_defining_formulas(self) -> None:
        for row in self.rows:
            with self.subTest(
                instance=row["instance"],
                m=row["m"],
                peak_type=row["peak_type"],
            ):
                if row["peak_type"] == "avg_peak":
                    expected_qmax = (
                        row["power_average_numerator"]
                        + row["power_average_denominator"] * row["power_lb"]
                    ) // (2 * row["power_average_denominator"])
                else:
                    expected_qmax = (
                        row["power_ub"] + row["power_lb"]
                    ) // 2
                expected_workload_lb = (
                    row["total_processing_time"] + row["m"] - 1
                ) // row["m"]
                expected_energy_lb = (
                    row["total_energy"] + row["qmax"] - 1
                ) // row["qmax"]
                expected_cycle_lb = max(
                    row["duration_lb"],
                    expected_workload_lb,
                    expected_energy_lb,
                )
                expected_initial_horizon = max(
                    expected_cycle_lb,
                    row["duration_lb"],
                    (
                        2 * row["total_processing_time"] + row["m"] - 1
                    ) // row["m"],
                )

                self.assertEqual(row["qmax"], expected_qmax)
                self.assertEqual(row["workload_lb"], expected_workload_lb)
                self.assertEqual(row["energy_lb"], expected_energy_lb)
                self.assertEqual(row["cycle_lb"], expected_cycle_lb)
                self.assertEqual(
                    row["initial_horizon"], expected_initial_horizon
                )
                self.assertEqual(
                    row["certified_cycle_ub"],
                    row["total_processing_time"],
                )

    def test_lutz2_m49_distinguishes_the_two_peak_definitions(self) -> None:
        selected = {
            row["peak_type"]: row
            for row in self.rows
            if row["instance"] == "LUTZ2" and row["m"] == 49
        }
        avg = selected["avg_peak"]
        ub_lb = selected["ub_lb_peak"]
        self.assertEqual(avg["qmax"], 670)
        self.assertEqual(ub_lb["qmax"], 914)
        self.assertEqual(avg["cycle_lb"], 19)
        self.assertEqual(ub_lb["cycle_lb"], 14)
        self.assertEqual(avg["initial_horizon"], 20)
        self.assertEqual(ub_lb["initial_horizon"], 20)
        self.assertEqual(avg["certified_cycle_ub"], 485)
        self.assertEqual(ub_lb["certified_cycle_ub"], 485)


if __name__ == "__main__":
    unittest.main()
