"""Regression checks for LCMS options, split products and analysis pages."""
import csv
import io
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd
from test_modified_pyparse_annotations import modified_pyparse as mp
from pyparse_runner_frame import PyParseRunnerFrame
from xinpilot_shared import _read_modified_pyparse_uv254_purity_by_product


class AnalysisNumericsTests(unittest.TestCase):
    def setUp(self):
        self.old_options = getattr(mp, "options", None)
        mp.options = SimpleNamespace(plate_row_no=1, plate_col_no=1, uv254_purity="True", uv254_exclude_rt="", calc_higherions="True", mass_abs_tol=.3)

    def tearDown(self):
        mp.options = self.old_options

    def hit(self, area, start, end):
        return {"well":1, "area":area, "areaAbs":area, "pStart":start, "pEnd":end, "time":(start+end)/2, "mass_conf":60, "mass+":47.05, "mass-":"-"}

    def test_split_product_totals_survive_export_and_xinpilot_import(self):
        hits = [self.hit(20, 1, 1.2), self.hit(30, 2, 2.2)]
        peaks = hits + [self.hit(50, 3, 3.2)]
        cp = pd.DataFrame([{"name":"Product1", "g_smiles":"CCO", "locations":[1], "hits":{"green":hits,"discarded":[]}}], index=["CCO"])
        output = mp.generateOutputTable(cp, "", [], ["Product1"], [], {1:100}, {1:peaks})
        self.assertEqual(50, output.loc[1,"Parea"])
        self.assertEqual(50, output.loc[1,"Purity254"])
        with tempfile.TemporaryDirectory() as tmp:
            mp.genAnalyticalTable(pd.DataFrame(), cp, tmp + "/", {1:"sample"}, ["Product1"], [], [], "")
            at = pd.read_csv(Path(tmp)/"aTable.csv")
            self.assertEqual(50, at.loc[at.data_type == "Percentage Area", "data_entry"].astype(float).iloc[0])
            pd.DataFrame([{"name":"Product1", "g_smiles":"CCO", "best_well":"A1", "best_purity254":50, "purity_by_well":str({"A1":50}), "qc_flag":"OK"}]).to_csv(Path(tmp)/"compoundtable.csv",index=False)
            values = _read_modified_pyparse_uv254_purity_by_product(Path(tmp))
            self.assertEqual(50, float(values["CCO"]["A1"].rstrip("%")))
        mp.options.uv254_exclude_rt = "3-3.2"
        output = mp.generateOutputTable(cp, "", [], ["Product1"], [], {1:100}, {1:peaks})
        self.assertEqual(100, output.loc[1,"Purity254"])
        self.assertEqual(100, mp.compute_uv254_purity(peaks, highlight_ranges=[(1,1.2),(2,2.2)], exclude_ranges=[(3,3.2)]))
        cp.at["CCO","hits"] = {"green":[],"discarded":hits}
        self.assertEqual(0, mp.generateOutputTable(cp, "", [], ["Product1"], [], {1:100}, {1:peaks}).loc[1,"Purity254"])

    def test_label_threshold_does_not_change_shading_or_purity(self):
        peak = self.hit(40,1,2)
        peak.update({"MS+":[(101.01,20)],"MS-":[]})
        self.assertEqual([], mp._observed_product_ions(peak,[100],.3))
        peak["MS+"] = [(101.01,20.1)]
        self.assertTrue(mp._observed_product_ions(peak,[100],.3))
        self.assertEqual(40, mp.compute_uv254_purity([peak,self.hit(60,3,4)], highlight_ranges=[(1,2)]))

    def test_uv254_channel_selection_ignores_other_wavelengths(self):
        channels = ["\nDescription\tDAD: 210\n", "\nDescription\tDAD: 254\n", "\nDescription\tDAD: TIC\n"]
        self.assertEqual([channels[1]], mp.getWatersData._uv254_chromatograms(channels))
        self.assertEqual([], mp.getWatersData._uv254_chromatograms([channels[0]]))


class AnalysisPageTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk()
        self.root.withdraw()
        self.frames=[]

    def tearDown(self):
        self.root.destroy()

    def page(self, kind):
        frame=PyParseRunnerFrame(self.root, "Modified PyParse - " + kind, Path(mp.__file__), True, analysis_kind=kind)
        self.frames.append(frame)
        return frame

    def test_hidden_settings_cannot_restore_elsd_or_non_strict_runs(self):
        frame=self.page("product")
        frame.import_state({"detector":"ELSD", "strict_product_assignment":False, "split_product_peaks":True, "uv254_exclude_rt":"0-0.8"})
        command=frame._build_cmd()
        self.assertEqual("UV", command[command.index("-d")+1])
        self.assertEqual("True", command[command.index("-spa")+1])
        self.assertEqual("True", command[command.index("-spp")+1])
        self.assertIn("-u254x",command)
        state=frame.export_state()
        self.assertEqual("UV",state["detector"])
        self.assertTrue(state["strict_product_assignment"])

    def test_impurity_page_has_only_file_inputs_and_explicit_defaults(self):
        frame=self.page("impurity")
        frame.import_state({"split_product_peaks":True, "uv254_exclude_rt":"0-1", "product_isotope_rt_block":"1-2"})
        command=frame._build_cmd()
        self.assertNotIn("-u254x",command)
        self.assertNotIn("-pir",command)
        self.assertEqual("False",command[command.index("-spp")+1])
        texts=[]
        pending=[frame]
        while pending:
            widget=pending.pop()
            pending.extend(widget.winfo_children())
            if "text" in widget.keys():texts.append(str(widget.cget("text")))
        self.assertNotIn("Run options",texts)
        self.assertIn("Output folder (choose a new folder for each analysis)",texts)

    def test_wrong_platemap_is_rejected_before_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"impurity.csv"
            path.write_text("well,desired product smiles,byproduct1 smiles\nA1,CCO,CC\n")
            frame=self.page("product")
            frame.input_data_var.set(str(path))
            frame.platemap_var.set(str(path))
            frame.output_dir_var.set(str(Path(tmp)/"results"))
            self.assertIn("impurity",frame._validate())

    def test_output_picker_remembers_each_pages_parent_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            product_parent=Path(tmp)/"products"
            impurity_parent=Path(tmp)/"impurities"
            product_parent.mkdir()
            impurity_parent.mkdir()
            product=self.page("product")
            impurity=self.page("impurity")
            product.output_dir_var.set(str(product_parent/"previous"))
            impurity.output_dir_var.set(str(impurity_parent/"previous"))
            # Changing the input clears the selected output, but not this
            # page's own browsing location.
            product.platemap_var.set(str(Path(tmp)/"new.csv"))
            with patch("pyparse_runner_frame.filedialog.askdirectory",return_value="") as picker:
                product._pick_output_dir()
                self.assertEqual(str(product_parent),picker.call_args.kwargs["initialdir"])
                impurity._pick_output_dir()
                self.assertEqual(str(impurity_parent),picker.call_args.kwargs["initialdir"])
            self.assertEqual("",product.output_dir_var.get())
            self.assertEqual(str(impurity_parent/"previous"),impurity.output_dir_var.get())

    def test_output_picker_rejects_existing_results_and_accepts_new_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            prior=Path(tmp)/"prior"
            prior.mkdir()
            (prior/"aTable.csv").write_text("existing results")
            frame=self.page("product")
            with patch("pyparse_runner_frame.filedialog.askdirectory",return_value=str(prior)), patch("pyparse_runner_frame.messagebox.showwarning") as warning:
                frame._pick_output_dir()
                warning.assert_called_once()
            self.assertEqual("",frame.output_dir_var.get())
            new=Path(tmp)/"new"
            with patch("pyparse_runner_frame.filedialog.askdirectory",return_value=str(new)):
                frame._pick_output_dir()
            self.assertEqual(str(new),frame.output_dir_var.get())


class AnalysisProjectStateTests(unittest.TestCase):
    def test_both_analysis_pages_round_trip_through_project_state(self):
        from integrated_full_software import IntegratedFullApp
        app=IntegratedFullApp()
        app.withdraw()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                product=Path(tmp)/"product.csv"
                impurity=Path(tmp)/"impurity.csv"
                product.write_text("well,desired product smiles\nA1,CCO\n")
                impurity.write_text("well,desired product smiles,byproduct1 smiles\nA1,CCO,CC\n")
                app._set_pyparse_input(product)
                app._set_modified_pyparse_input(impurity)
                app.modified_pyparse_tab.split_product_peaks_var.set(True)
                payload=app._project_payload()
                self.assertEqual(str(impurity),payload["modified_impurity_runner"]["platemap"])
                app.modified_pyparse_tab.import_state({})
                app.modified_impurity_tab.import_state({})
                app._apply_project_data(payload)
                self.assertEqual(str(product),app.modified_pyparse_tab.platemap_var.get())
                self.assertEqual(str(impurity),app.modified_impurity_tab.platemap_var.get())
                self.assertTrue(app.modified_pyparse_tab.split_product_peaks_var.get())
        finally:
            app.destroy()
