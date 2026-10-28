from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
MODIFIED_DIR = APP_DIR / "Modified PyParse"
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(MODIFIED_DIR))

spec = importlib.util.spec_from_file_location("xinpilot_modified_pyparse", MODIFIED_DIR / "PyParse.py")
modified_pyparse = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(modified_pyparse)

from cheminformatics_frame import CheminformaticsFrame, _trace_crop_box  # noqa: E402
import impurity_analysis as xinpilot_impurity_analysis  # noqa: E402
from integrated_full_software import IntegratedFullApp  # noqa: E402
from xinpilot_shared import (  # noqa: E402
    PRODUCT_REACTANT_MASS_CONFLICT,
    _canonical_smiles_key,
    _read_modified_pyparse_conflicts_by_product,
    _read_modified_pyparse_uv254_purity_by_product,
)
from pyparse_runner_frame import (  # noqa: E402
    PyParseRunnerFrame,
    _output_dir_has_pyparse_results,
    _pyparse_platemap_kind,
    _pyparse_platemap_signature,
)


class ModifiedPyParseAnnotationTests(unittest.TestCase):
    def test_duplicate_peak_records_product_reactant_mass_conflict(self):
        previous_plate_cols = modified_pyparse.options.plate_col_no
        modified_pyparse.options.plate_col_no = 12
        product_hit = {"time": 1.2842, "well": 2, "cluster": 0}
        reactant_hit = {"time": 1.2842, "well": 2, "cluster": 0}
        compounds = modified_pyparse.pd.DataFrame.from_dict(
            {
                "product": {
                    "name": "Product1",
                    "hits": {"green": [product_hit], "discarded": [], "discarded_by_cluster": []},
                    "comments": [],
                },
                "reactant": {
                    "name": "Reactant1",
                    "hits": {"green": [reactant_hit], "discarded": [], "discarded_by_cluster": []},
                    "comments": [],
                },
            },
            orient="index",
        )
        try:
            result = modified_pyparse.removeDupAssigns(
                compounds,
                internalSTD="",
                SMs=["Reactant1"],
                products=["Product1"],
                by_products=[],
            )
        finally:
            modified_pyparse.options.plate_col_no = previous_plate_cols

        self.assertEqual([], result.loc["product", "hits"]["green"])
        self.assertEqual(1, len(result.loc["reactant", "hits"]["green"]))
        self.assertEqual(
            {"A2": PRODUCT_REACTANT_MASS_CONFLICT},
            result.loc["product", "assignment_conflicts"],
        )

    def test_unassigned_product_peak_has_zero_uv254_purity(self):
        peaks = [
            {"pStart": 1.0, "pEnd": 1.2, "areaAbs": 38.68},
            {"pStart": 2.0, "pEnd": 2.2, "areaAbs": 61.32},
        ]
        self.assertEqual(
            0.0,
            modified_pyparse.compute_assigned_product_uv254_purity(
                peaks,
                accepted_hits=[],
                highlight_ranges=[(1.0, 1.2)],
            ),
        )
        self.assertEqual(
            38.68,
            modified_pyparse.compute_assigned_product_uv254_purity(
                peaks,
                accepted_hits=[peaks[0]],
                highlight_ranges=[(1.0, 1.2)],
            ),
        )

    def test_br_and_cl_keep_major_m_plus_two_but_small_isotopes_are_ignored(self):
        no_halogen = modified_pyparse._major_isotope_neutral_masses("CCO")
        bromide = modified_pyparse._major_isotope_neutral_masses("CCBr")
        chloride = modified_pyparse._major_isotope_neutral_masses("CCCl")

        self.assertEqual(1, len(no_halogen))
        self.assertEqual(2, len(bromide))
        self.assertEqual(2, len(chloride))
        self.assertAlmostEqual(2.00, bromide[1] - bromide[0], places=2)
        self.assertTrue(all(value == round(value, 2) for value in bromide + chloride))

    def test_multiple_bromines_keep_the_major_isotope_cluster(self):
        masses = modified_pyparse._major_isotope_neutral_masses("BrCBr")
        self.assertEqual(3, len(masses))
        self.assertEqual([2.00, 2.00], [round(b - a, 2) for a, b in zip(masses, masses[1:])])

    def test_target_ions_are_two_decimal_mz_values(self):
        self.assertEqual([99.01, 101.01], modified_pyparse._target_ion_masses([98.00, 100.00], "+"))
        self.assertEqual([96.99, 98.99], modified_pyparse._target_ion_masses([98.00, 100.00], "-"))

    def test_uv_words_are_filtered_by_product_summary_mode(self):
        peaks = [
            {"cpname": "RXN-4__Product1", "time": 1.2, "observed": True},
            {"cpname": "Impurity1", "time": 2.1, "observed": True},
            {"cpname": "Byproduct2", "time": 2.8, "observed": True},
            {"cpname": "Impurity3", "time": 3.4, "observed": False},
        ]
        self.assertEqual([(1.5, "Product")], modified_pyparse._uv_target_annotations(peaks, "product", [1.5]))
        self.assertEqual(
            [(2.1, "Impurity 1"), (2.8, "Impurity 2")],
            modified_pyparse._uv_target_annotations(peaks, "impurity", [1.5]),
        )

    def test_target_labels_require_strictly_over_20_percent_and_collapse_centroids(self):
        spectrum = [
            (386.89, 20.0), (387.06, 49.0),
            (387.22, 80.0), (387.23, 70.0),
        ]
        self.assertEqual(
            [387.22],
            modified_pyparse._observed_target_masses(spectrum, [387.10], 0.5),
        )
        self.assertEqual(
            [],
            modified_pyparse._observed_target_masses([(414.09, 20.0)], [414.14], 0.5),
        )

    def test_strong_es_trace_labels_require_over_50_percent_and_use_observed_mass(self):
        trace = [
            [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
            [0.0, 50.0, 10.0, 100.0, 20.0, 60.0],
        ]
        peaks = [
            {"time": 1.0, "MS+": [(150.0, 100.0)]},
            {"time": 3.02, "MS+": [(200.0, 20.0), (201.25, 90.0)]},
            {"time": 5.0, "MS+": [(300.0, 10.0), (301.75, 80.0)]},
        ]

        labels = modified_pyparse._strong_es_trace_mass_labels(
            trace, peaks, "MS+"
        )

        self.assertEqual([3.0, 5.0], [item["time"] for item in labels])
        self.assertEqual([201.25, 301.75], [item["mass"] for item in labels])
        self.assertNotIn(1.0, [item["time"] for item in labels])

    def test_observed_match_keeps_experimental_retention_time(self):
        peaks = [{"time": 1.53, "MS-": [(449.62, 60.0)], "MS+": []}]
        self.assertEqual(
            [{"time": 1.53, "masses": [449.62]}],
            modified_pyparse._observed_target_matches(peaks, [449.60], "-", [1.5], 0.5),
        )
        self.assertEqual(
            [],
            modified_pyparse._observed_target_matches(peaks, [449.60], "-", [], 0.5),
        )

    def test_trace_labels_are_horizontal_and_include_retention_time(self):
        modified_pyparse.options = SimpleNamespace(
            plate_col_no=12, uv254_exclude_rt="", min_peak_area=0.5,
            min_rel_intensity_well=0.08, min_rel_area_well=0.01,
        )
        trace = {
            "uv": [[0.0, 1.0, 1.5, 2.0, 3.0], [0.0, 15.0, 80.0, 10.0, 0.0]],
            "ms_plus": [[0.0, 1.0, 1.5, 2.0, 3.0], [0.0, 1.0, 2.0, 1.0, 0.0]],
            "ms_minus": [[0.0, 1.0, 1.5, 2.0, 3.0], [0.0, 5.0, 50.0, 4.0, 0.0]],
        }
        peak = {
            "time": 1.5, "pStart": 1.4, "pEnd": 1.6, "area": 80.0, "areaAbs": 80.0,
            "MS+": [], "MS-": [(345.17, 100.0), (414.09, 60.0)],
        }
        captured = []

        def capture_figure(*_args, **_kwargs):
            for axis in modified_pyparse.plt.gcf().axes:
                for item in axis.texts:
                    captured.append((item.get_text(), item.get_rotation(), item.get_color(), item.get_fontweight()))

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            modified_pyparse.plt, "savefig", side_effect=capture_figure
        ):
            (Path(tmp) / "graphs").mkdir()
            modified_pyparse.plotChroma(
                "Product1", 1, trace, 1.4, 1.6,
                [], f"{tmp}/", [], [(345.17, 100.0), (414.09, 60.0)], 415.10,
                [peak], target_masses=[415.10], annotation_mode="product",
            )

        labels = [item[0] for item in captured]
        self.assertIn("m/z 414.09\n1.50 min", labels)
        product_label = next(item for item in captured if item[0] == "Product\n1.50 min")
        self.assertEqual(0.0, product_label[1])
        self.assertEqual("black", product_label[2])
        self.assertEqual("bold", product_label[3])

    def test_generic_strong_es_mass_label_is_added_without_replacing_target_label(self):
        modified_pyparse.options = SimpleNamespace(
            plate_col_no=12, uv254_exclude_rt="", min_peak_area=0,
            min_rel_intensity_well=0, min_rel_area_well=0,
            calc_higherions="True",
        )
        trace = {
            "uv": [[1.0, 1.5, 2.0, 2.5, 3.0], [0.0, 80.0, 0.0, 50.0, 0.0]],
            "ms_plus": [[1.0, 1.5, 2.0, 2.5, 3.0], [0.0, 100.0, 5.0, 60.0, 0.0]],
            "ms_minus": [[1.0, 1.5, 2.0, 2.5, 3.0], [0.0, 5.0, 2.0, 2.0, 0.0]],
        }
        product_peak = {
            "time": 1.5, "pStart": 1.4, "pEnd": 1.6,
            "area": 80.0, "areaAbs": 80.0,
            "MS+": [(227.12, 100.0)], "MS-": [],
        }
        strong_non_target_peak = {
            "time": 2.5, "pStart": 2.4, "pEnd": 2.6,
            "area": 50.0, "areaAbs": 50.0,
            "MS+": [(333.33, 100.0), (334.33, 30.0)], "MS-": [],
        }
        evidence = modified_pyparse._resolve_product_evidence(
            [product_peak, strong_non_target_peak],
            [226.11],
            selected_peaks=[product_peak],
            tolerance=0.5,
        )
        captured = []

        def capture_figure(*_args, **_kwargs):
            for axis in modified_pyparse.plt.gcf().axes:
                captured.extend(item.get_text() for item in axis.texts)

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            modified_pyparse.plt, "savefig", side_effect=capture_figure
        ):
            (Path(tmp) / "graphs").mkdir()
            modified_pyparse.plotChroma(
                "Product1", 1, trace, 1.4, 1.6,
                [], f"{tmp}/", product_peak["MS+"], product_peak["MS-"], 226.11,
                [product_peak, strong_non_target_peak], target_masses=[226.11],
                annotation_mode="product", product_evidence=evidence,
            )

        self.assertIn("m/z 227.12\n1.50 min", captured)
        self.assertIn("m/z 333.33", captured)
        self.assertEqual(1, captured.count("m/z 227.12\n1.50 min"))

    def test_summary_exact_mass_is_two_decimal_places(self):
        self.assertEqual("123.46", CheminformaticsFrame._format_mass_2dp("123.456789"))

    def test_trace_rendering_obeys_configured_peak_thresholds(self):
        modified_pyparse.options = SimpleNamespace(
            min_peak_area=0.5, min_rel_intensity_well=0.30, min_rel_area_well=0.10
        )
        peaks = [
            {"area": 70.0, "areaAbs": 70.0},
            {"area": 20.0, "areaAbs": 20.0},
            {"area": 10.0, "areaAbs": 10.0},
        ]
        self.assertEqual(
            [peaks[0]],
            modified_pyparse._threshold_qualified_well_peaks(peaks),
        )

    def test_product_target_evidence_is_found_without_an_impurity_assignment(self):
        modified_pyparse.options = SimpleNamespace(
            min_peak_area=0,
            min_rel_intensity_well=0,
            min_rel_area_well=0,
            calc_higherions="True",
        )
        unrelated = {
            "time": 1.0, "area": 80, "areaAbs": 80,
            "MS+": [(150.0, 100.0)], "MS-": [],
        }
        product = {
            "time": 1.52, "area": 20, "areaAbs": 20,
            "MS+": [(227.19, 96.0)], "MS-": [],
            "pStart": 1.48, "pEnd": 1.56,
        }
        selected = modified_pyparse._best_observed_target_peak(
            [unrelated, product], [226.11], tolerance=0.5
        )
        self.assertIs(product, selected)

    def test_selected_product_evidence_uses_exact_peak_not_nearer_empty_record(self):
        modified_pyparse.options = SimpleNamespace(
            min_peak_area=0,
            min_rel_intensity_well=0,
            min_rel_area_well=0,
            calc_higherions="True",
        )
        product_peak = {
            "time": 1.8534, "pStart": 1.8392, "pEnd": 1.8934,
            "area": 42.12, "areaAbs": 483.85, "peakID": 87,
            "MS+": [(244.13, 100.0)], "MS-": [],
        }
        nearer_midpoint_record = {
            "time": 1.8618, "pStart": 0, "pEnd": 0,
            "area": 0, "areaAbs": 0, "peakID": 88,
            "MS+": [], "MS-": [],
        }
        accepted_hit = {
            "time": 1.8534, "pStart": 1.8392, "pEnd": 1.8934,
            "area": 42.12, "areaAbs": 483.85,
        }

        evidence = modified_pyparse._resolve_product_evidence(
            [product_peak, nearer_midpoint_record], [243.105942],
            selected_peaks=[accepted_hit], tolerance=0.5,
        )

        self.assertEqual(1, len(evidence))
        self.assertIs(product_peak, evidence[0]["peak"])
        self.assertEqual(1.8534, evidence[0]["time"])
        self.assertEqual([244.13], [ion["mass"] for ion in evidence[0]["ions"]])

    def test_higher_charge_product_evidence_uses_same_rule_as_identification(self):
        modified_pyparse.options = SimpleNamespace(
            min_peak_area=0,
            min_rel_intensity_well=0,
            min_rel_area_well=0,
            calc_higherions="True",
        )
        product_peak = {
            "time": 1.3725, "pStart": 1.3425, "pEnd": 1.4009,
            "area": 3.99, "areaAbs": 17.30, "peakID": 50,
            "MS+": [(128.16, 100.0), (114.22, 90.326)], "MS-": [],
        }
        accepted_hit = {
            "time": 1.3725, "pStart": 1.3425, "pEnd": 1.4009,
            "mass+": 114.22,
        }

        evidence = modified_pyparse._resolve_product_evidence(
            [product_peak], [226.110613], selected_peaks=[accepted_hit], tolerance=0.5,
        )

        self.assertEqual(1, len(evidence))
        ion = evidence[0]["ions"][0]
        self.assertEqual(114.22, ion["mass"])
        self.assertEqual(2, ion["charge"])
        self.assertEqual("[M+2H]2+", ion["adduct"])

        modified_pyparse.options.calc_higherions = "False"
        self.assertEqual(
            [],
            modified_pyparse._resolve_product_evidence(
                [product_peak], [226.110613], selected_peaks=[accepted_hit], tolerance=0.5,
            ),
        )

    def test_higher_charge_trace_label_uses_experimental_mass_and_charge(self):
        modified_pyparse.options = SimpleNamespace(
            plate_col_no=12, uv254_exclude_rt="", min_peak_area=0,
            min_rel_intensity_well=0, min_rel_area_well=0,
            calc_higherions="True",
        )
        trace = {
            "uv": [[1.2, 1.3725, 1.5], [0.0, 50.0, 0.0]],
            "ms_plus": [[1.2, 1.3725, 1.5], [5.0, 95.0, 5.0]],
            "ms_minus": [[1.2, 1.3725, 1.5], [2.0, 2.0, 2.0]],
        }
        peak = {
            "time": 1.3725, "pStart": 1.3425, "pEnd": 1.4009,
            "area": 3.99, "areaAbs": 17.30, "peakID": 50,
            "MS+": [(128.16, 100.0), (114.22, 90.326)], "MS-": [],
        }
        evidence = modified_pyparse._resolve_product_evidence(
            [peak], [226.110613], selected_peaks=[peak], tolerance=0.5,
        )
        captured = []

        def capture_figure(*_args, **_kwargs):
            for axis in modified_pyparse.plt.gcf().axes:
                captured.extend(item.get_text() for item in axis.texts)

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            modified_pyparse.plt, "savefig", side_effect=capture_figure
        ):
            (Path(tmp) / "graphs").mkdir()
            modified_pyparse.plotChroma(
                "Product2", 1, trace, 1.3425, 1.4009,
                [], f"{tmp}/", peak["MS+"], peak["MS-"], 226.110613,
                [peak], target_masses=[226.110613], annotation_mode="product",
                product_evidence=evidence,
            )

        self.assertIn("m/z 114.22 [M+2H]2+\n1.37 min", captured)
        self.assertIn("Product\n1.37 min", captured)
        self.assertNotIn("No observed target-mass trace available", captured)

    def test_frequent_impurity_search_allows_duplicate_peak_assignments(self):
        modified_pyparse.options = SimpleNamespace(
            mass_abs_tol=0.5,
            time_abs_tol=0.1,
            min_no_of_wells=1,
            plate_row_no=8,
            plate_col_no=12,
        )
        peak = {"well": 1, "time": 1.7967, "MS+": [], "MS-": []}
        duplicate_hit = {"well": 1, "time": 1.7967}
        compounds = modified_pyparse.pd.DataFrame([
            {"hits": {"green": [duplicate_hit]}},
            {"hits": {"green": [dict(duplicate_hit)]}},
        ])
        result = modified_pyparse.findImpurities(
            {1: [peak]}, compounds, "unused", {}
        )
        self.assertEqual([], result)

    def test_structure_preview_mz_is_calculated_from_cheminformatics(self):
        calculated = CheminformaticsFrame._structure_preview_mz("CCBr")
        self.assertEqual(2, len(calculated["minus"]))
        self.assertEqual(2, len(calculated["plus"]))
        self.assertAlmostEqual(2.00, calculated["minus"][1] - calculated["minus"][0], places=2)
        expected = (
            "ES− " + ", ".join(f"{value:.2f}" for value in calculated["minus"])
            + "; ES+ " + ", ".join(f"{value:.2f}" for value in calculated["plus"])
        )
        self.assertEqual(expected, CheminformaticsFrame._format_mz(calculated))

    def test_impurity_trace_lookup_prefers_combined_same_well_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            graphs = output_dir / "graphs"
            graphs.mkdir()
            expected = graphs / "chroma-ImpuritySummary__A1-A1-uv254.jpg"
            expected.touch()
            (graphs / "chroma-Impurity1__A1_A1-A1-uv254.jpg").touch()
            frame = object.__new__(CheminformaticsFrame)
            result = frame._find_impurity_trace_path(
                output_dir,
                "A1",
                [{"pyparse_name": "Impurity1__A1_A1", "label": "Impurity 1"}],
                avoid_uv254=False,
                prefer_uv254=True,
            )
            self.assertEqual(expected, result)
            expected.unlink()
            self.assertIsNone(frame._find_impurity_trace_path(
                output_dir,
                "A1",
                [{"pyparse_name": "Impurity1__A1_A1", "label": "Impurity 1"}],
                avoid_uv254=False,
                prefer_uv254=True,
                summary_only=True,
            ))

    def test_combined_impurity_trace_keeps_product_red_ranges(self):
        modified_pyparse.options = SimpleNamespace(
            plate_col_no=12, split_product_peaks="False", uv254_purity="True"
        )
        product_hit = {
            "well": 1, "time": 1.2, "pStart": 1.1, "pEnd": 1.3,
            "mass_conf": 80, "area": 90,
        }
        impurity_hit = {
            "well": 1, "time": 2.1, "pStart": 2.0, "pEnd": 2.2,
            "mass_conf": 70, "area": 40,
        }
        compound_df = modified_pyparse.pd.DataFrame([
            {
                "name": "Product1", "type": "Product", "locations": [1],
                "hits": {"green": [product_hit], "discarded": []},
                "g_smiles": "CCO", "mass1": 46.04,
            },
            {
                "name": "Impurity1__A1_A1", "type": "Byproduct", "locations": [1],
                "hits": {"green": [impurity_hit], "discarded": []},
                "g_smiles": "CCBr", "mass1": 107.96,
            },
        ])
        peak_data = [{
            "time": 1.2, "MS+": [], "MS-": [], "pStart": 1.1, "pEnd": 1.3,
            "area": 90, "areaAbs": 90,
        }]
        with patch.object(modified_pyparse, "plotChroma") as plot:
            modified_pyparse.plotImpuritySummaryTraces(
                compound_df, {1: {"uv": [], "ms_plus": [], "ms_minus": []}},
                {1: peak_data}, "unused/",
            )
        self.assertEqual(2, plot.call_count)
        first = plot.call_args_list[0]
        self.assertEqual("ImpuritySummary__A1", first.args[0])
        self.assertEqual([(1.1, 1.3)], first.kwargs["highlight_ranges"])
        self.assertEqual("impurity", first.kwargs["annotation_mode"])
        self.assertEqual("Impurity1", first.args[5][0]["cpname"].split("__", 1)[0])


class _FakeNotebook:
    def __init__(self, title):
        self.title = title

    def tab(self, _which, _option):
        return self.title


class _FakeTree:
    def __init__(self, existing, selected=()):
        self.existing = {str(value) for value in existing}
        self.selected = tuple(str(value) for value in selected)

    def selection(self):
        return self.selected

    def selection_remove(self, *items):
        self.selected = ()

    def selection_set(self, iid):
        self.selected = (str(iid),)

    def focus(self, _iid):
        return None

    def see(self, _iid):
        return None

    def exists(self, iid):
        return str(iid) in self.existing


class _FakeLabel:
    def __init__(self):
        self.config = {}

    def configure(self, **kwargs):
        self.config.update(kwargs)

    def bind(self, sequence, callback):
        return 'fake-binding'

    def unbind(self, sequence, binding=None):
        pass


class _FakeGridWidget(_FakeLabel):
    def __init__(self):
        super().__init__()
        self.grid_config = {}
        self.visible = True

    def grid_configure(self, **kwargs):
        self.grid_config.update(kwargs)

    def grid_remove(self):
        self.visible = False

    def grid(self):
        self.visible = True


class _FakeVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class AutomaticImpurityWorkflowTests(unittest.TestCase):
    def test_impurity_preview_uses_full_width_and_product_preview_restores_comparison(self):
        frame = object.__new__(CheminformaticsFrame)
        frame.product_structure_heading = _FakeGridWidget()
        frame.product_structure_lcms_heading = _FakeGridWidget()
        frame.product_structure_label = _FakeGridWidget()
        frame.product_structure_lcms_label = _FakeGridWidget()

        frame._set_product_structure_comparison_layout(impurity_mode=True)

        self.assertEqual("Potential impurity structures", frame.product_structure_heading.config["text"])
        self.assertEqual(2, frame.product_structure_heading.grid_config["columnspan"])
        self.assertEqual(2, frame.product_structure_label.grid_config["columnspan"])
        self.assertFalse(frame.product_structure_lcms_heading.visible)
        self.assertFalse(frame.product_structure_lcms_label.visible)

        frame._set_product_structure_comparison_layout(impurity_mode=False)

        self.assertEqual("Product Details structure", frame.product_structure_heading.config["text"])
        self.assertEqual(1, frame.product_structure_heading.grid_config["columnspan"])
        self.assertEqual(1, frame.product_structure_label.grid_config["columnspan"])
        self.assertTrue(frame.product_structure_lcms_heading.visible)
        self.assertTrue(frame.product_structure_lcms_label.visible)

    def test_all_valid_candidates_are_included_by_default(self):
        frame = object.__new__(CheminformaticsFrame)
        frame.impurity_exclusions = {}
        frame._impurity_cache_signature = ""
        frame._impurity_cache_rows = []
        frame._pyparse_rows = lambda: [{
            "reaction_name": "RXN-1",
            "reaction": "",
            "reaction_well": "A1",
            "pyparse_well": "C1",
            "desired product smiles": "CCO",
        }]
        frame._reaction_by_id = lambda _reaction_id: None
        frame.logw = lambda *_args, **_kwargs: None
        predicted = [
            {"reaction_name": "RXN-1", "reaction_well": "A1", "pyparse_well": "C1", "smiles": "CCN"},
            {"reaction_name": "RXN-1", "reaction_well": "A1", "pyparse_well": "C1", "smiles": "CCC"},
        ]

        with patch.object(xinpilot_impurity_analysis, "flatten_impurity_rows", return_value=predicted):
            rows = frame._impurity_rows()

        self.assertEqual(["Yes", "Yes"], [row["included"] for row in rows])
        self.assertEqual(2, len(frame._included_impurity_rows()))

        frame.impurity_exclusions[frame._impurity_target_key(rows[0])] = True
        self.assertEqual(["No", "Yes"], [row["included"] for row in frame._impurity_rows()])

    def test_prediction_deduplicates_structures_and_excludes_the_product(self):
        candidates = xinpilot_impurity_analysis.predict_impurities(
            "",
            "CCO",
            "CCN",
            "CCN",
            reactants=[
                {"smiles": "CCO", "name": "Desired product duplicate"},
                {"smiles": "CCN", "name": "Starting material"},
                {"smiles": "CCN", "name": "Duplicate starting material"},
            ],
            accepted_product_smiles=["CCO"],
        )

        smiles = [row["smiles"] for row in candidates]
        self.assertNotIn("CCO", smiles)
        self.assertEqual(len(smiles), len(set(smiles)))
        self.assertEqual(["CCN"], smiles)

    def test_generation_forwards_all_targets_for_ready_reactions_only(self):
        frame = object.__new__(CheminformaticsFrame)
        frame._pyparse_rows = lambda: [
            {"reaction_well": "A1", "pyparse_well": "C1", "desired product smiles": "CCO"},
            {"reaction_well": "A2", "pyparse_well": "", "desired product smiles": "CCN"},
        ]
        frame._is_valid_pyparse_well = lambda well: well == "C1"
        frame._included_impurity_rows = lambda: [
            {"reaction_well": "A1", "smiles": "CCC"},
            {"reaction_well": "A1", "smiles": "CCCl"},
            {"reaction_well": "A2", "smiles": "CCBr"},
        ]
        frame.impurity_pyparse_output_var = _FakeVar("automatic-impurities.csv")
        captured = {}
        frame._write_pyparse_platemap = lambda path, rows, impurities: captured.update({
            "path": path,
            "rows": rows,
            "impurities": impurities,
        })
        frame.modified_pyparse_input_callback = lambda path: captured.update({"callback": path})
        frame.logw = lambda *_args, **_kwargs: None

        with patch("cheminformatics_frame.messagebox.showinfo") as showinfo:
            frame._generate_impurity_pyparse_input()

        self.assertEqual(Path("automatic-impurities.csv"), captured["path"])
        self.assertEqual(1, len(captured["rows"]))
        self.assertEqual(["CCC", "CCCl"], [row["smiles"] for row in captured["impurities"]])
        self.assertEqual(captured["path"], captured["callback"])
        self.assertIn("all 2 valid predicted impurity target(s)", showinfo.call_args.args[1])


class CloseWorkflowTests(unittest.TestCase):
    @staticmethod
    def _app(export_result=True):
        events = []
        app = SimpleNamespace(
            _close_prompt_active=False,
            _export_project=lambda: events.append("export") or export_result,
            destroy=lambda: events.append("destroy"),
        )
        return app, events

    def test_yes_exports_then_closes(self):
        app, events = self._app(export_result=True)
        with patch("integrated_full_software.messagebox.askyesnocancel", return_value=True) as prompt:
            IntegratedFullApp._confirm_close(app)

        self.assertEqual(["export", "destroy"], events)
        self.assertIn("export a portable XinPilot project", prompt.call_args.args[1])
        self.assertFalse(app._close_prompt_active)

    def test_cancelled_or_failed_export_keeps_app_open(self):
        app, events = self._app(export_result=False)
        with patch("integrated_full_software.messagebox.askyesnocancel", return_value=True):
            IntegratedFullApp._confirm_close(app)
        self.assertEqual(["export"], events)

        app, events = self._app()
        with patch("integrated_full_software.messagebox.askyesnocancel", return_value=None):
            IntegratedFullApp._confirm_close(app)
        self.assertEqual([], events)

    def test_no_closes_without_exporting(self):
        app, events = self._app()
        with patch("integrated_full_software.messagebox.askyesnocancel", return_value=False):
            IntegratedFullApp._confirm_close(app)
        self.assertEqual(["destroy"], events)


class ProductSummarySelectionTests(unittest.TestCase):
    def test_modified_purity_keeps_product_identity_and_zeroes_unassigned_product(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            (output_dir / "compoundtable.csv").write_text(
                "name,g_smiles,best_well,best_purity254,purity_by_well,qc_flag\n"
                "Product1,CCO,None found.,0,{'A2': 38.68},NOT_FOUND\n"
                "StartingMaterial,CCN,A2,38.68,{'A2': 38.68},OK\n"
                "Product2,CCC,A3,42.13,{'A3': 42.13},OK\n",
                encoding="utf-8",
            )
            (output_dir / "aTable.csv").write_text(
                "well_ID,analyte_smiles,analyte_class,data_entry,data_type\n"
                "A2,CCO,desired product,0,Retention Time\n"
                "A2,CCO,desired product,0,Percentage Area\n"
                "A3,CCC,desired product,1.25,Retention Time\n"
                "A3,CCC,desired product,42.12,Percentage Area\n",
                encoding="utf-8",
            )

            values = _read_modified_pyparse_uv254_purity_by_product(output_dir)

        self.assertEqual("0.00%", values[_canonical_smiles_key("CCO")]["A2"])
        self.assertEqual("42.13%", values[_canonical_smiles_key("CCC")]["A3"])
        self.assertNotIn(_canonical_smiles_key("CCN"), values)

    def test_modified_purity_lookup_uses_product_and_well_not_well_alone(self):
        frame = object.__new__(CheminformaticsFrame)
        frame.modified_pyparse_purity_by_product = {
            _canonical_smiles_key("CCO"): {"A2": "0.00%"},
            _canonical_smiles_key("CCN"): {"A2": "38.68%"},
        }
        frame.modified_pyparse_purity_by_well = {"A2": "38.68%"}

        value = frame._modified_pyparse_purity_for_row({
            "desired product smiles": "CCO",
            "pyparse_well": "A2",
        })

        self.assertEqual("0.00%", value)

    def test_modified_conflict_reader_and_display_keep_numeric_purity_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            (output_dir / "compoundtable.csv").write_text(
                "name,g_smiles,best_well,best_purity254,purity_by_well,assignment_conflicts,qc_flag\n"
                "Product1,CCO,None found.,0,{'A2': 0},{'A2': 'PRODUCT_REACTANT_MASS_CONFLICT'},NOT_FOUND\n",
                encoding="utf-8",
            )
            conflicts = _read_modified_pyparse_conflicts_by_product(output_dir)

        key = _canonical_smiles_key("CCO")
        self.assertEqual(PRODUCT_REACTANT_MASS_CONFLICT, conflicts[key]["A2"])

        frame = object.__new__(CheminformaticsFrame)
        frame.modified_pyparse_purity_by_product = {key: {"A2": "0.00%"}}
        frame.modified_pyparse_conflicts_by_product = conflicts
        row = {"desired product smiles": "CCO", "pyparse_well": "A2"}

        self.assertEqual("0.00%", frame._modified_pyparse_purity_for_row(row))
        self.assertEqual(
            "0% ⚠ Product/reactant mass conflict",
            frame._modified_pyparse_purity_display_for_row(row),
        )

    def test_modified_es_crop_keeps_positive_trace_x_axis_values(self):
        width, height = 2000, 2000
        box = _trace_crop_box("es_trace_panels", width, height)

        self.assertEqual((0, 528, 2000, 1080), box)
        # The old crop ended at 52.5% and retained only the ES+ axis line and
        # tick marks.  The numerical labels immediately below it must remain.
        self.assertGreater(box[3], int(height * 0.525))
        self.assertLess(box[3], int(height * 0.55))

    def test_product_trace_lookup_never_falls_back_to_heatmaps_or_impurities(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            graphs = output_dir / "graphs"
            graphs.mkdir()
            (graphs / "heatmap_conversion.jpg").touch()
            (graphs / "chroma-ImpuritySummary__A1-A1.jpg").touch()
            frame = object.__new__(CheminformaticsFrame)
            row = {
                "product_id": "Product1",
                "desired product name": "Product1",
                "pyparse_well": "A1",
            }
            self.assertIsNone(frame._find_product_trace_path(output_dir, row, "A1"))
            expected = graphs / "chroma-Product1-A1.jpg"
            expected.touch()
            self.assertEqual(expected, frame._find_product_trace_path(output_dir, row, "A1"))

    def test_wrong_well_mapping_produces_no_product_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            graphs = output_dir / "graphs"
            graphs.mkdir()
            (graphs / "chroma-Product1-C1.jpg").touch()
            (output_dir / "compoundtable.csv").write_text(
                "name,g_smiles,best_well,purity_by_well\n"
                "Product1,CCO,C1,{'C1': 50}\n",
                encoding="utf-8",
            )
            frame = object.__new__(CheminformaticsFrame)
            frame.pyparse_result_dir = None
            frame.modified_pyparse_result_dir = output_dir
            frame.portable_trace_paths = {}
            paths = frame._product_trace_paths(
                {"desired product smiles": "CCO", "pyparse_well": "A1"},
                include_portable=False,
            )
            self.assertIsNone(paths["modified_uv"])
            self.assertIsNone(paths["modified_es"])

    def test_impurity_result_folder_does_not_replace_product_result_folder(self):
        frame = object.__new__(CheminformaticsFrame)
        product_dir = Path("product-results")
        impurity_dir = Path("impurity-results")
        frame.modified_pyparse_result_dir = product_dir
        frame.modified_pyparse_impurity_result_dir = None
        frame.portable_trace_paths = {
            "C1": {
                "pyparse_uv": "original.jpg",
                "modified_uv": "product-uv.jpg",
                "modified_es": "product-es.jpg",
                "impurity_pyparse": "original-impurity-view.jpg",
                "impurity_modified": "old-impurity.jpg",
            }
        }
        frame._refresh_product_structure_purity_display = lambda *_args, **_kwargs: None
        frame._refresh_product_structure_trace_display = lambda *_args, **_kwargs: None
        frame.logw = lambda *_args, **_kwargs: None

        frame.set_pyparse_result_dir("modified_impurity", impurity_dir)

        self.assertEqual(product_dir, frame.modified_pyparse_result_dir)
        self.assertEqual(impurity_dir, frame.modified_pyparse_impurity_result_dir)
        self.assertEqual(
            {
                "C1": {
                    "pyparse_uv": "original.jpg",
                    "modified_uv": "product-uv.jpg",
                    "modified_es": "product-es.jpg",
                    "impurity_pyparse": "original-impurity-view.jpg",
                }
            },
            frame.portable_trace_paths,
        )

    def test_product_reruns_invalidate_only_their_own_portable_trace_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            frame = object.__new__(CheminformaticsFrame)
            frame.modified_pyparse_result_dir = None
            frame.modified_pyparse_impurity_result_dir = Path("impurity-results")
            frame.pyparse_result_dir = None
            frame.portable_trace_paths = {
                "A1": {
                    "pyparse_uv": "original-a1.jpg",
                    "modified_uv": "old-product-uv-a1.jpg",
                    "modified_es": "old-product-es-a1.jpg",
                    "impurity_pyparse": "original-impurity-a1.jpg",
                    "impurity_modified": "impurity-a1.jpg",
                },
                "A2": {
                    "modified_uv": "old-product-uv-a2.jpg",
                    "modified_es": "old-product-es-a2.jpg",
                },
            }
            frame._refresh_product_structure_purity_display = lambda *_args, **_kwargs: None
            frame._refresh_product_structure_trace_display = lambda *_args, **_kwargs: None
            frame.logw = lambda *_args, **_kwargs: None

            frame.set_pyparse_result_dir("modified", output_dir)

            self.assertEqual(
                {
                    "A1": {
                        "pyparse_uv": "original-a1.jpg",
                        "impurity_pyparse": "original-impurity-a1.jpg",
                        "impurity_modified": "impurity-a1.jpg",
                    }
                },
                frame.portable_trace_paths,
            )

    def test_imported_product_trace_files_remain_resolvable_after_impurity_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "A1_pyparse_uv.jpg"
            modified_uv = root / "A1_modified_uv.jpg"
            modified_es = root / "A1_modified_es.jpg"
            old_impurity = root / "A1_impurity_modified.jpg"
            for path in (original, modified_uv, modified_es, old_impurity):
                path.touch()
            impurity_output = root / "new-impurity-output"
            impurity_output.mkdir()

            frame = object.__new__(CheminformaticsFrame)
            frame.pyparse_result_dir = None
            frame.modified_pyparse_result_dir = None
            frame.modified_pyparse_impurity_result_dir = None
            frame.portable_trace_paths = {
                "A1": {
                    "pyparse_uv": str(original),
                    "modified_uv": str(modified_uv),
                    "modified_es": str(modified_es),
                    "impurity_modified": str(old_impurity),
                }
            }
            frame._refresh_product_structure_purity_display = lambda *_args, **_kwargs: None
            frame._refresh_product_structure_trace_display = lambda *_args, **_kwargs: None
            frame.logw = lambda *_args, **_kwargs: None

            frame.set_pyparse_result_dir("modified_impurity", impurity_output)
            paths = frame._product_trace_paths({"pyparse_well": "A1"})

            self.assertEqual(original, paths["pyparse_uv"])
            self.assertEqual(modified_uv, paths["modified_uv"])
            self.assertEqual(modified_es, paths["modified_es"])
            self.assertNotIn("impurity_modified", frame.portable_trace_paths["A1"])

    def test_original_pyparse_rerun_preserves_modified_product_and_impurity_traces(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            frame = object.__new__(CheminformaticsFrame)
            frame.modified_pyparse_result_dir = None
            frame.modified_pyparse_impurity_result_dir = None
            frame.pyparse_result_dir = None
            frame.portable_trace_paths = {
                "B1": {
                    "pyparse_uv": "old-original.jpg",
                    "impurity_pyparse": "old-original-impurity-view.jpg",
                    "modified_uv": "modified-product-uv.jpg",
                    "modified_es": "modified-product-es.jpg",
                    "impurity_modified": "modified-impurity.jpg",
                }
            }
            frame._refresh_product_structure_purity_display = lambda *_args, **_kwargs: None
            frame._refresh_product_structure_trace_display = lambda *_args, **_kwargs: None
            frame.logw = lambda *_args, **_kwargs: None

            frame.set_pyparse_result_dir("standard", output_dir)

            self.assertEqual(
                {
                    "B1": {
                        "modified_uv": "modified-product-uv.jpg",
                        "modified_es": "modified-product-es.jpg",
                        "impurity_modified": "modified-impurity.jpg",
                    }
                },
                frame.portable_trace_paths,
            )

    def test_original_pyparse_trace_is_displayed_as_the_complete_figure(self):
        frame = object.__new__(CheminformaticsFrame)
        frame.product_structure_trace_widgets = [_FakeLabel(), _FakeLabel(), _FakeLabel()]
        frame.product_structure_trace_title_widgets = [_FakeLabel(), _FakeLabel(), _FakeLabel()]
        frame._product_trace_paths = lambda _row: {
            "pyparse_uv": "original.jpg",
            "modified_uv": "modified-uv.jpg",
            "modified_es": "modified-es.jpg",
        }
        frame._product_structure_trace_width = lambda: 900
        calls = []
        frame._load_trace_photo = lambda path, crop, **kwargs: calls.append((path, crop, kwargs)) or path

        frame._refresh_product_structure_trace_display({"pyparse_well": "A1"})

        self.assertEqual("full", calls[0][1])
        self.assertEqual("original.jpg", calls[0][0])

    def test_each_tab_switch_follows_the_row_most_recently_selected(self):
        frame = object.__new__(CheminformaticsFrame)
        products = [
            {"reaction_well": "A1", "pyparse_well": "A1"},
            {"reaction_well": "A2", "pyparse_well": "A2"},
            {"reaction_well": "A3", "pyparse_well": "A3"},
        ]
        impurities = [
            {"reaction_well": "A1", "pyparse_well": "A1"},
            {"reaction_well": "A2", "pyparse_well": "A2"},
            {"reaction_well": "A3", "pyparse_well": "A3"},
        ]
        frame._pyparse_rows = lambda: products
        frame._impurity_reaction_rows = lambda: impurities
        frame.product_structure_table = _FakeTree(range(3), selected=(1,))
        frame.product_impurity_table = _FakeTree(range(3), selected=(2,))
        frame._on_product_structure_select = lambda: None
        frame._on_product_impurity_select = lambda: None

        frame.product_summary_tables = _FakeNotebook("Impurities")
        frame._on_product_summary_table_changed()
        self.assertEqual(("1",), frame.product_impurity_table.selection())

        frame.product_impurity_table.selection_set("2")
        frame.product_summary_tables.title = "Products"
        frame._on_product_summary_table_changed()
        self.assertEqual(("2",), frame.product_structure_table.selection())

        frame.product_structure_table.selection_set("0")
        frame.product_summary_tables.title = "Impurities"
        frame._on_product_summary_table_changed()
        self.assertEqual(("0",), frame.product_impurity_table.selection())


class PyParseRunIsolationTests(unittest.TestCase):
    def test_platemap_kind_uses_actual_impurity_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            product = Path(tmp) / "product.csv"
            impurity = Path(tmp) / "impurity.csv"
            product.write_text("well,desired product smiles\nC1,CCO\n", encoding="utf-8")
            impurity.write_text(
                "well,desired product smiles,byproduct1 smiles\nC1,CCO,CCBr\n",
                encoding="utf-8",
            )
            self.assertEqual("product", _pyparse_platemap_kind(product))
            self.assertEqual("impurity", _pyparse_platemap_kind(impurity))

    def test_existing_pyparse_outputs_require_a_separate_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            self.assertFalse(_output_dir_has_pyparse_results(output_dir))
            (output_dir / "graphs").mkdir()
            (output_dir / "graphs" / "chroma-Product1-C1.jpg").touch()
            self.assertTrue(_output_dir_has_pyparse_results(output_dir))

    def test_generated_platemap_invalidates_output_even_at_same_path(self):
        frame = object.__new__(PyParseRunnerFrame)
        frame.platemap_var = _FakeVar("generated.csv")
        frame.output_dir_var = _FakeVar("selected-output")
        frame._suspend_platemap_invalidation = False
        frame._output_platemap_signature = ("old",)

        frame.set_platemap(Path("generated.csv"))

        self.assertEqual("generated.csv", frame.platemap_var.get())
        self.assertEqual("", frame.output_dir_var.get())
        self.assertIsNone(frame._output_platemap_signature)

    def test_in_place_platemap_edit_invalidates_selected_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            platemap = Path(tmp) / "generated.csv"
            platemap.write_text("well,desired product smiles\nC1,CCO\n", encoding="utf-8")
            frame = object.__new__(PyParseRunnerFrame)
            frame.platemap_var = _FakeVar(str(platemap))
            frame.output_dir_var = _FakeVar("selected-output")
            frame._suspend_platemap_invalidation = False
            frame._output_platemap_signature = _pyparse_platemap_signature(str(platemap))

            # Keep the same file path and byte count; content hashing must still
            # detect that the generated analysis input changed.
            platemap.write_text("well,desired product smiles\nC2,CCO\n", encoding="utf-8")

            self.assertTrue(frame._clear_stale_output_for_in_place_platemap_edit())
            self.assertEqual("", frame.output_dir_var.get())
            self.assertIsNone(frame._output_platemap_signature)


if __name__ == "__main__":
    unittest.main()
