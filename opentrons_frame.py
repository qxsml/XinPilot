from __future__ import annotations

from copy import deepcopy
from xinpilot.application.opentrons_domain import (
    FLEX_SLOTS,
    OT2_SLOTS,
    LABWARE_MAP_PROFILES,
    PLATE_STYLES,
    MIX_TIMINGS,
    TIP_POLICIES,
    BLOWOUT_LOCATIONS,
    TIP_DEPTH_REFERENCES,
    TIP_COLUMN_OPTIONS,
    TIP_WELL_OPTIONS,
    PIPETTE_MAX_UL,
    PIPETTE_MIN_UL,
    PIPETTE_TIPRACK_CAPACITIES,
    _tiprack_capacity,
    all_channel_source_wells,
    _style_dims,
    _style_disabled_labels,
    _style_well_labels,
    _parse_wells,
    _py_string,
    _well_parts,
    _row_number,
    _is_single_96_column,
    _eight_channel_patterns,
    _is_eight_channel_pattern,
    _split_eight_channel_patterns,
    OpentronsTransferRow,
    module_key_from_move_target,
    normalize_tip_policy,
    delay_air_gap_feature_enabled,
    batch_chemical_map,
    batch_building_block_map,
)
from xinpilot.application.opentrons_validation import (
    validate_used_pipette_tipracks,
    required_positive_float,
    optional_positive_float,
    optional_nonnegative_float,
    optional_nonnegative_float_or_none,
    validated_blowout_settings,
    validated_mix_settings,
    validated_delay_air_gap_settings,
    select_pipette_for_row,
    minimum_pipette_volume,
    nozzle_layout_for_row,
    current_labware_slot,
    single_nozzle_start_for_row,
    validate_sequence_tip_transitions,
)
from xinpilot.application.opentrons_protocol import OpentronsCompileRequest, compile_protocol
import math
from typing import Set
from tkinter import simpledialog
from uuid import uuid4

from xinpilot_shared import *
import well_map


ROBOT_OPTIONS = ("Flex", "OT-2")
FLEX_SLOT_GRID = (
    ("A1", "A2", "A3"),
    ("B1", "B2", "B3"),
    ("C1", "C2", "C3"),
    ("D1", "D2", "D3"),
)
OT2_SLOT_GRID = (
    ("10", "11", None),
    ("7", "8", "9"),
    ("4", "5", "6"),
    ("1", "2", "3"),
)
LABWARE_ROLES = ("source", "destination", "both")
TRANSFER_STRATEGIES = ("Single transfer", "Multi-dispense")
PIPETTE_SELECTIONS = ("Auto", "left", "right")
BATCH_VOLUME_MODE_UMOL = "umol"
BATCH_VOLUME_MODE_UL = "ul"
BATCH_VOLUME_MODE_LABELS = {
    BATCH_VOLUME_MODE_UMOL: "Target umol (preferred)",
    BATCH_VOLUME_MODE_UL: "Direct uL",
}
EIGHT_CHANNEL_MODES = ("Auto from wells", "Force single tip", "Force all channels")

TEMPERATURE_MODULE_LOAD_NAME = "temperature module gen2"
HEATER_SHAKER_LOAD_NAME = "heaterShakerModuleV1"
TEMPERATURE_MODULE_ADAPTERS = (
    "",
    "opentrons_aluminum_flat_bottom_plate",
    "opentrons_96_well_aluminum_block",
    "opentrons_96_deep_well_temp_mod_adapter",
)
HEATER_SHAKER_ADAPTERS = (
    "",
    "opentrons_universal_flat_adapter",
    "opentrons_universal_flat_adapter_type_b",
    "opentrons_96_pcr_adapter",
    "opentrons_96_deep_well_adapter",
    "opentrons_96_flat_bottom_adapter",
)
FLEX_POWERED_MODULE_SLOTS = tuple(slot for slot in FLEX_SLOTS if slot.endswith(("1", "3")))
OT2_TEMPERATURE_MODULE_SLOTS = ("1", "3", "4", "6", "7", "9", "10")
OT2_HEATER_SHAKER_SLOTS = ("1", "3", "4", "6", "7", "10")

PIPETTE_OPTIONS = {
    "Flex": (
        "None",
        "flex_1channel_50",
        "flex_1channel_1000",
        "flex_8channel_50",
        "flex_8channel_1000",
        "flex_96channel_200",
        "flex_96channel_1000",
    ),
    "OT-2": (
        "None",
        "p20_single_gen2",
        "p300_single_gen2",
        "p1000_single_gen2",
        "p20_multi_gen2",
        "p300_multi_gen2",
    ),
}


TIPRACK_OPTIONS = {
    "Flex": (
        "opentrons_flex_96_filtertiprack_50ul",
        "opentrons_flex_96_tiprack_50ul",
        "opentrons_flex_96_filtertiprack_200ul",
        "opentrons_flex_96_tiprack_200ul",
        "opentrons_flex_96_filtertiprack_1000ul",
        "opentrons_flex_96_tiprack_1000ul",
    ),
    "OT-2": (
        "opentrons_96_filtertiprack_20ul",
        "opentrons_96_tiprack_20ul",
        "opentrons_96_filtertiprack_200ul",
        "opentrons_96_tiprack_300ul",
        "opentrons_96_filtertiprack_1000ul",
        "opentrons_96_tiprack_1000ul",
    ),
}


LABWARE_OPTIONS = (
    "agilent_1_reservoir_290ml",
    "appliedbiosystemsmicroamp_384_wellplate_40ul",
    "armadillo_96_wellplate_200ul_pcr_full_skirt",
    "axygen_1_reservoir_90ml",
    "axygen_96_wellplate_500ul",
    "biorad_384_wellplate_50ul",
    "biorad_96_wellplate_200ul_pcr",
    "black_96_well_microtiter_plate_lid",
    "corning_12_wellplate_6.9ml_flat",
    "corning_24_wellplate_3.4ml_flat",
    "corning_384_wellplate_112ul_flat",
    "corning_48_wellplate_1.6ml_flat",
    "corning_6_wellplate_16.8ml_flat",
    "corning_96_wellplate_330ul",
    "corning_96_wellplate_360ul_flat",
    "corning_96_wellplate_360ul_lid",
    "corning_falcon_384_wellplate_130ul_flat",
    "corning_falcon_384_wellplate_130ul_flat_lid",
    "costar_96_wellplate_2.2ml",
    "eppendorf_384_wellplate_45ul",
    "eppendorf_96_tiprack_1000ul_eptips",
    "eppendorf_96_tiprack_10ul_eptips",
    "eppendorf_96_wellplate_1000ul",
    "eppendorf_96_wellplate_150ul",
    "eppendorf_96_wellplate_2000ul",
    "eppendorf_96_wellplate_2000ul_lobind",
    "eppendorf_96_wellplate_350ul_lobind",
    "eppendorf_96_wellplate_500ul",
    "eppendorf_96_wellplate_500ul_lobind",
    "ev_resin_tips_flex_96_labware",
    "ev_resin_tips_flex_96_tiprack_adapter",
    "ev_resin_tips_flex_short_adapter",
    "ev_resin_tips_flex_tall_adapter",
    "geb_96_tiprack_1000ul",
    "geb_96_tiprack_10ul",
    "greiner_384_wellplate_240ul",
    "greiner_96_wellplate_323ul",
    "greiner_96_wellplate_340ul_chimney",
    "greiner_96_wellplate_382ul",
    "ibidi_96_square_well_plate_300ul",
    "ibidi_96_square_well_plate_300ul_lid",
    "milliplex_r_96_well_microtiter_plate",
    "millipore_24_wellplate_800ul",
    "millipore_384_wellplate_100ul_filter",
    "millipore_96_wellplate_300ul_filter",
    "millipore_96_wellplate_300ul_hts_filter",
    "millipore_96_wellplate_300ul_pcr_filter",
    "millipore_96_wellplate_400ul",
    "millipore_96_wellplate_500ul_solvinet_filter",
    "millipore_96_wellplate_500ul_ultracel_filter",
    "nest_12_reservoir_15ml",
    "nest_12_reservoir_22ml",
    "nest_1_reservoir_195ml",
    "nest_1_reservoir_290ml",
    "nest_24_wellplate_10.4ml",
    "nest_8_reservoir_22ml",
    "nest_96_wellplate_100ul_pcr_full_skirt",
    "nest_96_wellplate_200ul_flat",
    "nest_96_wellplate_2ml_deep",
    "nunc_384_wellplate_100ul",
    "nunc_96_wellplate_450ul",
    "opentrons_10_tuberack_falcon_4x50ml_6x15ml_conical",
    "opentrons_10_tuberack_falcon_4x50ml_6x15ml_conical_acrylic",
    "opentrons_10_tuberack_nest_4x50ml_6x15ml_conical",
    "opentrons_12_well_aluminumblock_tough_22ml",
    "opentrons_15_tuberack_eppendorf_15ml_conical",
    "opentrons_15_tuberack_falcon_15ml_conical",
    "opentrons_15_tuberack_nest_15ml_conical",
    "opentrons_1_trash_1100ml_fixed",
    "opentrons_1_trash_3200ml_fixed",
    "opentrons_1_trash_850ml_fixed",
    "opentrons_1_well_aluminumblock_tough_300ml",
    "opentrons_24_aluminumblock_generic_2ml_screwcap",
    "opentrons_24_aluminumblock_nest_0.5ml_screwcap",
    "opentrons_24_aluminumblock_nest_1.5ml_screwcap",
    "opentrons_24_aluminumblock_nest_1.5ml_snapcap",
    "opentrons_24_aluminumblock_nest_2ml_screwcap",
    "opentrons_24_aluminumblock_nest_2ml_snapcap",
    "opentrons_96_wellplate_200ul_pcr_full_skirt",
    "opentrons_24_tuberack_eppendorf_1.5ml_safelock_snapcap",
    "opentrons_24_tuberack_eppendorf_2ml_safelock_snapcap",
    "opentrons_24_tuberack_eppendorf_2ml_safelock_snapcap_acrylic",
    "opentrons_24_tuberack_generic_0.75ml_snapcap_acrylic",
    "opentrons_24_tuberack_generic_2ml_screwcap",
    "opentrons_24_tuberack_nest_0.5ml_screwcap",
    "opentrons_24_tuberack_nest_1.5ml_screwcap",
    "opentrons_24_tuberack_nest_1.5ml_snapcap",
    "opentrons_24_tuberack_nest_2ml_screwcap",
    "opentrons_24_tuberack_nest_2ml_snapcap",
    "opentrons_40_aluminumblock_eppendorf_24x2ml_safelock_snapcap_generic_16x0.2ml_pcr_strip",
    "opentrons_4_well_aluminumblock_tough_72ml",
    "opentrons_6_tuberack_falcon_50ml_conical",
    "opentrons_6_tuberack_nest_50ml_conical",
    "opentrons_96_aluminumblock_biorad_wellplate_200ul",
    "opentrons_96_aluminumblock_generic_pcr_strip_200ul",
    "opentrons_96_aluminumblock_nest_wellplate_100ul",
    "opentrons_96_deep_well_adapter",
    "opentrons_96_deep_well_adapter_nest_wellplate_2ml_deep",
    "opentrons_96_deep_well_temp_mod_adapter",
    "opentrons_96_filtertiprack_1000ul",
    "opentrons_96_filtertiprack_10ul",
    "opentrons_96_filtertiprack_200ul",
    "opentrons_96_filtertiprack_20ul",
    "opentrons_96_flat_bottom_adapter",
    "opentrons_96_flat_bottom_adapter_nest_wellplate_200ul_flat",
    "opentrons_96_pcr_adapter",
    "opentrons_96_pcr_adapter_armadillo_wellplate_200ul",
    "opentrons_96_pcr_adapter_nest_wellplate_100ul_pcr_full_skirt",
    "opentrons_96_tiprack_1000ul",
    "opentrons_96_tiprack_10ul",
    "opentrons_96_tiprack_20ul",
    "opentrons_96_tiprack_300ul",
    "opentrons_96_well_aluminum_block",
    "opentrons_aluminum_flat_bottom_plate",
    "opentrons_calibration_adapter_heatershaker_module",
    "opentrons_calibration_adapter_temperature_module",
    "opentrons_calibration_adapter_thermocycler_module",
    "opentrons_calibrationblock_short_side_left",
    "opentrons_calibrationblock_short_side_right",
    "opentrons_flex_96_wellplate_200ul",
    "opentrons_flex_96_wellplate_1000ul",
    "opentrons_flex_96_wellplate_2ml_deep",
    "opentrons_flex_96_filtertiprack_1000ul",
    "opentrons_flex_96_filtertiprack_200ul",
    "opentrons_flex_96_filtertiprack_20ul",
    "opentrons_flex_96_filtertiprack_50ul",
    "opentrons_flex_96_tiprack_1000ul",
    "opentrons_flex_96_tiprack_200ul",
    "opentrons_flex_96_tiprack_20ul",
    "opentrons_flex_96_tiprack_50ul",
    "opentrons_flex_96_tiprack_adapter",
    "opentrons_flex_deck_riser",
    "opentrons_flex_lid_absorbance_plate_reader_module",
    "opentrons_flex_tiprack_lid",
    "opentrons_tough_12_reservoir_22ml",
    "opentrons_tough_1_reservoir_300ml",
    "opentrons_tough_4_reservoir_72ml",
    "opentrons_tough_pcr_auto_sealing_lid",
    "opentrons_tough_universal_lid",
    "opentrons_universal_flat_adapter",
    "opentrons_universal_flat_adapter_corning_384_wellplate_112ul_flat",
    "opentrons_universal_flat_adapter_type_b",
    "opentrons_vacuum_manifold_collar_short",
    "opentrons_vacuum_manifold_collar_tall",
    "opentrons_vacuum_manifold_spacer_short",
    "opentrons_vacuum_manifold_spacer_tall",
    "protocol_engine_lid_stack_object",
    "smc_384_read_plate",
    "thermofisher_nunc_maxisorp_lockwell_elisa",
    "thermoscientific_96_wellplate_800ul",
    "thermoscientific_abgene_96_wellplate_1.2ml",
    "thermoscientificnunc_96_wellplate_1000ul_filter",
    "thermoscientificnunc_96_wellplate_1300ul",
    "thermoscientificnunc_96_wellplate_2000ul",
    "tipone_96_tiprack_200ul",
    "usascientific_12_reservoir_22ml",
    "usascientific_96_wellplate_2.4ml_deep",
)


# These official definitions are deck accessories rather than pipettable labware.
# Their JSON definitions contain no wells, so assigning a plate map would be
# misleading and would let users generate invalid well references.
OFFICIAL_LABWARE_WITHOUT_WELLS = frozenset(
    {
        "black_96_well_microtiter_plate_lid",
        "corning_96_wellplate_360ul_lid",
        "corning_falcon_384_wellplate_130ul_flat_lid",
        "ev_resin_tips_flex_96_tiprack_adapter",
        "ev_resin_tips_flex_short_adapter",
        "ev_resin_tips_flex_tall_adapter",
        "ibidi_96_square_well_plate_300ul_lid",
        "opentrons_12_well_aluminumblock_tough_22ml",
        "opentrons_1_well_aluminumblock_tough_300ml",
        "opentrons_4_well_aluminumblock_tough_72ml",
        "opentrons_96_deep_well_adapter",
        "opentrons_96_deep_well_temp_mod_adapter",
        "opentrons_96_flat_bottom_adapter",
        "opentrons_aluminum_flat_bottom_plate",
        "opentrons_flex_96_tiprack_adapter",
        "opentrons_flex_deck_riser",
        "opentrons_flex_lid_absorbance_plate_reader_module",
        "opentrons_flex_tiprack_lid",
        "opentrons_tough_pcr_auto_sealing_lid",
        "opentrons_tough_universal_lid",
        "opentrons_universal_flat_adapter",
        "opentrons_universal_flat_adapter_type_b",
        "opentrons_vacuum_manifold_spacer_short",
        "opentrons_vacuum_manifold_spacer_tall",
        "protocol_engine_lid_stack_object",
    }
)

OFFICIAL_LABWARE_MAP_OVERRIDES = {
    "nest_8_reservoir_22ml": "8 well reservoir",
    "opentrons_40_aluminumblock_eppendorf_24x2ml_safelock_snapcap_generic_16x0.2ml_pcr_strip": "40 position mixed rack",
    "opentrons_calibration_adapter_heatershaker_module": "2 position (2 x 1)",
    "opentrons_calibration_adapter_temperature_module": "2 position (2 x 1)",
    "opentrons_calibration_adapter_thermocycler_module": "2 position (2 x 1)",
    "opentrons_calibrationblock_short_side_left": "2 position (1 x 2)",
    "opentrons_calibrationblock_short_side_right": "2 position (1 x 2)",
    "opentrons_vacuum_manifold_collar_short": "1 well",
    "opentrons_vacuum_manifold_collar_tall": "1 well",
    "thermofisher_nunc_maxisorp_lockwell_elisa": "96 well",
}


def _default_labware_map_style(load_name: object) -> Optional[str]:
    """Return the map geometry for a bundled official labware load name.

    ``None`` means that the name is custom/unknown and its user-selected style
    should be preserved. An empty string means that an official definition has
    no wells and therefore cannot be used as transfer labware.
    """
    text = str(load_name or "").strip().lower()
    if text not in LABWARE_OPTIONS:
        return None
    if text in OFFICIAL_LABWARE_WITHOUT_WELLS:
        return ""
    if text in OFFICIAL_LABWARE_MAP_OVERRIDES:
        return OFFICIAL_LABWARE_MAP_OVERRIDES[text]

    count_match = re.search(r"(?:^|_)(1|2|4|6|8|10|12|15|24|40|48|96|384)(?:_|$)", text)
    if not count_match:
        return None
    well_count = int(count_match.group(1))
    if well_count == 12:
        return "12 well reservoir" if "reservoir" in text else "12 well plate"
    styles_by_count = {
        1: "1 well",
        4: "4 well reservoir",
        6: "6 well",
        10: "10 tube rack",
        15: "15 tube rack",
        24: "24 well",
        40: "40 position mixed rack",
        48: "48 well",
        96: "96 well",
        384: "384 well",
    }
    if well_count in styles_by_count:
        return styles_by_count[well_count]
    return None

DEFAULT_PIPETTE_BY_ROBOT = {
    "Flex": {"left": "flex_1channel_50", "right": "flex_1channel_1000"},
    "OT-2": {"left": "p20_single_gen2", "right": "p1000_single_gen2"},
}

DEFAULT_TIPRACK_BY_PIPETTE = {
    "flex_1channel_50": "opentrons_flex_96_filtertiprack_50ul",
    "flex_1channel_1000": "opentrons_flex_96_filtertiprack_1000ul",
    "flex_8channel_50": "opentrons_flex_96_filtertiprack_50ul",
    "flex_8channel_1000": "opentrons_flex_96_filtertiprack_1000ul",
    "flex_96channel_200": "opentrons_flex_96_filtertiprack_200ul",
    "flex_96channel_1000": "opentrons_flex_96_filtertiprack_1000ul",
    "p20_single_gen2": "opentrons_96_filtertiprack_20ul",
    "p300_single_gen2": "opentrons_96_filtertiprack_200ul",
    "p1000_single_gen2": "opentrons_96_filtertiprack_1000ul",
    "p20_multi_gen2": "opentrons_96_filtertiprack_20ul",
    "p300_multi_gen2": "opentrons_96_filtertiprack_200ul",
}


class OpentronsFrame(ttk.Frame):
    def __init__(self, master, *, compound_provider=None, push_callback=None):
        super().__init__(master, style="Chem.TFrame")
        self.compound_provider = compound_provider
        self.push_callback = push_callback
        self.rows: List[Dict[str, object]] = []
        self._copied_transfer_rows: List[Dict[str, object]] = []
        self._context_transfer_row_index: Optional[int] = None
        self._editing_transfer_row_index: Optional[int] = None
        self._loading_transfer_row = False
        self._saving_transfer_row = False
        self._changing_transfer_type = False
        self._batch_editor_open = False
        self.protocol_name_var = tk.StringVar(value="")
        self.notes_var = tk.StringVar(value="")
        self.robot_var = tk.StringVar(value="Flex")
        self.api_level_var = tk.StringVar(value="2.21")
        self.left_pipette_var = tk.StringVar(value="flex_1channel_50")
        self.left_tiprack_var = tk.StringVar(value="opentrons_flex_96_filtertiprack_50ul")
        self.left_tiprack_slots_var = tk.StringVar(value="D1")
        self.left_tip_start_column_var = tk.StringVar(value="1")
        self.left_tip_start_well_var = tk.StringVar(value="A1")
        self.right_pipette_var = tk.StringVar(value="flex_1channel_1000")
        self.right_tiprack_var = tk.StringVar(value="opentrons_flex_96_filtertiprack_1000ul")
        self.right_tiprack_slots_var = tk.StringVar(value="D2")
        self.right_tip_start_column_var = tk.StringVar(value="1")
        self.right_tip_start_well_var = tk.StringVar(value="A1")
        self.trash_slot_var = tk.StringVar(value="A3")
        self.flex_gripper_var = tk.BooleanVar(value=False)
        self.temperature_module_enabled_var = tk.BooleanVar(value=False)
        self.temperature_module_slot_var = tk.StringVar(value="C3")
        self.temperature_module_labware_alias_var = tk.StringVar(value="")
        self.temperature_module_adapter_var = tk.StringVar(value="")
        self.temperature_module_target_var = tk.StringVar(value="4")
        self.temperature_module_wait_var = tk.BooleanVar(value=True)
        self.temperature_module_deactivate_var = tk.BooleanVar(value=True)
        self.heater_shaker_enabled_var = tk.BooleanVar(value=False)
        self.heater_shaker_slot_var = tk.StringVar(value="B3")
        self.heater_shaker_labware_alias_var = tk.StringVar(value="")
        self.heater_shaker_adapter_var = tk.StringVar(value="")
        self.heater_shaker_temperature_var = tk.StringVar(value="37")
        self.heater_shaker_speed_var = tk.StringVar(value="500")
        self.heater_shaker_duration_var = tk.StringVar(value="1")
        self.heater_shaker_wait_var = tk.BooleanVar(value=True)
        self.heater_shaker_deactivate_var = tk.BooleanVar(value=True)
        self.source_labware_var = tk.StringVar(value="nest_96_wellplate_2ml_deep")
        self.source_slot_var = tk.StringVar(value="C1")
        self.source_style_var = tk.StringVar(value="96 well")
        self.dest_labware_var = tk.StringVar(value="corning_96_wellplate_360ul_flat")
        self.dest_slot_var = tk.StringVar(value="C2")
        self.dest_style_var = tk.StringVar(value="96 well")
        self.source_labware_alias_var = tk.StringVar(value="source1")
        self.dest_labware_alias_var = tk.StringVar(value="dest1")
        self.labware_alias_var = tk.StringVar(value="")
        self.labware_role_var = tk.StringVar(value="source")
        self.labware_load_name_var = tk.StringVar(value="")
        self.labware_slot_var = tk.StringVar(value="C1")
        self.labware_map_style_var = tk.StringVar(value="96 well")
        self.labware_configs: List[Dict[str, str]] = [
            {
                "alias": "source1",
                "role": "source",
                "load_name": self.source_labware_var.get(),
                "slot": self.source_slot_var.get(),
                "map_style": self.source_style_var.get(),
            },
            {
                "alias": "dest1",
                "role": "destination",
                "load_name": self.dest_labware_var.get(),
                "slot": self.dest_slot_var.get(),
                "map_style": self.dest_style_var.get(),
            },
        ]
        self.step_name_var = tk.StringVar(value="")
        self.chemical_var = tk.StringVar(value="")
        self.reaction_umol_var = tk.StringVar(value="")
        self.is_building_block_var = tk.BooleanVar(value=False)
        self.source_well_var = tk.StringVar(value="A1")
        self.dest_wells_var = tk.StringVar(value="")
        self.volume_var = tk.StringVar(value="")
        self.strategy_var = tk.StringVar(value="Multi-dispense")
        self.row_pipette_var = tk.StringVar(value="Auto")
        self.tip_policy_var = tk.StringVar(value="Bin tip after row")
        self.blowout_location_var = tk.StringVar(value="No blowout")
        self.blowout_labware_alias_var = tk.StringVar(value="")
        self.blowout_well_var = tk.StringVar(value="")
        self.eight_channel_mode_var = tk.StringVar(value="Auto from wells")
        self.aspirate_rate_var = tk.StringVar(value="")
        self.dispense_rate_var = tk.StringVar(value="")
        self.aspirate_depth_mm_var = tk.StringVar(value="")
        self.aspirate_depth_reference_var = tk.StringVar(value="from bottom")
        self.dispense_depth_mm_var = tk.StringVar(value="")
        self.dispense_depth_reference_var = tk.StringVar(value="from top")
        self.multi_dispense_extra_percent_var = tk.StringVar(value="0")
        self.tip_touch_var = tk.BooleanVar(value=False)
        self.pre_wet_tip_var = tk.BooleanVar(value=False)
        self.mix_enabled_var = tk.BooleanVar(value=False)
        self.mix_timing_var = tk.StringVar(value="Before aspirating")
        self.mix_repetitions_var = tk.StringVar(value="3")
        self.mix_volume_var = tk.StringVar(value="")
        self.post_source_mix_delay_seconds_var = tk.StringVar(value="")
        self.mix_aspirate_rate_var = tk.StringVar(value="")
        self.mix_dispense_rate_var = tk.StringVar(value="")
        self.mix_aspirate_depth_mm_var = tk.StringVar(value="")
        self.mix_aspirate_depth_reference_var = tk.StringVar(value="from bottom")
        self.mix_dispense_depth_mm_var = tk.StringVar(value="")
        self.mix_dispense_depth_reference_var = tk.StringVar(value="from bottom")
        self.delay_air_gap_enabled_var = tk.BooleanVar(value=False)
        self.post_aspirate_delay_seconds_var = tk.StringVar(value="")
        self.post_dispense_delay_seconds_var = tk.StringVar(value="")
        self.pre_move_delay_seconds_var = tk.StringVar(value="")
        self.air_gap_enabled_var = tk.BooleanVar(value=False)
        self.air_gap_volume_var = tk.StringVar(value="")
        self.air_gap_height_var = tk.StringVar(value="5")
        self.air_gap_flow_rate_var = tk.StringVar(value="")
        self.delay_air_gap_summary_var = tk.StringVar(value="No delay or air gap")
        self.move_plate_var = tk.BooleanVar(value=False)
        self.move_labware_alias_var = tk.StringVar(value="dest1")
        self.move_to_slot_var = tk.StringVar(value="")
        self.move_use_gripper_var = tk.BooleanVar(value=False)
        self._copied_liquid_params: Optional[Dict[str, object]] = None
        self.deck_setup_hidden = False
        self.show_structure_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Ready")
        self.transfer_mode_status_var = tk.StringVar(
            value="Create or select a transfer row to enable editing."
        )
        self.pipette_summary_var = tk.StringVar(value="")
        self.labware_summary_var = tk.StringVar(value="")
        self.module_summary_var = tk.StringVar(value="No module configured")
        self.motion_summary_var = tk.StringVar(value="")
        self.structure_window: tk.Toplevel | None = None
        self.structure_image_label: ttk.Label | None = None
        self.structure_title_label: ttk.Label | None = None
        self.structure_photo = None
        self._build_ui()
        self._wire_transfer_row_autosave()
        self._wire_summary_updates()
        self._update_summaries()

    def _build_ui(self):
        plan_tab = ttk.Frame(self, style="Chem.TFrame")
        plan_tab.pack(fill="both", expand=True, padx=8, pady=8)

        self.plan_panes = ttk.Panedwindow(plan_tab, orient="vertical")
        self.plan_panes.pack(fill="both", expand=True)
        self.deck_pane = ttk.Frame(self.plan_panes, style="Chem.TFrame", padding=(0, 0, 0, 4))
        lower_pane = ttk.Frame(self.plan_panes, style="Chem.TFrame")
        self.plan_panes.add(self.deck_pane, weight=0)
        self.plan_panes.add(lower_pane, weight=1)

        self.lower_plan_panes = ttk.Panedwindow(lower_pane, orient="horizontal")
        self.lower_plan_panes.pack(fill="both", expand=True)
        row_pane = ttk.Frame(self.lower_plan_panes, style="Chem.TFrame", padding=(0, 0, 4, 0))
        table_pane = ttk.Frame(self.lower_plan_panes, style="Chem.TFrame")
        self.lower_plan_panes.add(row_pane, weight=5)
        self.lower_plan_panes.add(table_pane, weight=7)

        self._lower_sash_initialized = False

        def initialize_lower_sash(_event=None):
            if self._lower_sash_initialized:
                return
            try:
                width = self.lower_plan_panes.winfo_width()
                if width <= 10:
                    return
                target = int(width * 0.46)
                if width >= 900:
                    target = max(430, min(target, width - 430))
                self.lower_plan_panes.sashpos(0, target)
                self._lower_sash_initialized = True
            except tk.TclError:
                return

        self.lower_plan_panes.bind("<Configure>", initialize_lower_sash, add="+")
        self.after_idle(initialize_lower_sash)

        row_pane.rowconfigure(0, weight=1)
        row_pane.columnconfigure(0, weight=1)
        canvas_background = ttk.Style(self).lookup("Chem.TFrame", "background") or "#f4f6f8"
        self.transfer_row_canvas = tk.Canvas(
            row_pane,
            highlightthickness=0,
            borderwidth=0,
            background=canvas_background,
        )
        self.transfer_row_canvas.grid(row=0, column=0, sticky="nsew")
        self.transfer_row_scrollbar = ttk.Scrollbar(
            row_pane,
            orient="vertical",
            command=self.transfer_row_canvas.yview,
        )
        self.transfer_row_scrollbar.grid(row=0, column=1, sticky="ns")
        self.transfer_row_canvas.configure(yscrollcommand=self.transfer_row_scrollbar.set)
        self.transfer_row_content = ttk.Frame(self.transfer_row_canvas, style="Chem.TFrame")
        transfer_row_window = self.transfer_row_canvas.create_window(
            (0, 0),
            window=self.transfer_row_content,
            anchor="nw",
        )

        def refresh_transfer_scroll_region(_event=None):
            self.transfer_row_canvas.configure(scrollregion=self.transfer_row_canvas.bbox("all"))

        def fit_transfer_content_width(event):
            self.transfer_row_canvas.itemconfigure(transfer_row_window, width=event.width)

        self.transfer_row_content.bind("<Configure>", refresh_transfer_scroll_region)
        self.transfer_row_canvas.bind("<Configure>", fit_transfer_content_width)

        config = ttk.LabelFrame(self.deck_pane, text="Opentrons setup", padding=(8, 6), style="FileRegion.TLabelframe")
        config.pack(fill="both", expand=True)
        config.columnconfigure(0, weight=0)
        config.columnconfigure(1, weight=0, minsize=18)
        for col in (2, 3, 4, 5, 6):
            config.columnconfigure(col, weight=1, minsize=165)
        template_actions = ttk.Frame(config)
        template_actions.grid(row=0, column=0, sticky="nw")
        ttk.Button(template_actions, text="Hide", width=15, command=self._hide_deck_setup).pack(anchor="w", pady=(0, 3))
        ttk.Button(template_actions, text="Import Template...", width=15, command=self._import_deck_template).pack(anchor="w", pady=(0, 3))
        ttk.Button(template_actions, text="Save Template...", width=15, command=self._save_deck_template).pack(anchor="w")
        protocol_card = ttk.LabelFrame(config, text="Protocol", padding=(8, 5), style="FileRegion.TLabelframe")
        protocol_card.grid(row=0, column=2, sticky="nsew")
        self._field(protocol_card, 0, 0, "Name", self.protocol_name_var, width=14, stretch=False)
        self._field(protocol_card, 1, 0, "Robot", self.robot_var, width=8, combo=ROBOT_OPTIONS, callback=self._on_robot_changed, stretch=False)
        self._summary_card(config, 3, "Pipettes", self.pipette_summary_var, self._open_pipette_dialog, row=0)
        self._summary_card(config, 4, "Labware", self.labware_summary_var, self._open_labware_dialog, row=0)
        self.tip_location_summary_var = tk.StringVar(value="")
        self._summary_card(config, 5, "Tip Location", self.tip_location_summary_var, self._open_tip_location_dialog, row=0)
        self._summary_card(config, 6, "Temperature & Shaking", self.module_summary_var, self._open_module_dialog, row=0)
        style_region_widgets(config, "FileRegion")

        self.deck_show_bar = ttk.Frame(self.transfer_row_content, style="ChemRegion.TFrame")
        ttk.Button(self.deck_show_bar, text="Show Opentrons Setup", command=self._show_deck_setup, style="FileAction.TButton").pack(side="left")

        add = ttk.LabelFrame(self.transfer_row_content, text="Transfer row", padding=10, style="ChemRegion.TLabelframe")
        self.transfer_row_panel = add
        add.pack(fill="x", expand=False)
        add.columnconfigure(0, weight=1)

        row_buttons = ttk.Frame(add)
        self.row_action_toolbar = row_buttons
        row_buttons.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        self.create_single_button = ttk.Button(
            row_buttons,
            text="Create Single",
            command=self._create_single_row,
            style="ChemAction.TButton",
        )
        self.create_single_button.pack(side="left")
        self.create_batch_button = ttk.Button(
            row_buttons,
            text="Create Batch",
            command=self._create_batch_row,
            style="ChemAction.TButton",
        )
        self.create_batch_button.pack(side="left", padx=(6, 0))
        self.create_sequence_button = ttk.Button(
            row_buttons,
            text="Create Sequence",
            command=self._create_sequence_from_selected,
            style="ChemAction.TButton",
        )
        self.create_sequence_button.pack(side="left", padx=(6, 0))

        transfer_fields = ttk.Frame(add)
        self.transfer_fields_panel = transfer_fields
        transfer_fields.grid(row=1, column=0, sticky="ew")
        transfer_fields.columnconfigure(1, weight=1)
        transfer_fields.columnconfigure(3, weight=1)
        transfer_header = ttk.Frame(transfer_fields)
        transfer_header.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 4))
        transfer_header.columnconfigure(1, weight=1)
        self.transfer_type_notebook = ttk.Notebook(transfer_header, height=1)
        self.single_transfer_type_tab = ttk.Frame(self.transfer_type_notebook)
        self.batch_transfer_type_tab = ttk.Frame(self.transfer_type_notebook)
        self.transfer_type_notebook.add(self.single_transfer_type_tab, text="Single Transfer")
        self.transfer_type_notebook.add(self.batch_transfer_type_tab, text="Batch Transfer")
        self.transfer_type_notebook.select(self.single_transfer_type_tab)
        self.transfer_type_notebook.grid(row=0, column=0, sticky="nw")
        self.transfer_type_notebook.bind("<<NotebookTabChanged>>", self._on_transfer_type_changed)
        self.transfer_type_notebook.bind("<Button-1>", lambda _event: "break")
        self.transfer_mode_status_label = ttk.Label(
            transfer_header,
            textvariable=self.transfer_mode_status_var,
            style="ChemRegion.LiveEdit.TLabel",
            wraplength=300,
            width=1,
        )
        self.transfer_mode_status_label.grid(row=0, column=1, sticky="ew", padx=(12, 0))
        self.transfer_mode_status_label.bind(
            "<Configure>",
            lambda event: self.transfer_mode_status_label.configure(wraplength=max(80, event.width)),
        )
        self.chemical_field_label = ttk.Label(transfer_fields, text="Chemical ID")
        self.chemical_field_label.grid(row=1, column=0, sticky="w", padx=(0, 6), pady=3)
        self.chemical_combo = ttk.Combobox(
            transfer_fields,
            textvariable=self.chemical_var,
            values=self._compound_choices(),
            width=14,
            state="normal",
            postcommand=self._refresh_compound_choices,
        )
        self.chemical_combo.bind("<<ComboboxSelected>>", lambda _event: self._normalize_selected_compound())
        self.chemical_combo.grid(row=1, column=1, sticky="w", pady=3)
        self.batch_chemical_summary_var = tk.StringVar(value="Chemical IDs: mapping required")
        self.batch_chemical_summary_button = ttk.Button(
            transfer_fields,
            textvariable=self.batch_chemical_summary_var,
            command=self._open_batch_mapping,
            style="RowAction.TButton",
        )
        self.batch_chemical_summary_button.grid(row=1, column=1, columnspan=3, sticky="ew", pady=3)
        self.batch_chemical_summary_button.grid_remove()
        self.show_structure_check = ttk.Checkbutton(transfer_fields, text="Show structure", variable=self.show_structure_var, style="ChemRegion.Compact.TCheckbutton")
        self.show_structure_check.grid(row=1, column=2, sticky="w", padx=(6, 0), pady=3)
        self.building_block_check = ttk.Checkbutton(transfer_fields, text="Building block", variable=self.is_building_block_var, style="ChemRegion.Compact.TCheckbutton")
        self.building_block_check.grid(row=1, column=3, sticky="w", padx=(4, 0), pady=3)
        self._field(transfer_fields, 2, 0, "Step name", self.step_name_var, width=14)
        self._field(transfer_fields, 2, 2, "Pipette", self.row_pipette_var, width=10, combo=PIPETTE_SELECTIONS)
        self.source_labware_combo = self._field(
            transfer_fields, 3, 0, "Source labware", self.source_labware_alias_var,
            width=14, combo=self._source_labware_aliases(),
        )
        self.source_well_entry = self._field(transfer_fields, 4, 0, "Source well", self.source_well_var, width=16)
        self.source_map_button = ttk.Button(transfer_fields, text="Map", command=self._pick_source_well)
        self.source_map_button.grid(row=4, column=2, sticky="w", padx=(12, 0), pady=3)
        self.dest_labware_combo = self._field(
            transfer_fields, 5, 0, "Destination labware", self.dest_labware_alias_var,
            width=14, combo=self._dest_labware_aliases(),
        )
        self.dest_wells_entry = self._field(transfer_fields, 6, 0, "Destination wells", self.dest_wells_var, width=16)
        self.dest_map_button = ttk.Button(transfer_fields, text="Map", command=self._pick_dest_wells)
        self.dest_map_button.grid(row=6, column=2, sticky="w", padx=(12, 0), pady=3)
        self._field(
            transfer_fields,
            7,
            0,
            "Strategy",
            self.strategy_var,
            width=18,
            combo=TRANSFER_STRATEGIES,
            callback=self._on_strategy_changed,
        )
        self.reaction_umol_label = ttk.Label(transfer_fields, text="umol per rxn")
        self.reaction_umol_label.grid(row=8, column=0, sticky="w", pady=3)
        amount_fields = ttk.Frame(transfer_fields)
        amount_fields.grid(row=8, column=1, columnspan=3, sticky="w", pady=3)
        self.reaction_umol_entry = ttk.Entry(amount_fields, textvariable=self.reaction_umol_var, width=7)
        self.reaction_umol_entry.pack(side="left")
        self.volume_label = ttk.Label(amount_fields, text="Dispense volume/uL")
        self.volume_label.pack(side="left", padx=(6, 6))
        self.volume_entry = ttk.Entry(amount_fields, textvariable=self.volume_var, width=8)
        self.volume_entry.pack(side="left")

        move_box = ttk.Frame(add)
        self.move_plate_panel = move_box
        move_box.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        ttk.Checkbutton(move_box, text="Move plate after row", variable=self.move_plate_var).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(move_box, text="Use Flex gripper", variable=self.move_use_gripper_var).grid(row=0, column=2, columnspan=2, sticky="w", padx=(12, 0))
        self._field(move_box, 1, 0, "Move labware", self.move_labware_alias_var, width=12, combo=self._all_labware_aliases())
        ttk.Label(move_box, text="To location").grid(row=1, column=2, sticky="w", padx=(12, 6), pady=3)
        self.move_to_slot_entry = ttk.Entry(move_box, textvariable=self.move_to_slot_var, width=24, state="readonly")
        self.move_to_slot_entry.grid(row=1, column=3, sticky="w", pady=3)
        ttk.Button(move_box, text="Map", command=self._pick_move_target).grid(row=1, column=4, sticky="w", padx=(6, 0), pady=3)
        liquid_fields = ttk.LabelFrame(
            add,
            text="Liquid handling for this row",
            padding=(8, 5),
            style="ChemRegion.TLabelframe",
        )
        self.liquid_handling_panel = liquid_fields
        liquid_fields.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        for col in (1, 3):
            liquid_fields.columnconfigure(col, weight=1)
        liquid_header = ttk.Frame(liquid_fields)
        liquid_header.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 4))
        ttk.Button(
            liquid_header,
            text="Copy",
            width=7,
            command=self._copy_liquid_parameters,
            style="FileAction.TButton",
        ).pack(side="left")
        ttk.Button(
            liquid_header,
            text="Paste",
            width=7,
            command=self._paste_liquid_parameters,
            style="RowAction.TButton",
        ).pack(side="left", padx=(5, 0))
        self._field(liquid_fields, 1, 0, "Tip policy", self.tip_policy_var, width=18, combo=TIP_POLICIES)
        self._field(liquid_fields, 1, 2, "Extra aspirate (%)", self.multi_dispense_extra_percent_var, width=8)
        self._field(liquid_fields, 2, 0, "Aspirate from", self.aspirate_depth_reference_var, width=11, combo=TIP_DEPTH_REFERENCES)
        self._field(liquid_fields, 2, 2, "Aspirate depth mm", self.aspirate_depth_mm_var, width=8)
        self._field(liquid_fields, 3, 0, "Dispense from", self.dispense_depth_reference_var, width=11, combo=TIP_DEPTH_REFERENCES)
        self._field(liquid_fields, 3, 2, "Dispense depth mm", self.dispense_depth_mm_var, width=8)
        self._field(liquid_fields, 4, 0, "Aspirate rate uL/s", self.aspirate_rate_var, width=8)
        self._field(liquid_fields, 4, 2, "Dispense rate uL/s", self.dispense_rate_var, width=8)
        self._blowout_fields(liquid_fields, 5)
        liquid_actions = ttk.Frame(liquid_fields)
        liquid_actions.grid(row=8, column=0, columnspan=4, sticky="w", pady=3)
        ttk.Checkbutton(liquid_actions, text="Tip touch", variable=self.tip_touch_var).pack(side="left")
        ttk.Checkbutton(liquid_actions, text="Pre-wet tip", variable=self.pre_wet_tip_var).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(
            liquid_actions,
            text="Pipette mixing",
            variable=self.mix_enabled_var,
            command=self._on_mix_toggled,
        ).pack(side="left", padx=(8, 0))
        self.mix_settings_button = ttk.Button(
            liquid_actions,
            text="...",
            width=2,
            command=self._open_mix_dialog,
            state="disabled",
        )
        self.mix_settings_button.pack(side="left")
        ttk.Checkbutton(
            liquid_actions,
            text="Delay / air gap",
            variable=self.delay_air_gap_enabled_var,
            command=self._on_delay_air_gap_toggled,
        ).pack(side="left", padx=(6, 0))
        self.delay_air_gap_settings_button = ttk.Button(
            liquid_actions,
            text="...",
            width=2,
            command=self._open_delay_air_gap_dialog,
            state="disabled",
        )
        self.delay_air_gap_settings_button.pack(side="left")
        style_region_widgets(add, "ChemRegion")

        table_box = ttk.LabelFrame(table_pane, text="", padding=8, style="RowRegion.TLabelframe")
        self.protocol_plan_panel = table_box
        table_box.pack(fill="both", expand=True)
        table_box.rowconfigure(1, weight=1)
        table_box.columnconfigure(0, weight=1)
        plan_header = ttk.Frame(table_box)
        plan_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        plan_header.columnconfigure(0, weight=0)
        plan_header.columnconfigure(1, weight=0)
        plan_header.columnconfigure(3, weight=1)
        ttk.Label(plan_header, text="Protocol transfer plan", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Button(plan_header, text="Generate Protocol...", command=self._generate_protocol, style="ChemAction.TButton").grid(row=0, column=1, padx=(12, 0), sticky="w")
        self.push_cheminformatics_button = ttk.Button(
            plan_header,
            text="Push All to Cheminformatics",
            command=self._push_to_cheminformatics,
            style="ChemAction.TButton",
        )
        self.push_cheminformatics_button.grid(row=0, column=2, padx=(6, 0), sticky="w")
        plan_actions = ttk.Frame(plan_header)
        self.protocol_plan_action_toolbar = plan_actions
        plan_actions.grid(row=1, column=0, columnspan=4, sticky="w", pady=(5, 0))
        self.add_to_sequence_button = ttk.Button(
            plan_actions,
            text="Add to Sequence...",
            command=self._open_place_in_sequence_dialog,
            style="RowAction.TButton",
            state="disabled",
        )
        self.add_to_sequence_button.pack(side="left")
        self.ungroup_sequence_button = ttk.Button(
            plan_actions,
            text="Ungroup Sequence",
            command=self._ungroup_selected_sequence,
            style="RowAction.TButton",
            state="disabled",
        )
        self.ungroup_sequence_button.pack(side="left", padx=(6, 0))
        self.remove_row_button = ttk.Button(
            plan_actions,
            text="Delete",
            command=self._remove_selected,
            style="Danger.TButton",
            state="disabled",
        )
        self.remove_row_button.pack(side="left", padx=(10, 0))
        self.protocol_plan_status_label = ttk.Label(
            plan_header,
            textvariable=self.status_var,
            style="Muted.TLabel",
            wraplength=520,
            justify="left",
        )
        self.protocol_plan_status_label.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        self.tree = self._build_transfer_plan_tree(table_box, height=8)
        self.tree.grid(row=1, column=0, sticky="nsew")
        ybar = ttk.Scrollbar(table_box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ybar.set)
        ybar.grid(row=1, column=1, sticky="ns")
        self.plan_x_scrollbar = ttk.Scrollbar(table_box, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=self.plan_x_scrollbar.set)
        self.plan_x_scrollbar.grid(row=2, column=0, sticky="ew")
        style_region_widgets(table_box, "RowRegion")

        self.chemical_var.trace_add("write", self._on_structure_source_changed)
        self.chemical_var.trace_add("write", lambda *_args: self._calculate_dispense_volume_from_umol())
        self.reaction_umol_var.trace_add("write", lambda *_args: self._calculate_dispense_volume_from_umol())
        self.show_structure_var.trace_add("write", self._on_show_structure_toggle)
        self._row_editor_panels = (transfer_fields, liquid_fields, move_box)
        self._row_editor_enabled = False
        self._set_row_editor_enabled(False)
        self._update_transfer_type_controls()
        self._on_robot_changed(reset_api=False)

    def _summary_card(self, parent, col, title, summary_var, command, *, row=0):
        card = ttk.LabelFrame(parent, text=title, padding=(8, 5), style="FileRegion.TLabelframe")
        card.grid(row=row, column=col, sticky="nsew", padx=(6, 0))
        card.columnconfigure(0, weight=1)
        ttk.Label(card, textvariable=summary_var, style="Muted.TLabel", wraplength=155, justify="left").grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ttk.Button(card, text="Configure...", width=12, command=command).grid(row=1, column=0, sticky="w")

    def _wire_transfer_row_autosave(self):
        row_vars = (
            self.step_name_var,
            self.chemical_var,
            self.reaction_umol_var,
            self.is_building_block_var,
            self.source_well_var,
            self.dest_wells_var,
            self.volume_var,
            self.strategy_var,
            self.row_pipette_var,
            self.source_labware_alias_var,
            self.dest_labware_alias_var,
            self.tip_policy_var,
            self.blowout_location_var,
            self.blowout_labware_alias_var,
            self.blowout_well_var,
            self.aspirate_rate_var,
            self.dispense_rate_var,
            self.aspirate_depth_mm_var,
            self.aspirate_depth_reference_var,
            self.dispense_depth_mm_var,
            self.dispense_depth_reference_var,
            self.multi_dispense_extra_percent_var,
            self.tip_touch_var,
            self.pre_wet_tip_var,
            self.mix_enabled_var,
            self.mix_timing_var,
            self.mix_repetitions_var,
            self.mix_volume_var,
            self.post_source_mix_delay_seconds_var,
            self.mix_aspirate_rate_var,
            self.mix_dispense_rate_var,
            self.mix_aspirate_depth_mm_var,
            self.mix_aspirate_depth_reference_var,
            self.mix_dispense_depth_mm_var,
            self.mix_dispense_depth_reference_var,
            self.delay_air_gap_enabled_var,
            self.post_aspirate_delay_seconds_var,
            self.post_dispense_delay_seconds_var,
            self.pre_move_delay_seconds_var,
            self.air_gap_enabled_var,
            self.air_gap_volume_var,
            self.air_gap_height_var,
            self.air_gap_flow_rate_var,
            self.move_plate_var,
            self.move_labware_alias_var,
            self.move_to_slot_var,
            self.move_use_gripper_var,
        )
        for var in row_vars:
            var.trace_add("write", self._autosave_selected_transfer_row)
        self.mix_enabled_var.trace_add("write", self._update_mix_button_state)
        self.delay_air_gap_enabled_var.trace_add("write", self._update_delay_air_gap_button_state)

    def _build_transfer_plan_tree(self, parent, *, height: int) -> ttk.Treeview:
        columns = ("step", "chemical", "is_building_block", "source", "destinations", "umol", "volume", "strategy", "pipette", "liquid")
        tree = ttk.Treeview(parent, columns=columns, show="tree headings", height=height, selectmode="extended")
        tree.heading("#0", text="Sequence / Group")
        tree.column("#0", width=155, minwidth=100, anchor="w", stretch=False)
        for col, heading, width in (
            ("step", "Step", 150),
            ("chemical", "Chemical", 150),
            ("is_building_block", "BB?", 50),
            ("source", "Source", 120),
            ("destinations", "Destinations", 230),
            ("umol", "umol/well", 85),
            ("volume", "Dispense volume/uL", 115),
            ("strategy", "Strategy", 110),
            ("pipette", "Pipette", 80),
            ("liquid", "Liquid handling", 200),
        ):
            tree.heading(col, text=heading)
            tree.column(col, width=width, minwidth=50 if col == "is_building_block" else 70, anchor="e" if col in {"umol", "volume"} else "w", stretch=False)
        tree.bind("<<TreeviewSelect>>", self._on_transfer_row_select)
        tree.bind("<Control-c>", self._copy_selected_transfer_rows)
        tree.bind("<Control-C>", self._copy_selected_transfer_rows)
        tree.bind("<Control-v>", self._paste_copied_transfer_rows)
        tree.bind("<Control-V>", self._paste_copied_transfer_rows)
        tree.bind("<Button-3>", self._show_transfer_plan_menu)
        tree.bind("<ButtonPress-1>", self._on_plan_drag_start, add="+")
        tree.bind("<B1-Motion>", self._on_plan_drag_motion, add="+")
        tree.bind("<ButtonRelease-1>", self._on_plan_drag_release, add="+")
        tree.tag_configure("drop_target", background=COLORS["select"])
        tree.tag_configure("incomplete", background=COLORS["warning_light"], foreground=COLORS["warning"])
        tree.tag_configure("sequence", background=COLORS["blue_light"], font=("Segoe UI", 10, "bold"))
        tree.tag_configure("group", background=COLORS["panel_alt"], font=("Segoe UI", 10, "bold"))
        configure_table_tags(tree)
        return tree

    def _open_config_window(self, title: str):
        win = tk.Toplevel(self)
        win.title(title)
        win.transient(self.winfo_toplevel())
        win.resizable(True, False)
        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)
        return win, body

    def _open_pipette_dialog(self):
        robot = self.robot_var.get() if self.robot_var.get() in ROBOT_OPTIONS else "Flex"
        slots = FLEX_SLOTS if robot == "Flex" else OT2_SLOTS
        win, body = self._open_config_window("Opentrons pipettes")
        for col in (1, 3):
            body.columnconfigure(col, weight=1)
        self._field(body, 0, 0, "API level", self.api_level_var, width=10)
        if robot == "Flex":
            self._field(body, 0, 2, "Flex trash slot", self.trash_slot_var, width=10, combo=FLEX_SLOTS)
            ttk.Checkbutton(body, text="Flex gripper available", variable=self.flex_gripper_var).grid(row=0, column=4, columnspan=2, sticky="w", padx=(12, 0))
        else:
            self.flex_gripper_var.set(False)
            ttk.Label(body, text="OT-2 uses its fixed rear-right trash slot.", style="Muted.TLabel").grid(row=0, column=2, columnspan=4, sticky="w", padx=(12, 0))
        ttk.Separator(body).grid(row=1, column=0, columnspan=4, sticky="ew", pady=8)
        self._field(body, 2, 0, "Left pipette", self.left_pipette_var, width=28, combo=PIPETTE_OPTIONS[robot], callback=lambda: self._on_pipette_changed("left"))
        self._field(body, 3, 0, "Left tiprack", self.left_tiprack_var, width=42, combo=TIPRACK_OPTIONS[robot], span=3)
        self._field(body, 4, 0, "Left tip slot(s)", self.left_tiprack_slots_var, width=18, combo=slots)
        ttk.Button(body, text="Map", command=lambda: self._pick_deck_slots(self.left_tiprack_slots_var, multi=True, title="Select Left Tiprack Slots")).grid(row=4, column=2, sticky="w", padx=(12, 0), pady=3)
        ttk.Label(body, text="Multiple tip boxes are allowed.", style="Muted.TLabel").grid(row=4, column=3, columnspan=3, sticky="w", padx=(6, 0))
        ttk.Separator(body).grid(row=5, column=0, columnspan=4, sticky="ew", pady=8)
        self._field(body, 6, 0, "Right pipette", self.right_pipette_var, width=28, combo=PIPETTE_OPTIONS[robot], callback=lambda: self._on_pipette_changed("right"))
        self._field(body, 7, 0, "Right tiprack", self.right_tiprack_var, width=42, combo=TIPRACK_OPTIONS[robot], span=3)
        self._field(body, 8, 0, "Right tip slot(s)", self.right_tiprack_slots_var, width=18, combo=slots)
        ttk.Button(body, text="Map", command=lambda: self._pick_deck_slots(self.right_tiprack_slots_var, multi=True, title="Select Right Tiprack Slots")).grid(row=8, column=2, sticky="w", padx=(12, 0), pady=3)
        ttk.Label(body, text="Multiple tip boxes are allowed.", style="Muted.TLabel").grid(row=8, column=3, columnspan=3, sticky="w", padx=(6, 0))
        ttk.Button(body, text="Done", command=win.destroy).grid(row=9, column=3, sticky="e", pady=(10, 0))
        self._center_dialog(win)

    def _open_tip_location_dialog(self):
        win, body = self._open_config_window("Opentrons tip location")
        for col in (1,):
            body.columnconfigure(col, weight=1)
        ttk.Label(
            body,
            text=(
                "The start applies only to the first, partially used tip box. Later boxes are full. "
                "For Flex 8-channel SINGLE pickup, the generator chooses physical nozzle A1 or H1 from "
                "the deck rows used by each transfer. Pickup order follows that nozzle; every tip before "
                "the selected start in that order must already be absent."
            ),
            style="Muted.TLabel",
            wraplength=760,
        ).grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 8))
        for row_idx, (mount, pipette_var, column_var, well_var) in enumerate(
            (
                ("Left", self.left_pipette_var, self.left_tip_start_column_var, self.left_tip_start_well_var),
                ("Right", self.right_pipette_var, self.right_tip_start_column_var, self.right_tip_start_well_var),
            ),
            start=1,
        ):
            ttk.Label(body, text=f"{mount} pipette").grid(row=row_idx, column=0, sticky="w", pady=3)
            ttk.Label(body, textvariable=pipette_var, style="Muted.TLabel").grid(row=row_idx, column=1, sticky="w", pady=3)
            ttk.Label(body, text="8-channel start column").grid(row=row_idx, column=2, sticky="w", padx=(12, 6), pady=3)
            ttk.Combobox(body, textvariable=column_var, values=TIP_COLUMN_OPTIONS, width=6, state="readonly").grid(row=row_idx, column=3, sticky="w", pady=3)
            ttk.Label(body, text="Single-tip start well").grid(row=row_idx, column=4, sticky="w", padx=(12, 6), pady=3)
            ttk.Entry(body, textvariable=well_var, width=8, state="readonly").grid(row=row_idx, column=5, sticky="w", pady=3)
            ttk.Button(
                body,
                text="Map",
                command=lambda var=well_var: self._pick_tip_start_well(var),
                style="FileAction.TButton",
            ).grid(row=row_idx, column=6, sticky="w", padx=(6, 0), pady=3)
        ttk.Button(body, text="Done", command=win.destroy).grid(row=3, column=5, columnspan=2, sticky="e", pady=(10, 0))
        self._center_dialog(win)

    def _open_module_dialog(self):
        robot = self.robot_var.get() if self.robot_var.get() in ROBOT_OPTIONS else "Flex"
        win, body = self._open_config_window("Temperature and shaking modules")
        body.columnconfigure(0, weight=1)

        temp_box = ttk.LabelFrame(body, text="Temperature Module GEN2", padding=10)
        temp_box.grid(row=0, column=0, sticky="ew")
        for col in (1, 3):
            temp_box.columnconfigure(col, weight=1)
        ttk.Checkbutton(
            temp_box,
            text="Use Temperature Module GEN2",
            variable=self.temperature_module_enabled_var,
            command=self._on_module_configuration_changed,
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 4))
        self._field(
            temp_box,
            1,
            0,
            "Deck slot",
            self.temperature_module_slot_var,
            width=10,
            combo=self._supported_module_slots(robot, "temperature"),
        )
        ttk.Button(
            temp_box,
            text="Map",
            command=lambda: self._pick_deck_slots(
                self.temperature_module_slot_var,
                multi=False,
                title="Select Temperature Module Slot",
            ),
        ).grid(row=1, column=2, sticky="w", padx=(12, 0), pady=3)
        self._field(
            temp_box,
            2,
            0,
            "Starting labware (optional)",
            self.temperature_module_labware_alias_var,
            width=24,
            combo=self._all_labware_aliases(),
        )
        self._field(
            temp_box,
            3,
            0,
            "Adapter (optional)",
            self.temperature_module_adapter_var,
            width=44,
            combo=TEMPERATURE_MODULE_ADAPTERS,
            span=3,
        )
        self._field(temp_box, 4, 0, "Target temperature (°C)", self.temperature_module_target_var, width=10, stretch=False)
        ttk.Checkbutton(
            temp_box,
            text="Wait until the target temperature is reached",
            variable=self.temperature_module_wait_var,
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Checkbutton(
            temp_box,
            text="Deactivate after the final transfer row",
            variable=self.temperature_module_deactivate_var,
        ).grid(row=5, column=2, columnspan=2, sticky="w", padx=(12, 0), pady=(6, 0))

        heater_box = ttk.LabelFrame(body, text="Heater-Shaker Module", padding=10)
        heater_box.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        for col in (1, 3):
            heater_box.columnconfigure(col, weight=1)
        ttk.Checkbutton(
            heater_box,
            text="Use Heater-Shaker Module",
            variable=self.heater_shaker_enabled_var,
            command=self._on_module_configuration_changed,
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 4))
        self._field(
            heater_box,
            1,
            0,
            "Deck slot",
            self.heater_shaker_slot_var,
            width=10,
            combo=self._supported_module_slots(robot, "heater_shaker"),
        )
        ttk.Button(
            heater_box,
            text="Map",
            command=lambda: self._pick_deck_slots(
                self.heater_shaker_slot_var,
                multi=False,
                title="Select Heater-Shaker Slot",
            ),
        ).grid(row=1, column=2, sticky="w", padx=(12, 0), pady=3)
        self._field(
            heater_box,
            2,
            0,
            "Starting labware (optional)",
            self.heater_shaker_labware_alias_var,
            width=24,
            combo=self._all_labware_aliases(),
        )
        self._field(
            heater_box,
            3,
            0,
            "Adapter (optional)",
            self.heater_shaker_adapter_var,
            width=44,
            combo=HEATER_SHAKER_ADAPTERS,
            span=3,
        )
        self._field(heater_box, 4, 0, "Target temperature (°C)", self.heater_shaker_temperature_var, width=10, stretch=False)
        self._field(heater_box, 4, 2, "Shake speed (rpm)", self.heater_shaker_speed_var, width=10, stretch=False)
        self._field(heater_box, 5, 0, "Shake duration (min)", self.heater_shaker_duration_var, width=10, stretch=False)
        ttk.Checkbutton(
            heater_box,
            text="Wait until temperature / speed is reached",
            variable=self.heater_shaker_wait_var,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Checkbutton(
            heater_box,
            text="Deactivate heating after the final transfer row",
            variable=self.heater_shaker_deactivate_var,
        ).grid(row=6, column=2, columnspan=2, sticky="w", padx=(12, 0), pady=(6, 0))

        ttk.Label(
            body,
            text=(
                "Enable either module or both. Each enabled module needs its own deck slot; starting labware is optional. "
                "Temperature Module GEN2 controls 4–95 °C. Heater-Shaker controls 37–95 °C and optional "
                "200–3000 rpm timed shaking. A plate moved onto the Heater-Shaker runs the configured shake cycle "
                "before the next transfer row. Select an adapter before moving labware onto or off a module."
            ),
            style="Muted.TLabel",
            wraplength=760,
        ).grid(row=2, column=0, sticky="ew", pady=(10, 0))

        def apply_and_close():
            if not self._apply_module_setups_to_labware():
                return
            win.destroy()

        ttk.Button(body, text="Done", command=apply_and_close, style="FileAction.TButton").grid(
            row=3, column=0, sticky="e", pady=(10, 0)
        )
        self._on_module_configuration_changed()
        self._center_dialog(win)

    @staticmethod
    def _supported_module_slots(robot: str, module_kind: str) -> Tuple[str, ...]:
        if robot == "Flex":
            return FLEX_POWERED_MODULE_SLOTS
        if module_kind == "temperature":
            return OT2_TEMPERATURE_MODULE_SLOTS
        return OT2_HEATER_SHAKER_SLOTS

    def _on_module_configuration_changed(self):
        robot = self.robot_var.get() if self.robot_var.get() in ROBOT_OPTIONS else "Flex"
        for kind, enabled_var, slot_var, alias_var, other_enabled_var, other_alias_var in (
            (
                "temperature", self.temperature_module_enabled_var, self.temperature_module_slot_var,
                self.temperature_module_labware_alias_var, self.heater_shaker_enabled_var,
                self.heater_shaker_labware_alias_var,
            ),
            (
                "heater_shaker", self.heater_shaker_enabled_var, self.heater_shaker_slot_var,
                self.heater_shaker_labware_alias_var, self.temperature_module_enabled_var,
                self.temperature_module_labware_alias_var,
            ),
        ):
            supported = self._supported_module_slots(robot, kind)
            if slot_var.get().strip() not in supported:
                preferred = ("C3" if kind == "temperature" else "B3") if robot == "Flex" else ("3" if kind == "temperature" else "1")
                slot_var.set(preferred if preferred in supported else supported[0])
            if alias_var.get().strip() and alias_var.get().strip() not in self._all_labware_aliases():
                alias_var.set("")
        for child in self.winfo_children():
            self._refresh_combo_values(child, robot)
        self._update_summaries()

    def _apply_module_setups_to_labware(self) -> bool:
        robot = self.robot_var.get() if self.robot_var.get() in ROBOT_OPTIONS else "Flex"
        setups = []
        for label, kind, enabled_var, slot_var, alias_var in (
            (
                "Temperature Module GEN2", "temperature", self.temperature_module_enabled_var,
                self.temperature_module_slot_var, self.temperature_module_labware_alias_var,
            ),
            (
                "Heater-Shaker Module", "heater_shaker", self.heater_shaker_enabled_var,
                self.heater_shaker_slot_var, self.heater_shaker_labware_alias_var,
            ),
        ):
            if not enabled_var.get():
                continue
            alias = alias_var.get().strip()
            labware = self._labware_by_alias(alias) if alias else None
            slot = slot_var.get().strip()
            if slot not in self._supported_module_slots(robot, kind):
                messagebox.showwarning("Opentrons module", f"Slot {slot or '(blank)'} is not supported for {label} on {robot}.")
                return False
            if alias and labware is None:
                messagebox.showwarning(
                    "Opentrons module",
                    f"Select a valid starting labware alias for {label}, or leave it blank.",
                )
                return False
            setups.append((label, alias, slot, labware))
        starting_aliases = [alias for _label, alias, _slot, _labware in setups if alias]
        if len(set(starting_aliases)) != len(starting_aliases):
            messagebox.showwarning("Opentrons module", "The two modules must use different labware aliases.")
            return False
        if len({slot for _label, _alias, slot, _labware in setups}) != len(setups):
            messagebox.showwarning("Opentrons module", "The two modules must use different deck slots.")
            return False
        for _label, _alias, slot, labware in setups:
            if labware is not None:
                labware["slot"] = slot
        self._sync_legacy_labware_vars()
        self._refresh_labware_tree()
        self._update_summaries()
        return True

    def _module_state(self) -> Dict[str, object]:
        return {
            "temperature_module_enabled": self.temperature_module_enabled_var.get(),
            "temperature_module_slot": self.temperature_module_slot_var.get(),
            "temperature_module_labware_alias": self.temperature_module_labware_alias_var.get(),
            "temperature_module_adapter": self.temperature_module_adapter_var.get(),
            "temperature_module_target": self.temperature_module_target_var.get(),
            "temperature_module_wait": self.temperature_module_wait_var.get(),
            "temperature_module_deactivate": self.temperature_module_deactivate_var.get(),
            "heater_shaker_enabled": self.heater_shaker_enabled_var.get(),
            "heater_shaker_slot": self.heater_shaker_slot_var.get(),
            "heater_shaker_labware_alias": self.heater_shaker_labware_alias_var.get(),
            "heater_shaker_adapter": self.heater_shaker_adapter_var.get(),
            "heater_shaker_temperature": self.heater_shaker_temperature_var.get(),
            "heater_shaker_speed": self.heater_shaker_speed_var.get(),
            "heater_shaker_duration": self.heater_shaker_duration_var.get(),
            "heater_shaker_wait": self.heater_shaker_wait_var.get(),
            "heater_shaker_deactivate": self.heater_shaker_deactivate_var.get(),
        }

    def _apply_module_state(self, data: Dict[str, object]):
        has_dual_module_state = any(
            key in data for key in ("temperature_module_enabled", "heater_shaker_enabled")
        )
        if has_dual_module_state:
            self.temperature_module_enabled_var.set(bool(data.get("temperature_module_enabled", False)))
            self.temperature_module_slot_var.set(str(data.get("temperature_module_slot", "C3") or "C3"))
            self.temperature_module_labware_alias_var.set(str(data.get("temperature_module_labware_alias", "") or ""))
            self.temperature_module_adapter_var.set(str(data.get("temperature_module_adapter", "") or ""))
            self.temperature_module_target_var.set(str(data.get("temperature_module_target", "4") or ""))
            self.temperature_module_wait_var.set(bool(data.get("temperature_module_wait", True)))
            self.temperature_module_deactivate_var.set(bool(data.get("temperature_module_deactivate", True)))
            self.heater_shaker_enabled_var.set(bool(data.get("heater_shaker_enabled", False)))
            self.heater_shaker_slot_var.set(str(data.get("heater_shaker_slot", "B3") or "B3"))
            self.heater_shaker_labware_alias_var.set(str(data.get("heater_shaker_labware_alias", "") or ""))
            self.heater_shaker_adapter_var.set(str(data.get("heater_shaker_adapter", "") or ""))
            self.heater_shaker_temperature_var.set(str(data.get("heater_shaker_temperature", "37") or ""))
            self.heater_shaker_speed_var.set(str(data.get("heater_shaker_speed", "500") or ""))
            self.heater_shaker_duration_var.set(str(data.get("heater_shaker_duration", "1") or ""))
            self.heater_shaker_wait_var.set(bool(data.get("heater_shaker_wait", True)))
            self.heater_shaker_deactivate_var.set(bool(data.get("heater_shaker_deactivate", True)))
            return

        legacy_type = str(data.get("module_type", "None") or "None")
        legacy_slot = str(data.get("module_slot", "C3") or "C3")
        legacy_alias = str(data.get("module_labware_alias", "") or "")
        legacy_adapter = str(data.get("module_adapter", "") or "")
        legacy_temperature = str(data.get("module_temperature", "") or "")
        legacy_wait = bool(data.get("module_wait", True))
        legacy_deactivate = bool(data.get("module_deactivate", True))
        self.temperature_module_enabled_var.set(legacy_type == "Temperature Module GEN2")
        self.temperature_module_slot_var.set(legacy_slot if legacy_type == "Temperature Module GEN2" else "C3")
        self.temperature_module_labware_alias_var.set(legacy_alias if legacy_type == "Temperature Module GEN2" else "")
        self.temperature_module_adapter_var.set(legacy_adapter if legacy_type == "Temperature Module GEN2" else "")
        self.temperature_module_target_var.set(legacy_temperature if legacy_type == "Temperature Module GEN2" and legacy_temperature else "4")
        self.temperature_module_wait_var.set(legacy_wait)
        self.temperature_module_deactivate_var.set(legacy_deactivate)
        self.heater_shaker_enabled_var.set(legacy_type == "Heater-Shaker Module")
        self.heater_shaker_slot_var.set(legacy_slot if legacy_type == "Heater-Shaker Module" else "B3")
        self.heater_shaker_labware_alias_var.set(legacy_alias if legacy_type == "Heater-Shaker Module" else "")
        self.heater_shaker_adapter_var.set(legacy_adapter if legacy_type == "Heater-Shaker Module" else "")
        self.heater_shaker_temperature_var.set(legacy_temperature if legacy_type == "Heater-Shaker Module" else "37")
        self.heater_shaker_speed_var.set(str(data.get("module_shake_speed", "500") or ""))
        self.heater_shaker_duration_var.set(str(data.get("module_shake_duration", "1") or ""))
        self.heater_shaker_wait_var.set(legacy_wait)
        self.heater_shaker_deactivate_var.set(legacy_deactivate)

    def _pick_tip_start_well(self, var: tk.StringVar):
        dlg = well_map.WellMapDialog(
            self,
            8,
            12,
            var.get(),
            vertical_view=False,
            anchor=self,
            single_select=True,
        )
        dlg.title("Select Tip Start Well")
        self.wait_window(dlg)
        if getattr(dlg, "result_labels", ""):
            var.set(dlg.result_labels)

    def _open_labware_dialog(self):
        robot = self.robot_var.get() if self.robot_var.get() in ROBOT_OPTIONS else "Flex"
        slots = FLEX_SLOTS if robot == "Flex" else OT2_SLOTS
        win, body = self._open_config_window("Opentrons labware")
        for col in (1, 3, 5):
            body.columnconfigure(col, weight=1)
        self._field(body, 0, 0, "Alias", self.labware_alias_var, width=18)
        self._field(body, 0, 2, "Role", self.labware_role_var, width=14, combo=LABWARE_ROLES)
        self._field(body, 0, 4, "Slot", self.labware_slot_var, width=10, combo=slots)
        ttk.Button(body, text="Map", command=lambda: self._pick_deck_slots(self.labware_slot_var, multi=False, title="Select Labware Slot")).grid(row=0, column=6, sticky="w", padx=(6, 0), pady=3)
        self._field(
            body,
            1,
            0,
            "Load name",
            self.labware_load_name_var,
            width=44,
            combo=LABWARE_OPTIONS,
            callback=self._auto_update_labware_map_style,
            span=3,
        )
        self._field(body, 1, 4, "Map style", self.labware_map_style_var, width=24, combo=PLATE_STYLES)
        ttk.Label(
            body,
            text=(
                "Use short aliases such as source1, reaction_plate, or product_plate. "
                "Role 'both' makes the same labware available in both source and destination selectors. "
                "Map style updates automatically for bundled Opentrons labware; choose it manually for custom labware."
            ),
            style="Muted.TLabel",
            wraplength=720,
        ).grid(row=2, column=0, columnspan=6, sticky="w", pady=(0, 4))
        actions = ttk.Frame(body)
        actions.grid(row=3, column=0, columnspan=6, sticky="w", pady=(4, 8))
        ttk.Button(actions, text="Add / Update Labware", command=self._add_update_labware_config, style="FileAction.TButton").pack(side="left")
        ttk.Button(actions, text="Remove Selected", command=self._remove_selected_labware_config, style="Danger.TButton").pack(side="left", padx=(6, 0))
        columns = ("alias", "role", "load_name", "slot", "map_style")
        self.labware_tree = ttk.Treeview(body, columns=columns, show="headings", height=7)
        for col, text, width in (
            ("alias", "Alias", 130),
            ("role", "Role", 100),
            ("load_name", "Load name", 360),
            ("slot", "Slot", 80),
            ("map_style", "Map style", 175),
        ):
            self.labware_tree.heading(col, text=text)
            self.labware_tree.column(col, width=width, anchor="w")
        self.labware_tree.grid(row=4, column=0, columnspan=6, sticky="nsew")
        self.labware_tree.bind("<<TreeviewSelect>>", self._on_labware_config_select)
        body.rowconfigure(4, weight=1)
        ttk.Label(
            body,
            text="Well labels come from the selected Opentrons labware definition. For 48-well/custom plates, confirm A1 and spacing in the JSON before running.",
            style="Muted.TLabel",
            wraplength=760,
        ).grid(row=5, column=0, columnspan=6, sticky="ew", pady=(10, 0))
        ttk.Button(body, text="Done", command=win.destroy).grid(row=6, column=5, sticky="e", pady=(10, 0))
        self._refresh_labware_tree()
        self._center_dialog(win)

    def _open_motion_dialog(self):
        win, body = self._open_config_window("Liquid handling")
        for col in (1, 3):
            body.columnconfigure(col, weight=1)
        self._field(body, 0, 0, "Tip policy", self.tip_policy_var, width=22, combo=TIP_POLICIES)
        self._field(body, 1, 0, "8-channel behavior", self.eight_channel_mode_var, width=22, combo=EIGHT_CHANNEL_MODES)
        self._field(body, 2, 0, "Aspirate rate uL/s", self.aspirate_rate_var, width=14)
        self._field(body, 2, 2, "Dispense rate uL/s", self.dispense_rate_var, width=14)
        self._field(body, 3, 0, "Aspirate from", self.aspirate_depth_reference_var, width=14, combo=TIP_DEPTH_REFERENCES)
        self._field(body, 3, 2, "Aspirate depth mm", self.aspirate_depth_mm_var, width=14)
        self._field(body, 4, 0, "Dispense from", self.dispense_depth_reference_var, width=14, combo=TIP_DEPTH_REFERENCES)
        self._field(body, 4, 2, "Dispense depth mm", self.dispense_depth_mm_var, width=14)
        self._field(body, 5, 0, "Extra aspirate volume (%)", self.multi_dispense_extra_percent_var, width=14)
        ttk.Checkbutton(body, text="Tip touch after dispense", variable=self.tip_touch_var).grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Checkbutton(body, text="Pre-wet tip before aspirating", variable=self.pre_wet_tip_var).grid(row=7, column=0, columnspan=4, sticky="w", pady=(4, 0))
        mix_actions = ttk.Frame(body)
        mix_actions.grid(row=8, column=0, columnspan=4, sticky="w", pady=(4, 0))
        ttk.Checkbutton(
            mix_actions,
            text="Pipette mixing for this row",
            variable=self.mix_enabled_var,
            command=self._on_mix_toggled,
        ).pack(side="left")
        ttk.Button(mix_actions, text="Mix settings...", command=self._open_mix_dialog).pack(side="left", padx=(8, 0))
        ttk.Label(
            body,
            text="Leave depth blank to use the Opentrons default well position. From top uses mm down into the well.",
            style="Muted.TLabel",
            wraplength=680,
        ).grid(row=9, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self._blowout_fields(body, 10)
        ttk.Button(body, text="Done", command=win.destroy).grid(row=13, column=3, sticky="e", pady=(10, 0))
        self._center_dialog(win)

    def _blowout_fields(self, parent, row):
        self._field(parent, row, 0, "Blowout", self.blowout_location_var, width=18, combo=BLOWOUT_LOCATIONS)
        self._field(parent, row + 1, 0, "Waste labware", self.blowout_labware_alias_var, width=16, combo=self._dest_labware_aliases())
        self._field(parent, row + 1, 2, "Waste well", self.blowout_well_var, width=8)
        ttk.Label(
            parent,
            text="Waste fields apply to Liquid waste. Extra aspirate requires Source or Liquid waste. "
                 "Source can contaminate stock after the tip contacts a sample.",
            style="Muted.TLabel", wraplength=540,
        ).grid(row=row + 2, column=0, columnspan=4, sticky="ew", pady=(2, 3))

    def _on_strategy_changed(self):
        if not self._confirm_multi_dispense_destination_mixing(
            strategy=self.strategy_var.get(),
            timing=self.mix_timing_var.get(),
            enabled=bool(self.mix_enabled_var.get()),
        ):
            self._loading_transfer_row = True
            try:
                self.mix_timing_var.set("Before aspirating")
            finally:
                self._loading_transfer_row = False
            self._autosave_selected_transfer_row()
            self.status_var.set(
                "Destination mixing was not enabled; Multi-dispense mixing remains before aspiration."
            )

    @staticmethod
    def _uses_multi_dispense_destination_mixing(*, strategy: object, timing: object, enabled: bool) -> bool:
        return (
            bool(enabled)
            and str(strategy or "").strip() == "Multi-dispense"
            and str(timing or "").strip() in {"After dispensing", "Before and after"}
        )

    def _confirm_multi_dispense_destination_mixing(
        self,
        *,
        strategy: object,
        timing: object,
        enabled: bool,
        parent=None,
    ) -> bool:
        if not self._uses_multi_dispense_destination_mixing(
            strategy=strategy,
            timing=timing,
            enabled=enabled,
        ):
            return True
        return bool(
            messagebox.askokcancel(
                "Multi-dispense contamination warning",
                "Destination mixing during Multi-dispense aspirates from a destination well while the tip still "
                "contains liquid for later destinations. This can carry material into subsequent wells and alter "
                "their composition.\n\nContinue with destination mixing enabled?",
                icon=messagebox.WARNING,
                default=messagebox.CANCEL,
                parent=parent or self.winfo_toplevel(),
            )
        )

    def _on_mix_toggled(self):
        self._update_mix_button_state()
        if self.mix_enabled_var.get():
            self._open_mix_dialog(disable_on_cancel=True)

    def _update_mix_button_state(self, *_args):
        button = getattr(self, "mix_settings_button", None)
        if button is not None:
            button.configure(
                state="normal"
                if getattr(self, "_row_editor_enabled", False) and self.mix_enabled_var.get()
                else "disabled"
            )

    def _open_mix_dialog(self, *, disable_on_cancel: bool = False):
        if not self.mix_enabled_var.get() and not disable_on_cancel:
            self.mix_enabled_var.set(True)
        strategy = self.strategy_var.get()
        allowed_timings = MIX_TIMINGS
        current_timing = self.mix_timing_var.get()
        if current_timing not in allowed_timings:
            current_timing = allowed_timings[0]

        timing_var = tk.StringVar(value=current_timing)
        repetitions_var = tk.StringVar(value=self.mix_repetitions_var.get() or "3")
        volume_var = tk.StringVar(value=self.mix_volume_var.get() or self.volume_var.get())
        post_source_mix_delay_var = tk.StringVar(value=self.post_source_mix_delay_seconds_var.get())
        aspirate_rate_var = tk.StringVar(value=self.mix_aspirate_rate_var.get())
        dispense_rate_var = tk.StringVar(value=self.mix_dispense_rate_var.get())
        aspirate_depth_var = tk.StringVar(value=self.mix_aspirate_depth_mm_var.get())
        aspirate_reference_var = tk.StringVar(value=self.mix_aspirate_depth_reference_var.get() or "from bottom")
        dispense_depth_var = tk.StringVar(value=self.mix_dispense_depth_mm_var.get())
        dispense_reference_var = tk.StringVar(value=self.mix_dispense_depth_reference_var.get() or "from bottom")

        win, body = self._open_config_window("Pipette mixing for this transfer row")
        for col in (1, 3):
            body.columnconfigure(col, weight=1)
        self._field(body, 0, 0, "When to mix", timing_var, width=20, combo=allowed_timings)
        self._field(body, 0, 2, "Repetitions", repetitions_var, width=10, stretch=False)
        self._field(body, 1, 0, "Mix volume/uL", volume_var, width=12, stretch=False)
        self._field(body, 1, 2, "Delay after source mixing (s)", post_source_mix_delay_var, width=12, stretch=False)
        ttk.Separator(body).grid(row=2, column=0, columnspan=4, sticky="ew", pady=8)
        self._field(body, 3, 0, "Aspirate from", aspirate_reference_var, width=14, combo=TIP_DEPTH_REFERENCES)
        self._field(body, 3, 2, "Aspirate depth mm", aspirate_depth_var, width=12, stretch=False)
        self._field(body, 4, 0, "Aspirate speed uL/s", aspirate_rate_var, width=12, stretch=False)
        self._field(body, 5, 0, "Dispense from", dispense_reference_var, width=14, combo=TIP_DEPTH_REFERENCES)
        self._field(body, 5, 2, "Dispense depth mm", dispense_depth_var, width=12, stretch=False)
        self._field(body, 6, 0, "Dispense speed uL/s", dispense_rate_var, width=12, stretch=False)
        explanation = (
            "Before aspiration mixes the source well. After dispensing mixes each destination well. For "
            "Multi-dispense, destination mixing can carry material into later wells because the tip still contains "
            "the remaining batch; saving that choice requires confirmation. The optional source-mixing delay runs "
            "after source mixing and before aspiration only."
        )
        ttk.Label(body, text=explanation, style="Muted.TLabel", wraplength=680).grid(
            row=7, column=0, columnspan=4, sticky="w", pady=(8, 0)
        )
        actions = ttk.Frame(body)
        actions.grid(row=8, column=0, columnspan=4, sticky="e", pady=(12, 0))

        def cancel():
            if disable_on_cancel:
                self.mix_enabled_var.set(False)
            win.destroy()

        def save():
            try:
                values = self._validated_mix_settings(
                    enabled=True,
                    strategy=strategy,
                    timing=timing_var.get(),
                    repetitions=repetitions_var.get(),
                    volume=volume_var.get(),
                    post_source_mix_delay=post_source_mix_delay_var.get(),
                    aspirate_rate=aspirate_rate_var.get(),
                    dispense_rate=dispense_rate_var.get(),
                    aspirate_depth=aspirate_depth_var.get(),
                    aspirate_reference=aspirate_reference_var.get(),
                    dispense_depth=dispense_depth_var.get(),
                    dispense_reference=dispense_reference_var.get(),
                )
            except Exception as exc:
                messagebox.showwarning("Pipette mixing", str(exc), parent=win)
                return
            if not self._confirm_multi_dispense_destination_mixing(
                strategy=strategy,
                timing=values["mix_timing"],
                enabled=True,
                parent=win,
            ):
                return
            self._loading_transfer_row = True
            try:
                self.mix_enabled_var.set(True)
                self.mix_timing_var.set(values["mix_timing"])
                self.mix_repetitions_var.set(str(values["mix_repetitions"]))
                self.mix_volume_var.set(str(values["mix_volume_ul"]))
                post_source_mix_delay = values["post_source_mix_delay_seconds"]
                self.post_source_mix_delay_seconds_var.set(
                    "" if post_source_mix_delay is None else str(post_source_mix_delay)
                )
                self.mix_aspirate_rate_var.set(aspirate_rate_var.get().strip())
                self.mix_dispense_rate_var.set(dispense_rate_var.get().strip())
                self.mix_aspirate_depth_mm_var.set(aspirate_depth_var.get().strip())
                self.mix_aspirate_depth_reference_var.set(values["mix_aspirate_depth_reference"])
                self.mix_dispense_depth_mm_var.set(dispense_depth_var.get().strip())
                self.mix_dispense_depth_reference_var.set(values["mix_dispense_depth_reference"])
            finally:
                self._loading_transfer_row = False
            self._autosave_selected_transfer_row()
            self._update_summaries()
            win.destroy()

        ttk.Button(actions, text="Cancel", command=cancel).pack(side="left")
        ttk.Button(actions, text="Save mixing", command=save, style="ChemAction.TButton").pack(side="left", padx=(6, 0))
        win.protocol("WM_DELETE_WINDOW", cancel)
        self._center_dialog(win)

    def _on_delay_air_gap_toggled(self):
        self._update_delay_air_gap_button_state()
        if self.delay_air_gap_enabled_var.get():
            self._open_delay_air_gap_dialog(disable_on_cancel=True)

    def _update_delay_air_gap_button_state(self, *_args):
        button = getattr(self, "delay_air_gap_settings_button", None)
        if button is not None:
            button.configure(
                state="normal"
                if getattr(self, "_row_editor_enabled", False) and self.delay_air_gap_enabled_var.get()
                else "disabled"
            )

    def _open_delay_air_gap_dialog(self, *, disable_on_cancel: bool = False):
        if not self.delay_air_gap_enabled_var.get() and not disable_on_cancel:
            self.delay_air_gap_enabled_var.set(True)
        aspirate_delay_var = tk.StringVar(value=self.post_aspirate_delay_seconds_var.get())
        dispense_delay_var = tk.StringVar(value=self.post_dispense_delay_seconds_var.get())
        pre_move_delay_var = tk.StringVar(value=self.pre_move_delay_seconds_var.get())
        air_gap_enabled_var = tk.BooleanVar(value=self.air_gap_enabled_var.get())
        air_gap_volume_var = tk.StringVar(value=self.air_gap_volume_var.get())
        air_gap_height_var = tk.StringVar(value=self.air_gap_height_var.get() or "5")
        air_gap_flow_rate_var = tk.StringVar(value=self.air_gap_flow_rate_var.get())

        win, body = self._open_config_window("Delay and air gap for this transfer row")
        for col in (1, 3):
            body.columnconfigure(col, weight=1)
        ttk.Label(body, text="Timed delays", font=("", 10, "bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 4)
        )
        self._field(body, 1, 0, "After aspiration (s)", aspirate_delay_var, width=12, stretch=False)
        self._field(body, 1, 2, "After dispensing (s)", dispense_delay_var, width=12, stretch=False)
        self._field(body, 2, 0, "Before plate movement (s)", pre_move_delay_var, width=12, stretch=False)
        ttk.Label(
            body,
            text=(
                "After-aspiration delay holds the tip at the aspiration position before retracting. "
                "Before-plate-movement delay is used only when Move plate after row is enabled."
            ),
            style="Muted.TLabel",
            wraplength=700,
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(5, 8))
        ttk.Separator(body).grid(row=4, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        ttk.Checkbutton(
            body,
            text="Use an air gap after aspiration",
            variable=air_gap_enabled_var,
        ).grid(row=5, column=0, columnspan=4, sticky="w")
        volume_widget = self._field(body, 6, 0, "Air-gap volume/uL", air_gap_volume_var, width=12, stretch=False)
        height_widget = self._field(body, 6, 2, "Height above well (mm)", air_gap_height_var, width=12, stretch=False)
        flow_widget = self._field(body, 7, 0, "Air-gap speed uL/s", air_gap_flow_rate_var, width=12, stretch=False)
        ttk.Label(
            body,
            text=(
                "Single transfer releases the air gap above each destination before destination mixing. "
                "Multi-dispense uses one air gap per aspiration batch and clears it after the batch."
            ),
            style="Muted.TLabel",
            wraplength=700,
        ).grid(row=8, column=0, columnspan=4, sticky="w", pady=(8, 0))

        def sync_air_gap_fields(*_args):
            state = "normal" if air_gap_enabled_var.get() else "disabled"
            for widget in (volume_widget, height_widget, flow_widget):
                widget.configure(state=state)

        air_gap_enabled_var.trace_add("write", sync_air_gap_fields)
        sync_air_gap_fields()
        actions = ttk.Frame(body)
        actions.grid(row=9, column=0, columnspan=4, sticky="e", pady=(12, 0))

        def cancel():
            if disable_on_cancel:
                self.delay_air_gap_enabled_var.set(False)
            win.destroy()

        def save():
            try:
                values = self._validated_delay_air_gap_settings(
                    post_aspirate_delay=aspirate_delay_var.get(),
                    post_dispense_delay=dispense_delay_var.get(),
                    pre_move_delay=pre_move_delay_var.get(),
                    air_gap_enabled=bool(air_gap_enabled_var.get()),
                    air_gap_volume=air_gap_volume_var.get(),
                    air_gap_height=air_gap_height_var.get(),
                    air_gap_flow_rate=air_gap_flow_rate_var.get(),
                )
            except Exception as exc:
                messagebox.showwarning("Delay and air gap", str(exc), parent=win)
                return
            self._loading_transfer_row = True
            try:
                self.delay_air_gap_enabled_var.set(True)
                self.post_aspirate_delay_seconds_var.set(aspirate_delay_var.get().strip())
                self.post_dispense_delay_seconds_var.set(dispense_delay_var.get().strip())
                self.pre_move_delay_seconds_var.set(pre_move_delay_var.get().strip())
                self.air_gap_enabled_var.set(bool(values["air_gap_enabled"]))
                self.air_gap_volume_var.set(
                    str(values["air_gap_volume_ul"]) if values["air_gap_volume_ul"] is not None else air_gap_volume_var.get().strip()
                )
                self.air_gap_height_var.set(
                    str(values["air_gap_height_mm"])
                    if values["air_gap_enabled"]
                    else (air_gap_height_var.get().strip() or "5")
                )
                self.air_gap_flow_rate_var.set(air_gap_flow_rate_var.get().strip())
            finally:
                self._loading_transfer_row = False
            self._autosave_selected_transfer_row()
            self._update_summaries()
            win.destroy()

        ttk.Button(actions, text="Cancel", command=cancel).pack(side="left")
        ttk.Button(actions, text="Save settings", command=save, style="ChemAction.TButton").pack(side="left", padx=(6, 0))
        win.protocol("WM_DELETE_WINDOW", cancel)
        self._center_dialog(win)

    def _hide_deck_setup(self):
        if self.deck_setup_hidden:
            return
        try:
            self.plan_panes.forget(self.deck_pane)
        except tk.TclError:
            return
        self.deck_setup_hidden = True
        self.deck_show_bar.pack(fill="x", padx=2, pady=(0, 6), before=self.transfer_row_panel)

    def _show_deck_setup(self):
        if not self.deck_setup_hidden:
            return
        try:
            self.plan_panes.insert(0, self.deck_pane, weight=0)
        except tk.TclError:
            self.plan_panes.add(self.deck_pane, weight=0)
        self.deck_setup_hidden = False
        self.deck_show_bar.pack_forget()

    def _deck_template_state(self) -> Dict[str, object]:
        return {
            "template_type": "opentrons_protocol_generator_deck_setup",
            "version": 8,
            "robot": self.robot_var.get(),
            "api_level": self.api_level_var.get(),
            "left_pipette": self.left_pipette_var.get(),
            "left_tiprack": self.left_tiprack_var.get(),
            "left_tiprack_slots": self.left_tiprack_slots_var.get(),
            "left_tip_start_column": self.left_tip_start_column_var.get(),
            "left_tip_start_well": self.left_tip_start_well_var.get(),
            "right_pipette": self.right_pipette_var.get(),
            "right_tiprack": self.right_tiprack_var.get(),
            "right_tiprack_slots": self.right_tiprack_slots_var.get(),
            "right_tip_start_column": self.right_tip_start_column_var.get(),
            "right_tip_start_well": self.right_tip_start_well_var.get(),
            "trash_slot": self.trash_slot_var.get(),
            "flex_gripper": self.flex_gripper_var.get(),
            **self._module_state(),
            "source_labware": self.source_labware_var.get(),
            "source_slot": self.source_slot_var.get(),
            "source_style": self.source_style_var.get(),
            "dest_labware": self.dest_labware_var.get(),
            "dest_slot": self.dest_slot_var.get(),
            "dest_style": self.dest_style_var.get(),
            "labware_configs": [dict(item) for item in self.labware_configs],
            "transfer_type": "batch" if self._is_batch_transfer_mode() else "single",
            "step_name": self.step_name_var.get(),
            "chemical": self.chemical_var.get(),
            "reaction_umol": self.reaction_umol_var.get(),
            "is_building_block": self.is_building_block_var.get(),
            "tip_policy": self.tip_policy_var.get(),
            "blowout_location": self.blowout_location_var.get(),
            "blowout_labware_alias": self.blowout_labware_alias_var.get().strip(),
            "blowout_well": self.blowout_well_var.get().strip().upper(),
            "eight_channel_mode": self.eight_channel_mode_var.get(),
            "aspirate_rate": self.aspirate_rate_var.get(),
            "dispense_rate": self.dispense_rate_var.get(),
            "aspirate_depth_mm": self.aspirate_depth_mm_var.get(),
            "aspirate_depth_reference": self.aspirate_depth_reference_var.get(),
            "dispense_depth_mm": self.dispense_depth_mm_var.get(),
            "dispense_depth_reference": self.dispense_depth_reference_var.get(),
            "multi_dispense_extra_percent": self.multi_dispense_extra_percent_var.get(),
            "tip_touch": self.tip_touch_var.get(),
            "pre_wet_tip": self.pre_wet_tip_var.get(),
            "mix_enabled": self.mix_enabled_var.get(),
            "mix_timing": self.mix_timing_var.get(),
            "mix_repetitions": self.mix_repetitions_var.get(),
            "mix_volume_ul": self.mix_volume_var.get(),
            "post_source_mix_delay_seconds": self.post_source_mix_delay_seconds_var.get(),
            "mix_aspirate_rate": self.mix_aspirate_rate_var.get(),
            "mix_dispense_rate": self.mix_dispense_rate_var.get(),
            "mix_aspirate_depth_mm": self.mix_aspirate_depth_mm_var.get(),
            "mix_aspirate_depth_reference": self.mix_aspirate_depth_reference_var.get(),
            "mix_dispense_depth_mm": self.mix_dispense_depth_mm_var.get(),
            "mix_dispense_depth_reference": self.mix_dispense_depth_reference_var.get(),
            "delay_air_gap_enabled": self.delay_air_gap_enabled_var.get(),
            "post_aspirate_delay_seconds": self.post_aspirate_delay_seconds_var.get(),
            "post_dispense_delay_seconds": self.post_dispense_delay_seconds_var.get(),
            "pre_move_delay_seconds": self.pre_move_delay_seconds_var.get(),
            "air_gap_enabled": self.air_gap_enabled_var.get(),
            "air_gap_volume_ul": self.air_gap_volume_var.get(),
            "air_gap_height_mm": self.air_gap_height_var.get(),
            "air_gap_flow_rate": self.air_gap_flow_rate_var.get(),
        }

    def _apply_deck_template(self, data: Dict[str, object]):
        if not isinstance(data, dict):
            raise ValueError("Deck template must be a JSON object.")
        self.robot_var.set(str(data.get("robot", "Flex") or "Flex"))
        self.api_level_var.set(str(data.get("api_level", "2.21") or "2.21"))
        self.left_pipette_var.set(str(data.get("left_pipette", "flex_1channel_50") or "flex_1channel_50"))
        self.left_tiprack_var.set(str(data.get("left_tiprack", "opentrons_flex_96_filtertiprack_50ul") or "opentrons_flex_96_filtertiprack_50ul"))
        self.left_tiprack_slots_var.set(str(data.get("left_tiprack_slots", "D1") or "D1"))
        self.left_tip_start_column_var.set(str(data.get("left_tip_start_column", "1") or "1"))
        self.left_tip_start_well_var.set(str(data.get("left_tip_start_well", "A1") or "A1"))
        self.right_pipette_var.set(str(data.get("right_pipette", "flex_1channel_1000") or "flex_1channel_1000"))
        self.right_tiprack_var.set(str(data.get("right_tiprack", "opentrons_flex_96_filtertiprack_1000ul") or "opentrons_flex_96_filtertiprack_1000ul"))
        self.right_tiprack_slots_var.set(str(data.get("right_tiprack_slots", "D2") or "D2"))
        self.right_tip_start_column_var.set(str(data.get("right_tip_start_column", "1") or "1"))
        self.right_tip_start_well_var.set(str(data.get("right_tip_start_well", "A1") or "A1"))
        self.trash_slot_var.set(str(data.get("trash_slot", "A3") or "A3"))
        self.flex_gripper_var.set(bool(data.get("flex_gripper", False)))
        self._apply_module_state(data)
        self.source_labware_var.set(str(data.get("source_labware", "nest_96_wellplate_2ml_deep") or "nest_96_wellplate_2ml_deep"))
        self.source_slot_var.set(str(data.get("source_slot", "C1") or "C1"))
        self.source_style_var.set(str(data.get("source_style", "96 well") or "96 well"))
        self.dest_labware_var.set(str(data.get("dest_labware", "corning_96_wellplate_360ul_flat") or "corning_96_wellplate_360ul_flat"))
        self.dest_slot_var.set(str(data.get("dest_slot", "C2") or "C2"))
        self.dest_style_var.set(str(data.get("dest_style", "96 well") or "96 well"))
        configs = data.get("labware_configs")
        if isinstance(configs, list) and configs:
            self.labware_configs = [dict(item) for item in configs if isinstance(item, dict)]
        else:
            self.labware_configs = [
                {"alias": "source1", "role": "source", "load_name": self.source_labware_var.get(), "slot": self.source_slot_var.get(), "map_style": self.source_style_var.get()},
                {"alias": "dest1", "role": "destination", "load_name": self.dest_labware_var.get(), "slot": self.dest_slot_var.get(), "map_style": self.dest_style_var.get()},
            ]
        if self._source_labware_aliases():
            self.source_labware_alias_var.set(self._source_labware_aliases()[0])
        if self._dest_labware_aliases():
            self.dest_labware_alias_var.set(self._dest_labware_aliases()[0])
        self.step_name_var.set(str(data.get("step_name", "") or ""))
        self.chemical_var.set(str(data.get("chemical", "") or ""))
        self.reaction_umol_var.set(str(data.get("reaction_umol", "") or ""))
        self.is_building_block_var.set(coerce_bool(data.get("is_building_block", False)))
        self.tip_policy_var.set(self._normalize_tip_policy(data.get("tip_policy")))
        self.blowout_location_var.set(str(data.get("blowout_location", "No blowout") or "No blowout"))
        self.blowout_labware_alias_var.set(str(data.get("blowout_labware_alias", "") or ""))
        self.blowout_well_var.set(str(data.get("blowout_well", "") or ""))
        self.eight_channel_mode_var.set(str(data.get("eight_channel_mode", "Auto from wells") or "Auto from wells"))
        self.aspirate_rate_var.set(str(data.get("aspirate_rate", "") or ""))
        self.dispense_rate_var.set(str(data.get("dispense_rate", "") or ""))
        self.aspirate_depth_mm_var.set(str(data.get("aspirate_depth_mm", "") or ""))
        self.aspirate_depth_reference_var.set(str(data.get("aspirate_depth_reference", "from bottom") or "from bottom"))
        self.dispense_depth_mm_var.set(str(data.get("dispense_depth_mm", "") or ""))
        self.dispense_depth_reference_var.set(str(data.get("dispense_depth_reference", "from top") or "from top"))
        self.multi_dispense_extra_percent_var.set(str(data.get("multi_dispense_extra_percent", "0") or "0"))
        self.tip_touch_var.set(bool(data.get("tip_touch", False)))
        self.pre_wet_tip_var.set(bool(data.get("pre_wet_tip", False)))
        self.mix_enabled_var.set(bool(data.get("mix_enabled", False)))
        self.mix_timing_var.set(str(data.get("mix_timing", "Before aspirating") or "Before aspirating"))
        self.mix_repetitions_var.set(str(data.get("mix_repetitions", "3") or "3"))
        self.mix_volume_var.set(str(data.get("mix_volume_ul", "") or ""))
        self.post_source_mix_delay_seconds_var.set(str(data.get("post_source_mix_delay_seconds", "") or ""))
        self.mix_aspirate_rate_var.set(str(data.get("mix_aspirate_rate", "") or ""))
        self.mix_dispense_rate_var.set(str(data.get("mix_dispense_rate", "") or ""))
        self.mix_aspirate_depth_mm_var.set(str(data.get("mix_aspirate_depth_mm", "") or ""))
        self.mix_aspirate_depth_reference_var.set(str(data.get("mix_aspirate_depth_reference", "from bottom") or "from bottom"))
        self.mix_dispense_depth_mm_var.set(str(data.get("mix_dispense_depth_mm", "") or ""))
        self.mix_dispense_depth_reference_var.set(str(data.get("mix_dispense_depth_reference", "from bottom") or "from bottom"))
        self.delay_air_gap_enabled_var.set(self._delay_air_gap_feature_enabled(data))
        self.post_aspirate_delay_seconds_var.set(str(data.get("post_aspirate_delay_seconds", "") or ""))
        self.post_dispense_delay_seconds_var.set(str(data.get("post_dispense_delay_seconds", "") or ""))
        self.pre_move_delay_seconds_var.set(str(data.get("pre_move_delay_seconds", "") or ""))
        self.air_gap_enabled_var.set(bool(data.get("air_gap_enabled", False)))
        self.air_gap_volume_var.set(str(data.get("air_gap_volume_ul", "") or ""))
        self.air_gap_height_var.set(str(data.get("air_gap_height_mm", "5") or "5"))
        self.air_gap_flow_rate_var.set(str(data.get("air_gap_flow_rate", "") or ""))
        self._on_strategy_changed()
        self._on_robot_changed()
        self._update_summaries()

    def _save_deck_template(self):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out = filedialog.asksaveasfilename(
            title="Save Opentrons deck template",
            defaultextension=".json",
            initialdir=str(OUTPUT_DIR),
            initialfile="opentrons_deck_template.json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not out:
            return
        Path(out).write_text(json.dumps(self._deck_template_state(), indent=2), encoding="utf-8")
        self.status_var.set(f"Saved deck template {Path(out).name}")

    def _import_deck_template(self):
        path = filedialog.askopenfilename(
            title="Import Opentrons deck template",
            initialdir=str(OUTPUT_DIR if OUTPUT_DIR.exists() else ROOT),
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self._apply_deck_template(data)
        except Exception as exc:
            messagebox.showwarning("Opentrons", f"Could not import deck template:\n{exc}")
            return
        self.status_var.set(f"Imported deck template {Path(path).name}")

    def _field(self, parent, row, col, label, var, *, width=16, combo=None, callback=None, span=1, stretch=True):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=(0 if col == 0 else 12, 6), pady=3)
        if combo is None:
            widget = ttk.Entry(parent, textvariable=var, width=width)
        else:
            widget = ttk.Combobox(parent, textvariable=var, values=combo, width=width, state="normal")
            if callback:
                widget.bind("<<ComboboxSelected>>", lambda _event: callback())
            if var is self.chemical_var:
                self.chemical_combo = widget
                widget.configure(postcommand=self._refresh_compound_choices)
        widget.grid(row=row, column=col + 1, columnspan=span, sticky="ew" if stretch else "w", pady=3)
        return widget

    def _compound_records(self):
        if not callable(self.compound_provider):
            return []
        try:
            records = list(self.compound_provider() or [])
            return [SimpleNamespace(values=record) if isinstance(record, dict) else record for record in records]
        except Exception:
            return []

    @staticmethod
    def _record_chemical_id(values: Dict[str, object]) -> str:
        for key in ("ID", "Chemical ID", "chemical_id", "chemical"):
            value = str(values.get(key, "") or "").strip()
            if value:
                return value
        return ""

    def _compound_choices(self) -> List[str]:
        choices: List[str] = []
        for rec in self._compound_records():
            vals = _record_values(rec)
            cid = self._record_chemical_id(vals)
            name = str(vals.get("Name", "") or "").strip()
            label = cid if not name else f"{cid} - {name}" if cid else name
            if label and label not in choices:
                choices.append(label)
        return choices

    def _refresh_compound_choices(self):
        if hasattr(self, "chemical_combo"):
            self.chemical_combo.configure(values=self._compound_choices())

    def _normalize_selected_compound(self):
        text = self.chemical_var.get().strip()
        if " - " in text:
            self.chemical_var.set(text.split(" - ", 1)[0].strip())

    @staticmethod
    def _record_concentration_m(values: Dict[str, object]) -> Optional[float]:
        for key in ("Conc.", "Concentration (M)", "Concentration M", "concentration_M", "concentration_m", "Concentration"):
            raw = values.get(key)
            if raw in (None, ""):
                continue
            try:
                number = float(raw)
            except (TypeError, ValueError):
                continue
            if math.isfinite(number) and number > 0:
                return number
        return None

    @staticmethod
    def _volume_from_umol_and_conc(umol: object, concentration_m: Optional[float]) -> str:
        if concentration_m is None or not math.isfinite(concentration_m) or concentration_m <= 0:
            return ""
        try:
            amount = float(str(umol or "").strip())
        except (TypeError, ValueError):
            return ""
        if not math.isfinite(amount) or amount <= 0:
            return ""
        volume = amount / concentration_m
        return f"{volume:.6g}" if math.isfinite(volume) and volume > 0 else ""

    def _calculate_dispense_volume_from_umol(self):
        if hasattr(self, "transfer_type_notebook") and self._is_batch_transfer_mode():
            return
        data = self._compound_for_chemical_label(self.chemical_var.get())
        if not data:
            return
        calculated = self._volume_from_umol_and_conc(
            self.reaction_umol_var.get(),
            self._record_concentration_m(data),
        )
        if calculated and calculated != self.volume_var.get().strip():
            self.volume_var.set(calculated)

    def _source_labware_aliases(self) -> List[str]:
        return [item["alias"] for item in self.labware_configs if item.get("role") in {"source", "both"}]

    def _dest_labware_aliases(self) -> List[str]:
        return [item["alias"] for item in self.labware_configs if item.get("role") in {"destination", "both"}]

    def _all_labware_aliases(self) -> List[str]:
        return [item["alias"] for item in self.labware_configs]

    def _labware_by_alias(self, alias: object) -> Optional[Dict[str, str]]:
        wanted = str(alias or "").strip()
        for item in self.labware_configs:
            if item.get("alias") == wanted:
                return item
        return None

    def _selected_source_labware(self) -> Dict[str, str]:
        item = self._labware_by_alias(self.source_labware_alias_var.get())
        if not item or item.get("role") not in {"source", "both"}:
            raise ValueError("Select a valid source labware alias.")
        return item

    def _selected_dest_labware(self) -> Dict[str, str]:
        item = self._labware_by_alias(self.dest_labware_alias_var.get())
        if not item or item.get("role") not in {"destination", "both"}:
            raise ValueError("Select a valid destination labware alias.")
        return item

    def _refresh_labware_alias_combos(self):
        for child in self.winfo_children():
            self._refresh_labware_alias_combo_values(child)

    def _refresh_labware_alias_combo_values(self, widget):
        if isinstance(widget, ttk.Combobox):
            current = widget.cget("textvariable")
            if current == str(self.source_labware_alias_var):
                widget.configure(values=self._source_labware_aliases())
            elif current in {str(self.dest_labware_alias_var), str(self.blowout_labware_alias_var)}:
                widget.configure(values=self._dest_labware_aliases())
            elif current == str(self.move_labware_alias_var):
                widget.configure(values=self._all_labware_aliases())
            elif current in {
                str(self.temperature_module_labware_alias_var),
                str(self.heater_shaker_labware_alias_var),
            }:
                widget.configure(values=self._all_labware_aliases())
        for child in widget.winfo_children():
            self._refresh_labware_alias_combo_values(child)

    def _liquid_parameters_from_form(self) -> Dict[str, object]:
        return {
            "tip_policy": self.tip_policy_var.get(),
            "blowout_location": self.blowout_location_var.get(),
            "blowout_labware_alias": self.blowout_labware_alias_var.get().strip(),
            "blowout_well": self.blowout_well_var.get().strip().upper(),
            "aspirate_rate": self.aspirate_rate_var.get(),
            "dispense_rate": self.dispense_rate_var.get(),
            "aspirate_depth_mm": self.aspirate_depth_mm_var.get(),
            "aspirate_depth_reference": self.aspirate_depth_reference_var.get(),
            "dispense_depth_mm": self.dispense_depth_mm_var.get(),
            "dispense_depth_reference": self.dispense_depth_reference_var.get(),
            "multi_dispense_extra_percent": self.multi_dispense_extra_percent_var.get(),
            "tip_touch": bool(self.tip_touch_var.get()),
            "pre_wet_tip": bool(self.pre_wet_tip_var.get()),
            "mix_enabled": bool(self.mix_enabled_var.get()),
            "mix_timing": self.mix_timing_var.get(),
            "mix_repetitions": self.mix_repetitions_var.get(),
            "mix_volume_ul": self.mix_volume_var.get(),
            "post_source_mix_delay_seconds": self.post_source_mix_delay_seconds_var.get(),
            "mix_aspirate_rate": self.mix_aspirate_rate_var.get(),
            "mix_dispense_rate": self.mix_dispense_rate_var.get(),
            "mix_aspirate_depth_mm": self.mix_aspirate_depth_mm_var.get(),
            "mix_aspirate_depth_reference": self.mix_aspirate_depth_reference_var.get(),
            "mix_dispense_depth_mm": self.mix_dispense_depth_mm_var.get(),
            "mix_dispense_depth_reference": self.mix_dispense_depth_reference_var.get(),
            "delay_air_gap_enabled": bool(self.delay_air_gap_enabled_var.get()),
            "post_aspirate_delay_seconds": self.post_aspirate_delay_seconds_var.get(),
            "post_dispense_delay_seconds": self.post_dispense_delay_seconds_var.get(),
            "pre_move_delay_seconds": self.pre_move_delay_seconds_var.get(),
            "air_gap_enabled": bool(self.air_gap_enabled_var.get()),
            "air_gap_volume_ul": self.air_gap_volume_var.get(),
            "air_gap_height_mm": self.air_gap_height_var.get(),
            "air_gap_flow_rate": self.air_gap_flow_rate_var.get(),
        }

    def _apply_liquid_parameters(self, params: Dict[str, object]):
        self.tip_policy_var.set(self._normalize_tip_policy(params.get("tip_policy")))
        self.blowout_location_var.set(str(params.get("blowout_location", "No blowout") or "No blowout"))
        self.blowout_labware_alias_var.set(str(params.get("blowout_labware_alias", "") or ""))
        self.blowout_well_var.set(str(params.get("blowout_well", "") or ""))
        self.aspirate_rate_var.set(str(params.get("aspirate_rate", "") or ""))
        self.dispense_rate_var.set(str(params.get("dispense_rate", "") or ""))
        self.aspirate_depth_mm_var.set(str(params.get("aspirate_depth_mm", "") or ""))
        self.aspirate_depth_reference_var.set(str(params.get("aspirate_depth_reference", "from bottom") or "from bottom"))
        self.dispense_depth_mm_var.set(str(params.get("dispense_depth_mm", "") or ""))
        self.dispense_depth_reference_var.set(str(params.get("dispense_depth_reference", "from top") or "from top"))
        self.multi_dispense_extra_percent_var.set(str(params.get("multi_dispense_extra_percent", "0") or "0"))
        self.tip_touch_var.set(bool(params.get("tip_touch", False)))
        self.pre_wet_tip_var.set(bool(params.get("pre_wet_tip", False)))
        self.mix_enabled_var.set(bool(params.get("mix_enabled", False)))
        self.mix_timing_var.set(str(params.get("mix_timing", "Before aspirating") or "Before aspirating"))
        self.mix_repetitions_var.set(str(params.get("mix_repetitions", "3") or "3"))
        self.mix_volume_var.set(str(params.get("mix_volume_ul", "") or ""))
        self.post_source_mix_delay_seconds_var.set(str(params.get("post_source_mix_delay_seconds", "") or ""))
        self.mix_aspirate_rate_var.set(str(params.get("mix_aspirate_rate", "") or ""))
        self.mix_dispense_rate_var.set(str(params.get("mix_dispense_rate", "") or ""))
        self.mix_aspirate_depth_mm_var.set(str(params.get("mix_aspirate_depth_mm", "") or ""))
        self.mix_aspirate_depth_reference_var.set(str(params.get("mix_aspirate_depth_reference", "from bottom") or "from bottom"))
        self.mix_dispense_depth_mm_var.set(str(params.get("mix_dispense_depth_mm", "") or ""))
        self.mix_dispense_depth_reference_var.set(str(params.get("mix_dispense_depth_reference", "from bottom") or "from bottom"))
        self.delay_air_gap_enabled_var.set(self._delay_air_gap_feature_enabled(params))
        self.post_aspirate_delay_seconds_var.set(str(params.get("post_aspirate_delay_seconds", "") or ""))
        self.post_dispense_delay_seconds_var.set(str(params.get("post_dispense_delay_seconds", "") or ""))
        self.pre_move_delay_seconds_var.set(str(params.get("pre_move_delay_seconds", "") or ""))
        self.air_gap_enabled_var.set(bool(params.get("air_gap_enabled", False)))
        self.air_gap_volume_var.set(str(params.get("air_gap_volume_ul", "") or ""))
        self.air_gap_height_var.set(str(params.get("air_gap_height_mm", "5") or "5"))
        self.air_gap_flow_rate_var.set(str(params.get("air_gap_flow_rate", "") or ""))
        self._on_strategy_changed()

    def _copy_liquid_parameters(self):
        self._copied_liquid_params = dict(self._liquid_parameters_from_form())
        self.status_var.set("Copied liquid handling parameters.")

    def _paste_liquid_parameters(self):
        if not self._copied_liquid_params:
            messagebox.showwarning("Opentrons", "No liquid handling parameters have been copied yet.")
            return
        self._apply_liquid_parameters(self._copied_liquid_params)
        self.status_var.set("Pasted liquid handling parameters.")

    def _occupied_deck_slots(self, current_var: Optional[tk.StringVar] = None) -> set[str]:
        occupied: set[str] = set()
        for item in self.labware_configs:
            slot = str(item.get("slot", "") or "").strip()
            if slot:
                occupied.add(slot)
        for pipette_var, slots_var in (
            (self.left_pipette_var, self.left_tiprack_slots_var),
            (self.right_pipette_var, self.right_tiprack_slots_var),
        ):
            if pipette_var.get().strip() != "None":
                occupied.update(part.strip() for part in slots_var.get().split(",") if part.strip())
        if self.robot_var.get() == "Flex":
            trash = self.trash_slot_var.get().strip()
            if trash:
                occupied.add(trash)
        for module in self._configured_module_locations():
            if module["slot"]:
                occupied.add(module["slot"])
        if current_var is self.labware_slot_var:
            current_labware = self._labware_by_alias(self.labware_alias_var.get())
            if current_labware:
                occupied.discard(str(current_labware.get("slot", "") or "").strip())
        elif current_var in (self.temperature_module_slot_var, self.heater_shaker_slot_var):
            own_slot = (
                self.temperature_module_slot_var.get().strip()
                if current_var is self.temperature_module_slot_var
                else self.heater_shaker_slot_var.get().strip()
            )
            occupied.discard(own_slot)
            alias_var = (
                self.temperature_module_labware_alias_var
                if current_var is self.temperature_module_slot_var
                else self.heater_shaker_labware_alias_var
            )
            module_labware = self._labware_by_alias(alias_var.get())
            if module_labware:
                occupied.discard(str(module_labware.get("slot", "") or "").strip())
        elif current_var is self.left_tiprack_slots_var or current_var is self.right_tiprack_slots_var:
            occupied.difference_update(part.strip() for part in current_var.get().split(",") if part.strip())
        return occupied

    def _initial_deck_slot_occupants(self) -> Dict[str, str]:
        occupants: Dict[str, str] = {}
        for item in self.labware_configs:
            slot = str(item.get("slot", "") or "").strip()
            alias = str(item.get("alias", "") or "labware").strip() or "labware"
            if slot:
                occupants[slot] = alias
        for mount, pipette_var, slots_var in (
            ("left", self.left_pipette_var, self.left_tiprack_slots_var),
            ("right", self.right_pipette_var, self.right_tiprack_slots_var),
        ):
            if pipette_var.get().strip() == "None":
                continue
            for idx, slot in enumerate([part.strip() for part in slots_var.get().split(",") if part.strip()], start=1):
                occupants[slot] = f"{mount} tiprack {idx}"
        if self.robot_var.get() == "Flex":
            trash = self.trash_slot_var.get().strip()
            if trash:
                occupants[trash] = "trash"
        for module in self._configured_module_locations():
            if module["slot"]:
                occupants[module["slot"]] = module["label"]
        return occupants

    def _configured_module_locations(self) -> List[Dict[str, str]]:
        modules: List[Dict[str, str]] = []
        if self.temperature_module_enabled_var.get():
            slot = self.temperature_module_slot_var.get().strip()
            modules.append({
                "key": "temperature",
                "slot": slot,
                "label": "Temperature Module GEN2",
                "target": f"Temperature Module GEN2 @ {slot}",
            })
        if self.heater_shaker_enabled_var.get():
            slot = self.heater_shaker_slot_var.get().strip()
            modules.append({
                "key": "heater_shaker",
                "slot": slot,
                "label": "Heater-Shaker Module",
                "target": f"Heater-Shaker Module @ {slot}",
            })
        return modules

    _module_key_from_move_target = staticmethod(module_key_from_move_target)

    def _validate_move_target_slot_available(self, move_labware_alias: str, move_to_slot: str):
        module_key = self._module_key_from_move_target(move_to_slot)
        if module_key:
            module = next((item for item in self._configured_module_locations() if item["key"] == module_key), None)
            if module is None:
                raise ValueError("The selected module move target is no longer configured. Select the move location again.")
            adapter_var = self.temperature_module_adapter_var if module_key == "temperature" else self.heater_shaker_adapter_var
            if not adapter_var.get().strip():
                raise ValueError(f"Select an adapter for {module['label']} before moving labware onto it.")
            return
        labware = self._labware_by_alias(move_labware_alias) or {}
        current_slot = str(labware.get("slot", "") or "").strip()
        occupant = self._initial_deck_slot_occupants().get(move_to_slot)
        if occupant and move_to_slot != current_slot:
            raise ValueError(
                f"Move target slot {move_to_slot} is already occupied by {occupant}. "
                "Choose an empty slot or remove/move that labware first."
            )

    def _pick_move_target(self):
        robot = self.robot_var.get() if self.robot_var.get() in ROBOT_OPTIONS else "Flex"
        slots = FLEX_SLOTS if robot == "Flex" else OT2_SLOTS
        slot_grid = FLEX_SLOT_GRID if robot == "Flex" else OT2_SLOT_GRID
        occupied = self._occupied_deck_slots()
        win = tk.Toplevel(self)
        win.title("Select Move Target Location")
        win.transient(self.winfo_toplevel())
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Empty deck slot", font=("", 10, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", padx=6, pady=(0, 4))
        for row_idx, row_slots in enumerate(slot_grid, start=1):
            for col_idx, slot in enumerate(row_slots):
                if slot is None:
                    ttk.Label(frame, text="Fixed trash", style="Muted.TLabel").grid(row=row_idx, column=col_idx, sticky="nsew", padx=6, pady=4)
                    continue
                state = "disabled" if slot in occupied or slot not in slots else "normal"
                ttk.Button(
                    frame,
                    text=slot,
                    command=lambda value=slot: (self.move_to_slot_var.set(value), win.destroy()),
                    state=state,
                ).grid(row=row_idx, column=col_idx, sticky="ew", padx=6, pady=4)
        module_row = len(slot_grid) + 1
        modules = self._configured_module_locations()
        ttk.Label(frame, text="Configured module", font=("", 10, "bold")).grid(row=module_row, column=0, columnspan=3, sticky="w", padx=6, pady=(10, 4))
        if modules:
            for idx, module in enumerate(modules, start=1):
                ttk.Button(
                    frame,
                    text=module["target"],
                    command=lambda value=module["target"]: (self.move_to_slot_var.set(value), win.destroy()),
                ).grid(row=module_row + idx, column=0, columnspan=3, sticky="ew", padx=6, pady=3)
        else:
            ttk.Label(frame, text="No module configured", style="Muted.TLabel").grid(row=module_row + 1, column=0, columnspan=3, sticky="w", padx=6, pady=3)
        for col_idx in range(3):
            frame.columnconfigure(col_idx, weight=1, minsize=110)
        self._center_dialog(win)

    def _pick_deck_slots(self, var: tk.StringVar, *, multi: bool, title: str):
        robot = self.robot_var.get() if self.robot_var.get() in ROBOT_OPTIONS else "Flex"
        if var is self.temperature_module_slot_var:
            slots = self._supported_module_slots(robot, "temperature")
        elif var is self.heater_shaker_slot_var:
            slots = self._supported_module_slots(robot, "heater_shaker")
        else:
            slots = FLEX_SLOTS if robot == "Flex" else OT2_SLOTS
        slot_grid = FLEX_SLOT_GRID if robot == "Flex" else OT2_SLOT_GRID
        selected = {part.strip() for part in var.get().split(",") if part.strip()}
        occupied = self._occupied_deck_slots(var)
        win = tk.Toplevel(self)
        win.title(title)
        win.transient(self.winfo_toplevel())
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text=("Back of deck" if robot == "Flex" else "Back of OT-2 deck"),
            style="Muted.TLabel",
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=6, pady=(0, 4))
        slot_vars: Dict[str, tk.BooleanVar] = {}
        for row_idx, row_slots in enumerate(slot_grid, start=1):
            for col_idx, slot in enumerate(row_slots):
                if slot is None:
                    ttk.Label(frame, text="Fixed trash", style="Muted.TLabel").grid(row=row_idx, column=col_idx, sticky="nsew", padx=6, pady=4)
                    continue
                flag = tk.BooleanVar(value=slot in selected)
                slot_vars[slot] = flag
                state = "disabled" if slot in occupied or slot not in slots else "normal"
                if multi:
                    ttk.Checkbutton(frame, text=slot, variable=flag, state=state).grid(row=row_idx, column=col_idx, sticky="w", padx=6, pady=4)
                else:
                    ttk.Button(frame, text=slot, command=lambda value=slot: (var.set(value), win.destroy()), state=state).grid(row=row_idx, column=col_idx, sticky="ew", padx=6, pady=4)
        for col_idx in range(3):
            frame.columnconfigure(col_idx, weight=1, minsize=96)
        if multi:
            def apply_selection():
                values = [slot for slot in slots if slot_vars[slot].get()]
                var.set(",".join(values))
                win.destroy()

            ttk.Button(frame, text="Apply", command=apply_selection, style="FileAction.TButton").grid(row=len(slot_grid) + 1, column=0, sticky="w", padx=6, pady=(8, 0))
        ttk.Label(frame, text="Front of deck", style="Muted.TLabel").grid(row=len(slot_grid) + 2, column=0, columnspan=3, sticky="w", padx=6, pady=(6, 0))
        self._center_dialog(win)

    def _refresh_labware_tree(self):
        tree = getattr(self, "labware_tree", None)
        if tree is None:
            return
        tree.delete(*tree.get_children())
        for idx, item in enumerate(self.labware_configs):
            tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(item.get("alias", ""), item.get("role", ""), item.get("load_name", ""), item.get("slot", ""), item.get("map_style", "")),
            )

    def _auto_update_labware_map_style(self):
        map_style = _default_labware_map_style(self.labware_load_name_var.get())
        if map_style is not None:
            self.labware_map_style_var.set(map_style)

    def _add_update_labware_config(self):
        alias = self.labware_alias_var.get().strip()
        role = self.labware_role_var.get().strip()
        load_name = self.labware_load_name_var.get().strip()
        slot = self.labware_slot_var.get().strip()
        map_style = self.labware_map_style_var.get().strip()
        robot = self.robot_var.get() if self.robot_var.get() in ROBOT_OPTIONS else "Flex"
        slots = FLEX_SLOTS if robot == "Flex" else OT2_SLOTS
        if not alias:
            messagebox.showwarning("Opentrons labware", "Alias is required.")
            return
        if role not in LABWARE_ROLES:
            messagebox.showwarning("Opentrons labware", "Role must be source, destination, or both.")
            return
        if not load_name:
            messagebox.showwarning("Opentrons labware", "Load name is required.")
            return
        if slot not in slots:
            messagebox.showwarning("Opentrons labware", f"Slot {slot} is not valid for {robot}.")
            return
        if map_style not in PLATE_STYLES:
            messagebox.showwarning("Opentrons labware", "Map style is required.")
            return
        entry = {"alias": alias, "role": role, "load_name": load_name, "slot": slot, "map_style": map_style}
        for idx, item in enumerate(self.labware_configs):
            if item.get("alias") == alias:
                self.labware_configs[idx] = entry
                break
        else:
            self.labware_configs.append(entry)
        source_aliases = self._source_labware_aliases()
        dest_aliases = self._dest_labware_aliases()
        if self.source_labware_alias_var.get() not in source_aliases:
            self.source_labware_alias_var.set(alias if role in {"source", "both"} else (source_aliases[0] if source_aliases else ""))
        if self.dest_labware_alias_var.get() not in dest_aliases:
            self.dest_labware_alias_var.set(alias if role in {"destination", "both"} else (dest_aliases[0] if dest_aliases else ""))
        self._sync_legacy_labware_vars()
        self._refresh_labware_tree()
        self._refresh_labware_alias_combos()
        self._update_summaries()

    def _remove_selected_labware_config(self):
        tree = getattr(self, "labware_tree", None)
        if tree is None or not tree.selection():
            messagebox.showwarning("Opentrons labware", "Select a labware row first.")
            return
        for iid in sorted(tree.selection(), key=lambda value: int(value), reverse=True):
            del self.labware_configs[int(iid)]
        if self.source_labware_alias_var.get() not in self._source_labware_aliases() and self._source_labware_aliases():
            self.source_labware_alias_var.set(self._source_labware_aliases()[0])
        if self.dest_labware_alias_var.get() not in self._dest_labware_aliases() and self._dest_labware_aliases():
            self.dest_labware_alias_var.set(self._dest_labware_aliases()[0])
        for alias_var in (self.temperature_module_labware_alias_var, self.heater_shaker_labware_alias_var):
            if alias_var.get() not in self._all_labware_aliases():
                alias_var.set("")
        self._sync_legacy_labware_vars()
        self._refresh_labware_tree()
        self._refresh_labware_alias_combos()
        self._update_summaries()

    def _on_labware_config_select(self, _event=None):
        tree = getattr(self, "labware_tree", None)
        if tree is None or not tree.selection():
            return
        try:
            item = self.labware_configs[int(tree.selection()[0])]
        except Exception:
            return
        self.labware_alias_var.set(item.get("alias", ""))
        self.labware_role_var.set(item.get("role", "source"))
        self.labware_load_name_var.set(item.get("load_name", ""))
        self.labware_slot_var.set(item.get("slot", ""))
        self.labware_map_style_var.set(item.get("map_style", "96 well"))

    def _sync_legacy_labware_vars(self):
        source = self._labware_by_alias(self.source_labware_alias_var.get()) or next((item for item in self.labware_configs if item.get("role") in {"source", "both"}), None)
        dest = self._labware_by_alias(self.dest_labware_alias_var.get()) or next((item for item in self.labware_configs if item.get("role") in {"destination", "both"}), None)
        if source:
            self.source_labware_var.set(source.get("load_name", self.source_labware_var.get()))
            self.source_slot_var.set(source.get("slot", self.source_slot_var.get()))
            self.source_style_var.set(source.get("map_style", self.source_style_var.get()))
        if dest:
            self.dest_labware_var.set(dest.get("load_name", self.dest_labware_var.get()))
            self.dest_slot_var.set(dest.get("slot", self.dest_slot_var.get()))
            self.dest_style_var.set(dest.get("map_style", self.dest_style_var.get()))

    def _center_dialog(self, win):
        win.update_idletasks()
        parent = self.winfo_toplevel()
        x = parent.winfo_rootx() + max(40, (parent.winfo_width() - win.winfo_width()) // 2)
        y = parent.winfo_rooty() + max(40, (parent.winfo_height() - win.winfo_height()) // 3)
        win.geometry(f"+{x}+{y}")

    def _wire_summary_updates(self):
        vars_to_watch = (
            self.robot_var,
            self.api_level_var,
            self.left_pipette_var,
            self.left_tiprack_var,
            self.left_tiprack_slots_var,
            self.left_tip_start_column_var,
            self.left_tip_start_well_var,
            self.right_pipette_var,
            self.right_tiprack_var,
            self.right_tiprack_slots_var,
            self.right_tip_start_column_var,
            self.right_tip_start_well_var,
            self.trash_slot_var,
            self.flex_gripper_var,
            self.temperature_module_enabled_var,
            self.temperature_module_slot_var,
            self.temperature_module_labware_alias_var,
            self.temperature_module_adapter_var,
            self.temperature_module_target_var,
            self.temperature_module_wait_var,
            self.temperature_module_deactivate_var,
            self.heater_shaker_enabled_var,
            self.heater_shaker_slot_var,
            self.heater_shaker_labware_alias_var,
            self.heater_shaker_adapter_var,
            self.heater_shaker_temperature_var,
            self.heater_shaker_speed_var,
            self.heater_shaker_duration_var,
            self.heater_shaker_wait_var,
            self.heater_shaker_deactivate_var,
            self.source_labware_var,
            self.source_slot_var,
            self.source_style_var,
            self.dest_labware_var,
            self.dest_slot_var,
            self.dest_style_var,
            self.tip_policy_var,
            self.blowout_location_var,
            self.blowout_labware_alias_var,
            self.blowout_well_var,
            self.eight_channel_mode_var,
            self.aspirate_rate_var,
            self.dispense_rate_var,
            self.aspirate_depth_mm_var,
            self.aspirate_depth_reference_var,
            self.dispense_depth_mm_var,
            self.dispense_depth_reference_var,
            self.multi_dispense_extra_percent_var,
            self.tip_touch_var,
            self.pre_wet_tip_var,
            self.mix_enabled_var,
            self.mix_timing_var,
            self.mix_repetitions_var,
            self.mix_volume_var,
            self.post_source_mix_delay_seconds_var,
            self.mix_aspirate_rate_var,
            self.mix_dispense_rate_var,
            self.mix_aspirate_depth_mm_var,
            self.mix_aspirate_depth_reference_var,
            self.mix_dispense_depth_mm_var,
            self.mix_dispense_depth_reference_var,
            self.delay_air_gap_enabled_var,
            self.post_aspirate_delay_seconds_var,
            self.post_dispense_delay_seconds_var,
            self.pre_move_delay_seconds_var,
            self.air_gap_enabled_var,
            self.air_gap_volume_var,
            self.air_gap_height_var,
            self.air_gap_flow_rate_var,
        )
        for var in vars_to_watch:
            var.trace_add("write", lambda *_args: self._update_summaries())

    def _update_summaries(self):
        if not hasattr(self, "pipette_summary_var"):
            return
        left = self.left_pipette_var.get().strip() or "left not set"
        right = self.right_pipette_var.get().strip() or "right not set"
        left_summary = "not mounted" if left == "None" else f"{self._short_summary_text(left)} {self.left_tiprack_slots_var.get() or 'no tips'}"
        right_summary = "not mounted" if right == "None" else f"{self._short_summary_text(right)} {self.right_tiprack_slots_var.get() or 'no tips'}"
        self.pipette_summary_var.set(
            f"{self.robot_var.get()} API {self.api_level_var.get()} | "
            f"L {left_summary} | R {right_summary}"
            + (" | gripper" if self.robot_var.get() == "Flex" and self.flex_gripper_var.get() else "")
        )
        source_count = len(self._source_labware_aliases())
        dest_count = len(self._dest_labware_aliases())
        labware_bits = [f"{item.get('alias')} {item.get('slot')}" for item in self.labware_configs[:3]]
        suffix = "..." if len(self.labware_configs) > 3 else ""
        self.labware_summary_var.set(
            f"{source_count} source, {dest_count} destination | " + ", ".join(labware_bits) + suffix
        )
        if hasattr(self, "tip_location_summary_var"):
            self.tip_location_summary_var.set(
                f"L col {self.left_tip_start_column_var.get() or '1'}, {self.left_tip_start_well_var.get() or 'A1'} | "
                f"R col {self.right_tip_start_column_var.get() or '1'}, {self.right_tip_start_well_var.get() or 'A1'}"
            )
        module_bits = []
        if self.temperature_module_enabled_var.get():
            module_bits.append(
                f"Temperature {self.temperature_module_slot_var.get() or 'no slot'} "
                f"{self.temperature_module_target_var.get() or '?'} °C "
                f"{self.temperature_module_labware_alias_var.get() or 'empty start'}"
            )
        if self.heater_shaker_enabled_var.get():
            shake = self.heater_shaker_speed_var.get().strip()
            duration = self.heater_shaker_duration_var.get().strip()
            shake_text = f", {shake} rpm/{duration or '?'} min" if shake else ""
            module_bits.append(
                f"Heater-Shaker {self.heater_shaker_slot_var.get() or 'no slot'} "
                f"{self.heater_shaker_temperature_var.get() or 'no heat'} °C{shake_text} "
                f"{self.heater_shaker_labware_alias_var.get() or 'empty start'}"
            )
        if not module_bits:
            self.module_summary_var.set("No module configured")
        else:
            self.module_summary_var.set(" | ".join(module_bits))
        asp = self.aspirate_rate_var.get().strip() or "default"
        disp = self.dispense_rate_var.get().strip() or "default"
        asp_depth = self._format_depth_summary(self.aspirate_depth_mm_var.get(), self.aspirate_depth_reference_var.get())
        disp_depth = self._format_depth_summary(self.dispense_depth_mm_var.get(), self.dispense_depth_reference_var.get())
        extra_percent = self.multi_dispense_extra_percent_var.get().strip().rstrip("%").strip() or "0"
        touch = "tip touch on" if self.tip_touch_var.get() else "tip touch off"
        pre_wet = "pre-wet on" if self.pre_wet_tip_var.get() else "pre-wet off"
        if self.mix_enabled_var.get():
            mix = (
                f"mix {self.mix_timing_var.get().lower()}, {self.mix_repetitions_var.get() or '?'} x "
                f"{self.mix_volume_var.get() or '?'} uL"
            )
            post_source_mix_delay = self.post_source_mix_delay_seconds_var.get().strip()
            if (
                self.mix_timing_var.get() in {"Before aspirating", "Before and after"}
                and post_source_mix_delay
                and post_source_mix_delay not in {"0", "0.0"}
            ):
                mix += f", source wait {post_source_mix_delay}s"
        else:
            mix = "mix off"
        delay_air_bits = []
        aspirate_delay = self.post_aspirate_delay_seconds_var.get().strip()
        dispense_delay = self.post_dispense_delay_seconds_var.get().strip()
        pre_move_delay = self.pre_move_delay_seconds_var.get().strip()
        if self.delay_air_gap_enabled_var.get():
            if aspirate_delay and aspirate_delay not in {"0", "0.0"}:
                delay_air_bits.append(f"asp wait {aspirate_delay}s")
            if dispense_delay and dispense_delay not in {"0", "0.0"}:
                delay_air_bits.append(f"disp wait {dispense_delay}s")
            if pre_move_delay and pre_move_delay not in {"0", "0.0"}:
                delay_air_bits.append(f"move wait {pre_move_delay}s")
            if self.air_gap_enabled_var.get():
                delay_air_bits.append(
                    f"air gap {self.air_gap_volume_var.get().strip() or '?'} uL"
                )
        delay_air_summary = (
            " | ".join(delay_air_bits)
            if delay_air_bits
            else ("Enabled; no delay or air gap configured" if self.delay_air_gap_enabled_var.get() else "Delay / air gap off")
        )
        self.delay_air_gap_summary_var.set(delay_air_summary)
        extra = f" | Flex trash {self.trash_slot_var.get()}" if self.robot_var.get() == "Flex" else ""
        self.motion_summary_var.set(
            f"{self.tip_policy_var.get()} | 8-channel {self.eight_channel_mode_var.get()} | "
            f"aspirate {asp}, {asp_depth} | dispense {disp}, {disp_depth} | extra aspirate {extra_percent}% | "
            f"{touch} | {pre_wet} | {mix} | {delay_air_summary}{extra}"
        )

    @staticmethod
    def _format_depth_summary(mm_value: object, reference: object) -> str:
        text = str(mm_value or "").strip()
        if not text:
            return "default depth"
        return f"{text} mm {reference or 'from bottom'}"

    @staticmethod
    def _short_summary_text(value: object, max_chars: int = 18) -> str:
        text = str(value or "").strip()
        return text if len(text) <= max_chars else f"{text[:max_chars - 3]}..."

    _normalize_tip_policy = staticmethod(normalize_tip_policy)

    _delay_air_gap_feature_enabled = staticmethod(delay_air_gap_feature_enabled)

    @staticmethod
    def _row_is_batch(row: Dict[str, object]) -> bool:
        return str(row.get("batch_transfer_kind", "") or "").strip() in {"individual", "8-channel"}

    def _is_batch_transfer_mode(self) -> bool:
        notebook = getattr(self, "transfer_type_notebook", None)
        return bool(
            notebook is not None
            and notebook.select() == str(self.batch_transfer_type_tab)
        )

    def _set_transfer_type(self, batch: bool):
        notebook = getattr(self, "transfer_type_notebook", None)
        if notebook is None:
            return
        target = self.batch_transfer_type_tab if batch else self.single_transfer_type_tab
        if notebook.select() == str(target):
            self._update_transfer_type_controls()
            return
        self._changing_transfer_type = True
        try:
            notebook.select(target)
        finally:
            self._changing_transfer_type = False
        self._update_transfer_type_controls()

    def _selected_is_batch(self) -> bool:
        idx = self._selected_row_index() if hasattr(self, "tree") else None
        return idx is not None and self._row_is_batch(self.rows[idx])

    @staticmethod
    def _interactive_descendants(parent) -> List[tk.Widget]:
        widgets: List[tk.Widget] = []
        for child in parent.winfo_children():
            try:
                if "state" in child.keys():
                    widgets.append(child)
            except (AttributeError, tk.TclError):
                pass
            widgets.extend(OpentronsFrame._interactive_descendants(child))
        return widgets

    def _set_row_editor_enabled(self, enabled: bool):
        self._row_editor_enabled = bool(enabled)
        state = "normal" if enabled else "disabled"
        for panel in getattr(self, "_row_editor_panels", ()):
            for widget in self._interactive_descendants(panel):
                try:
                    widget.configure(state=state)
                except tk.TclError:
                    continue
        if hasattr(self, "move_to_slot_entry"):
            self.move_to_slot_entry.configure(state="readonly" if enabled else "disabled")
        selected = bool(self._selected_row_indices()) if hasattr(self, "tree") else False
        if hasattr(self, "remove_row_button"):
            self.remove_row_button.configure(state="normal" if selected else "disabled")
        if hasattr(self, "push_cheminformatics_button"):
            self.push_cheminformatics_button.configure(state="normal" if self.rows else "disabled")
        self._update_transfer_type_controls()
        if enabled:
            self._update_mix_button_state()
            self._update_delay_air_gap_button_state()

    def _update_transfer_type_controls(self):
        if not hasattr(self, "chemical_combo"):
            return
        batch = self._is_batch_transfer_mode()
        selected_idx = self._selected_row_index() if hasattr(self, "tree") else None
        editor_enabled = bool(
            getattr(self, "_row_editor_enabled", False)
            and selected_idx is not None
            and 0 <= selected_idx < len(self.rows)
        )
        state = "normal" if editor_enabled else "disabled"
        self.reaction_umol_entry.configure(state="disabled" if batch or not editor_enabled else "normal")
        self.volume_entry.configure(state="disabled" if batch or not editor_enabled else "normal")
        self.source_well_entry.configure(state="readonly" if batch and editor_enabled else state)
        self.dest_wells_entry.configure(state="readonly" if batch and editor_enabled else state)
        self.source_labware_combo.configure(state="disabled" if batch or not editor_enabled else "normal")
        self.dest_labware_combo.configure(state="disabled" if batch or not editor_enabled else "normal")
        map_style = "RowAction.TButton" if batch and editor_enabled else "TButton"
        self.source_map_button.configure(state=state, style=map_style)
        self.dest_map_button.configure(state=state, style=map_style)
        if batch:
            self.chemical_field_label.configure(text="Chemical IDs")
            self.chemical_combo.grid_remove()
            self.show_structure_check.grid_remove()
            self.building_block_check.grid_remove()
            self.batch_chemical_summary_button.grid()
            self.batch_chemical_summary_button.configure(state=state)
        else:
            self.chemical_field_label.configure(text="Chemical ID")
            self.batch_chemical_summary_button.grid_remove()
            self.chemical_combo.grid()
            self.show_structure_check.grid()
            self.building_block_check.grid()
            self.chemical_combo.configure(state=state)
            self.show_structure_check.configure(state=state)
            self.building_block_check.configure(state=state)
        if batch:
            self.show_structure_var.set(False)

    def _on_transfer_type_changed(self, _event=None):
        if self._changing_transfer_type or not hasattr(self, "tree"):
            return
        idx = self._selected_row_index()
        if idx is not None and self._row_is_batch(self.rows[idx]) != self._is_batch_transfer_mode():
            self._start_new_transfer(announce=False)
        self._update_transfer_type_controls()
        if self._is_batch_transfer_mode():
            self.transfer_mode_status_var.set(
                "Batch mode: click Map to assign sources, Chemical IDs, volumes, and destinations."
            )
        else:
            self._calculate_dispense_volume_from_umol()

    def _edit_selected_transfer(self):
        """Backward-compatible activation helper; row selection now always edits."""
        idx = self._selected_row_index()
        if idx is None:
            messagebox.showwarning("Opentrons", "Select a transfer plan row first.")
            return
        self._on_transfer_row_select()

    def _on_robot_changed(self, reset_api=True):
        robot = self.robot_var.get() if self.robot_var.get() in ROBOT_OPTIONS else "Flex"
        slots = FLEX_SLOTS if robot == "Flex" else OT2_SLOTS
        for var in (self.source_slot_var, self.dest_slot_var, self.left_tiprack_slots_var, self.right_tiprack_slots_var):
            if var.get().strip() not in slots:
                var.set(slots[0])
        for kind, slot_var, flex_default, ot2_default in (
            ("temperature", self.temperature_module_slot_var, "C3", "3"),
            ("heater_shaker", self.heater_shaker_slot_var, "B3", "1"),
        ):
            module_slots = self._supported_module_slots(robot, kind)
            if slot_var.get().strip() not in module_slots:
                preferred = flex_default if robot == "Flex" else ot2_default
                slot_var.set(preferred if preferred in module_slots else module_slots[0])
        defaults = DEFAULT_PIPETTE_BY_ROBOT[robot]
        for mount, pipette_var, tiprack_var in (
            ("left", self.left_pipette_var, self.left_tiprack_var),
            ("right", self.right_pipette_var, self.right_tiprack_var),
        ):
            if pipette_var.get() not in PIPETTE_OPTIONS[robot]:
                pipette_var.set(defaults[mount])
            if tiprack_var.get() not in TIPRACK_OPTIONS[robot]:
                tiprack_var.set(DEFAULT_TIPRACK_BY_PIPETTE.get(pipette_var.get(), TIPRACK_OPTIONS[robot][0]))
        if reset_api:
            self.api_level_var.set("2.21" if robot == "Flex" else "2.15")
        for child in self.winfo_children():
            self._refresh_combo_values(child, robot)
        self._refresh_labware_alias_combos()
        self._update_summaries()

    def _on_pipette_changed(self, mount=None):
        robot = self.robot_var.get() if self.robot_var.get() in ROBOT_OPTIONS else "Flex"
        for side, pipette_var, tiprack_var in (
            ("left", self.left_pipette_var, self.left_tiprack_var),
            ("right", self.right_pipette_var, self.right_tiprack_var),
        ):
            if mount is not None and side != mount:
                continue
            pipette = pipette_var.get().strip()
            # A compatible explicit rack choice survives pipette re-selection.
            rack = tiprack_var.get().strip()
            allowed = PIPETTE_TIPRACK_CAPACITIES.get(
                pipette,
                (200, 300) if pipette.startswith("p300_") else (PIPETTE_MAX_UL.get(pipette),),
            )
            capacity = _tiprack_capacity(rack)
            compatible = rack in TIPRACK_OPTIONS[robot] and capacity in allowed
            if pipette in {"", "None"} or compatible:
                continue
            default_tiprack = DEFAULT_TIPRACK_BY_PIPETTE.get(pipette)
            if default_tiprack and default_tiprack in TIPRACK_OPTIONS[robot]:
                tiprack_var.set(default_tiprack)

    def _refresh_combo_values(self, widget, robot: str):
        if isinstance(widget, ttk.Combobox):
            current = widget.cget("textvariable")
            if current in {str(self.left_pipette_var), str(self.right_pipette_var)}:
                widget.configure(values=PIPETTE_OPTIONS[robot])
            elif current in {str(self.left_tiprack_var), str(self.right_tiprack_var)}:
                widget.configure(values=TIPRACK_OPTIONS[robot])
            elif current in {
                str(self.source_slot_var),
                str(self.dest_slot_var),
                str(self.labware_slot_var),
                str(self.left_tiprack_slots_var),
                str(self.right_tiprack_slots_var),
            }:
                widget.configure(values=FLEX_SLOTS if robot == "Flex" else OT2_SLOTS)
            elif current == str(self.temperature_module_slot_var):
                widget.configure(values=self._supported_module_slots(robot, "temperature"))
            elif current == str(self.heater_shaker_slot_var):
                widget.configure(values=self._supported_module_slots(robot, "heater_shaker"))
            elif current == str(self.temperature_module_adapter_var):
                widget.configure(values=TEMPERATURE_MODULE_ADAPTERS)
            elif current == str(self.heater_shaker_adapter_var):
                widget.configure(values=HEATER_SHAKER_ADAPTERS)
            elif current == str(self.trash_slot_var):
                widget.configure(values=FLEX_SLOTS)
        for child in widget.winfo_children():
            self._refresh_combo_values(child, robot)

    def _physical_source_wells_for_row(self, row: Dict[str, object]) -> List[str]:
        """Resolve ordinary rows with the same capacity/nozzle rules as export.

        Incomplete drafts still reserve their entered anchor; final protocol
        compilation validates them before any commands can be exported.
        """
        anchor = str(row.get("source_well", "") or "").strip().upper()
        fallback = [anchor] if anchor else []
        if not row.get("dest_wells") or not row.get("volume_ul"):
            return fallback
        if "robot_var" not in self.__dict__:
            return fallback
        source = self._labware_by_alias(row.get("source_labware_alias", "source1"))
        destination = self._labware_by_alias(row.get("dest_labware_alias", "dest1"))
        if not source or not destination:
            return fallback
        volume = required_positive_float(row["volume_ul"], "Transfer volume")
        extra = optional_nonnegative_float(row.get("multi_dispense_extra_percent", "0"), "Extra aspirate percentage")
        mix_volume = (optional_positive_float(row.get("mix_volume_ul", ""), "Mix volume") or 0.0) if row.get("mix_enabled") else 0.0
        air_volume = 0.0
        if delay_air_gap_feature_enabled(row) and row.get("air_gap_enabled"):
            air_volume = optional_positive_float(row.get("air_gap_volume_ul", ""), "Air-gap volume") or 0.0
        needed = minimum_pipette_volume(volume, row.get("strategy"), extra, air_volume, mix_volume)
        pipettes = self._configured_pipettes()
        mount = select_pipette_for_row(pipettes, str(row.get("pipette_key", "Auto")), needed)
        layout = self._nozzle_layout_for_row(
            self.robot_var.get(), str(pipettes[mount]["name"]),
            _parse_wells(str(row["dest_wells"]), destination["map_style"]), destination["map_style"],
        )
        if layout == "all":
            return all_channel_source_wells(anchor, source["map_style"], source["load_name"])
        return fallback

    def _source_well_availability(
        self,
        labware_alias: object,
        chemical_id: object,
        *,
        exclude_row_index: Optional[int] = None,
    ) -> Tuple[Set[str], Set[str]]:
        wanted_alias = str(labware_alias or "").strip()
        usages: List[Tuple[str, str]] = []
        for row_index, row in enumerate(self.rows):
            if row_index == exclude_row_index:
                continue
            if str(row.get("source_labware_alias", "") or "").strip() != wanted_alias:
                continue
            if self._row_is_batch(row):
                batch_labels = {
                    value.strip().upper()
                    for value in str(row.get("batch_source_wells", "") or "").split(",")
                    if value.strip()
                }
                if batch_labels:
                    chemical_map = {
                        str(key).strip().upper(): str(value or "").strip()
                        for key, value in dict(row.get("batch_source_chemicals", {}) or {}).items()
                    }
                    usages.extend(
                        (label, chemical_map.get(label, str(row.get("chemical", "") or "")))
                        for label in batch_labels
                    )
                    continue
            try:
                labels = self._physical_source_wells_for_row(row)
            except ValueError:
                labels = [str(row.get("source_well", "") or "").strip().upper()]
            usages.extend((label, str(row.get("chemical", "") or "")) for label in labels if label)
        return tecan_frame.classify_source_well_usage(usages, chemical_id)

    def _source_well_chemical_assignments(
        self,
        labware_alias: object,
        *,
        exclude_row_index: Optional[int] = None,
    ) -> Dict[str, str]:
        """Return only unambiguous, nonblank Chemical IDs for physical source wells."""
        wanted_alias = str(labware_alias or "").strip()
        chemicals_by_label: Dict[str, Dict[str, str]] = {}

        def remember(label: object, chemical_id: object):
            normalized_label = str(label or "").strip().upper()
            chemical = str(chemical_id or "").strip()
            if not normalized_label:
                return
            chemicals_by_label.setdefault(normalized_label, {}).setdefault(
                chemical.casefold(), chemical
            )

        for row_index, row in enumerate(self.rows):
            if row_index == exclude_row_index:
                continue
            if str(row.get("source_labware_alias", "") or "").strip() != wanted_alias:
                continue
            if self._row_is_batch(row):
                batch_labels = [
                    value.strip().upper()
                    for value in str(row.get("batch_source_wells", "") or "").split(",")
                    if value.strip()
                ]
                if batch_labels:
                    chemical_map = self._batch_chemical_map(row)
                    fallback = str(row.get("chemical", "") or "").strip()
                    for label in batch_labels:
                        remember(label, chemical_map.get(label, fallback))
                    continue
            try:
                labels = self._physical_source_wells_for_row(row)
            except ValueError:
                labels = [row.get("source_well", "")]
            for label in labels:
                remember(label, row.get("chemical", ""))

        assignments: Dict[str, str] = {}
        for label, chemicals in chemicals_by_label.items():
            if len(chemicals) != 1 or "" in chemicals:
                continue
            assignments[label] = next(iter(chemicals.values()))
        return assignments

    def _source_well_conflict(
        self,
        labware_alias: object,
        source_well: object,
        chemical_id: object,
        *,
        exclude_row_index: Optional[int] = None,
    ) -> str:
        blocked, _reusable = self._source_well_availability(
            labware_alias,
            chemical_id,
            exclude_row_index=exclude_row_index,
        )
        label = str(source_well or "").strip().upper()
        if label in blocked:
            return (
                f"Source well {label} in {labware_alias} is already assigned to another Chemical ID. "
                "Choose another source well or use the same Chemical ID."
            )
        return ""

    def _used_destination_wells(
        self,
        labware_alias: object,
        *,
        exclude_row_index: Optional[int] = None,
    ) -> Set[str]:
        """Return physical destination wells already referenced on one labware."""
        wanted_alias = str(labware_alias or "").strip()
        used: Set[str] = set()
        labware = self._labware_by_alias(wanted_alias) or {}
        map_style = str(labware.get("map_style", self.dest_style_var.get()))
        for row_index, row in enumerate(self.rows):
            if row_index == exclude_row_index:
                continue
            if str(row.get("dest_labware_alias", "") or "").strip() != wanted_alias:
                continue
            if self._row_is_batch(row):
                groups = self._batch_destination_groups(row)
                if groups:
                    used.update(well for group in groups for well in group)
                    continue
            try:
                used.update(_parse_wells(str(row.get("dest_wells", "") or ""), map_style))
            except (TypeError, ValueError):
                used.update(
                    value.strip().upper()
                    for value in str(row.get("dest_wells", "") or "").split(",")
                    if value.strip()
                )
        return used

    def _pick_dest_wells(self):
        if self._is_batch_transfer_mode():
            self._open_batch_mapping()
            return
        try:
            dest_labware = self._selected_dest_labware()
            map_style = dest_labware.get("map_style", self.dest_style_var.get())
            dest_alias = dest_labware.get("alias", self.dest_labware_alias_var.get())
        except ValueError:
            map_style = self.dest_style_var.get()
            dest_alias = self.dest_labware_alias_var.get()
        rows, cols = _style_dims(map_style)
        used_wells = self._used_destination_wells(
            dest_alias,
            exclude_row_index=self._selected_row_index(),
        )
        dlg = well_map.WellMapDialog(
            self,
            rows,
            cols,
            self.dest_wells_var.get(),
            vertical_view=False,
            anchor=self,
            highlight_labels=used_wells,
            highlight_hint="Light blue destination wells are used by another transfer and remain reusable.",
            disabled_labels=_style_disabled_labels(map_style),
            disabled_hint="Gray positions do not exist in this labware.",
        )
        self.wait_window(dlg)
        if getattr(dlg, "result_labels", ""):
            self.dest_wells_var.set(dlg.result_labels)

    def _pick_source_well(self):
        if self._is_batch_transfer_mode():
            self._open_batch_mapping()
            return
        try:
            source_labware = self._selected_source_labware()
            map_style = source_labware.get("map_style", self.source_style_var.get())
            labware_alias = source_labware.get("alias", self.source_labware_alias_var.get())
        except ValueError:
            map_style = self.source_style_var.get()
            labware_alias = self.source_labware_alias_var.get()
        rows, cols = _style_dims(map_style)
        current_chemical = self._chemical_id_from_label(self.chemical_var.get())
        remembered_chemicals = self._source_well_chemical_assignments(
            labware_alias,
            exclude_row_index=self._selected_row_index(),
        )
        blocked, reusable = self._source_well_availability(
            labware_alias,
            current_chemical,
            exclude_row_index=self._selected_row_index(),
        )
        if not current_chemical:
            auto_reusable = set(remembered_chemicals)
            blocked.difference_update(auto_reusable)
            reusable.update(auto_reusable)
        blocked.update(_style_disabled_labels(map_style))
        dlg = well_map.WellMapDialog(
            self,
            rows,
            cols,
            self.source_well_var.get(),
            vertical_view=False,
            anchor=self,
            single_select=True,
            highlight_labels=reusable,
            disabled_labels=blocked,
            highlight_hint="Light blue source wells already use this Chemical ID and can be reused.",
            disabled_hint="Gray source wells are unavailable or assigned to another Chemical ID.",
        )
        dlg.title("Select Source Well")
        self.wait_window(dlg)
        if getattr(dlg, "result_labels", ""):
            selected_well = str(dlg.result_labels).strip().upper()
            self.source_well_var.set(selected_well)
            remembered = remembered_chemicals.get(selected_well, "")
            if remembered and (
                not current_chemical or current_chemical.casefold() == remembered.casefold()
            ):
                self.chemical_var.set(remembered)

    def _open_batch_mapping(self) -> bool:
        """Atomically update the mapping of the selected batch row."""
        edit_index = self._selected_row_index()
        if (
            edit_index is None
            or not (0 <= edit_index < len(self.rows))
            or not self._row_is_batch(self.rows[edit_index])
        ):
            messagebox.showwarning("Batch Transfer", "Create or select a batch row before opening Map.")
            return False
        saved = self._open_batch_transfer(edit_index=edit_index)
        if saved:
            self._editing_transfer_row_index = edit_index
            self.transfer_mode_status_var.set(
                f"Editing batch row {edit_index + 1}: common settings save automatically; Map updates mappings atomically."
            )
            self._update_transfer_type_controls()
        return saved

    def _configured_batch_8_channel_mount(self, selected: Optional[str] = None) -> str:
        robot = self.robot_var.get() if self.robot_var.get() in ROBOT_OPTIONS else "Flex"
        configured = {
            "left": self.left_pipette_var.get().strip(),
            "right": self.right_pipette_var.get().strip(),
        }
        if robot == "Flex":
            candidates = [mount for mount, name in configured.items() if name.startswith("flex_8channel")]
        else:
            candidates = [mount for mount, name in configured.items() if name.endswith("_multi_gen2")]
        requested = str(self.row_pipette_var.get() if selected is None else selected).strip() or "Auto"
        if requested in ("left", "right"):
            if requested in candidates:
                return requested
            raise ValueError(
                f"The selected {requested} pipette is not an 8-channel pipette configured for {robot}. "
                "Choose Auto or select a configured 8-channel mount."
            )
        if not candidates:
            raise ValueError(f"Configure an 8-channel pipette for {robot} before adding an 8-channel batch transfer.")
        return candidates[0]

    def _batch_kind_step(self, initial_kind: str) -> Tuple[str, str]:
        result = {"action": "cancel"}
        win = tk.Toplevel(self)
        win.title("Batch Transfer — Transfer Type")
        win.transient(self.winfo_toplevel())
        win.grab_set()
        win.resizable(False, False)
        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        kind_var = tk.StringVar(value=initial_kind if initial_kind in {"individual", "8-channel"} else "individual")
        ttk.Label(body, text="Choose the batch execution method", font=("", 10, "bold")).pack(anchor="w")
        ttk.Radiobutton(body, text="Individual Transfers", variable=kind_var, value="individual").pack(anchor="w", pady=(10, 2))
        ttk.Label(body, text="Creates one pipetting operation per source; each source may use its own volume.", style="Muted.TLabel").pack(anchor="w", padx=(22, 0))
        ttk.Radiobutton(body, text="8-Channel Column Transfer", variable=kind_var, value="8-channel").pack(anchor="w", pady=(10, 2))
        ttk.Label(body, text="Moves one complete 8-well pattern simultaneously with one common volume.", style="Muted.TLabel").pack(anchor="w", padx=(22, 0))
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(14, 0))
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(buttons, text="Next", command=lambda: (result.update(action="next"), win.destroy()), style="ChemAction.TButton").pack(side="right", padx=(0, 6))
        self._center_dialog(win)
        self.wait_window(win)
        return str(result["action"]), kind_var.get()

    def _batch_source_labware_step(
        self,
        initial_alias: str,
        *,
        has_existing_mapping: bool,
    ) -> Tuple[str, str]:
        aliases = self._source_labware_aliases()
        if not aliases:
            raise ValueError("Add source labware before configuring the batch.")
        selected_alias = initial_alias if initial_alias in aliases else ""
        result = {"action": "cancel", "alias": selected_alias}
        win = tk.Toplevel(self)
        win.title("Batch Transfer - Source Labware")
        win.transient(self.winfo_toplevel())
        win.grab_set()
        win.resizable(False, False)
        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Choose source labware", font=("", 10, "bold")).pack(anchor="w")
        source_alias_var = tk.StringVar(value=selected_alias)
        ttk.Combobox(
            body,
            textvariable=source_alias_var,
            values=aliases,
            state="readonly",
            width=28,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Label(
            body,
            text=(
                "Changing source labware clears the staged source wells, Chemical IDs, building-block flags, "
                "and destination mappings so they can be remapped safely."
            ),
            style="Muted.TLabel",
            wraplength=480,
        ).pack(anchor="w", pady=(8, 0))
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(14, 0))

        def save_and_continue():
            requested_alias = source_alias_var.get().strip()
            if requested_alias not in aliases:
                messagebox.showwarning("Batch Transfer", "Select valid source labware.", parent=win)
                return
            if requested_alias != str(initial_alias or "").strip() and has_existing_mapping:
                if not messagebox.askyesno(
                    "Change source labware",
                    "Changing source labware clears the staged source wells, Chemical IDs, building-block flags, "
                    "and destination mappings. Continue?",
                    parent=win,
                ):
                    return
            result.update(action="next", alias=requested_alias)
            win.destroy()

        ttk.Button(
            buttons,
            text="Back",
            command=lambda: (result.update(action="back"), win.destroy()),
        ).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(
            buttons,
            text="Next",
            command=save_and_continue,
            style="ChemAction.TButton",
        ).pack(side="right", padx=(0, 6))
        self._center_dialog(win)
        self.wait_window(win)
        return str(result["action"]), str(result["alias"])

    def _batch_source_step(
        self,
        kind: str,
        source_alias: str,
        sources: List[str],
        *,
        exclude_row_index: Optional[int],
    ) -> Tuple[str, List[str]]:
        source_labware = self._labware_by_alias(source_alias)
        if not source_labware or source_labware.get("role") not in {"source", "both"}:
            raise ValueError("Select valid source labware before configuring the batch.")
        source_style = str(source_labware.get("map_style", self.source_style_var.get()))
        source_patterns = _eight_channel_patterns(source_style) if kind == "8-channel" else None
        if kind == "8-channel" and not source_patterns:
            raise ValueError("8-channel batch source labware must use a 96-well or 384-well map.")
        blocked, reusable = self._source_well_availability(
            source_alias,
            "",
            exclude_row_index=exclude_row_index,
        )
        used_wells = blocked | reusable
        rows, cols = _style_dims(source_style)
        dlg = well_map.WellMapDialog(
            self,
            rows,
            cols,
            ",".join(sources),
            vertical_view=False,
            anchor=self,
            highlight_labels=used_wells,
            disabled_labels=_style_disabled_labels(source_style),
            highlight_hint="Light blue wells are used elsewhere; their Chemical ID will be checked before saving.",
            disabled_hint="Gray positions do not exist in this labware.",
            instruction=(
                "Select one complete 8-channel source pattern."
                if kind == "8-channel"
                else "Select one or more source wells. Volume requirements are assigned after Chemical IDs."
            ),
            selection_limit=8 if kind == "8-channel" else None,
            required_count=8 if kind == "8-channel" else None,
            pattern_groups=source_patterns,
            show_back=True,
        )
        dlg.title("Batch Transfer — Select Sources")
        self.wait_window(dlg)
        if dlg.back_requested:
            return "back", sources
        selected = [value for value in dlg.result_labels.split(",") if value]
        return ("next", selected) if selected else ("cancel", sources)

    def _batch_chemical_step(
        self,
        sources: List[str],
        initial: Dict[str, str],
        initial_building_blocks: Dict[str, bool],
    ) -> Tuple[str, Dict[str, str], Dict[str, bool]]:
        result = {"action": "cancel"}
        win = tk.Toplevel(self)
        win.title("Batch Transfer — Optional Chemical IDs")
        win.transient(self.winfo_toplevel())
        win.grab_set()
        win.resizable(True, True)
        shell = ttk.Frame(win, padding=14)
        shell.pack(fill="both", expand=True)
        ttk.Label(
            shell,
            text=(
                "Assign a Chemical ID and mark whether it is a building block for each physical source well. "
                "Leave Chemical ID blank for workup steps."
            ),
            wraplength=620,
        ).pack(anchor="w", pady=(0, 8))

        table_host = ttk.Frame(shell)
        table_host.pack(fill="both", expand=True)
        visible_rows = min(10, max(1, len(sources)))
        canvas = tk.Canvas(
            table_host,
            width=620,
            height=34 + (visible_rows * 30),
            highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(table_host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        body = ttk.Frame(canvas)
        body_window = canvas.create_window((0, 0), window=body, anchor="nw")

        def refresh_scroll_region(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def fit_body_width(event):
            canvas.itemconfigure(body_window, width=event.width)

        body.bind("<Configure>", refresh_scroll_region)
        canvas.bind("<Configure>", fit_body_width)

        ttk.Label(body, text="Source", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(body, text="Chemical ID", style="Muted.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(body, text="Building block", style="Muted.TLabel").grid(
            row=0, column=2, sticky="w", padx=(12, 0)
        )
        choices = self._compound_choices()
        variables: Dict[str, tk.StringVar] = {}
        building_block_variables: Dict[str, tk.BooleanVar] = {}
        for row_index, source in enumerate(sources, start=1):
            ttk.Label(body, text=source, width=8).grid(row=row_index, column=0, sticky="w", pady=2)
            variable = tk.StringVar(value=str(initial.get(source, "") or ""))
            variables[source] = variable
            ttk.Combobox(body, textvariable=variable, values=choices, state="normal", width=38).grid(
                row=row_index, column=1, sticky="ew", pady=2
            )
            building_block_variable = tk.BooleanVar(
                value=coerce_bool(initial_building_blocks.get(source, False))
            )
            building_block_variables[source] = building_block_variable
            ttk.Checkbutton(body, variable=building_block_variable).grid(
                row=row_index, column=2, sticky="w", padx=(12, 0), pady=2
            )
        buttons = ttk.Frame(shell)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="Back", command=lambda: (result.update(action="back"), win.destroy())).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(buttons, text="Next", command=lambda: (result.update(action="next"), win.destroy()), style="ChemAction.TButton").pack(side="right", padx=(0, 6))
        body.columnconfigure(1, weight=1)
        self._center_dialog(win)
        self.wait_window(win)
        assignments = {
            source: self._chemical_id_from_label(variable.get())
            for source, variable in variables.items()
        }
        building_blocks = {
            source: bool(building_block_variables[source].get()) if assignments.get(source, "") else False
            for source in sources
        }
        return str(result["action"]), assignments, building_blocks

    def _batch_volume_step(
        self,
        kind: str,
        sources: List[str],
        chemicals: Dict[str, str],
        building_blocks: Dict[str, bool],
        initial_modes: Dict[str, str],
        initial_umol: Dict[str, str],
        initial_volumes_ul: Dict[str, str],
    ) -> Tuple[str, Dict[str, str], Dict[str, str], Dict[str, str]]:
        result = {"action": "cancel"}
        modes: Dict[str, str] = {}
        umol_values = {
            source: str(initial_umol.get(source, "") or "").strip()
            for source in sources
        }
        volume_values = {
            source: str(initial_volumes_ul.get(source, "") or "").strip()
            for source in sources
        }
        for source in sources:
            initial_mode = str(initial_modes.get(source, "") or "").strip().lower()
            if initial_mode in {BATCH_VOLUME_MODE_UMOL, BATCH_VOLUME_MODE_UL}:
                modes[source] = initial_mode
            elif building_blocks.get(source, False):
                modes[source] = BATCH_VOLUME_MODE_UMOL
            else:
                modes[source] = BATCH_VOLUME_MODE_UL

        def concentration_for(source: str) -> Optional[float]:
            chemical = chemicals.get(source, "")
            compound = self._compound_for_chemical_label(chemical) if chemical else None
            return self._record_concentration_m(compound) if compound else None

        def source_state(source: str) -> Tuple[str, str, str]:
            mode = modes.get(source, BATCH_VOLUME_MODE_UL)
            if mode == BATCH_VOLUME_MODE_UMOL:
                amount = self._positive_float_or_none(umol_values.get(source, ""))
                if amount is None:
                    volume_values[source] = ""
                    return umol_values.get(source, ""), "", "Enter target umol"
                concentration_m = concentration_for(source)
                if concentration_m is None:
                    volume_values[source] = ""
                    return umol_values.get(source, ""), "", "Missing Compound Notes concentration"
                calculated = self._volume_from_umol_and_conc(amount, concentration_m)
                volume_values[source] = calculated
                return umol_values.get(source, ""), calculated, "Ready"
            volume = self._positive_float_or_none(volume_values.get(source, ""))
            if volume is None:
                return volume_values.get(source, ""), "", "Enter direct uL"
            final = f"{volume:.6g}"
            volume_values[source] = final
            return final, final, "Ready"

        win = tk.Toplevel(self)
        win.title("Batch Transfer — Volume Requirements")
        win.transient(self.winfo_toplevel())
        win.grab_set()
        win.resizable(True, True)
        shell = ttk.Frame(win, padding=14)
        shell.pack(fill="both", expand=True)
        ttk.Label(
            shell,
            text=(
                "Any source can use target umol when a Compound Notes concentration is available, or direct uL. "
                "Building blocks default to target umol."
            ),
            wraplength=850,
        ).pack(anchor="w", pady=(0, 8))

        columns = ("source", "chemical", "bb", "input", "value", "final", "status")
        tree = ttk.Treeview(shell, columns=columns, show="headings", height=min(8, max(1, len(sources))), selectmode="browse")
        for column, heading, width in (
            ("source", "Source", 72),
            ("chemical", "Chemical ID", 160),
            ("bb", "BB?", 48),
            ("input", "Input", 150),
            ("value", "Entered value", 100),
            ("final", "Final uL", 90),
            ("status", "Status", 220),
        ):
            tree.heading(column, text=heading)
            tree.column(column, width=width, minwidth=45, anchor="w", stretch=column in {"chemical", "status"})
        tree.pack(fill="both", expand=True)

        editor = ttk.LabelFrame(shell, text="Selected source", padding=10)
        editor.pack(fill="x", pady=(10, 0))
        selected_var = tk.StringVar(value=sources[0] if sources else "")
        selected_label_var = tk.StringVar(value="")
        mode_label_var = tk.StringVar(value="")
        value_var = tk.StringVar(value="")
        status_var = tk.StringVar(value="")
        ttk.Label(editor, textvariable=selected_label_var, width=26).grid(row=0, column=0, sticky="w", padx=(0, 8))
        mode_combo = ttk.Combobox(editor, textvariable=mode_label_var, width=23, state="readonly")
        mode_combo.grid(row=0, column=1, sticky="w", padx=(0, 8))
        ttk.Entry(editor, textvariable=value_var, width=12).grid(row=0, column=2, sticky="w", padx=(0, 8))

        def refresh_tree() -> None:
            for source in sources:
                entered, final, status = source_state(source)
                mode_label = BATCH_VOLUME_MODE_LABELS[modes[source]]
                values = (
                    source,
                    chemicals.get(source, "") or "unassigned",
                    "Yes" if building_blocks.get(source, False) else "No",
                    mode_label,
                    entered,
                    final,
                    status,
                )
                if tree.exists(source):
                    tree.item(source, values=values)
                else:
                    tree.insert("", "end", iid=source, values=values)

        def load_selected(_event=None) -> None:
            selected = tree.selection()
            source = selected[0] if selected else selected_var.get()
            if not source:
                return
            selected_var.set(source)
            selected_label_var.set(f"{source} — {chemicals.get(source, '') or 'unassigned'}")
            mode_combo.configure(
                state="readonly",
                values=(
                    BATCH_VOLUME_MODE_LABELS[BATCH_VOLUME_MODE_UMOL],
                    BATCH_VOLUME_MODE_LABELS[BATCH_VOLUME_MODE_UL],
                ),
            )
            mode_label_var.set(BATCH_VOLUME_MODE_LABELS[modes[source]])
            value_var.set(
                umol_values.get(source, "")
                if modes[source] == BATCH_VOLUME_MODE_UMOL
                else volume_values.get(source, "")
            )

        def selected_mode() -> str:
            return (
                BATCH_VOLUME_MODE_UMOL
                if mode_label_var.get() == BATCH_VOLUME_MODE_LABELS[BATCH_VOLUME_MODE_UMOL]
                else BATCH_VOLUME_MODE_UL
            )

        def change_selected_mode(_event=None) -> None:
            source = selected_var.get()
            if not source:
                return
            mode = selected_mode()
            modes[source] = mode
            value_var.set(
                umol_values.get(source, "")
                if mode == BATCH_VOLUME_MODE_UMOL
                else volume_values.get(source, "")
            )

        def update_selected() -> None:
            source = selected_var.get()
            if not source:
                return
            mode = selected_mode()
            modes[source] = mode
            if mode == BATCH_VOLUME_MODE_UMOL:
                umol_values[source] = value_var.get().strip()
            else:
                volume_values[source] = value_var.get().strip()
            refresh_tree()
            tree.selection_set(source)
            tree.focus(source)
            load_selected()

        def apply_to_all() -> None:
            source = selected_var.get()
            if not source:
                return
            value = value_var.get().strip()
            if self._positive_float_or_none(value) is None:
                messagebox.showwarning("Batch Transfer", "Enter a positive value before using Apply to all.", parent=win)
                return
            mode = selected_mode()
            if mode == BATCH_VOLUME_MODE_UMOL:
                for target in sources:
                    modes[target] = BATCH_VOLUME_MODE_UMOL
                    umol_values[target] = value
                status_var.set(f"Applied {value} umol to all {len(sources)} source(s).")
            else:
                for target in sources:
                    modes[target] = BATCH_VOLUME_MODE_UL
                    volume_values[target] = value
                status_var.set(f"Applied {value} uL to all {len(sources)} source(s).")
            refresh_tree()
            tree.selection_set(source)
            tree.focus(source)
            load_selected()

        def next_step() -> None:
            update_selected()
            problems = []
            final_numbers = []
            for source in sources:
                _entered, final, status = source_state(source)
                number = self._positive_float_or_none(final)
                if number is None:
                    problems.append(f"{source}: {status}")
                else:
                    final_numbers.append(number)
            refresh_tree()
            if problems:
                messagebox.showwarning(
                    "Batch Transfer — Volume required",
                    "Complete the following source volume(s) before continuing:\n"
                    + "\n".join(f"- {problem}" for problem in problems),
                    parent=win,
                )
                return
            if kind == "8-channel" and final_numbers:
                first = final_numbers[0]
                if any(not math.isclose(first, value, rel_tol=1e-9, abs_tol=1e-6) for value in final_numbers[1:]):
                    messagebox.showwarning(
                        "Batch Transfer — 8-channel volume mismatch",
                        "An 8-channel transfer requires the same final dispense volume for every active source well. "
                        "Review the entered and calculated volumes before continuing.",
                        parent=win,
                    )
                    return
            result["action"] = "next"
            win.destroy()

        ttk.Button(editor, text="Update selected", command=update_selected, style="FileAction.TButton").grid(
            row=0, column=3, sticky="w", padx=(0, 6)
        )
        ttk.Button(editor, text="Apply to all", command=apply_to_all, style="RowAction.TButton").grid(
            row=0, column=4, sticky="w"
        )
        ttk.Label(editor, textvariable=status_var, style="Muted.TLabel").grid(
            row=1, column=0, columnspan=5, sticky="w", pady=(8, 0)
        )
        buttons = ttk.Frame(shell)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="Back", command=lambda: (result.update(action="back"), win.destroy())).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(buttons, text="Next", command=next_step, style="ChemAction.TButton").pack(side="right", padx=(0, 6))
        tree.bind("<<TreeviewSelect>>", load_selected)
        mode_combo.bind("<<ComboboxSelected>>", change_selected_mode)
        refresh_tree()
        if sources:
            tree.selection_set(sources[0])
            tree.focus(sources[0])
            load_selected()
        self._center_dialog(win)
        self.wait_window(win)
        return str(result["action"]), modes, umol_values, volume_values

    def _batch_destination_labware_step(
        self,
        initial_alias: str,
        *,
        has_existing_mapping: bool,
    ) -> Tuple[str, str]:
        aliases = self._dest_labware_aliases()
        if not aliases:
            raise ValueError("Add destination labware before configuring the batch.")
        selected_alias = initial_alias if initial_alias in aliases else ""
        result = {"action": "cancel", "alias": selected_alias}
        win = tk.Toplevel(self)
        win.title("Batch Transfer - Destination Labware")
        win.transient(self.winfo_toplevel())
        win.grab_set()
        win.resizable(False, False)
        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Choose destination labware", font=("", 10, "bold")).pack(anchor="w")
        dest_alias_var = tk.StringVar(value=selected_alias)
        ttk.Combobox(
            body,
            textvariable=dest_alias_var,
            values=aliases,
            state="readonly",
            width=28,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Label(
            body,
            text="Changing destination labware clears the staged destination mappings so they can be remapped safely.",
            style="Muted.TLabel",
            wraplength=480,
        ).pack(anchor="w", pady=(8, 0))
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(14, 0))

        def save_and_continue():
            requested_alias = dest_alias_var.get().strip()
            if requested_alias not in aliases:
                messagebox.showwarning("Batch Transfer", "Select valid destination labware.", parent=win)
                return
            if requested_alias != str(initial_alias or "").strip() and has_existing_mapping:
                if not messagebox.askyesno(
                    "Change destination labware",
                    "Changing destination labware clears the staged destination mappings. Continue?",
                    parent=win,
                ):
                    return
            result.update(action="next", alias=requested_alias)
            win.destroy()

        ttk.Button(
            buttons,
            text="Back",
            command=lambda: (result.update(action="back"), win.destroy()),
        ).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(
            buttons,
            text="Next",
            command=save_and_continue,
            style="ChemAction.TButton",
        ).pack(side="right", padx=(0, 6))
        self._center_dialog(win)
        self.wait_window(win)
        return str(result["action"]), str(result["alias"])

    def _batch_destination_step(
        self,
        kind: str,
        sources: List[str],
        dest_alias: str,
        destination_sets: List[List[str]],
        *,
        exclude_row_index: Optional[int] = None,
    ) -> Tuple[str, str, List[List[str]]]:
        while True:
            aliases = self._dest_labware_aliases()
            if not aliases:
                raise ValueError("Add destination labware before configuring the batch.")
            if dest_alias not in aliases:
                action, requested_alias = self._batch_destination_labware_step(
                    dest_alias,
                    has_existing_mapping=bool(destination_sets),
                )
                if action == "back":
                    return "back", dest_alias, destination_sets
                if action != "next":
                    return "cancel", dest_alias, destination_sets
                if requested_alias != dest_alias:
                    dest_alias = requested_alias
                    destination_sets = []
            dest_labware = self._labware_by_alias(dest_alias) or {}
            dest_style = str(dest_labware.get("map_style", self.dest_style_var.get()))
            dest_patterns = _eight_channel_patterns(dest_style) if kind == "8-channel" else None
            if kind == "8-channel" and not dest_patterns:
                raise ValueError("8-channel batch destination labware must use a 96-well or 384-well map.")
            rows, cols = _style_dims(dest_style)
            used_wells = self._used_destination_wells(
                dest_alias,
                exclude_row_index=exclude_row_index,
            )
            dlg = well_map.WellMapDialog(
                self,
                rows,
                cols,
                vertical_view=False,
                anchor=self,
                highlight_labels=used_wells,
                highlight_hint="Light blue destination wells are used by another transfer and remain reusable.",
                disabled_labels=_style_disabled_labels(dest_style),
                disabled_hint="Gray positions do not exist in this labware.",
                instruction=(
                    "Select a matching 8-channel destination pattern and click Add Destination Set."
                    if kind == "8-channel"
                    else f"Select exactly {len(sources)} wells and click Add Destination Set."
                ),
                selection_limit=8 if kind == "8-channel" else len(sources),
                required_count=8 if kind == "8-channel" else len(sources),
                pattern_groups=dest_patterns,
                destination_set_mode=True,
                initial_groups=destination_sets,
                show_back=True,
                labware_value=dest_alias,
                labware_values=aliases,
            )
            dlg.title("Batch Transfer — Destination Labware and Wells")
            self.wait_window(dlg)
            if dlg.labware_change_requested:
                requested = dlg.requested_labware
                current_groups = [list(group) for group in dlg.result_groups]
                if requested != dest_alias and current_groups:
                    if not messagebox.askyesno(
                        "Change destination labware",
                        "Changing destination labware clears the recorded destination sets. Continue?",
                    ):
                        destination_sets = current_groups
                        continue
                dest_alias = requested
                destination_sets = []
                continue
            if dlg.back_requested:
                return "back", dest_alias, destination_sets
            if dlg.result_groups:
                return "next", dest_alias, [list(group) for group in dlg.result_groups]
            return "cancel", dest_alias, destination_sets

    def _batch_review_step(
        self,
        kind: str,
        sources: List[str],
        chemicals: Dict[str, str],
        dest_alias: str,
        destination_sets: List[List[str]],
        *,
        source_alias: str,
        building_blocks: Dict[str, bool],
        volume_modes: Dict[str, str],
        source_umol: Dict[str, str],
        source_volumes_ul: Dict[str, str],
        editing: bool,
    ) -> str:
        result = {"action": "cancel"}
        win = tk.Toplevel(self)
        win.title("Review Batch Transfer")
        win.transient(self.winfo_toplevel())
        win.grab_set()
        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Review the saved logical batch", font=("", 10, "bold")).pack(anchor="w")
        lines = [
            f"Method: {'Individual Transfers' if kind == 'individual' else '8-Channel Column Transfer'}",
            f"Source labware: {source_alias}",
            f"Destination labware: {dest_alias}",
            "",
            "Source volume requirements",
        ]
        for source in sources:
            chemical = chemicals.get(source, "") or "unassigned"
            building_block = "; building block" if building_blocks.get(source, False) else ""
            mode = volume_modes.get(source, BATCH_VOLUME_MODE_UL)
            if mode == BATCH_VOLUME_MODE_UMOL:
                entered = f"{source_umol.get(source, '')} umol"
            else:
                entered = f"{source_volumes_ul.get(source, '')} uL direct"
            lines.append(
                f"  {source} [{chemical}{building_block}] — {entered}; final {source_volumes_ul.get(source, '')} uL"
            )
        lines.extend(("", "Destination mapping"))
        for set_index, destinations in enumerate(destination_sets, start=1):
            lines.append(f"Destination Set {set_index}")
            for source, destination in zip(sources, destinations):
                chemical = chemicals.get(source, "") or "unassigned"
                building_block = "; building block" if building_blocks.get(source, False) else ""
                lines.append(f"  {source} [{chemical}{building_block}]  →  {destination}")
        preview = tk.Text(body, width=70, height=min(20, max(8, len(lines))), wrap="none")
        preview.pack(fill="both", expand=True, pady=(8, 0))
        preview.insert("1.0", "\n".join(lines))
        preview.configure(state="disabled")
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="Back", command=lambda: (result.update(action="back"), win.destroy())).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(
            buttons,
            text="Update Batch Transfer" if editing else "Save Batch Transfer",
            command=lambda: (result.update(action="save"), win.destroy()),
            style="ChemAction.TButton",
        ).pack(side="right", padx=(0, 6))
        self._center_dialog(win)
        self.wait_window(win)
        return str(result["action"])

    def _build_logical_batch_row(
        self,
        kind: str,
        sources: List[str],
        chemicals: Dict[str, str],
        dest_alias: str,
        destination_sets: List[List[str]],
        *,
        source_alias: Optional[str] = None,
        building_blocks: Optional[Dict[str, bool]] = None,
        volume_modes: Optional[Dict[str, str]] = None,
        source_umol: Optional[Dict[str, str]] = None,
        source_volumes_ul: Optional[Dict[str, str]] = None,
        exclude_row_index: Optional[int],
    ) -> Dict[str, object]:
        if not sources:
            raise ValueError("Select at least one batch source well.")
        if not destination_sets or any(len(group) != len(sources) for group in destination_sets):
            raise ValueError("Every destination set must contain one destination for each selected source.")
        source_alias = str(source_alias or self.source_labware_alias_var.get()).strip()
        for source in sources:
            conflict = self._source_well_conflict(
                source_alias,
                source,
                chemicals.get(source, ""),
                exclude_row_index=exclude_row_index,
            )
            if conflict:
                raise ValueError(conflict)
        pipette_choice = self.row_pipette_var.get().strip() or "Auto"
        pipette_mount = self._configured_batch_8_channel_mount(pipette_choice) if kind == "8-channel" else ""
        flattened_destinations = [well for group in destination_sets for well in group]
        building_blocks = building_blocks or {}
        if source_volumes_ul is None:
            source_volumes_ul = {source: self.volume_var.get().strip() for source in sources}
        normalized_volumes = {
            source: str(source_volumes_ul.get(source, "") or "").strip()
            for source in sources
        }
        missing_volumes = [
            source for source in sources
            if self._positive_float_or_none(normalized_volumes.get(source, "")) is None
        ]
        if missing_volumes:
            raise ValueError("Enter a positive dispense volume for " + ", ".join(missing_volumes) + ".")
        volume_numbers = [float(normalized_volumes[source]) for source in sources]
        if kind == "8-channel" and any(
            not math.isclose(volume_numbers[0], value, rel_tol=1e-9, abs_tol=1e-6)
            for value in volume_numbers[1:]
        ):
            raise ValueError("An 8-channel transfer requires the same final dispense volume for every active source well.")
        normalized_modes = {
            source: (
                BATCH_VOLUME_MODE_UMOL
                if str((volume_modes or {}).get(source, "") or "").strip().lower() == BATCH_VOLUME_MODE_UMOL
                else BATCH_VOLUME_MODE_UL
            )
            for source in sources
        }
        normalized_umol = {
            source: str((source_umol or {}).get(source, "") or "").strip()
            for source in sources
        }
        base_volume = normalized_volumes[sources[0]]
        original = {
            "chemical": self.chemical_var.get(),
            "reaction_umol": self.reaction_umol_var.get(),
            "building_block": self.is_building_block_var.get(),
            "source": self.source_well_var.get(),
            "destinations": self.dest_wells_var.get(),
            "source_alias": self.source_labware_alias_var.get(),
            "dest_alias": self.dest_labware_alias_var.get(),
            "pipette": self.row_pipette_var.get(),
            "volume": self.volume_var.get(),
        }
        self._loading_transfer_row = True
        try:
            self.chemical_var.set(chemicals.get(sources[0], ""))
            self.reaction_umol_var.set("")
            self.is_building_block_var.set(False)
            self.source_well_var.set(sources[0])
            self.dest_wells_var.set(",".join(flattened_destinations))
            self.source_labware_alias_var.set(source_alias)
            self.dest_labware_alias_var.set(dest_alias)
            self.row_pipette_var.set(pipette_choice)
            self.volume_var.set(base_volume)
            base = self._transfer_from_form(exclude_row_index=exclude_row_index)
        finally:
            self.chemical_var.set(original["chemical"])
            self.reaction_umol_var.set(original["reaction_umol"])
            self.is_building_block_var.set(bool(original["building_block"]))
            self.source_well_var.set(original["source"])
            self.dest_wells_var.set(original["destinations"])
            self.source_labware_alias_var.set(original["source_alias"])
            self.dest_labware_alias_var.set(original["dest_alias"])
            self.row_pipette_var.set(original["pipette"])
            self.volume_var.set(original["volume"])
            self._loading_transfer_row = False
        row = self._transfer_row_dict(base)
        row.update({
            "chemical": "",
            "reaction_umol": "",
            "is_building_block": False,
            "source_well": sources[0],
            "dest_wells": ",".join(flattened_destinations),
            "dest_labware_alias": dest_alias,
            "pipette_key": pipette_choice,
            "batch_pipette_mount": pipette_mount,
            "batch_transfer_version": 4,
            "batch_transfer_kind": kind,
            "batch_source_wells": ",".join(sources),
            "batch_source_chemicals": {source: chemicals.get(source, "") for source in sources},
            "batch_source_building_blocks": {
                source: bool(building_blocks.get(source, False)) if chemicals.get(source, "") else False
                for source in sources
            },
            "batch_source_volume_modes": normalized_modes,
            "batch_source_umol": normalized_umol,
            "batch_source_volumes_ul": normalized_volumes,
            "batch_destination_sets": [list(group) for group in destination_sets],
        })
        return row

    def _open_batch_transfer(self, edit_index: Optional[int] = None) -> bool:
        if self._batch_editor_open:
            return False
        self._batch_editor_open = True
        try:
            existing = self.rows[edit_index] if edit_index is not None else {}
            if edit_index is not None and not self._row_is_batch(existing):
                raise ValueError("The selected plan item is not a batch transfer.")
            kind = str(existing.get("batch_transfer_kind", "individual") or "individual")
            sources = [value for value in str(existing.get("batch_source_wells", "") or "").split(",") if value]
            chemicals = {
                str(key).strip().upper(): str(value or "").strip()
                for key, value in dict(existing.get("batch_source_chemicals", {}) or {}).items()
            }
            building_blocks = {
                str(key).strip().upper(): coerce_bool(value)
                for key, value in dict(existing.get("batch_source_building_blocks", {}) or {}).items()
            }
            volume_modes = self._batch_volume_mode_map(existing) if existing else {}
            source_umol = self._batch_umol_map(existing) if existing else {}
            source_volumes_ul = self._batch_final_volume_map(existing) if existing else {}
            new_batch = edit_index is None or coerce_bool(existing.get("_draft", False))
            dest_alias = (
                ""
                if new_batch
                else str(existing.get("dest_labware_alias", self.dest_labware_alias_var.get()) or self.dest_labware_alias_var.get())
            )
            destination_sets = [list(group) for group in existing.get("batch_destination_sets", []) or []]
            source_alias = (
                ""
                if new_batch
                else str(existing.get("source_labware_alias", self.source_labware_alias_var.get()) or self.source_labware_alias_var.get())
            )
            step = 0
            while True:
                if step == 0:
                    previous_kind = kind
                    action, kind = self._batch_kind_step(kind)
                    if action != "next":
                        return False
                    if kind != previous_kind:
                        sources = []
                        chemicals = {}
                        building_blocks = {}
                        volume_modes = {}
                        source_umol = {}
                        source_volumes_ul = {}
                        destination_sets = []
                    if kind == "8-channel":
                        self._configured_batch_8_channel_mount()
                    step = 1
                elif step == 1:
                    action, selected_source_alias = self._batch_source_labware_step(
                        source_alias,
                        has_existing_mapping=bool(
                            sources or chemicals or building_blocks or destination_sets
                        ),
                    )
                    if action == "back":
                        step = 0
                        continue
                    if action != "next":
                        return False
                    if selected_source_alias != source_alias:
                        source_alias = selected_source_alias
                        sources = []
                        chemicals = {}
                        building_blocks = {}
                        volume_modes = {}
                        source_umol = {}
                        source_volumes_ul = {}
                        destination_sets = []
                    step = 2
                elif step == 2:
                    action, selected_sources = self._batch_source_step(
                        kind,
                        source_alias,
                        sources,
                        exclude_row_index=edit_index,
                    )
                    if action == "back":
                        step = 1
                        continue
                    if action != "next":
                        return False
                    if selected_sources != sources:
                        chemicals = {source: chemicals.get(source, "") for source in selected_sources}
                        building_blocks = {
                            source: building_blocks.get(source, False) for source in selected_sources
                        }
                        volume_modes = {
                            source: volume_modes.get(source, "") for source in selected_sources
                        }
                        source_umol = {
                            source: source_umol.get(source, "") for source in selected_sources
                        }
                        source_volumes_ul = {
                            source: source_volumes_ul.get(source, "") for source in selected_sources
                        }
                        destination_sets = []
                    remembered_chemicals = self._source_well_chemical_assignments(
                        source_alias,
                        exclude_row_index=edit_index,
                    )
                    chemicals = {
                        source: chemicals.get(source, "") or remembered_chemicals.get(source, "")
                        for source in selected_sources
                    }
                    sources = selected_sources
                    step = 3
                elif step == 3:
                    action, chemicals, building_blocks = self._batch_chemical_step(
                        sources, chemicals, building_blocks
                    )
                    if action == "back":
                        step = 2
                        continue
                    if action != "next":
                        return False
                    step = 4
                elif step == 4:
                    action, volume_modes, source_umol, source_volumes_ul = self._batch_volume_step(
                        kind,
                        sources,
                        chemicals,
                        building_blocks,
                        volume_modes,
                        source_umol,
                        source_volumes_ul,
                    )
                    if action == "back":
                        step = 3
                        continue
                    if action != "next":
                        return False
                    step = 5
                elif step == 5:
                    action, dest_alias, destination_sets = self._batch_destination_step(
                        kind,
                        sources,
                        dest_alias,
                        destination_sets,
                        exclude_row_index=edit_index,
                    )
                    if action == "back":
                        step = 4
                        continue
                    if action != "next":
                        return False
                    step = 6
                else:
                    action = self._batch_review_step(
                        kind,
                        sources,
                        chemicals,
                        dest_alias,
                        destination_sets,
                        source_alias=source_alias,
                        building_blocks=building_blocks,
                        volume_modes=volume_modes,
                        source_umol=source_umol,
                        source_volumes_ul=source_volumes_ul,
                        editing=edit_index is not None,
                    )
                    if action == "back":
                        step = 5
                        continue
                    if action != "save":
                        return False
                    batch_row = self._build_logical_batch_row(
                        kind,
                        sources,
                        chemicals,
                        dest_alias,
                        destination_sets,
                        source_alias=source_alias,
                        building_blocks=building_blocks,
                        volume_modes=volume_modes,
                        source_umol=source_umol,
                        source_volumes_ul=source_volumes_ul,
                        exclude_row_index=edit_index,
                    )
                    if edit_index is None:
                        self.rows.append(batch_row)
                        saved_index = len(self.rows) - 1
                    else:
                        self.rows[edit_index] = batch_row
                        saved_index = edit_index
                    self._refresh_table()
                    self._set_transfer_type(True)
                    self._select_transfer_row(saved_index)
                    self._on_transfer_row_select()
                    self.status_var.set(
                        f"{'Updated' if edit_index is not None else 'Added'} one logical batch transfer with "
                        f"{len(sources)} source(s), {len(destination_sets)} destination set(s), and saved source volumes."
                    )
                    return True
        except Exception as exc:
            messagebox.showwarning("Batch Transfer", str(exc))
            return False
        finally:
            self._batch_editor_open = False

    def _new_transfer_draft(self, *, batch: bool) -> Dict[str, object]:
        source_aliases = self._source_labware_aliases()
        dest_aliases = self._dest_labware_aliases()
        source_alias = "" if batch else (source_aliases[0] if source_aliases else "")
        dest_alias = "" if batch else (dest_aliases[0] if dest_aliases else "")
        row = self._transfer_row_dict(OpentronsTransferRow(
            source_well="",
            dest_wells="",
            volume_ul=0.0,
            strategy="Multi-dispense",
            source_labware_alias=source_alias,
            dest_labware_alias=dest_alias,
            move_labware_alias=dest_alias,
        ))
        row["volume_ul"] = ""
        row["_draft"] = True
        if batch:
            row.update({
                "chemical": "",
                "reaction_umol": "",
                "is_building_block": False,
                "batch_transfer_version": 4,
                "batch_transfer_kind": "individual",
                "batch_source_wells": "",
                "batch_source_chemicals": {},
                "batch_source_building_blocks": {},
                "batch_source_volume_modes": {},
                "batch_source_umol": {},
                "batch_source_volumes_ul": {},
                "batch_destination_sets": [],
                "batch_pipette_mount": "",
            })
        return row

    def _append_and_edit_draft(self, *, batch: bool):
        self.rows.append(self._new_transfer_draft(batch=batch))
        idx = len(self.rows) - 1
        self._refresh_table()
        self._select_transfer_row(idx)
        self._on_transfer_row_select()
        if batch:
            self.status_var.set(
                f"Created incomplete batch row {idx + 1}; click Map to assign sources, Chemical IDs, volumes, and destinations."
            )
        else:
            self.status_var.set(
                f"Created incomplete single row {idx + 1}; changes save automatically as you complete it."
            )

    def _create_single_row(self):
        self._append_and_edit_draft(batch=False)

    def _create_batch_row(self):
        self._append_and_edit_draft(batch=True)

    def _add_row(self):
        """Backward-compatible internal alias for the row-first single creation action."""
        self._create_single_row()

    @staticmethod
    def _transfer_row_dict(transfer: OpentronsTransferRow) -> Dict[str, object]:
        return {
            "step_name": transfer.step_name,
            "chemical": transfer.chemical,
            "reaction_umol": transfer.reaction_umol,
            "is_building_block": transfer.is_building_block,
            "source_well": transfer.source_well,
            "dest_wells": transfer.dest_wells,
            "volume_ul": transfer.volume_ul,
            "source_labware_alias": transfer.source_labware_alias,
            "dest_labware_alias": transfer.dest_labware_alias,
            "strategy": transfer.strategy,
            "pipette_key": transfer.pipette_key,
            "tip_policy": transfer.tip_policy,
            "blowout_location": transfer.blowout_location,
            "blowout_labware_alias": transfer.blowout_labware_alias,
            "blowout_well": transfer.blowout_well,
            "aspirate_rate": transfer.aspirate_rate,
            "dispense_rate": transfer.dispense_rate,
            "aspirate_depth_mm": transfer.aspirate_depth_mm,
            "aspirate_depth_reference": transfer.aspirate_depth_reference,
            "dispense_depth_mm": transfer.dispense_depth_mm,
            "dispense_depth_reference": transfer.dispense_depth_reference,
            "multi_dispense_extra_percent": transfer.multi_dispense_extra_percent,
            "tip_touch": transfer.tip_touch,
            "pre_wet_tip": transfer.pre_wet_tip,
            "mix_enabled": transfer.mix_enabled,
            "mix_timing": transfer.mix_timing,
            "mix_repetitions": transfer.mix_repetitions,
            "mix_volume_ul": transfer.mix_volume_ul,
            "post_source_mix_delay_seconds": transfer.post_source_mix_delay_seconds,
            "mix_aspirate_rate": transfer.mix_aspirate_rate,
            "mix_dispense_rate": transfer.mix_dispense_rate,
            "mix_aspirate_depth_mm": transfer.mix_aspirate_depth_mm,
            "mix_aspirate_depth_reference": transfer.mix_aspirate_depth_reference,
            "mix_dispense_depth_mm": transfer.mix_dispense_depth_mm,
            "mix_dispense_depth_reference": transfer.mix_dispense_depth_reference,
            "delay_air_gap_enabled": transfer.delay_air_gap_enabled,
            "post_aspirate_delay_seconds": transfer.post_aspirate_delay_seconds,
            "post_dispense_delay_seconds": transfer.post_dispense_delay_seconds,
            "pre_move_delay_seconds": transfer.pre_move_delay_seconds,
            "air_gap_enabled": transfer.air_gap_enabled,
            "air_gap_volume_ul": transfer.air_gap_volume_ul,
            "air_gap_height_mm": transfer.air_gap_height_mm,
            "air_gap_flow_rate": transfer.air_gap_flow_rate,
            "move_plate": transfer.move_plate,
            "move_labware_alias": transfer.move_labware_alias,
            "move_to_slot": transfer.move_to_slot,
            "move_use_gripper": transfer.move_use_gripper,
            "note": transfer.note,
            "batch_transfer_kind": transfer.batch_transfer_kind,
            "batch_source_wells": transfer.batch_source_wells,
        }

    def _autosave_selected_transfer_row(self, *_args):
        if self._loading_transfer_row or self._saving_transfer_row:
            return
        idx = self._editing_transfer_row_index
        if idx is None or not (0 <= idx < len(self.rows)):
            return
        if self._selected_row_index() != idx:
            self._editing_transfer_row_index = None
            return

        existing = self.rows[idx]
        is_batch = self._row_is_batch(existing)
        self._saving_transfer_row = True
        incomplete_reason = ""
        try:
            raw_row = self._row_with_raw_form_settings(existing)
            self.rows[idx] = raw_row
            if is_batch:
                saved_row = self._batch_row_with_common_form_settings(raw_row)
                incomplete_reason = self._batch_mapping_incomplete_reason(saved_row)
                if incomplete_reason:
                    saved_row["_draft"] = True
                else:
                    saved_row.pop("_draft", None)
            else:
                transfer = self._transfer_from_form(exclude_row_index=idx)
                saved_row = self._transfer_row_dict(transfer)
                for key in (
                    "sequence_id", "sequence_name", "sequence_order", "sequence_version",
                    "sequence_group_id", "sequence_group_name", "sequence_group_order", "sequence_row_order",
                    "sequence_sample_count_target",
                ):
                    if key in existing:
                        saved_row[key] = existing[key]
                saved_row.pop("_draft", None)
        except (TypeError, ValueError) as exc:
            saved_row = self.rows[idx]
            saved_row["_draft"] = True
            incomplete_reason = str(exc)
        finally:
            self._saving_transfer_row = False

        self.rows[idx] = saved_row
        if self.tree.exists(str(idx)):
            self.tree.item(str(idx), values=self._transfer_row_values(self.rows[idx], idx), tags=self._transfer_row_tags(self.rows[idx], idx))
        self._update_batch_chemical_summary(saved_row)
        if incomplete_reason:
            row_label = "Batch row" if is_batch else "Row"
            self.status_var.set(f"Incomplete {row_label.lower()} {idx + 1}: {incomplete_reason}")
        elif is_batch:
            self.status_var.set(
                f"Auto-saved common settings for batch row {idx + 1}; well mapping and Chemical IDs are unchanged."
            )
        else:
            self.status_var.set(f"Auto-saved Opentrons transfer row {idx + 1}.")

    def _row_with_raw_form_settings(self, existing: Dict[str, object]) -> Dict[str, object]:
        saved = deepcopy(existing)
        is_batch = self._row_is_batch(existing)
        saved.update({
            "step_name": self.step_name_var.get().strip(),
            "strategy": self.strategy_var.get(),
            "pipette_key": self.row_pipette_var.get().strip() or "Auto",
            "tip_policy": self._normalize_tip_policy(self.tip_policy_var.get()),
            "blowout_location": self.blowout_location_var.get(),
            "blowout_labware_alias": self.blowout_labware_alias_var.get().strip(),
            "blowout_well": self.blowout_well_var.get().strip().upper(),
            "aspirate_rate": self.aspirate_rate_var.get().strip(),
            "dispense_rate": self.dispense_rate_var.get().strip(),
            "aspirate_depth_mm": self.aspirate_depth_mm_var.get().strip(),
            "aspirate_depth_reference": self.aspirate_depth_reference_var.get(),
            "dispense_depth_mm": self.dispense_depth_mm_var.get().strip(),
            "dispense_depth_reference": self.dispense_depth_reference_var.get(),
            "multi_dispense_extra_percent": self.multi_dispense_extra_percent_var.get().strip(),
            "tip_touch": bool(self.tip_touch_var.get()),
            "pre_wet_tip": bool(self.pre_wet_tip_var.get()),
            "mix_enabled": bool(self.mix_enabled_var.get()),
            "mix_timing": self.mix_timing_var.get(),
            "mix_repetitions": self.mix_repetitions_var.get().strip(),
            "mix_volume_ul": self.mix_volume_var.get().strip(),
            "post_source_mix_delay_seconds": self.post_source_mix_delay_seconds_var.get().strip(),
            "mix_aspirate_rate": self.mix_aspirate_rate_var.get().strip(),
            "mix_dispense_rate": self.mix_dispense_rate_var.get().strip(),
            "mix_aspirate_depth_mm": self.mix_aspirate_depth_mm_var.get().strip(),
            "mix_aspirate_depth_reference": self.mix_aspirate_depth_reference_var.get(),
            "mix_dispense_depth_mm": self.mix_dispense_depth_mm_var.get().strip(),
            "mix_dispense_depth_reference": self.mix_dispense_depth_reference_var.get(),
            "delay_air_gap_enabled": bool(self.delay_air_gap_enabled_var.get()),
            "post_aspirate_delay_seconds": self.post_aspirate_delay_seconds_var.get().strip(),
            "post_dispense_delay_seconds": self.post_dispense_delay_seconds_var.get().strip(),
            "pre_move_delay_seconds": self.pre_move_delay_seconds_var.get().strip(),
            "air_gap_enabled": bool(self.air_gap_enabled_var.get()),
            "air_gap_volume_ul": self.air_gap_volume_var.get().strip(),
            "air_gap_height_mm": self.air_gap_height_var.get().strip() or "5",
            "air_gap_flow_rate": self.air_gap_flow_rate_var.get().strip(),
            "move_plate": bool(self.move_plate_var.get()),
            "move_labware_alias": self.move_labware_alias_var.get().strip(),
            "move_to_slot": self.move_to_slot_var.get().strip(),
            "move_use_gripper": bool(self.move_use_gripper_var.get()),
            "_draft": True,
        })
        if is_batch:
            saved.update({
                "chemical": "",
                "reaction_umol": "",
                "is_building_block": False,
            })
        else:
            saved.update({
                "chemical": self._chemical_id_from_label(self.chemical_var.get()),
                "reaction_umol": self.reaction_umol_var.get().strip(),
                "is_building_block": bool(self.is_building_block_var.get()),
                "volume_ul": self.volume_var.get().strip(),
                "source_labware_alias": self.source_labware_alias_var.get().strip(),
                "dest_labware_alias": self.dest_labware_alias_var.get().strip(),
                "source_well": self.source_well_var.get().strip().upper(),
                "dest_wells": self.dest_wells_var.get().strip().upper(),
            })
        return saved

    def _batch_mapping_incomplete_reason(self, row: Dict[str, object]) -> str:
        sources = self._batch_sources(row)
        if not sources:
            return "click Map to select batch source wells"
        destination_sets = self._batch_destination_groups(row)
        if not destination_sets:
            return "click Map to add at least one destination set"
        if any(len(group) != len(sources) for group in destination_sets):
            return "every destination set must contain one destination for each source"
        return ""

    def _basic_incomplete_row_reasons(self, row: Dict[str, object]) -> List[str]:
        reasons: List[str] = []
        if self._row_is_batch(row):
            mapping_reason = self._batch_mapping_incomplete_reason(row)
            if mapping_reason:
                reasons.append(mapping_reason)
            if not self._batch_has_complete_volumes(row):
                reasons.append("click Map to enter a positive volume for every source")
            elif (
                str(row.get("batch_transfer_kind", "") or "") == "8-channel"
                and self._batch_common_final_volume(row) is None
            ):
                reasons.append("8-channel sources must use the same final dispense volume")
        else:
            if not str(row.get("source_well", "") or "").strip():
                reasons.append("select a source well")
            if not str(row.get("dest_wells", "") or "").strip():
                reasons.append("select destination wells")
            try:
                if float(row.get("volume_ul", "")) <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                reasons.append("enter a positive dispense volume")
        return reasons

    def _incomplete_row_reason(self, row: Dict[str, object]) -> str:
        reasons = self._basic_incomplete_row_reasons(row)
        return "; ".join(reasons) or "finish or correct its row settings"

    def _incomplete_rows_message(self, action: str) -> str:
        details = [
            f"Row {index + 1}: {self._incomplete_row_reason(row)}"
            for index, row in enumerate(self.rows)
            if row.get("_draft")
        ]
        if not details:
            return ""
        return (
            f"Complete the following Opentrons row(s) before {action}:\n"
            + "\n".join(f"- {detail}" for detail in details)
        )

    def _batch_row_with_common_form_settings(self, existing: Dict[str, object]) -> Dict[str, object]:
        """Apply common form controls while preserving the batch's atomic well mapping."""
        tip_policy = self._normalize_tip_policy(self.tip_policy_var.get())
        self.tip_policy_var.set(tip_policy)
        if tip_policy not in TIP_POLICIES:
            raise ValueError("Tip policy must be Bin tip after row, Return tip to box, or Keep tip mounted.")
        if self.aspirate_depth_reference_var.get() not in TIP_DEPTH_REFERENCES:
            raise ValueError("Aspirate from must be from bottom or from top.")
        if self.dispense_depth_reference_var.get() not in TIP_DEPTH_REFERENCES:
            raise ValueError("Dispense from must be from bottom or from top.")
        self._optional_positive_float(self.aspirate_rate_var.get(), "Aspirate rate")
        self._optional_positive_float(self.dispense_rate_var.get(), "Dispense rate")
        self._optional_nonnegative_float_or_none(self.aspirate_depth_mm_var.get(), "Aspirate depth")
        self._optional_nonnegative_float_or_none(self.dispense_depth_mm_var.get(), "Dispense depth")
        self._optional_nonnegative_float(
            self.multi_dispense_extra_percent_var.get(), "Extra aspirate volume percentage"
        )
        mix_settings = self._validated_mix_settings(
            enabled=bool(self.mix_enabled_var.get()),
            strategy=self.strategy_var.get(),
            timing=self.mix_timing_var.get(),
            repetitions=self.mix_repetitions_var.get(),
            volume=self.mix_volume_var.get(),
            post_source_mix_delay=self.post_source_mix_delay_seconds_var.get(),
            aspirate_rate=self.mix_aspirate_rate_var.get(),
            dispense_rate=self.mix_dispense_rate_var.get(),
            aspirate_depth=self.mix_aspirate_depth_mm_var.get(),
            aspirate_reference=self.mix_aspirate_depth_reference_var.get(),
            dispense_depth=self.mix_dispense_depth_mm_var.get(),
            dispense_reference=self.mix_dispense_depth_reference_var.get(),
        )
        delay_air_gap_enabled = bool(self.delay_air_gap_enabled_var.get())
        delay_air_gap_settings = self._validated_delay_air_gap_settings(
            post_aspirate_delay=(self.post_aspirate_delay_seconds_var.get() if delay_air_gap_enabled else ""),
            post_dispense_delay=(self.post_dispense_delay_seconds_var.get() if delay_air_gap_enabled else ""),
            pre_move_delay=(self.pre_move_delay_seconds_var.get() if delay_air_gap_enabled else ""),
            air_gap_enabled=(delay_air_gap_enabled and bool(self.air_gap_enabled_var.get())),
            air_gap_volume=self.air_gap_volume_var.get(),
            air_gap_height=self.air_gap_height_var.get(),
            air_gap_flow_rate=self.air_gap_flow_rate_var.get(),
        )
        move_labware = self.move_labware_alias_var.get().strip()
        move_to_slot = self.move_to_slot_var.get().strip()
        if self.move_plate_var.get():
            if move_labware not in self._all_labware_aliases():
                raise ValueError("Select a valid labware alias to move.")
            robot = self.robot_var.get() if self.robot_var.get() in ROBOT_OPTIONS else "Flex"
            slots = FLEX_SLOTS if robot == "Flex" else OT2_SLOTS
            if move_to_slot not in slots and self._module_key_from_move_target(move_to_slot) is None:
                raise ValueError(f"Move target location {move_to_slot or '(blank)'} is not valid for {robot}.")
            self._validate_move_target_slot_available(move_labware, move_to_slot)

        pipette_choice = self.row_pipette_var.get().strip() or "Auto"
        batch_kind = str(existing.get("batch_transfer_kind", "") or "")
        execution_mount = (
            self._configured_batch_8_channel_mount(pipette_choice)
            if batch_kind == "8-channel"
            else ""
        )
        saved = deepcopy(existing)
        saved.update({
            "step_name": self.step_name_var.get().strip(),
            "strategy": self.strategy_var.get(),
            "pipette_key": pipette_choice,
            "batch_pipette_mount": execution_mount,
            "tip_policy": tip_policy,
            "blowout_location": self.blowout_location_var.get(),
            "blowout_labware_alias": self.blowout_labware_alias_var.get().strip(),
            "blowout_well": self.blowout_well_var.get().strip().upper(),
            "aspirate_rate": self.aspirate_rate_var.get().strip(),
            "dispense_rate": self.dispense_rate_var.get().strip(),
            "aspirate_depth_mm": self.aspirate_depth_mm_var.get().strip(),
            "aspirate_depth_reference": self.aspirate_depth_reference_var.get(),
            "dispense_depth_mm": self.dispense_depth_mm_var.get().strip(),
            "dispense_depth_reference": self.dispense_depth_reference_var.get(),
            "multi_dispense_extra_percent": self.multi_dispense_extra_percent_var.get().strip(),
            "tip_touch": bool(self.tip_touch_var.get()),
            "pre_wet_tip": bool(self.pre_wet_tip_var.get()),
            "mix_enabled": bool(mix_settings["mix_enabled"]),
            "mix_timing": str(mix_settings["mix_timing"]),
            "mix_repetitions": str(mix_settings["mix_repetitions"] or "3"),
            "mix_volume_ul": (
                str(mix_settings["mix_volume_ul"])
                if mix_settings["mix_volume_ul"] is not None
                else self.mix_volume_var.get().strip()
            ),
            "post_source_mix_delay_seconds": self.post_source_mix_delay_seconds_var.get().strip(),
            "mix_aspirate_rate": self.mix_aspirate_rate_var.get().strip(),
            "mix_dispense_rate": self.mix_dispense_rate_var.get().strip(),
            "mix_aspirate_depth_mm": self.mix_aspirate_depth_mm_var.get().strip(),
            "mix_aspirate_depth_reference": str(mix_settings["mix_aspirate_depth_reference"]),
            "mix_dispense_depth_mm": self.mix_dispense_depth_mm_var.get().strip(),
            "mix_dispense_depth_reference": str(mix_settings["mix_dispense_depth_reference"]),
            "delay_air_gap_enabled": delay_air_gap_enabled,
            "post_aspirate_delay_seconds": self.post_aspirate_delay_seconds_var.get().strip(),
            "post_dispense_delay_seconds": self.post_dispense_delay_seconds_var.get().strip(),
            "pre_move_delay_seconds": self.pre_move_delay_seconds_var.get().strip(),
            "air_gap_enabled": bool(self.air_gap_enabled_var.get()),
            "air_gap_volume_ul": (
                str(delay_air_gap_settings["air_gap_volume_ul"])
                if delay_air_gap_settings["air_gap_volume_ul"] is not None
                else self.air_gap_volume_var.get().strip()
            ),
            "air_gap_height_mm": (
                str(delay_air_gap_settings["air_gap_height_mm"])
                if delay_air_gap_settings["air_gap_enabled"]
                else (self.air_gap_height_var.get().strip() or "5")
            ),
            "air_gap_flow_rate": self.air_gap_flow_rate_var.get().strip(),
            "move_plate": bool(self.move_plate_var.get()),
            "move_labware_alias": move_labware,
            "move_to_slot": move_to_slot,
            "move_use_gripper": bool(self.move_use_gripper_var.get()),
        })
        return saved

    def _start_new_transfer(self, *, announce: bool = True, clear_step_name: bool = True):
        tree = getattr(self, "tree", None)
        self._loading_transfer_row = True
        if tree is not None:
            selected = tree.selection()
            if selected:
                tree.selection_remove(*selected)
            tree.focus("")
        try:
            if clear_step_name:
                self.step_name_var.set("")
            if self._is_batch_transfer_mode():
                self.source_well_var.set("")
                self.dest_wells_var.set("")
        finally:
            self._loading_transfer_row = False
        self._context_transfer_row_index = None
        self._editing_transfer_row_index = None
        self.transfer_mode_status_var.set("Create or select a transfer row to enable editing.")
        self._set_row_editor_enabled(False)
        if hasattr(self, "add_to_sequence_button"):
            self.add_to_sequence_button.configure(state="disabled")
        if hasattr(self, "ungroup_sequence_button"):
            self.ungroup_sequence_button.configure(state="disabled")
        if hasattr(self, "remove_row_button"):
            self.remove_row_button.configure(state="disabled")
        if announce:
            self.status_var.set("No row selected; the row editor is disabled.")

    def _selected_row_indices(self) -> List[int]:
        indices: List[int] = []
        for iid in self.tree.selection():
            try:
                idx = int(iid)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(self.rows):
                indices.append(idx)
        return sorted(set(indices))

    def _selected_row_index(self) -> Optional[int]:
        selected = self._selected_row_indices()
        if not selected:
            return None
        try:
            focused = int(self.tree.focus())
        except (TypeError, ValueError):
            focused = selected[0]
        return focused if focused in selected else selected[0]

    @staticmethod
    def _sequence_id(row: Dict[str, object]) -> str:
        return str(row.get("sequence_id", "") or "").strip()

    @staticmethod
    def _sequence_name(row: Dict[str, object]) -> str:
        return str(row.get("sequence_name", "") or "").strip() or "Sequence"

    @staticmethod
    def _sequence_group_id(row: Dict[str, object]) -> str:
        return str(row.get("sequence_group_id", "") or "").strip()

    @staticmethod
    def _sequence_group_name(row: Dict[str, object]) -> str:
        return str(row.get("sequence_group_name", "") or "").strip() or "Group"

    @staticmethod
    def _clear_sequence_metadata(row: Dict[str, object]) -> None:
        for key in (
            "sequence_id", "sequence_name", "sequence_order", "sequence_version",
            "sequence_group_id", "sequence_group_name", "sequence_group_order", "sequence_row_order",
            "sequence_sample_count_target",
        ):
            row.pop(key, None)

    def _sequence_row_indices(self, sequence_id: str) -> List[int]:
        return [idx for idx, row in enumerate(self.rows) if self._sequence_id(row) == sequence_id]

    def _sequence_group_ids(self, sequence_id: str) -> List[str]:
        group_ids: List[str] = []
        for idx in self._sequence_row_indices(sequence_id):
            group_id = self._sequence_group_id(self.rows[idx])
            if group_id and group_id not in group_ids:
                group_ids.append(group_id)
        return group_ids

    def _sequence_group_row_indices(self, group_id: str) -> List[int]:
        return [idx for idx, row in enumerate(self.rows) if self._sequence_group_id(row) == group_id]

    def _selected_sequence_ids(self) -> List[str]:
        sequence_ids: List[str] = []
        for iid in self.tree.selection():
            if str(iid).startswith("sequence:"):
                sequence_id = str(iid).split(":", 1)[1]
            elif str(iid).startswith("group:"):
                group_indices = self._sequence_group_row_indices(str(iid).split(":", 1)[1])
                sequence_id = self._sequence_id(self.rows[group_indices[0]]) if group_indices else ""
            else:
                try:
                    row = self.rows[int(iid)]
                except (TypeError, ValueError, IndexError):
                    continue
                sequence_id = self._sequence_id(row)
            if sequence_id and sequence_id not in sequence_ids:
                sequence_ids.append(sequence_id)
        return sequence_ids

    def _selected_group_ids(self) -> List[str]:
        group_ids: List[str] = []
        for iid in self.tree.selection():
            if str(iid).startswith("group:"):
                group_id = str(iid).split(":", 1)[1]
            else:
                try:
                    group_id = self._sequence_group_id(self.rows[int(iid)])
                except (TypeError, ValueError, IndexError):
                    continue
            if group_id and group_id not in group_ids:
                group_ids.append(group_id)
        return group_ids

    def _sync_sequence_order(self, sequence_id: str) -> None:
        indices = self._sequence_row_indices(sequence_id)
        group_ids = self._sequence_group_ids(sequence_id)
        sequence_name = self._sequence_name(self.rows[indices[0]]) if indices else "Sequence"
        existing_target = 0
        for idx in indices:
            try:
                candidate_target = int(float(self.rows[idx].get("sequence_sample_count_target", 0) or 0))
            except (TypeError, ValueError):
                continue
            if candidate_target > 0:
                existing_target = candidate_target
                break
        group_totals = [self._sequence_group_position_count(group_id) for group_id in group_ids]
        if group_totals and all(total > 0 and total == group_totals[0] for total in group_totals):
            sample_target = group_totals[0]
        elif existing_target > 0:
            sample_target = existing_target
        else:
            sample_target = group_totals[0] if group_totals else 0
        flat_order = 0
        for group_order, group_id in enumerate(group_ids, start=1):
            group_indices = self._sequence_group_row_indices(group_id)
            default_group_name = f"Group {group_order}"
            group_name = next(
                (
                    str(self.rows[idx].get("sequence_group_name", "") or "").strip()
                    for idx in group_indices
                    if str(self.rows[idx].get("sequence_group_name", "") or "").strip()
                ),
                default_group_name,
            )
            if re.fullmatch(r"Group\s+\d+", group_name, flags=re.IGNORECASE):
                group_name = default_group_name
            for row_order, idx in enumerate(group_indices, start=1):
                flat_order += 1
                self.rows[idx].update({
                    "sequence_id": sequence_id,
                    "sequence_name": sequence_name,
                    "sequence_order": flat_order,
                    "sequence_version": 2,
                    "sequence_group_id": group_id,
                    "sequence_group_name": group_name,
                    "sequence_group_order": group_order,
                    "sequence_row_order": row_order,
                    "sequence_sample_count_target": sample_target,
                })

    def _normalize_imported_sequences(self) -> None:
        sequence_ids = []
        for row in self.rows:
            sequence_id = self._sequence_id(row)
            if sequence_id and sequence_id not in sequence_ids:
                sequence_ids.append(sequence_id)
        for sequence_id in sequence_ids:
            indices = self._sequence_row_indices(sequence_id)
            contiguous = indices == list(range(indices[0], indices[-1] + 1)) if indices else False
            if not contiguous:
                for idx in indices:
                    self._clear_sequence_metadata(self.rows[idx])
                continue
            name = next(
                (self._sequence_name(self.rows[idx]) for idx in indices if self._sequence_name(self.rows[idx])),
                "Sequence",
            )
            for idx in indices:
                self.rows[idx]["sequence_name"] = name
                if not self._sequence_group_id(self.rows[idx]):
                    legacy_order = int(self.rows[idx].get("sequence_order", 0) or 0)
                    self.rows[idx]["sequence_group_id"] = uuid4().hex
                    self.rows[idx]["sequence_group_name"] = f"Group {legacy_order or indices.index(idx) + 1}"
                    self.rows[idx]["sequence_row_order"] = 1
            self._sync_sequence_order(sequence_id)

    def _create_sequence_from_selected(self):
        selected = self._selected_row_indices()
        if not selected:
            messagebox.showwarning("Opentrons", "Select at least one transfer row to create a Sequence.")
            return
        if selected != list(range(selected[0], selected[-1] + 1)):
            messagebox.showwarning("Opentrons", "Sequence child rows must be contiguous in the transfer plan.")
            return
        if any(self._sequence_id(self.rows[idx]) for idx in selected):
            messagebox.showwarning("Opentrons", "Ungroup rows from their current Sequence before regrouping them.")
            return
        default_name = f"Sequence {1 + len({self._sequence_id(row) for row in self.rows if self._sequence_id(row)})}"
        name = simpledialog.askstring(
            "Create Sequence",
            "Sequence name:",
            initialvalue=default_name,
            parent=self.winfo_toplevel(),
        )
        if name is None:
            return
        name = name.strip()
        if not name:
            messagebox.showwarning("Opentrons", "Sequence name cannot be blank.")
            return
        sequence_id = uuid4().hex
        for order, idx in enumerate(selected, start=1):
            self.rows[idx].update({
                "sequence_id": sequence_id,
                "sequence_name": name,
                "sequence_order": order,
                "sequence_version": 2,
                "sequence_group_id": uuid4().hex,
                "sequence_group_name": f"Group {order}",
                "sequence_group_order": order,
                "sequence_row_order": 1,
            })
        self._sync_sequence_order(sequence_id)
        self._refresh_table()
        parent_iid = f"sequence:{sequence_id}"
        if self.tree.exists(parent_iid):
            self.tree.item(parent_iid, open=True)
            self.tree.selection_set(parent_iid)
            self.tree.focus(parent_iid)
        self._on_transfer_row_select()
        self.status_var.set(f"Created Sequence '{name}' with {len(selected)} Group(s).")

    def _ungroup_selected_sequence(self):
        sequence_ids = self._selected_sequence_ids()
        selected_rows = self._selected_row_indices()
        if not sequence_ids:
            messagebox.showwarning("Opentrons", "Select a Sequence or one of its child rows first.")
            return
        if len(sequence_ids) != 1:
            messagebox.showwarning("Opentrons", "Ungroup rows from one Sequence at a time.")
            return
        sequence_id = sequence_ids[0]
        sequence_indices = self._sequence_row_indices(sequence_id)
        if any(f"sequence:{sequence_id}" == iid for iid in self.tree.selection()):
            affected = list(sequence_indices)
            for idx in affected:
                self._clear_sequence_metadata(self.rows[idx])
        else:
            affected = list(selected_rows)
            for group_id in self._selected_group_ids():
                if f"group:{group_id}" in self.tree.selection():
                    affected.extend(self._sequence_group_row_indices(group_id))
            affected = sorted(set(idx for idx in affected if idx in sequence_indices))
            if not affected:
                messagebox.showwarning("Opentrons", "Select a Sequence Group or child row to ungroup.")
                return
            extracted = [self.rows[idx] for idx in affected]
            first_sequence_index = min(sequence_indices)
            for idx in sorted(affected, reverse=True):
                del self.rows[idx]
            remaining = self._sequence_row_indices(sequence_id)
            insert_at = (max(remaining) + 1) if remaining else first_sequence_index
            for row in extracted:
                self._clear_sequence_metadata(row)
            self.rows[insert_at:insert_at] = extracted
            if remaining:
                self._sync_sequence_order(sequence_id)
        self._refresh_table()
        self._start_new_transfer(announce=False)
        self.status_var.set(f"Removed {len(set(affected))} row(s) from their Sequence.")

    def _rename_selected_sequence(self):
        sequence_ids = self._selected_sequence_ids()
        if len(sequence_ids) != 1:
            messagebox.showwarning("Opentrons", "Select exactly one Sequence to rename.")
            return
        sequence_id = sequence_ids[0]
        indices = self._sequence_row_indices(sequence_id)
        if not indices:
            return
        old_name = self._sequence_name(self.rows[indices[0]])
        name = simpledialog.askstring(
            "Rename Sequence",
            "Sequence name:",
            initialvalue=old_name,
            parent=self.winfo_toplevel(),
        )
        if name is None:
            return
        name = name.strip()
        if not name:
            messagebox.showwarning("Opentrons", "Sequence name cannot be blank.")
            return
        for idx in indices:
            self.rows[idx]["sequence_name"] = name
        self._refresh_table()
        parent_iid = f"sequence:{sequence_id}"
        if self.tree.exists(parent_iid):
            self.tree.item(parent_iid, open=True)
            self.tree.selection_set(parent_iid)
            self.tree.focus(parent_iid)
        self.status_var.set(f"Renamed Sequence '{old_name}' to '{name}'.")

    def _rename_selected_group(self):
        group_ids = self._selected_group_ids()
        if len(group_ids) != 1:
            messagebox.showwarning("Opentrons", "Select exactly one Sequence Group to rename.")
            return
        group_id = group_ids[0]
        indices = self._sequence_group_row_indices(group_id)
        if not indices:
            return
        old_name = self._sequence_group_name(self.rows[indices[0]])
        name = simpledialog.askstring(
            "Rename Sequence Group", "Group name:", initialvalue=old_name, parent=self.winfo_toplevel()
        )
        if name is None:
            return
        name = name.strip()
        if not name:
            messagebox.showwarning("Opentrons", "Group name cannot be blank.")
            return
        for idx in indices:
            self.rows[idx]["sequence_group_name"] = name
        self._sync_sequence_order(self._sequence_id(self.rows[indices[0]]))
        self._refresh_table()
        iid = f"group:{group_id}"
        if self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.focus(iid)
        self.status_var.set(f"Renamed Group '{old_name}' to '{name}'.")

    def _move_selected_sequence_group(self, direction: int):
        group_ids = self._selected_group_ids()
        if len(group_ids) != 1:
            messagebox.showwarning("Opentrons", "Select exactly one Sequence Group to move.")
            return
        group_id = group_ids[0]
        indices = self._sequence_group_row_indices(group_id)
        if not indices:
            return
        sequence_id = self._sequence_id(self.rows[indices[0]])
        groups = self._sequence_group_ids(sequence_id)
        position = groups.index(group_id)
        target_position = position + direction
        if not (0 <= target_position < len(groups)):
            return
        self._move_sequence_group_relative(
            group_id, groups[target_position], after=(direction > 0)
        )
        self._refresh_table()
        iid = f"group:{group_id}"
        if self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.focus(iid)
        self.status_var.set("Reordered Sequence Group.")

    def _move_selected_sequence_child(self, direction: int):
        selected = self._selected_row_indices()
        if len(selected) != 1:
            messagebox.showwarning("Opentrons", "Select exactly one Sequence child row to move.")
            return
        idx = selected[0]
        group_id = self._sequence_group_id(self.rows[idx])
        indices = self._sequence_group_row_indices(group_id) if group_id else []
        if idx not in indices:
            messagebox.showwarning("Opentrons", "The selected row is not part of a Sequence.")
            return
        position = indices.index(idx)
        target_position = position + direction
        if not (0 <= target_position < len(indices)):
            return
        target_idx = indices[target_position]
        self.rows[idx], self.rows[target_idx] = self.rows[target_idx], self.rows[idx]
        self._sync_sequence_order(self._sequence_id(self.rows[target_idx]))
        self._refresh_table()
        new_idx = target_idx
        if self.tree.exists(str(new_idx)):
            self.tree.selection_set(str(new_idx))
            self.tree.focus(str(new_idx))
            self.tree.see(str(new_idx))
        self._on_transfer_row_select()

    def _row_sequence_position_count(self, row: Dict[str, object]) -> int:
        try:
            return len(self._sequence_positions(row))
        except (TypeError, ValueError):
            return 0

    def _sequence_group_position_count(self, group_id: str) -> int:
        return sum(
            self._row_sequence_position_count(self.rows[idx])
            for idx in self._sequence_group_row_indices(group_id)
        )

    def _sequence_expected_position_count(self, sequence_id: str) -> int:
        indices = self._sequence_row_indices(sequence_id)
        if indices:
            try:
                target = int(float(self.rows[indices[0]].get("sequence_sample_count_target", 0) or 0))
            except (TypeError, ValueError):
                target = 0
            if target > 0:
                return target
        group_ids = self._sequence_group_ids(sequence_id)
        return self._sequence_group_position_count(group_ids[0]) if group_ids else 0

    def _place_rows_in_sequence(
        self,
        selected_indices: List[int],
        sequence_id: str,
        placement: str,
        *,
        target_group_id: str = "",
        target_row_index: Optional[int] = None,
    ) -> List[int]:
        selected_indices = sorted(set(selected_indices))
        if not selected_indices:
            raise ValueError("Select at least one transfer row to place in a Sequence.")
        if not all(0 <= idx < len(self.rows) for idx in selected_indices):
            raise ValueError("One of the selected transfer rows no longer exists.")
        destination_indices = self._sequence_row_indices(sequence_id)
        if not destination_indices:
            raise ValueError("The destination Sequence no longer exists.")
        destination_name = self._sequence_name(self.rows[destination_indices[0]])
        selected_rows = [self.rows[idx] for idx in selected_indices]
        target_row = self.rows[target_row_index] if target_row_index is not None else None
        if target_row is not None and any(target_row is row for row in selected_rows):
            raise ValueError("Choose an insertion row outside the rows being moved.")
        source_sequence_ids = {
            self._sequence_id(row) for row in selected_rows if self._sequence_id(row)
        }
        fallback_index = min(selected_indices)
        for idx in sorted(selected_indices, reverse=True):
            del self.rows[idx]

        destination_indices = self._sequence_row_indices(sequence_id)
        if placement.startswith("group_"):
            group_indices = self._sequence_group_row_indices(target_group_id)
            if not group_indices:
                raise ValueError("The destination Group no longer exists after removing the selected rows.")
            if placement == "group_start":
                insert_at = min(group_indices)
            elif placement == "group_end":
                insert_at = max(group_indices) + 1
            elif placement in {"group_before_row", "group_after_row"}:
                if target_row is None:
                    raise ValueError("Choose a destination row for this placement.")
                target_index = next(
                    (idx for idx, row in enumerate(self.rows) if row is target_row),
                    None,
                )
                if target_index is None or self._sequence_group_id(self.rows[target_index]) != target_group_id:
                    raise ValueError("The destination row no longer belongs to the selected Group.")
                insert_at = target_index + (1 if placement == "group_after_row" else 0)
            else:
                raise ValueError("Unsupported existing-Group placement.")
            group_name = self._sequence_group_name(self.rows[group_indices[0]])
            group_id = target_group_id
        else:
            destination_indices = self._sequence_row_indices(sequence_id)
            group_ids = self._sequence_group_ids(sequence_id)
            group_id = uuid4().hex
            group_name = f"Group {len(group_ids) + 1}"
            if not destination_indices:
                insert_at = fallback_index
            elif placement == "new_group_start":
                insert_at = min(destination_indices)
            elif placement == "new_group_end":
                insert_at = max(destination_indices) + 1
            elif placement in {"new_group_before", "new_group_after"}:
                group_indices = self._sequence_group_row_indices(target_group_id)
                if not group_indices:
                    raise ValueError("Choose an existing Group as the insertion reference.")
                insert_at = min(group_indices) if placement == "new_group_before" else max(group_indices) + 1
            else:
                raise ValueError("Unsupported new-Group placement.")

        for row_order, row in enumerate(selected_rows, start=1):
            self._clear_sequence_metadata(row)
            row.update({
                "sequence_id": sequence_id,
                "sequence_name": destination_name,
                "sequence_version": 2,
                "sequence_group_id": group_id,
                "sequence_group_name": group_name,
                "sequence_row_order": row_order,
            })
        self.rows[insert_at:insert_at] = selected_rows

        for source_sequence_id in source_sequence_ids | {sequence_id}:
            if self._sequence_row_indices(source_sequence_id):
                self._sync_sequence_order(source_sequence_id)
        return [
            next(idx for idx, candidate in enumerate(self.rows) if candidate is row)
            for row in selected_rows
        ]

    def _move_sequence_group_relative(self, group_id: str, target_group_id: str, *, after: bool) -> None:
        if group_id == target_group_id:
            return
        source_indices = self._sequence_group_row_indices(group_id)
        target_indices = self._sequence_group_row_indices(target_group_id)
        if not source_indices or not target_indices:
            raise ValueError("The dragged Group or destination Group no longer exists.")
        sequence_id = self._sequence_id(self.rows[source_indices[0]])
        if self._sequence_id(self.rows[target_indices[0]]) != sequence_id:
            raise ValueError("Move Groups between Sequences by moving their child rows with Add to Sequence.")
        sequence_indices = self._sequence_row_indices(sequence_id)
        groups = self._sequence_group_ids(sequence_id)
        groups.remove(group_id)
        target_position = groups.index(target_group_id) + (1 if after else 0)
        groups.insert(target_position, group_id)
        rows_by_group = {
            current_group_id: [self.rows[idx] for idx in self._sequence_group_row_indices(current_group_id)]
            for current_group_id in groups
        }
        reordered = [row for current_group_id in groups for row in rows_by_group[current_group_id]]
        start = min(sequence_indices)
        self.rows[start:start + len(sequence_indices)] = reordered
        self._sync_sequence_order(sequence_id)

    def _open_place_in_sequence_dialog(self):
        selected = self._selected_row_indices()
        if not selected:
            messagebox.showwarning("Opentrons", "Select one or more transfer rows to add or move.")
            return
        sequence_ids = []
        for row in self.rows:
            sequence_id = self._sequence_id(row)
            if sequence_id and sequence_id not in sequence_ids:
                sequence_ids.append(sequence_id)
        if not sequence_ids:
            messagebox.showwarning("Opentrons", "Create a Sequence before adding rows to it.")
            return

        win = tk.Toplevel(self)
        win.title("Place in Sequence")
        win.transient(self.winfo_toplevel())
        win.resizable(True, True)
        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=f"Place {len(selected)} selected row(s):", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        destination_tree = ttk.Treeview(body, show="tree", selectmode="browse", height=12)
        destination_tree.pack(fill="both", expand=True, pady=(6, 6))
        for sequence_id in sequence_ids:
            indices = self._sequence_row_indices(sequence_id)
            if not indices:
                continue
            sequence_iid = f"dest-sequence:{sequence_id}"
            destination_tree.insert("", "end", iid=sequence_iid, text=self._sequence_name(self.rows[indices[0]]), open=True)
            for group_id in self._sequence_group_ids(sequence_id):
                group_indices = self._sequence_group_row_indices(group_id)
                if not group_indices:
                    continue
                total = self._sequence_group_position_count(group_id)
                group_iid = f"dest-group:{group_id}"
                destination_tree.insert(
                    sequence_iid, "end", iid=group_iid,
                    text=f"{self._sequence_group_name(self.rows[group_indices[0]])} ({total} positions)", open=True,
                )
                for idx in group_indices:
                    label = str(self.rows[idx].get("step_name", "") or f"Row {idx + 1}")
                    destination_tree.insert(group_iid, "end", iid=f"dest-row:{idx}", text=label)

        placement_var = tk.StringVar()
        placement_combo = ttk.Combobox(body, textvariable=placement_var, state="readonly")
        placement_combo.pack(fill="x")
        preview_var = tk.StringVar(value="Select a Sequence, Group, or row destination.")
        ttk.Label(body, textvariable=preview_var, style="Muted.TLabel", wraplength=520, justify="left").pack(fill="x", pady=(6, 0))
        placement_codes: Dict[str, str] = {}

        def update_placements(_event=None):
            iid = destination_tree.focus()
            placement_codes.clear()
            if iid.startswith("dest-sequence:"):
                labels = ("Create new Group at beginning", "Create new Group at end")
                placement_codes.update({labels[0]: "new_group_start", labels[1]: "new_group_end"})
                sequence_id = iid.split(":", 1)[1]
                preview_var.set(
                    f"Sequence target: {self._sequence_name(self.rows[self._sequence_row_indices(sequence_id)[0]])}. "
                    "The selected rows will form one new Group."
                )
            elif iid.startswith("dest-group:"):
                labels = (
                    "Add at beginning of this Group", "Add at end of this Group",
                    "Create new Group before this Group", "Create new Group after this Group",
                )
                placement_codes.update({
                    labels[0]: "group_start", labels[1]: "group_end",
                    labels[2]: "new_group_before", labels[3]: "new_group_after",
                })
                group_id = iid.split(":", 1)[1]
                current = self._sequence_group_position_count(group_id)
                added = sum(self._row_sequence_position_count(self.rows[idx]) for idx in selected)
                expected = self._sequence_expected_position_count(
                    self._sequence_id(self.rows[self._sequence_group_row_indices(group_id)[0]])
                )
                preview_var.set(
                    f"Existing Group coverage: {current}/{expected or current}. Adding inside it would make "
                    f"{current + added}/{expected or current}; a new Group would start at {added}/{expected or current}."
                )
            elif iid.startswith("dest-row:"):
                labels = ("Insert before this row", "Insert after this row")
                placement_codes.update({labels[0]: "group_before_row", labels[1]: "group_after_row"})
                target_idx = int(iid.split(":", 1)[1])
                group_id = self._sequence_group_id(self.rows[target_idx])
                current = self._sequence_group_position_count(group_id)
                added = sum(self._row_sequence_position_count(self.rows[idx]) for idx in selected)
                expected = self._sequence_expected_position_count(self._sequence_id(self.rows[target_idx]))
                preview_var.set(
                    f"Insert within {self._sequence_group_name(self.rows[target_idx])}: coverage becomes "
                    f"{current + added}/{expected or current}. Following rows shift to later sample ranges."
                )
            else:
                labels = ()
            placement_combo.configure(values=labels)
            placement_var.set(labels[0] if labels else "")

        destination_tree.bind("<<TreeviewSelect>>", update_placements)
        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(10, 0))

        def apply_placement():
            iid = destination_tree.focus()
            code = placement_codes.get(placement_var.get(), "")
            if not iid or not code:
                messagebox.showwarning("Opentrons", "Choose a destination and placement.", parent=win)
                return
            if iid.startswith("dest-sequence:"):
                sequence_id = iid.split(":", 1)[1]
                target_group_id = ""
                target_row_index = None
            elif iid.startswith("dest-group:"):
                target_group_id = iid.split(":", 1)[1]
                group_indices = self._sequence_group_row_indices(target_group_id)
                sequence_id = self._sequence_id(self.rows[group_indices[0]])
                target_row_index = None
            else:
                target_row_index = int(iid.split(":", 1)[1])
                target_group_id = self._sequence_group_id(self.rows[target_row_index])
                sequence_id = self._sequence_id(self.rows[target_row_index])
            source_sequences = {
                self._sequence_id(self.rows[idx]) for idx in selected if self._sequence_id(self.rows[idx])
            }
            if any(source_sequence != sequence_id for source_sequence in source_sequences):
                if not messagebox.askyesno(
                    "Move between Sequences",
                    "Move the selected row(s) out of their current Sequence and into the chosen Sequence?",
                    parent=win,
                ):
                    return
            try:
                moved_indices = self._place_rows_in_sequence(
                    selected, sequence_id, code,
                    target_group_id=target_group_id,
                    target_row_index=target_row_index,
                )
            except ValueError as exc:
                messagebox.showwarning("Opentrons", str(exc), parent=win)
                return
            win.destroy()
            self._refresh_table()
            moved_iids = [str(idx) for idx in moved_indices]
            self.tree.selection_set(moved_iids)
            self.tree.focus(moved_iids[0])
            self.tree.see(moved_iids[-1])
            self._on_transfer_row_select()
            self.status_var.set(f"Placed {len(moved_indices)} row(s) in the selected Sequence location.")

        ttk.Button(actions, text="Place", command=apply_placement, style="ChemAction.TButton").pack(side="right")
        ttk.Button(actions, text="Cancel", command=win.destroy).pack(side="right", padx=(0, 6))
        first_sequence = destination_tree.get_children("")[0]
        destination_tree.selection_set(first_sequence)
        destination_tree.focus(first_sequence)
        update_placements()
        win.grab_set()
        win.wait_window()

    def _clear_plan_drop_target(self) -> None:
        target = getattr(self, "_plan_drag_target_iid", "")
        if target and self.tree.exists(target):
            self.tree.item(target, tags=())
        self._plan_drag_target_iid = ""

    def _on_plan_drag_start(self, event):
        iid = self.tree.identify_row(event.y)
        self._plan_drag_start_xy = (event.x, event.y)
        self._plan_drag_source_iid = iid
        self._plan_drag_moved = False
        self._clear_plan_drop_target()
        if not iid or iid.startswith("sequence:"):
            return
        if iid not in self.tree.selection():
            self.tree.selection_set(iid)
            self.tree.focus(iid)

    def _on_plan_drag_motion(self, event):
        source_iid = getattr(self, "_plan_drag_source_iid", "")
        start_xy = getattr(self, "_plan_drag_start_xy", (event.x, event.y))
        if not source_iid or source_iid.startswith("sequence:"):
            return
        if abs(event.x - start_xy[0]) + abs(event.y - start_xy[1]) < 6:
            return
        self._plan_drag_moved = True
        tree_height = self.tree.winfo_height()
        if event.y < 24:
            self.tree.yview_scroll(-1, "units")
        elif event.y > tree_height - 24:
            self.tree.yview_scroll(1, "units")
        target_iid = self.tree.identify_row(event.y)
        if not target_iid or target_iid == source_iid:
            self._clear_plan_drop_target()
            return
        if target_iid != getattr(self, "_plan_drag_target_iid", ""):
            self._clear_plan_drop_target()
            self._plan_drag_target_iid = target_iid
            if self.tree.exists(target_iid):
                self.tree.item(target_iid, tags=("drop_target",))
        if target_iid.startswith("sequence:"):
            hint = "Drop to create a new Group at the end of this Sequence."
        elif target_iid.startswith("group:"):
            bbox = self.tree.bbox(target_iid)
            relative_y = event.y - bbox[1] if bbox else 0
            if bbox and relative_y < bbox[3] / 3:
                hint = "Drop to create a new Group before this Group."
            elif bbox and relative_y > bbox[3] * 2 / 3:
                hint = "Drop to create a new Group after this Group."
            else:
                hint = "Drop to append to this Group."
        else:
            bbox = self.tree.bbox(target_iid)
            after = bool(bbox and event.y >= bbox[1] + bbox[3] / 2)
            hint = f"Drop to insert {'after' if after else 'before'} this row."
        self.status_var.set(hint)

    def _on_plan_drag_release(self, event):
        source_iid = getattr(self, "_plan_drag_source_iid", "")
        target_iid = getattr(self, "_plan_drag_target_iid", "")
        moved = bool(getattr(self, "_plan_drag_moved", False))
        self._plan_drag_source_iid = ""
        self._plan_drag_moved = False
        self._clear_plan_drop_target()
        if not moved or not source_iid or not target_iid or not self.tree.exists(target_iid):
            return
        try:
            if source_iid.startswith("group:"):
                if not target_iid.startswith("group:"):
                    raise ValueError("Drop a Group above or below another Group in the same Sequence.")
                source_group_id = source_iid.split(":", 1)[1]
                target_group_id = target_iid.split(":", 1)[1]
                bbox = self.tree.bbox(target_iid)
                after = bool(bbox and event.y >= bbox[1] + bbox[3] / 2)
                self._move_sequence_group_relative(source_group_id, target_group_id, after=after)
                self._refresh_table()
                moved_iid = f"group:{source_group_id}"
                if self.tree.exists(moved_iid):
                    self.tree.selection_set(moved_iid)
                    self.tree.focus(moved_iid)
                self.status_var.set("Reordered Sequence Group.")
                return

            selected = self._selected_row_indices()
            if not selected:
                try:
                    selected = [int(source_iid)]
                except ValueError:
                    raise ValueError("Drag transfer rows or Group headers, not the Sequence header.")
            if target_iid.startswith("sequence:"):
                sequence_id = target_iid.split(":", 1)[1]
                placement = "new_group_end"
                target_group_id = ""
                target_row_index = None
            elif target_iid.startswith("group:"):
                target_group_id = target_iid.split(":", 1)[1]
                group_indices = self._sequence_group_row_indices(target_group_id)
                sequence_id = self._sequence_id(self.rows[group_indices[0]])
                bbox = self.tree.bbox(target_iid)
                relative_y = event.y - bbox[1] if bbox else 0
                if bbox and relative_y < bbox[3] / 3:
                    placement = "new_group_before"
                elif bbox and relative_y > bbox[3] * 2 / 3:
                    placement = "new_group_after"
                else:
                    placement = "group_end"
                target_row_index = None
            else:
                target_row_index = int(target_iid)
                target_group_id = self._sequence_group_id(self.rows[target_row_index])
                if not target_group_id:
                    raise ValueError("Drop onto a Sequence, Group, or Sequence child row.")
                sequence_id = self._sequence_id(self.rows[target_row_index])
                bbox = self.tree.bbox(target_iid)
                placement = "group_after_row" if bbox and event.y >= bbox[1] + bbox[3] / 2 else "group_before_row"
            source_sequences = {
                self._sequence_id(self.rows[idx]) for idx in selected if self._sequence_id(self.rows[idx])
            }
            if any(source_sequence != sequence_id for source_sequence in source_sequences):
                if not messagebox.askyesno(
                    "Move between Sequences",
                    "Move the dragged row(s) into the destination Sequence?",
                ):
                    return
            moved_indices = self._place_rows_in_sequence(
                selected, sequence_id, placement,
                target_group_id=target_group_id,
                target_row_index=target_row_index,
            )
            self._refresh_table()
            moved_iids = [str(idx) for idx in moved_indices]
            self.tree.selection_set(moved_iids)
            self.tree.focus(moved_iids[0])
            self.tree.see(moved_iids[-1])
            self._on_transfer_row_select()
            self.status_var.set(f"Moved {len(moved_indices)} row(s) within the Sequence plan.")
        except ValueError as exc:
            messagebox.showwarning("Opentrons", str(exc))

    def _copy_selected_transfer_rows(self, _event=None):
        selected = self._selected_row_indices()
        if not selected:
            self.status_var.set("Select one or more transfer rows to copy.")
            return "break"
        self._copied_transfer_rows = [deepcopy(self.rows[idx]) for idx in selected]
        count = len(self._copied_transfer_rows)
        self.status_var.set(f"Copied {count} transfer row{'s' if count != 1 else ''}.")
        return "break"

    def _paste_copied_transfer_rows(self, _event=None, *, anchor_index: Optional[int] = None):
        if not self._copied_transfer_rows:
            self.status_var.set("Copy one or more transfer rows before pasting.")
            return "break"
        if anchor_index is None or not (0 <= anchor_index < len(self.rows)):
            anchor_index = self._selected_row_index()
        if anchor_index is None:
            self.status_var.set("Select the transfer row after which the copied rows should be pasted.")
            return "break"

        anchor_sequence_id = self._sequence_id(self.rows[anchor_index])
        if anchor_sequence_id:
            anchor_index = max(self._sequence_row_indices(anchor_sequence_id))

        inserted_rows = [deepcopy(row) for row in self._copied_transfer_rows]
        for row in inserted_rows:
            self._clear_sequence_metadata(row)
        insert_at = anchor_index + 1
        self.rows[insert_at:insert_at] = inserted_rows
        self._refresh_table()
        inserted_iids = [str(idx) for idx in range(insert_at, insert_at + len(inserted_rows))]
        self.tree.selection_set(inserted_iids)
        self.tree.focus(inserted_iids[0])
        self.tree.see(inserted_iids[-1])
        self._context_transfer_row_index = None
        self._on_transfer_row_select()
        count = len(inserted_rows)
        self.status_var.set(
            f"Pasted {count} transfer row{'s' if count != 1 else ''} after row {anchor_index + 1}."
        )
        return "break"

    def _show_transfer_plan_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            if iid not in self.tree.selection():
                self.tree.selection_set(iid)
            self.tree.focus(iid)
            try:
                self._context_transfer_row_index = int(iid)
            except ValueError:
                self._context_transfer_row_index = None
        else:
            self._context_transfer_row_index = self._selected_row_index()

        menu = tk.Menu(self, tearoff=False)
        menu.add_command(
            label="Copy selected rows",
            command=self._copy_selected_transfer_rows,
            state=("normal" if self._selected_row_indices() else "disabled"),
        )
        menu.add_command(
            label="Paste rows after selected",
            command=lambda anchor_index=self._context_transfer_row_index: self._paste_copied_transfer_rows(
                anchor_index=anchor_index
            ),
            state=(
                "normal"
                if self._copied_transfer_rows and self._context_transfer_row_index is not None
                else "disabled"
            ),
        )
        menu.add_separator()
        menu.add_command(
            label="Create Sequence from selected rows",
            command=self._create_sequence_from_selected,
            state=("normal" if self._selected_row_indices() else "disabled"),
        )
        menu.add_command(
            label="Add / move selected rows to Sequence...",
            command=self._open_place_in_sequence_dialog,
            state=("normal" if self._selected_row_indices() else "disabled"),
        )
        menu.add_command(
            label="Rename Sequence",
            command=self._rename_selected_sequence,
            state=("normal" if len(self._selected_sequence_ids()) == 1 else "disabled"),
        )
        menu.add_command(
            label="Ungroup selected Sequence row(s)",
            command=self._ungroup_selected_sequence,
            state=("normal" if self._selected_sequence_ids() else "disabled"),
        )
        menu.add_command(
            label="Rename Group",
            command=self._rename_selected_group,
            state=("normal" if len(self._selected_group_ids()) == 1 else "disabled"),
        )
        menu.add_command(
            label="Move Group up",
            command=lambda: self._move_selected_sequence_group(-1),
            state=("normal" if len(self._selected_group_ids()) == 1 else "disabled"),
        )
        menu.add_command(
            label="Move Group down",
            command=lambda: self._move_selected_sequence_group(1),
            state=("normal" if len(self._selected_group_ids()) == 1 else "disabled"),
        )
        menu.add_command(
            label="Move Sequence child up",
            command=lambda: self._move_selected_sequence_child(-1),
            state=("normal" if len(self._selected_row_indices()) == 1 and self._selected_sequence_ids() else "disabled"),
        )
        menu.add_command(
            label="Move Sequence child down",
            command=lambda: self._move_selected_sequence_child(1),
            state=("normal" if len(self._selected_row_indices()) == 1 and self._selected_sequence_ids() else "disabled"),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _on_transfer_row_select(self, _event=None):
        idx = self._selected_row_index()
        if idx is None:
            self._editing_transfer_row_index = None
            self._set_row_editor_enabled(False)
            sequence_ids = self._selected_sequence_ids()
            if sequence_ids:
                sequence_id = sequence_ids[0]
                indices = self._sequence_row_indices(sequence_id)
                name = self._sequence_name(self.rows[indices[0]]) if indices else "Sequence"
                group_ids = self._selected_group_ids()
                if group_ids:
                    group_id = group_ids[0]
                    group_indices = self._sequence_group_row_indices(group_id)
                    group_name = self._sequence_group_name(self.rows[group_indices[0]]) if group_indices else "Group"
                    total = self._sequence_group_position_count(group_id)
                    expected = self._sequence_expected_position_count(sequence_id)
                    self.transfer_mode_status_var.set(
                        f"{group_name} selected; select a child row to edit its existing settings."
                    )
                    self.status_var.set(f"{name} / {group_name}: {total}/{expected or total} sample positions.")
                else:
                    self.transfer_mode_status_var.set(
                        f"Sequence '{name}' selected; select a Group or child row to edit."
                    )
                    self.status_var.set(
                        f"Sequence '{name}' contains {len(self._sequence_group_ids(sequence_id))} Group(s) and {len(indices)} row(s)."
                    )
            else:
                self.transfer_mode_status_var.set("Create or select a transfer row to enable editing.")
            self.remove_row_button.configure(state="normal" if self.tree.selection() else "disabled")
            self.ungroup_sequence_button.configure(state="normal" if sequence_ids else "disabled")
            self.add_to_sequence_button.configure(state="disabled")
            return
        row = self.rows[idx]
        is_batch = self._row_is_batch(row)
        self._editing_transfer_row_index = idx
        self._set_transfer_type(is_batch)
        self.transfer_mode_status_var.set(
            f"Editing batch row {idx + 1}. Common edits stay in the project; use Map for well assignments."
            if is_batch
            else f"Editing single row {idx + 1}. Edits stay in the project; Export Project saves a file."
        )
        self._loading_transfer_row = True
        try:
            self.step_name_var.set(str(row.get("step_name", "") or ""))
            self.chemical_var.set(str(row.get("chemical", "") or ""))
            self.reaction_umol_var.set(str(row.get("reaction_umol", "") or ""))
            self.is_building_block_var.set(coerce_bool(row.get("is_building_block", False)))
            self.source_well_var.set(
                str(row.get("batch_source_wells", "") or row.get("source_well", "") or "")
                if is_batch
                else str(row.get("source_well", "") or "")
            )
            self.dest_wells_var.set(str(row.get("dest_wells", "") or ""))
            if is_batch and coerce_bool(row.get("_draft", False)):
                self.source_labware_alias_var.set(str(row.get("source_labware_alias", "") or ""))
                self.dest_labware_alias_var.set(str(row.get("dest_labware_alias", "") or ""))
            else:
                self.source_labware_alias_var.set(str(row.get("source_labware_alias", self.source_labware_alias_var.get()) or "source1"))
                self.dest_labware_alias_var.set(str(row.get("dest_labware_alias", self.dest_labware_alias_var.get()) or "dest1"))
            volume = self._batch_common_final_volume(row) if is_batch else row.get("volume_ul", "")
            if volume in (None, ""):
                volume_text = ""
            else:
                try:
                    volume_text = f"{float(volume):.1f}"
                except (TypeError, ValueError):
                    volume_text = str(volume)
            self.volume_var.set(volume_text)
            self.strategy_var.set(str(row.get("strategy", "Multi-dispense") or "Multi-dispense"))
            self.row_pipette_var.set(str(row.get("pipette_key", "Auto") or "Auto"))
            self.tip_policy_var.set(self._normalize_tip_policy(row.get("tip_policy", self.tip_policy_var.get())))
            self.blowout_location_var.set(str(row.get("blowout_location", "No blowout") or "No blowout"))
            self.blowout_labware_alias_var.set(str(row.get("blowout_labware_alias", "") or ""))
            self.blowout_well_var.set(str(row.get("blowout_well", "") or ""))
            self.aspirate_rate_var.set(str(row.get("aspirate_rate", "") or ""))
            self.dispense_rate_var.set(str(row.get("dispense_rate", "") or ""))
            self.aspirate_depth_mm_var.set(str(row.get("aspirate_depth_mm", "") or ""))
            self.aspirate_depth_reference_var.set(str(row.get("aspirate_depth_reference", "from bottom") or "from bottom"))
            self.dispense_depth_mm_var.set(str(row.get("dispense_depth_mm", "") or ""))
            self.dispense_depth_reference_var.set(str(row.get("dispense_depth_reference", "from top") or "from top"))
            self.multi_dispense_extra_percent_var.set(str(row.get("multi_dispense_extra_percent", "0") or "0"))
            self.tip_touch_var.set(bool(row.get("tip_touch", False)))
            self.pre_wet_tip_var.set(bool(row.get("pre_wet_tip", False)))
            self.mix_enabled_var.set(bool(row.get("mix_enabled", False)))
            self.mix_timing_var.set(str(row.get("mix_timing", "Before aspirating") or "Before aspirating"))
            self.mix_repetitions_var.set(str(row.get("mix_repetitions", "3") or "3"))
            self.mix_volume_var.set(str(row.get("mix_volume_ul", "") or ""))
            self.post_source_mix_delay_seconds_var.set(str(row.get("post_source_mix_delay_seconds", "") or ""))
            self.mix_aspirate_rate_var.set(str(row.get("mix_aspirate_rate", "") or ""))
            self.mix_dispense_rate_var.set(str(row.get("mix_dispense_rate", "") or ""))
            self.mix_aspirate_depth_mm_var.set(str(row.get("mix_aspirate_depth_mm", "") or ""))
            self.mix_aspirate_depth_reference_var.set(str(row.get("mix_aspirate_depth_reference", "from bottom") or "from bottom"))
            self.mix_dispense_depth_mm_var.set(str(row.get("mix_dispense_depth_mm", "") or ""))
            self.mix_dispense_depth_reference_var.set(str(row.get("mix_dispense_depth_reference", "from bottom") or "from bottom"))
            self.delay_air_gap_enabled_var.set(self._delay_air_gap_feature_enabled(row))
            self.post_aspirate_delay_seconds_var.set(str(row.get("post_aspirate_delay_seconds", "") or ""))
            self.post_dispense_delay_seconds_var.set(str(row.get("post_dispense_delay_seconds", "") or ""))
            self.pre_move_delay_seconds_var.set(str(row.get("pre_move_delay_seconds", "") or ""))
            self.air_gap_enabled_var.set(bool(row.get("air_gap_enabled", False)))
            self.air_gap_volume_var.set(str(row.get("air_gap_volume_ul", "") or ""))
            self.air_gap_height_var.set(str(row.get("air_gap_height_mm", "5") or "5"))
            self.air_gap_flow_rate_var.set(str(row.get("air_gap_flow_rate", "") or ""))
            self.move_plate_var.set(bool(row.get("move_plate", False)))
            self.move_labware_alias_var.set(str(row.get("move_labware_alias", self.dest_labware_alias_var.get()) or ""))
            self.move_to_slot_var.set(str(row.get("move_to_slot", "") or ""))
            self.move_use_gripper_var.set(bool(row.get("move_use_gripper", False)))
        finally:
            self._loading_transfer_row = False
        self._update_batch_chemical_summary(row)
        self._set_row_editor_enabled(True)
        self.remove_row_button.configure(state="normal")
        self.add_to_sequence_button.configure(state="normal")
        self.ungroup_sequence_button.configure(
            state="normal" if self._sequence_id(row) else "disabled"
        )
        self.status_var.set(
            f"Editing {'incomplete ' if row.get('_draft') else ''}{'batch' if is_batch else 'single'} row {idx + 1}; changes save automatically."
        )

    def _update_batch_chemical_summary(self, row: Optional[Dict[str, object]] = None):
        if not hasattr(self, "batch_chemical_summary_var"):
            return
        if row is None:
            idx = self._selected_row_index() if hasattr(self, "tree") else None
            row = self.rows[idx] if idx is not None and 0 <= idx < len(self.rows) else None
        if not row or not self._row_is_batch(row):
            self.batch_chemical_summary_var.set("Chemical IDs: mapping required")
            return
        sources = self._batch_sources(row)
        chemical_map = self._batch_chemical_map(row)
        assigned = sum(1 for source in sources if chemical_map.get(source, ""))
        if not sources:
            summary = "Chemical IDs: mapping required — View/Edit in Map"
        else:
            summary = f"Chemical IDs: {assigned} assigned, {len(sources) - assigned} blank — View/Edit in Map"
        self.batch_chemical_summary_var.set(summary)

    def _transfer_from_form(self, *, exclude_row_index: Optional[int] = None) -> OpentronsTransferRow:
        source_well = self.source_well_var.get().strip().upper()
        source_labware = self._selected_source_labware()
        dest_labware = self._selected_dest_labware()
        dest_wells = ",".join(_parse_wells(self.dest_wells_var.get(), dest_labware.get("map_style", self.dest_style_var.get())))
        if not source_well:
            raise ValueError("Source well is required.")
        if not dest_wells:
            raise ValueError("Select at least one destination well.")
        volume = self._required_positive_float(self.volume_var.get(), "Dispense volume/uL")
        parsed_source_wells = _parse_wells(source_well, source_labware.get("map_style", self.source_style_var.get()))
        if len(parsed_source_wells) != 1:
            raise ValueError("Source well must be a single well.")
        chemical_id = self._chemical_id_from_label(self.chemical_var.get())
        conflict = self._source_well_conflict(
            source_labware.get("alias", ""),
            parsed_source_wells[0],
            chemical_id,
            exclude_row_index=exclude_row_index,
        )
        if conflict:
            raise ValueError(conflict)
        tip_policy = self._normalize_tip_policy(self.tip_policy_var.get())
        self.tip_policy_var.set(tip_policy)
        if tip_policy not in TIP_POLICIES:
            raise ValueError("Tip policy must be Bin tip after row, Return tip to box, or Keep tip mounted.")
        if self.aspirate_depth_reference_var.get() not in TIP_DEPTH_REFERENCES:
            raise ValueError("Aspirate from must be from bottom or from top.")
        if self.dispense_depth_reference_var.get() not in TIP_DEPTH_REFERENCES:
            raise ValueError("Dispense from must be from bottom or from top.")
        self._optional_positive_float(self.aspirate_rate_var.get(), "Aspirate rate")
        self._optional_positive_float(self.dispense_rate_var.get(), "Dispense rate")
        self._optional_nonnegative_float_or_none(self.aspirate_depth_mm_var.get(), "Aspirate depth")
        self._optional_nonnegative_float_or_none(self.dispense_depth_mm_var.get(), "Dispense depth")
        self._optional_nonnegative_float(self.multi_dispense_extra_percent_var.get(), "Extra aspirate volume percentage")
        mix_settings = self._validated_mix_settings(
            enabled=bool(self.mix_enabled_var.get()),
            strategy=self.strategy_var.get(),
            timing=self.mix_timing_var.get(),
            repetitions=self.mix_repetitions_var.get(),
            volume=self.mix_volume_var.get(),
            post_source_mix_delay=self.post_source_mix_delay_seconds_var.get(),
            aspirate_rate=self.mix_aspirate_rate_var.get(),
            dispense_rate=self.mix_dispense_rate_var.get(),
            aspirate_depth=self.mix_aspirate_depth_mm_var.get(),
            aspirate_reference=self.mix_aspirate_depth_reference_var.get(),
            dispense_depth=self.mix_dispense_depth_mm_var.get(),
            dispense_reference=self.mix_dispense_depth_reference_var.get(),
        )
        delay_air_gap_feature_enabled = bool(self.delay_air_gap_enabled_var.get())
        delay_air_gap_settings = self._validated_delay_air_gap_settings(
            post_aspirate_delay=(self.post_aspirate_delay_seconds_var.get() if delay_air_gap_feature_enabled else ""),
            post_dispense_delay=(self.post_dispense_delay_seconds_var.get() if delay_air_gap_feature_enabled else ""),
            pre_move_delay=(self.pre_move_delay_seconds_var.get() if delay_air_gap_feature_enabled else ""),
            air_gap_enabled=(delay_air_gap_feature_enabled and bool(self.air_gap_enabled_var.get())),
            air_gap_volume=self.air_gap_volume_var.get(),
            air_gap_height=self.air_gap_height_var.get(),
            air_gap_flow_rate=self.air_gap_flow_rate_var.get(),
        )
        move_labware = self.move_labware_alias_var.get().strip()
        move_to_slot = self.move_to_slot_var.get().strip()
        if self.move_plate_var.get():
            if move_labware not in self._all_labware_aliases():
                raise ValueError("Select a valid labware alias to move.")
            robot = self.robot_var.get() if self.robot_var.get() in ROBOT_OPTIONS else "Flex"
            slots = FLEX_SLOTS if robot == "Flex" else OT2_SLOTS
            if move_to_slot not in slots and self._module_key_from_move_target(move_to_slot) is None:
                raise ValueError(f"Move target location {move_to_slot or '(blank)'} is not valid for {robot}.")
            self._validate_move_target_slot_available(move_labware, move_to_slot)
        return OpentronsTransferRow(
            step_name=self.step_name_var.get().strip(),
            chemical=chemical_id,
            reaction_umol=self.reaction_umol_var.get().strip(),
            is_building_block=bool(self.is_building_block_var.get()),
            source_well=parsed_source_wells[0],
            dest_wells=dest_wells,
            volume_ul=volume,
            strategy=self.strategy_var.get(),
            pipette_key=self.row_pipette_var.get().strip() or "Auto",
            source_labware_alias=source_labware.get("alias", ""),
            dest_labware_alias=dest_labware.get("alias", ""),
            tip_policy=tip_policy,
            blowout_location=self.blowout_location_var.get(),
            blowout_labware_alias=self.blowout_labware_alias_var.get().strip(),
            blowout_well=self.blowout_well_var.get().strip().upper(),
            aspirate_rate=self.aspirate_rate_var.get().strip(),
            dispense_rate=self.dispense_rate_var.get().strip(),
            aspirate_depth_mm=self.aspirate_depth_mm_var.get().strip(),
            aspirate_depth_reference=self.aspirate_depth_reference_var.get(),
            dispense_depth_mm=self.dispense_depth_mm_var.get().strip(),
            dispense_depth_reference=self.dispense_depth_reference_var.get(),
            multi_dispense_extra_percent=self.multi_dispense_extra_percent_var.get().strip(),
            tip_touch=bool(self.tip_touch_var.get()),
            pre_wet_tip=bool(self.pre_wet_tip_var.get()),
            mix_enabled=bool(mix_settings["mix_enabled"]),
            mix_timing=str(mix_settings["mix_timing"]),
            mix_repetitions=str(mix_settings["mix_repetitions"] or "3"),
            mix_volume_ul=(str(mix_settings["mix_volume_ul"]) if mix_settings["mix_volume_ul"] is not None else ""),
            post_source_mix_delay_seconds=self.post_source_mix_delay_seconds_var.get().strip(),
            mix_aspirate_rate=self.mix_aspirate_rate_var.get().strip(),
            mix_dispense_rate=self.mix_dispense_rate_var.get().strip(),
            mix_aspirate_depth_mm=self.mix_aspirate_depth_mm_var.get().strip(),
            mix_aspirate_depth_reference=str(mix_settings["mix_aspirate_depth_reference"]),
            mix_dispense_depth_mm=self.mix_dispense_depth_mm_var.get().strip(),
            mix_dispense_depth_reference=str(mix_settings["mix_dispense_depth_reference"]),
            delay_air_gap_enabled=delay_air_gap_feature_enabled,
            post_aspirate_delay_seconds=self.post_aspirate_delay_seconds_var.get().strip(),
            post_dispense_delay_seconds=self.post_dispense_delay_seconds_var.get().strip(),
            pre_move_delay_seconds=self.pre_move_delay_seconds_var.get().strip(),
            air_gap_enabled=bool(self.air_gap_enabled_var.get()),
            air_gap_volume_ul=(
                str(delay_air_gap_settings["air_gap_volume_ul"])
                if delay_air_gap_settings["air_gap_volume_ul"] is not None
                else self.air_gap_volume_var.get().strip()
            ),
            air_gap_height_mm=(
                str(delay_air_gap_settings["air_gap_height_mm"])
                if delay_air_gap_settings["air_gap_enabled"]
                else (self.air_gap_height_var.get().strip() or "5")
            ),
            air_gap_flow_rate=self.air_gap_flow_rate_var.get().strip(),
            move_plate=bool(self.move_plate_var.get()),
            move_labware_alias=move_labware,
            move_to_slot=move_to_slot,
            move_use_gripper=bool(self.move_use_gripper_var.get()),
            note=self.notes_var.get().strip(),
        )

    def _chemical_id_from_label(self, label: object) -> str:
        text = str(label or "").strip()
        if " - " in text:
            return text.split(" - ", 1)[0].strip()
        lookup = {choice.casefold(): self._record_chemical_id(_record_values(rec)) for rec in self._compound_records() for choice in self._compound_labels_for_record(rec)}
        return lookup.get(text.casefold(), text)

    def _compound_labels_for_record(self, rec) -> List[str]:
        vals = _record_values(rec)
        cid = self._record_chemical_id(vals)
        name = str(vals.get("Name", "") or "").strip()
        label = cid if not name else f"{cid} - {name}" if cid else name
        return [x for x in (cid, name, label) if x]

    def _compound_for_chemical_label(self, label: str):
        wanted = (label or "").strip().casefold()
        if not wanted:
            return None
        wanted_id = wanted.split(" - ", 1)[0].strip() if " - " in wanted else wanted
        for rec in self._compound_records():
            data = _record_values(rec)
            cid = self._record_chemical_id(data)
            name = str(data.get("Name", "") or "").strip()
            compound_label = cid if not name else f"{cid} - {name}" if cid else name
            for candidate in (cid, name, compound_label):
                text = str(candidate or "").strip().casefold()
                if text and text in {wanted, wanted_id}:
                    return data
        return None

    def _on_show_structure_toggle(self, *_args):
        if self.show_structure_var.get():
            self._refresh_structure_window()
        else:
            self._close_structure_window()

    def _on_structure_source_changed(self, *_args):
        if self.show_structure_var.get():
            self.after_idle(self._refresh_structure_window)

    def _close_structure_window(self):
        win = self.structure_window
        self.structure_window = None
        self.structure_image_label = None
        self.structure_title_label = None
        self.structure_photo = None
        if win is not None and win.winfo_exists():
            try:
                win.destroy()
            except Exception:
                pass

    def _on_structure_window_closed(self):
        self.show_structure_var.set(False)
        self._close_structure_window()

    def _ensure_structure_window(self):
        if self.structure_window is not None and self.structure_window.winfo_exists():
            return
        win = tk.Toplevel(self)
        win.title("Chemical Structure")
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", self._on_structure_window_closed)
        try:
            win.transient(self.winfo_toplevel())
        except Exception:
            pass
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill="both", expand=True)
        self.structure_title_label = ttk.Label(frame, text="", anchor="center")
        self.structure_title_label.pack(fill="x", pady=(0, 6))
        self.structure_image_label = ttk.Label(frame, text="", anchor="center")
        self.structure_image_label.pack(fill="both", expand=True)
        self.structure_window = win
        try:
            tecan_frame._position_toplevel_near(win, self.chemical_combo)
        except Exception:
            pass

    def _refresh_structure_window(self):
        if not self.show_structure_var.get():
            return
        self._ensure_structure_window()
        if self.structure_window is None or not self.structure_window.winfo_exists():
            return
        label = self.chemical_var.get().strip()
        data = self._compound_for_chemical_label(label)
        title = label or "No Chemical ID"
        smiles = str((data or {}).get("SMILES", "") or "").strip()
        display_name = str((data or {}).get("Name", "") or "").strip()
        if display_name and display_name.casefold() not in title.casefold():
            title = f"{title} - {display_name}" if label else display_name
        if self.structure_title_label is not None:
            self.structure_title_label.configure(text=title)
        if self.structure_image_label is None:
            return
        self.structure_photo = None
        if not smiles:
            self.structure_image_label.configure(image="", text="Structure not found")
            return
        if Chem is None or Draw is None or ImageTk is None:
            self.structure_image_label.configure(image="", text="Structure renderer unavailable")
            return
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            self.structure_image_label.configure(image="", text="Invalid SMILES")
            return
        try:
            img = Draw.MolToImage(mol, size=(300, 220))
            self.structure_photo = ImageTk.PhotoImage(img)
            self.structure_image_label.configure(image=self.structure_photo, text="")
        except Exception as exc:
            self.structure_image_label.configure(image="", text=f"Structure render failed: {exc}")

    @staticmethod
    def _batch_sources(row: Dict[str, object]) -> List[str]:
        return [
            value.strip().upper()
            for value in str(row.get("batch_source_wells", "") or "").split(",")
            if value.strip()
        ]

    _batch_chemical_map = staticmethod(batch_chemical_map)

    _batch_building_block_map = staticmethod(batch_building_block_map)

    @staticmethod
    def _batch_string_map(row: Dict[str, object], key: str) -> Dict[str, str]:
        raw = row.get(key)
        if not isinstance(raw, dict):
            return {}
        return {
            str(source).strip().upper(): str(value or "").strip()
            for source, value in raw.items()
            if str(source).strip()
        }

    def _batch_volume_mode_map(self, row: Dict[str, object]) -> Dict[str, str]:
        sources = self._batch_sources(row)
        raw = self._batch_string_map(row, "batch_source_volume_modes")
        if not isinstance(row.get("batch_source_volume_modes"), dict):
            return {source: BATCH_VOLUME_MODE_UL for source in sources}
        return {
            source: (
                BATCH_VOLUME_MODE_UMOL
                if raw.get(source, "").strip().lower() == BATCH_VOLUME_MODE_UMOL
                else BATCH_VOLUME_MODE_UL
            )
            for source in sources
        }

    def _batch_umol_map(self, row: Dict[str, object]) -> Dict[str, str]:
        return self._batch_string_map(row, "batch_source_umol")

    def _batch_final_volume_map(self, row: Dict[str, object]) -> Dict[str, str]:
        sources = self._batch_sources(row)
        if isinstance(row.get("batch_source_volumes_ul"), dict):
            stored = self._batch_string_map(row, "batch_source_volumes_ul")
            return {source: stored.get(source, "") for source in sources}
        legacy = str(row.get("volume_ul", "") or "").strip()
        return {source: legacy for source in sources}

    @staticmethod
    def _positive_float_or_none(value: object) -> Optional[float]:
        try:
            number = float(str(value or "").strip())
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) and number > 0 else None

    def _batch_reaction_umol_for_source(self, row: Dict[str, object], source: str) -> str:
        source = str(source or "").strip().upper()
        modes = self._batch_volume_mode_map(row)
        umol_values = self._batch_umol_map(row)
        if modes.get(source) == BATCH_VOLUME_MODE_UMOL:
            return umol_values.get(source, "")
        if not self._batch_building_block_map(row).get(source, False):
            return ""
        if not hasattr(self, "compound_provider"):
            return ""
        volume = self._positive_float_or_none(self._batch_final_volume_map(row).get(source, ""))
        chemical = self._batch_chemical_map(row).get(source, "")
        compound = self._compound_for_chemical_label(chemical) if chemical else None
        concentration_m = self._record_concentration_m(compound) if compound else None
        if volume is None or concentration_m is None:
            return ""
        return f"{volume * concentration_m:.6g}"

    def _batch_common_final_volume(self, row: Dict[str, object]) -> Optional[float]:
        sources = self._batch_sources(row)
        values = [
            self._positive_float_or_none(self._batch_final_volume_map(row).get(source, ""))
            for source in sources
        ]
        if not values or any(value is None for value in values):
            return None
        first = float(values[0])
        if any(not math.isclose(first, float(value), rel_tol=1e-9, abs_tol=1e-6) for value in values[1:]):
            return None
        return first

    def _batch_has_complete_volumes(self, row: Dict[str, object]) -> bool:
        sources = self._batch_sources(row)
        volumes = self._batch_final_volume_map(row)
        return bool(sources) and all(self._positive_float_or_none(volumes.get(source, "")) is not None for source in sources)

    @staticmethod
    def _batch_destination_groups(row: Dict[str, object]) -> List[List[str]]:
        groups = row.get("batch_destination_sets", []) or []
        return [
            [str(value).strip().upper() for value in group if str(value).strip()]
            for group in groups
            if isinstance(group, (list, tuple))
        ]

    def _expand_logical_protocol_row(self, logical_row: Dict[str, object]) -> List[Dict[str, object]]:
        if not self._row_is_batch(logical_row):
            return [deepcopy(logical_row)]
        kind = str(logical_row.get("batch_transfer_kind", "") or "")
        sources = self._batch_sources(logical_row)
        chemicals = self._batch_chemical_map(logical_row)
        building_blocks = self._batch_building_block_map(logical_row)
        source_volumes = self._batch_final_volume_map(logical_row)
        destination_sets = self._batch_destination_groups(logical_row)
        if not sources or not destination_sets or any(len(group) != len(sources) for group in destination_sets):
            raise ValueError(
                "A batch transfer has an incomplete source/destination mapping. "
                "Select the row, click Map, and save it again."
            )
        expanded: List[Dict[str, object]] = []
        if kind == "individual":
            base_step_name = str(logical_row.get("step_name", "") or "").strip()
            for source_index, source in enumerate(sources):
                row = deepcopy(logical_row)
                row["batch_transfer_kind"] = ""
                row["batch_source_wells"] = ""
                row["source_well"] = source
                row["chemical"] = chemicals.get(source, "")
                row["is_building_block"] = building_blocks.get(source, False)
                row["reaction_umol"] = self._batch_reaction_umol_for_source(logical_row, source)
                source_volume = self._positive_float_or_none(source_volumes.get(source, ""))
                if source_volume is not None:
                    row["volume_ul"] = source_volume
                elif isinstance(logical_row.get("batch_source_volumes_ul"), dict):
                    raise ValueError(f"Batch source {source} requires a positive dispense volume.")
                row["dest_wells"] = ",".join(group[source_index] for group in destination_sets)
                row["move_plate"] = bool(logical_row.get("move_plate", False)) and source_index == len(sources) - 1
                if base_step_name and len(sources) > 1:
                    row["step_name"] = f"{base_step_name} {source_index + 1}"
                expanded.append(row)
        else:
            common_volume = self._batch_common_final_volume(logical_row)
            if common_volume is None and isinstance(logical_row.get("batch_source_volumes_ul"), dict):
                raise ValueError("An 8-channel batch transfer requires the same final dispense volume for every source.")
            row = deepcopy(logical_row)
            if common_volume is not None:
                row["volume_ul"] = common_volume
            row["source_well"] = sources[0]
            row["dest_wells"] = ",".join(well for group in destination_sets for well in group)
            row["batch_source_wells"] = ",".join(sources)
            row["batch_source_chemicals"] = chemicals
            row["batch_source_building_blocks"] = building_blocks
            row["chemical"] = ""
            execution_mount = str(logical_row.get("batch_pipette_mount", "") or "").strip()
            if execution_mount:
                row["pipette_key"] = execution_mount
            expanded.append(row)
        return expanded

    def _sequence_positions(self, logical_row: Dict[str, object]) -> List[Dict[str, object]]:
        """Expand one Sequence child into one physical action per mapped sample position."""
        kind = str(logical_row.get("batch_transfer_kind", "") or "")
        positions: List[Dict[str, object]] = []
        if kind == "8-channel":
            sources = self._batch_sources(logical_row)
            chemicals = self._batch_chemical_map(logical_row)
            building_blocks = self._batch_building_block_map(logical_row)
            common_volume = self._batch_common_final_volume(logical_row)
            destination_sets = self._batch_destination_groups(logical_row)
            if not sources or not destination_sets or any(len(group) != len(sources) for group in destination_sets):
                raise ValueError(
                    f"Sequence child '{self._sequence_name(logical_row)}' has an incomplete 8-channel mapping."
                )
            if common_volume is None and isinstance(logical_row.get("batch_source_volumes_ul"), dict):
                raise ValueError(
                    f"Sequence child '{self._sequence_name(logical_row)}' requires one common 8-channel volume."
                )
            for destination_index, group in enumerate(destination_sets):
                row = deepcopy(logical_row)
                if common_volume is not None:
                    row["volume_ul"] = common_volume
                row["source_well"] = sources[0]
                row["dest_wells"] = ",".join(group)
                row["batch_source_wells"] = ",".join(sources)
                row["batch_source_chemicals"] = chemicals
                row["batch_source_building_blocks"] = building_blocks
                row["batch_destination_sets"] = [list(group)]
                row["chemical"] = ""
                row["move_plate"] = bool(logical_row.get("move_plate", False)) and destination_index == len(destination_sets) - 1
                execution_mount = str(logical_row.get("batch_pipette_mount", "") or "").strip()
                if execution_mount:
                    row["pipette_key"] = execution_mount
                positions.append(row)
            return positions

        if kind == "individual":
            sources = self._batch_sources(logical_row)
            chemicals = self._batch_chemical_map(logical_row)
            building_blocks = self._batch_building_block_map(logical_row)
            source_volumes = self._batch_final_volume_map(logical_row)
            destination_sets = self._batch_destination_groups(logical_row)
            if not sources or not destination_sets or any(len(group) != len(sources) for group in destination_sets):
                raise ValueError(
                    f"Sequence child '{self._sequence_name(logical_row)}' has an incomplete Individual Batch mapping."
                )
            total_positions = len(destination_sets) * len(sources)
            position_index = 0
            for group in destination_sets:
                for source_index, source in enumerate(sources):
                    row = deepcopy(logical_row)
                    row["batch_transfer_kind"] = ""
                    row["batch_source_wells"] = ""
                    row["source_well"] = source
                    row["chemical"] = chemicals.get(source, "")
                    row["is_building_block"] = building_blocks.get(source, False)
                    row["reaction_umol"] = self._batch_reaction_umol_for_source(logical_row, source)
                    source_volume = self._positive_float_or_none(source_volumes.get(source, ""))
                    if source_volume is not None:
                        row["volume_ul"] = source_volume
                    elif isinstance(logical_row.get("batch_source_volumes_ul"), dict):
                        raise ValueError(f"Batch source {source} requires a positive dispense volume.")
                    row["dest_wells"] = group[source_index]
                    row["move_plate"] = bool(logical_row.get("move_plate", False)) and position_index == total_positions - 1
                    positions.append(row)
                    position_index += 1
            return positions

        destination_wells = [
            value.strip().upper()
            for value in str(logical_row.get("dest_wells", "") or "").split(",")
            if value.strip()
        ]
        if not destination_wells:
            raise ValueError("A Sequence child has no mapped destination wells.")
        for destination_index, destination_well in enumerate(destination_wells):
            row = deepcopy(logical_row)
            row["dest_wells"] = destination_well
            row["move_plate"] = bool(logical_row.get("move_plate", False)) and destination_index == len(destination_wells) - 1
            positions.append(row)
        return positions

    def _expand_sequence_rows(self, sequence_rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
        sequence_name = self._sequence_name(sequence_rows[0])
        sequence_id = self._sequence_id(sequence_rows[0])
        group_rows: List[Tuple[str, str, List[Dict[str, object]]]] = []
        seen_group_ids: Set[str] = set()
        for row_index, row in enumerate(sequence_rows, start=1):
            group_id = self._sequence_group_id(row)
            if not group_id:
                group_id = f"legacy-group-{row_index}"
                group_name = f"Group {row_index}"
                members = [row]
            elif group_id in seen_group_ids:
                continue
            else:
                group_name = self._sequence_group_name(row)
                members = [member for member in sequence_rows if self._sequence_group_id(member) == group_id]
            seen_group_ids.add(group_id)
            group_rows.append((group_id, group_name, members))
        if not group_rows:
            raise ValueError(f"Sequence '{sequence_name}' contains no Groups.")

        group_positions: List[List[Dict[str, object]]] = []
        for _group_id, _group_name, members in group_rows:
            positions: List[Dict[str, object]] = []
            for member_index, member in enumerate(members, start=1):
                member_positions = self._sequence_positions(member)
                for local_index, position in enumerate(member_positions, start=1):
                    position["sequence_group_member_index"] = member_index
                    position["sequence_group_member_position"] = local_index
                    position["sequence_group_member_position_count"] = len(member_positions)
                    positions.append(position)
            group_positions.append(positions)
        sample_counts = [len(positions) for positions in group_positions]
        if len(set(sample_counts)) != 1:
            details = ", ".join(
                f"{group_rows[group_index][1]}={count}"
                for group_index, count in enumerate(sample_counts)
            )
            raise ValueError(
                f"Sequence '{sequence_name}' Groups must collectively cover the same number of sample positions "
                f"({details}). Add, move, or remap rows until every Group has matching coverage."
            )
        eight_channel_flags = [
            str(row.get("batch_transfer_kind", "") or "") == "8-channel"
            for row in sequence_rows
        ]
        if any(eight_channel_flags) and not all(eight_channel_flags):
            raise ValueError(
                f"Sequence '{sequence_name}' cannot mix 8-channel child rows with single-nozzle child rows."
            )
        sample_count = sample_counts[0]
        expanded: List[Dict[str, object]] = []
        for sample_index in range(sample_count):
            for group_index, positions in enumerate(group_positions):
                row = positions[sample_index]
                group_id, group_name, _members = group_rows[group_index]
                row.update({
                    "sequence_id": sequence_id,
                    "sequence_name": sequence_name,
                    "sequence_sample_index": sample_index + 1,
                    "sequence_sample_count": sample_count,
                    "sequence_group_id": group_id,
                    "sequence_group_name": group_name,
                    "sequence_group_index": group_index + 1,
                    "sequence_group_count": len(group_rows),
                    "sequence_child_index": group_index + 1,
                    "sequence_child_count": len(group_rows),
                })
                expanded.append(row)
        return expanded

    def _expanded_protocol_rows(self) -> List[Dict[str, object]]:
        expanded: List[Dict[str, object]] = []
        handled_sequence_ids: Set[str] = set()
        for sequence_id in {
            self._sequence_id(row) for row in self.rows if self._sequence_id(row)
        }:
            indices = self._sequence_row_indices(sequence_id)
            if indices != list(range(indices[0], indices[-1] + 1)):
                name = self._sequence_name(self.rows[indices[0]])
                raise ValueError(
                    f"Sequence '{name}' is split by rows outside the Sequence. Ungroup and recreate it from contiguous rows."
                )
            for group_id in self._sequence_group_ids(sequence_id):
                group_indices = self._sequence_group_row_indices(group_id)
                if group_indices != list(range(group_indices[0], group_indices[-1] + 1)):
                    group_name = self._sequence_group_name(self.rows[group_indices[0]])
                    raise ValueError(
                        f"Sequence Group '{group_name}' is split by another Group. Reorder its rows so each Group is contiguous."
                    )
        for logical_row in self.rows:
            sequence_id = self._sequence_id(logical_row)
            if not sequence_id:
                expanded.extend(self._expand_logical_protocol_row(logical_row))
                continue
            if sequence_id in handled_sequence_ids:
                continue
            sequence_rows = [row for row in self.rows if self._sequence_id(row) == sequence_id]
            expanded.extend(self._expand_sequence_rows(sequence_rows))
            handled_sequence_ids.add(sequence_id)
        return expanded

    def rows_for_cheminformatics(self) -> List[Dict[str, object]]:
        rows: List[Dict[str, object]] = []
        for block_index, logical_row in enumerate(self.rows, start=1):
            if logical_row.get("_draft"):
                continue
            mappings: List[Tuple[str, str, str, bool, float, str]] = []
            if self._row_is_batch(logical_row):
                sources = self._batch_sources(logical_row)
                chemicals = self._batch_chemical_map(logical_row)
                building_blocks = self._batch_building_block_map(logical_row)
                source_volumes = self._batch_final_volume_map(logical_row)
                destination_sets = self._batch_destination_groups(logical_row)
                if any(len(group) != len(sources) for group in destination_sets):
                    continue
                for source_index, source_well in enumerate(sources):
                    chemical = chemicals.get(source_well, "")
                    for destination_set in destination_sets:
                        mappings.append((
                            source_well,
                            destination_set[source_index],
                            chemical,
                            building_blocks.get(source_well, False),
                            float(source_volumes.get(source_well, 0.0) or 0.0),
                            self._batch_reaction_umol_for_source(logical_row, source_well),
                        ))
            else:
                dest_labware = self._labware_by_alias(logical_row.get("dest_labware_alias", "dest1")) or {}
                try:
                    dest_wells = _parse_wells(
                        str(logical_row.get("dest_wells", "")),
                        dest_labware.get("map_style", self.dest_style_var.get()),
                    )
                except Exception:
                    continue
                physical_sources = self._physical_source_wells_for_row(logical_row)
                chemical = str(logical_row.get("chemical", "") or "").strip()
                is_building_block = coerce_bool(logical_row.get("is_building_block", False))
                volume = float(logical_row.get("volume_ul", 0.0) or 0.0)
                reaction_umol = str(logical_row.get("reaction_umol", "") or "")
                for index, well in enumerate(dest_wells):
                    source_well = physical_sources[index % len(physical_sources)] if physical_sources else ""
                    mappings.append((source_well, well, chemical, is_building_block, volume, reaction_umol))
            dest_labware = self._labware_by_alias(logical_row.get("dest_labware_alias", "dest1")) or {}
            source_labware = self._labware_by_alias(logical_row.get("source_labware_alias", "source1")) or {}
            for source_well, well, chemical, is_building_block, volume, reaction_umol in mappings:
                if not chemical:
                    continue
                rows.append({
                    "block": block_index,
                    "source": "Opentrons",
                    "chemical": chemical,
                    "chemical_id": chemical,
                    "is_building_block": is_building_block,
                    "well": well,
                    "reaction_well": well,
                    "volume_uL": volume,
                    "dispensed_uL": volume,
                    "reaction_umol": reaction_umol,
                    "dispensed_umol": reaction_umol,
                    "dest_labware": dest_labware.get("load_name", self.dest_labware_var.get()),
                    "dest_labware_alias": logical_row.get("dest_labware_alias", "dest1"),
                    "dest_map_style": dest_labware.get("map_style", self.dest_style_var.get()),
                    "destination_location": f"{logical_row.get('dest_labware_alias', 'dest1')}:{well}",
                    "source_labware": source_labware.get("load_name", self.source_labware_var.get()),
                    "source_labware_alias": logical_row.get("source_labware_alias", "source1"),
                    "source_map_style": source_labware.get("map_style", self.source_style_var.get()),
                    "source_well": source_well,
                    "building_block_location": f"{logical_row.get('source_labware_alias', 'source1')}:{source_well}",
                    "strategy": str(logical_row.get("strategy", "") or ""),
                    "pipette": str(logical_row.get("pipette_key", "Auto") or "Auto"),
                    "notes": str(logical_row.get("note", "") or ""),
                })
        return rows

    def _push_to_cheminformatics(self):
        incomplete = self._incomplete_rows_message("pushing to Cheminformatics")
        if incomplete:
            messagebox.showwarning("Opentrons", incomplete)
            return
        rows = self.rows_for_cheminformatics()
        if not rows:
            messagebox.showwarning("Opentrons", "No Opentrons rows with Chemical IDs and destination wells to push.")
            return
        if callable(self.push_callback):
            self.push_callback(rows)
            self.status_var.set(f"Pushed {len(rows)} Opentrons row(s) to Cheminformatics")
        else:
            messagebox.showwarning("Opentrons", "Cheminformatics push is not connected.")

    def _refresh_table(self):
        self._normalize_imported_sequences()
        self.tree.delete(*self.tree.get_children())
        sequence_parents: Dict[str, str] = {}
        group_parents: Dict[str, str] = {}
        for idx, row in enumerate(self.rows):
            sequence_id = self._sequence_id(row)
            parent = ""
            child_text = ""
            if sequence_id:
                parent = sequence_parents.get(sequence_id, "")
                if not parent:
                    parent = f"sequence:{sequence_id}"
                    sequence_parents[sequence_id] = parent
                    indices = self._sequence_row_indices(sequence_id)
                    sequence_name = self._sequence_name(row)
                    group_ids = self._sequence_group_ids(sequence_id)
                    expected = self._sequence_expected_position_count(sequence_id)
                    self.tree.insert(
                        "",
                        "end",
                        iid=parent,
                        text=sequence_name,
                        tags=("sequence",),
                        values=(
                            f"{len(group_ids)} Groups / {expected} samples", "", "", "", "", "", "",
                            "Sequence", "", f"{len(indices)} rows",
                        ),
                        open=True,
                    )
                group_id = self._sequence_group_id(row)
                group_parent = group_parents.get(group_id, "")
                if not group_parent:
                    group_parent = f"group:{group_id}"
                    group_parents[group_id] = group_parent
                    group_indices = self._sequence_group_row_indices(group_id)
                    total = self._sequence_group_position_count(group_id)
                    expected = self._sequence_expected_position_count(sequence_id)
                    coverage = f"{total}/{expected or total} samples"
                    if expected and total != expected:
                        coverage += " — incomplete" if total < expected else " — overfilled"
                    self.tree.insert(
                        parent,
                        "end",
                        iid=group_parent,
                        text=self._sequence_group_name(row),
                        tags=("group",),
                        values=(coverage, "", "", "", "", "", "", "Group", "", f"{len(group_indices)} rows"),
                        open=True,
                    )
                parent = group_parent
                child_text = str(row.get("sequence_row_order", "") or (self._sequence_group_row_indices(group_id).index(idx) + 1))
            self.tree.insert(
                parent,
                "end",
                iid=str(idx),
                text=child_text,
                values=self._transfer_row_values(row, idx),
                tags=self._transfer_row_tags(row, idx),
            )
        self.remove_row_button.configure(state="disabled")
        self.ungroup_sequence_button.configure(state="disabled")
        self.add_to_sequence_button.configure(state="disabled")
        self.push_cheminformatics_button.configure(state="normal" if self.rows else "disabled")
        sequence_count = len(sequence_parents)
        sequence_text = f" in {sequence_count} Sequence{'s' if sequence_count != 1 else ''}" if sequence_count else ""
        self.status_var.set(f"{len(self.rows)} Opentrons transfer row(s){sequence_text}")

    @staticmethod
    def _transfer_row_tags(row, index):
        return ("incomplete",) if coerce_bool(row.get("_draft", False)) else (stripe_tag(index),)

    def _display_row_volume(self, row: Dict[str, object]) -> str:
        if self._row_is_batch(row) and isinstance(row.get("batch_source_volumes_ul"), dict):
            values = [
                self._positive_float_or_none(value)
                for value in self._batch_final_volume_map(row).values()
            ]
            valid = [value for value in values if value is not None]
            if valid and len(valid) == len(values):
                first = float(valid[0])
                if any(not math.isclose(first, float(value), rel_tol=1e-9, abs_tol=1e-6) for value in valid[1:]):
                    return "varies"
                value = first
            else:
                return ""
        else:
            value = row.get("volume_ul", "")
        if value in (None, ""):
            return ""
        try:
            return f"{float(value):.1f}"
        except (TypeError, ValueError):
            return str(value)

    def _transfer_row_values(self, row: Dict[str, object], idx: Optional[int] = None) -> Tuple[object, ...]:
        step_name = str(row.get("step_name", "") or "").strip()
        if not step_name:
            prefix = "Batch" if self._row_is_batch(row) else "Transfer"
            step_name = f"{prefix} {idx + 1}" if idx is not None else prefix
        if row.get("_draft"):
            step_name = f"Incomplete — {step_name}"
        if self._row_is_batch(row):
            sources = self._batch_sources(row)
            chemical_map = self._batch_chemical_map(row)
            building_block_map = self._batch_building_block_map(row)
            destination_sets = self._batch_destination_groups(row)
            assigned = sum(1 for source in sources if chemical_map.get(source, ""))
            building_blocks = sum(
                1 for source in sources if chemical_map.get(source, "") and building_block_map.get(source, False)
            )
            kind = str(row.get("batch_transfer_kind", "") or "")
            kind_label = "Individual" if kind == "individual" else "8-channel"
            return (
                step_name,
                f"{assigned}/{len(sources)} assigned",
                f"{building_blocks}/{assigned} BB",
                f"{row.get('source_labware_alias', 'source1')}:{len(sources)} wells",
                f"{row.get('dest_labware_alias', 'dest1')}:{len(destination_sets)} sets/{sum(len(group) for group in destination_sets)} wells",
                "",
                self._display_row_volume(row),
                f"Batch: {kind_label}",
                row.get("pipette_key", "Auto"),
                self._row_liquid_summary(row),
            )
        return (
            step_name,
            row.get("chemical", ""),
            "Yes" if coerce_bool(row.get("is_building_block", False)) else "",
            f"{row.get('source_labware_alias', 'source1')}:{row.get('source_well', '')}",
            f"{row.get('dest_labware_alias', 'dest1')}:{row.get('dest_wells', '')}",
            row.get("reaction_umol", ""),
            self._display_row_volume(row),
            row.get("strategy", ""),
            row.get("pipette_key", "Auto"),
            self._row_liquid_summary(row),
        )

    def _select_transfer_row(self, idx: int):
        if self.tree.exists(str(idx)):
            self.tree.selection_set(str(idx))
            self.tree.focus(str(idx))
            self.tree.see(str(idx))

    def _row_liquid_summary(self, row: Dict[str, object]) -> str:
        parts = [str(row.get("tip_policy", "") or ""), f"blowout: {row.get('blowout_location') or 'No blowout'}"]
        if row.get("blowout_location") == "Liquid waste":
            parts.append(f"{row.get('blowout_labware_alias', '')}:{row.get('blowout_well', '')}")
        extra = str(row.get("multi_dispense_extra_percent", "") or "").strip()
        if extra:
            parts.append(f"extra {extra.rstrip('%')}%")
        asp_depth = self._format_depth_summary(row.get("aspirate_depth_mm", ""), row.get("aspirate_depth_reference", "from bottom"))
        disp_depth = self._format_depth_summary(row.get("dispense_depth_mm", ""), row.get("dispense_depth_reference", "from top"))
        if asp_depth != "default depth":
            parts.append(f"asp {asp_depth}")
        if disp_depth != "default depth":
            parts.append(f"disp {disp_depth}")
        if row.get("tip_touch"):
            parts.append("touch")
        if row.get("pre_wet_tip"):
            parts.append("pre-wet")
        if row.get("mix_enabled"):
            timing = str(row.get("mix_timing", "Before aspirating") or "Before aspirating")
            timing_label = {
                "Before aspirating": "mix before",
                "After dispensing": "mix after",
                "Before and after": "mix before+after",
            }.get(timing, "mix")
            parts.append(
                f"{timing_label} {row.get('mix_repetitions', '?')}x{row.get('mix_volume_ul', '?')}uL"
            )
            post_source_mix_delay = str(row.get("post_source_mix_delay_seconds", "") or "").strip()
            if (
                timing in {"Before aspirating", "Before and after"}
                and post_source_mix_delay
                and post_source_mix_delay not in {"0", "0.0"}
            ):
                parts.append(f"source wait {post_source_mix_delay}s")
        aspirate_delay = str(row.get("post_aspirate_delay_seconds", "") or "").strip()
        dispense_delay = str(row.get("post_dispense_delay_seconds", "") or "").strip()
        pre_move_delay = str(row.get("pre_move_delay_seconds", "") or "").strip()
        if row.get("delay_air_gap_enabled"):
            if aspirate_delay and aspirate_delay not in {"0", "0.0"}:
                parts.append(f"asp wait {aspirate_delay}s")
            if dispense_delay and dispense_delay not in {"0", "0.0"}:
                parts.append(f"disp wait {dispense_delay}s")
            if row.get("air_gap_enabled"):
                parts.append(f"air gap {row.get('air_gap_volume_ul', '?')}uL")
            if row.get("move_plate") and pre_move_delay and pre_move_delay not in {"0", "0.0"}:
                parts.append(f"move wait {pre_move_delay}s")
        if row.get("move_plate"):
            parts.append(f"move {row.get('move_labware_alias', '')}->{row.get('move_to_slot', '')}")
        return " | ".join(part for part in parts if part)

    def _remove_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Opentrons", "Select a transfer row first.")
            return
        indices = set(self._selected_row_indices())
        for iid in sel:
            if str(iid).startswith("sequence:"):
                indices.update(self._sequence_row_indices(str(iid).split(":", 1)[1]))
            elif str(iid).startswith("group:"):
                indices.update(self._sequence_group_row_indices(str(iid).split(":", 1)[1]))
        if not indices:
            return
        affected_sequence_ids = {
            self._sequence_id(self.rows[idx]) for idx in indices if self._sequence_id(self.rows[idx])
        }
        for idx in sorted(indices, reverse=True):
            del self.rows[idx]
        for sequence_id in affected_sequence_ids:
            remaining = self._sequence_row_indices(sequence_id)
            if remaining:
                self._sync_sequence_order(sequence_id)
        self._refresh_table()
        self._start_new_transfer(announce=False)

    def _collect_module_configs(self, robot: str, api_parts: Tuple[int, int]) -> List[Dict[str, object]]:
        module_configs: List[Dict[str, object]] = []

        def validate_common(label: str, kind: str, slot: str, alias: str, adapter: str) -> Optional[Dict[str, str]]:
            if slot not in self._supported_module_slots(robot, kind):
                raise ValueError(f"Slot {slot or '(blank)'} is not supported for {label} on {robot}.")
            if adapter and api_parts < (2, 15):
                raise ValueError("Separate module adapters require Opentrons API level 2.15 or newer.")
            if not alias:
                return None
            labware = self._labware_by_alias(alias)
            if not labware:
                raise ValueError(f"Select a valid starting labware alias for {label}, or leave it blank.")
            if str(labware.get("slot", "") or "").strip() != slot:
                raise ValueError(
                    f"Starting labware {alias} must use the same deck slot as {label} ({slot}). "
                    "Open Temperature & Shaking and click Done to synchronize it."
                )
            return labware

        if self.temperature_module_enabled_var.get():
            if api_parts < (2, 3):
                raise ValueError("Temperature Module GEN2 requires Opentrons API level 2.3 or newer.")
            slot = self.temperature_module_slot_var.get().strip()
            alias = self.temperature_module_labware_alias_var.get().strip()
            adapter = self.temperature_module_adapter_var.get().strip()
            validate_common("Temperature Module GEN2", "temperature", slot, alias, adapter)
            temperature_text = self.temperature_module_target_var.get().strip()
            if not temperature_text:
                raise ValueError("Enter a target temperature for the Temperature Module.")
            target_temperature = float(temperature_text)
            if not 4 <= target_temperature <= 95:
                raise ValueError("Temperature Module target temperature must be 4–95 °C.")
            if not self.temperature_module_wait_var.get() and any(
                str(row.get("source_labware_alias", "") or "").strip() == alias
                or str(row.get("dest_labware_alias", "") or "").strip() == alias
                for row in self.rows
            ):
                raise ValueError(
                    "Enable 'Wait until reached' when transfer rows access Temperature Module labware. "
                    "Concurrent temperature changes are only safe here when the robot works on other labware."
                )
            module_configs.append({
                "key": "temperature",
                "type": "Temperature Module GEN2",
                "load_name": TEMPERATURE_MODULE_LOAD_NAME,
                "slot": slot,
                "labware_alias": alias,
                "adapter": adapter,
                "target_temperature": target_temperature,
                "shake_speed": None,
                "shake_duration_minutes": None,
                "wait_until_ready": bool(self.temperature_module_wait_var.get()),
                "deactivate_after_run": bool(self.temperature_module_deactivate_var.get()),
            })

        if self.heater_shaker_enabled_var.get():
            if api_parts < (2, 13):
                raise ValueError("Heater-Shaker Module requires Opentrons API level 2.13 or newer.")
            slot = self.heater_shaker_slot_var.get().strip()
            alias = self.heater_shaker_labware_alias_var.get().strip()
            adapter = self.heater_shaker_adapter_var.get().strip()
            validate_common("Heater-Shaker Module", "heater_shaker", slot, alias, adapter)
            temperature_text = self.heater_shaker_temperature_var.get().strip()
            shake_text = self.heater_shaker_speed_var.get().strip()
            duration_text = self.heater_shaker_duration_var.get().strip()
            target_temperature = float(temperature_text) if temperature_text else None
            if target_temperature is not None and not 37 <= target_temperature <= 95:
                raise ValueError("Heater-Shaker target temperature must be 37–95 °C, or blank for no heating.")
            shake_speed = float(shake_text) if shake_text else None
            if shake_speed is not None and not 200 <= shake_speed <= 3000:
                raise ValueError("Heater-Shaker speed must be 200–3000 rpm, or blank for no shaking.")
            shake_duration = float(duration_text) if shake_speed is not None and duration_text else None
            if shake_speed is not None and (shake_duration is None or shake_duration <= 0):
                raise ValueError("Enter a shake duration greater than zero minutes when shaking is enabled.")
            if shake_speed is not None and not self.heater_shaker_wait_var.get() and api_parts < (2, 27):
                raise ValueError("Concurrent Heater-Shaker shaking requires Opentrons API level 2.27 or newer.")
            if target_temperature is None and shake_speed is None:
                raise ValueError("Configure a target temperature, a shake speed, or both for the Heater-Shaker.")
            module_configs.append({
                "key": "heater_shaker",
                "type": "Heater-Shaker Module",
                "load_name": HEATER_SHAKER_LOAD_NAME,
                "slot": slot,
                "labware_alias": alias,
                "adapter": adapter,
                "target_temperature": target_temperature,
                "shake_speed": shake_speed,
                "shake_duration_minutes": shake_duration,
                "wait_until_ready": bool(self.heater_shaker_wait_var.get()),
                "deactivate_after_run": bool(self.heater_shaker_deactivate_var.get()),
            })

        aliases = [str(config["labware_alias"]) for config in module_configs if config.get("labware_alias")]
        slots = [str(config["slot"]) for config in module_configs]
        if len(set(aliases)) != len(aliases):
            raise ValueError("Temperature Module and Heater-Shaker must use different labware aliases.")
        if len(set(slots)) != len(slots):
            raise ValueError("Temperature Module and Heater-Shaker must use different deck slots.")
        return module_configs

    def _configured_pipettes(self):
        configured_pipettes = {
            "left": {
                "name": self.left_pipette_var.get().strip(),
                "tiprack": self.left_tiprack_var.get().strip(),
                "tiprack_slots": [s.strip() for s in self.left_tiprack_slots_var.get().split(",") if s.strip()],
                "tip_start_column": self.left_tip_start_column_var.get().strip() or "1",
                "tip_start_well": self.left_tip_start_well_var.get().strip().upper() or "A1",
            },
            "right": {
                "name": self.right_pipette_var.get().strip(),
                "tiprack": self.right_tiprack_var.get().strip(),
                "tiprack_slots": [s.strip() for s in self.right_tiprack_slots_var.get().split(",") if s.strip()],
                "tip_start_column": self.right_tip_start_column_var.get().strip() or "1",
                "tip_start_well": self.right_tip_start_well_var.get().strip().upper() or "A1",
            },
        }
        return {
            mount: cfg
            for mount, cfg in configured_pipettes.items()
            if str(cfg.get("name", "") or "").strip() not in {"", "None"}
        }

    def _collect_config(self):
        robot = self.robot_var.get().strip()
        if robot not in ROBOT_OPTIONS:
            raise ValueError("Robot must be Flex or OT-2.")
        incomplete = self._incomplete_rows_message("generating a protocol")
        if incomplete:
            raise ValueError(incomplete)
        pipettes = self._configured_pipettes()
        if not pipettes:
            raise ValueError("Configure at least one left or right pipette.")
        for mount, cfg in pipettes.items():
            pipette = str(cfg["name"])
            if pipette not in PIPETTE_OPTIONS[robot]:
                raise ValueError(f"{mount.title()} pipette {pipette} is not valid for {robot}.")
            if pipette.startswith("flex_96channel"):
                raise ValueError("Flex 96-channel generation is intentionally held back until full-plate compatibility checks are added.")
        slots = FLEX_SLOTS if robot == "Flex" else OT2_SLOTS
        if not self._source_labware_aliases():
            raise ValueError("Add at least one source labware.")
        if not self._dest_labware_aliases():
            raise ValueError("Add at least one destination labware.")
        aliases = [item.get("alias", "") for item in self.labware_configs]
        if len(set(aliases)) != len(aliases):
            raise ValueError("Labware aliases must be unique.")
        if not self.rows:
            raise ValueError("Add at least one transfer row.")
        if self.eight_channel_mode_var.get() not in EIGHT_CHANNEL_MODES:
            raise ValueError("8-channel behavior must be Auto from wells, Force single tip, or Force all channels.")
        api_match = re.fullmatch(r"(\d+)\.(\d+)", self.api_level_var.get().strip())
        if api_match is None:
            raise ValueError("Opentrons API level must use major.minor format, for example 2.20.")
        api_parts = (int(api_match.group(1)), int(api_match.group(2)))
        module_configs = self._collect_module_configs(robot, api_parts)
        module_labware_aliases = {
            str(config.get("labware_alias", "") or "").strip()
            for config in module_configs
            if str(config.get("labware_alias", "") or "").strip()
        }
        used_slots = []
        for item in self.labware_configs:
            alias = item.get("alias", "")
            if not alias:
                raise ValueError("Every labware row needs an alias.")
            if item.get("role") not in LABWARE_ROLES:
                raise ValueError(f"Labware {alias} must have role source, destination, or both.")
            if not item.get("load_name"):
                raise ValueError(f"Labware {alias} needs a load name.")
            if item.get("map_style") not in PLATE_STYLES:
                raise ValueError(f"Labware {alias} needs a valid map style.")
            if alias not in module_labware_aliases:
                used_slots.append(str(item.get("slot", "")).strip())
        used_slots.extend(str(config.get("slot", "") or "").strip() for config in module_configs)
        if robot == "Flex":
            used_slots.append(self.trash_slot_var.get().strip())
        for slot in used_slots:
            if slot not in slots:
                raise ValueError(f"Slot {slot} is not valid for {robot}.")
        if len(set(used_slots)) != len(used_slots):
            raise ValueError("Deck slots must not overlap.")
        aspirate_rate = self._optional_positive_float(self.aspirate_rate_var.get(), "Aspirate rate")
        dispense_rate = self._optional_positive_float(self.dispense_rate_var.get(), "Dispense rate")
        aspirate_depth_mm = self._optional_nonnegative_float_or_none(self.aspirate_depth_mm_var.get(), "Aspirate depth")
        dispense_depth_mm = self._optional_nonnegative_float_or_none(self.dispense_depth_mm_var.get(), "Dispense depth")
        aspirate_depth_reference = self.aspirate_depth_reference_var.get()
        dispense_depth_reference = self.dispense_depth_reference_var.get()
        if aspirate_depth_reference not in TIP_DEPTH_REFERENCES:
            raise ValueError("Aspirate depth reference must be from bottom or from top.")
        if dispense_depth_reference not in TIP_DEPTH_REFERENCES:
            raise ValueError("Dispense depth reference must be from bottom or from top.")
        multi_dispense_extra_percent = self._optional_nonnegative_float(
            self.multi_dispense_extra_percent_var.get(),
            "Extra aspirate volume percentage",
        )
        return (
            robot,
            pipettes,
            aspirate_rate,
            dispense_rate,
            aspirate_depth_mm,
            aspirate_depth_reference,
            dispense_depth_mm,
            dispense_depth_reference,
            multi_dispense_extra_percent,
            module_configs,
        )

    def _validate_used_pipette_tipracks(self, robot, pipettes, rows, module_configs):
        return validate_used_pipette_tipracks(
            self.labware_configs, self.trash_slot_var.get(), robot, pipettes, rows, module_configs,
        )

    _required_positive_float = staticmethod(required_positive_float)

    _optional_positive_float = staticmethod(optional_positive_float)

    _optional_nonnegative_float = staticmethod(optional_nonnegative_float)

    _optional_nonnegative_float_or_none = staticmethod(optional_nonnegative_float_or_none)

    def _validated_blowout_settings(self, row, protocol_rows, *, row_number):
        return validated_blowout_settings(self.labware_configs, row, protocol_rows, row_number=row_number)

    _validated_mix_settings = staticmethod(validated_mix_settings)

    _validated_delay_air_gap_settings = staticmethod(validated_delay_air_gap_settings)

    _select_pipette_for_row = staticmethod(select_pipette_for_row)

    def _nozzle_layout_for_row(self, robot, pipette_name, dest_wells, dest_style, *, force_all_channels=False):
        return nozzle_layout_for_row(
            robot, pipette_name, dest_wells, dest_style,
            force_all_channels=force_all_channels, eight_channel_mode=self.eight_channel_mode_var.get(),
        )

    _current_labware_slot = staticmethod(current_labware_slot)

    _single_nozzle_start_for_row = staticmethod(single_nozzle_start_for_row)

    def _sequence_tip_warnings(self) -> List[str]:
        warnings: List[str] = []
        seen: Set[str] = set()
        for row in self.rows:
            sequence_id = self._sequence_id(row)
            if not sequence_id or sequence_id in seen:
                continue
            seen.add(sequence_id)
            indices = self._sequence_row_indices(sequence_id)
            if not indices:
                continue
            group_ids = self._sequence_group_ids(sequence_id)
            final_group_indices = self._sequence_group_row_indices(group_ids[-1]) if group_ids else [indices[-1]]
            keep_rows = [
                self.rows[idx]
                for idx in final_group_indices
                if self._normalize_tip_policy(self.rows[idx].get("tip_policy")) == "Keep tip mounted"
            ]
            if keep_rows:
                name = self._sequence_name(keep_rows[0])
                group_name = self._sequence_group_name(keep_rows[0])
                warnings.append(
                    f"Sequence '{name}' ends with Keep tip mounted for one or more rows in {group_name}. "
                    "The same tip will carry into the next "
                    "sample or following plan item when the pipette/nozzle configuration remains compatible."
                )
        return warnings

    _validate_sequence_tip_transitions = staticmethod(validate_sequence_tip_transitions)

    def _build_script_text(self) -> str:
        config = self._collect_config()
        request = OpentronsCompileRequest(
            robot=config[0], pipettes=config[1], module_configs=config[9],
            labware_configs=self.labware_configs,
            rows=self._expanded_protocol_rows(),
            deck_occupants=self._initial_deck_slot_occupants(),
            api_level=self.api_level_var.get(),
            protocol_name=self.protocol_name_var.get(),
            source_style=self.source_style_var.get(), dest_style=self.dest_style_var.get(),
            eight_channel_mode=self.eight_channel_mode_var.get(),
            tip_policy=self.tip_policy_var.get(), flex_gripper=bool(self.flex_gripper_var.get()),
            trash_slot=self.trash_slot_var.get(),
        )
        return compile_protocol(request)

    def _generate_protocol(self):
        try:
            text = self._build_script_text()
        except Exception as exc:
            messagebox.showwarning("Opentrons", str(exc))
            return
        sequence_warnings = self._sequence_tip_warnings()
        if sequence_warnings and not messagebox.askyesno(
            "Sequence tip warning",
            "\n\n".join(sequence_warnings) + "\n\nGenerate the protocol anyway?",
        ):
            return
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out = filedialog.asksaveasfilename(
            title="Generate Opentrons protocol",
            defaultextension=".py",
            initialdir=str(OUTPUT_DIR),
            initialfile=f"{self.protocol_name_var.get().strip() or 'opentrons_protocol'}.py",
            filetypes=[("Python", "*.py"), ("All files", "*.*")],
        )
        if not out:
            return
        Path(out).write_text(text, encoding="utf-8")
        self.status_var.set(f"Generated {Path(out).name}")
        messagebox.showinfo("Opentrons", f"Protocol generated:\n{out}")

    def export_state(self) -> Dict[str, object]:
        return {
            "protocol_name": self.protocol_name_var.get(),
            "notes": self.notes_var.get(),
            "robot": self.robot_var.get(),
            "api_level": self.api_level_var.get(),
            "left_pipette": self.left_pipette_var.get(),
            "left_tiprack": self.left_tiprack_var.get(),
            "left_tiprack_slots": self.left_tiprack_slots_var.get(),
            "left_tip_start_column": self.left_tip_start_column_var.get(),
            "left_tip_start_well": self.left_tip_start_well_var.get(),
            "right_pipette": self.right_pipette_var.get(),
            "right_tiprack": self.right_tiprack_var.get(),
            "right_tiprack_slots": self.right_tiprack_slots_var.get(),
            "right_tip_start_column": self.right_tip_start_column_var.get(),
            "right_tip_start_well": self.right_tip_start_well_var.get(),
            "trash_slot": self.trash_slot_var.get(),
            "flex_gripper": self.flex_gripper_var.get(),
            **self._module_state(),
            "source_labware": self.source_labware_var.get(),
            "source_slot": self.source_slot_var.get(),
            "source_style": self.source_style_var.get(),
            "dest_labware": self.dest_labware_var.get(),
            "dest_slot": self.dest_slot_var.get(),
            "dest_style": self.dest_style_var.get(),
            "source_labware_alias": self.source_labware_alias_var.get(),
            "dest_labware_alias": self.dest_labware_alias_var.get(),
            "labware_configs": [dict(item) for item in self.labware_configs],
            "step_name": self.step_name_var.get(),
            "tip_policy": self.tip_policy_var.get(),
            "blowout_location": self.blowout_location_var.get(),
            "blowout_labware_alias": self.blowout_labware_alias_var.get().strip(),
            "blowout_well": self.blowout_well_var.get().strip().upper(),
            "eight_channel_mode": self.eight_channel_mode_var.get(),
            "aspirate_rate": self.aspirate_rate_var.get(),
            "dispense_rate": self.dispense_rate_var.get(),
            "aspirate_depth_mm": self.aspirate_depth_mm_var.get(),
            "aspirate_depth_reference": self.aspirate_depth_reference_var.get(),
            "dispense_depth_mm": self.dispense_depth_mm_var.get(),
            "dispense_depth_reference": self.dispense_depth_reference_var.get(),
            "multi_dispense_extra_percent": self.multi_dispense_extra_percent_var.get(),
            "tip_touch": self.tip_touch_var.get(),
            "pre_wet_tip": self.pre_wet_tip_var.get(),
            "mix_enabled": self.mix_enabled_var.get(),
            "mix_timing": self.mix_timing_var.get(),
            "mix_repetitions": self.mix_repetitions_var.get(),
            "mix_volume_ul": self.mix_volume_var.get(),
            "post_source_mix_delay_seconds": self.post_source_mix_delay_seconds_var.get(),
            "mix_aspirate_rate": self.mix_aspirate_rate_var.get(),
            "mix_dispense_rate": self.mix_dispense_rate_var.get(),
            "mix_aspirate_depth_mm": self.mix_aspirate_depth_mm_var.get(),
            "mix_aspirate_depth_reference": self.mix_aspirate_depth_reference_var.get(),
            "mix_dispense_depth_mm": self.mix_dispense_depth_mm_var.get(),
            "mix_dispense_depth_reference": self.mix_dispense_depth_reference_var.get(),
            "delay_air_gap_enabled": self.delay_air_gap_enabled_var.get(),
            "post_aspirate_delay_seconds": self.post_aspirate_delay_seconds_var.get(),
            "post_dispense_delay_seconds": self.post_dispense_delay_seconds_var.get(),
            "pre_move_delay_seconds": self.pre_move_delay_seconds_var.get(),
            "air_gap_enabled": self.air_gap_enabled_var.get(),
            "air_gap_volume_ul": self.air_gap_volume_var.get(),
            "air_gap_height_mm": self.air_gap_height_var.get(),
            "air_gap_flow_rate": self.air_gap_flow_rate_var.get(),
            "rows": [dict(row) for row in self.rows],
        }

    def import_state(self, data: Dict[str, object]):
        if not isinstance(data, dict):
            return
        self.protocol_name_var.set(str(data.get("protocol_name", "") or ""))
        self.notes_var.set(str(data.get("notes", "") or ""))
        self.robot_var.set(str(data.get("robot", "Flex") or "Flex"))
        self.api_level_var.set(str(data.get("api_level", "2.21") or "2.21"))
        old_mount = str(data.get("mount", "right") or "right")
        old_pipette = str(data.get("pipette", "") or "")
        old_tiprack = str(data.get("tiprack", "") or "")
        old_tiprack_slots = str(data.get("tiprack_slots", "") or "")
        self.left_pipette_var.set(str(data.get("left_pipette", "") or (old_pipette if old_mount == "left" else "flex_1channel_50")))
        self.left_tiprack_var.set(str(data.get("left_tiprack", "") or (old_tiprack if old_mount == "left" else "opentrons_flex_96_filtertiprack_50ul")))
        self.left_tiprack_slots_var.set(str(data.get("left_tiprack_slots", "") or (old_tiprack_slots if old_mount == "left" else "D1")))
        self.left_tip_start_column_var.set(str(data.get("left_tip_start_column", "1") or "1"))
        self.left_tip_start_well_var.set(str(data.get("left_tip_start_well", "A1") or "A1"))
        self.right_pipette_var.set(str(data.get("right_pipette", "") or (old_pipette if old_mount != "left" and old_pipette else "flex_1channel_1000")))
        self.right_tiprack_var.set(str(data.get("right_tiprack", "") or (old_tiprack if old_mount != "left" and old_tiprack else "opentrons_flex_96_filtertiprack_1000ul")))
        self.right_tiprack_slots_var.set(str(data.get("right_tiprack_slots", "") or (old_tiprack_slots if old_mount != "left" and old_tiprack_slots else "D2")))
        self.right_tip_start_column_var.set(str(data.get("right_tip_start_column", "1") or "1"))
        self.right_tip_start_well_var.set(str(data.get("right_tip_start_well", "A1") or "A1"))
        self.trash_slot_var.set(str(data.get("trash_slot", "A3") or "A3"))
        self.flex_gripper_var.set(bool(data.get("flex_gripper", False)))
        self._apply_module_state(data)
        self.source_labware_var.set(str(data.get("source_labware", "nest_96_wellplate_2ml_deep") or "nest_96_wellplate_2ml_deep"))
        self.source_slot_var.set(str(data.get("source_slot", "C1") or "C1"))
        self.source_style_var.set(str(data.get("source_style", "96 well") or "96 well"))
        self.dest_labware_var.set(str(data.get("dest_labware", "corning_96_wellplate_360ul_flat") or "corning_96_wellplate_360ul_flat"))
        self.dest_slot_var.set(str(data.get("dest_slot", "C2") or "C2"))
        self.dest_style_var.set(str(data.get("dest_style", "96 well") or "96 well"))
        configs = data.get("labware_configs")
        if isinstance(configs, list) and configs:
            self.labware_configs = [dict(item) for item in configs if isinstance(item, dict)]
        else:
            self.labware_configs = [
                {"alias": "source1", "role": "source", "load_name": self.source_labware_var.get(), "slot": self.source_slot_var.get(), "map_style": self.source_style_var.get()},
                {"alias": "dest1", "role": "destination", "load_name": self.dest_labware_var.get(), "slot": self.dest_slot_var.get(), "map_style": self.dest_style_var.get()},
            ]
        source_alias = str(data.get("source_labware_alias", "") or "")
        dest_alias = str(data.get("dest_labware_alias", "") or "")
        self.source_labware_alias_var.set(source_alias if source_alias in self._source_labware_aliases() else (self._source_labware_aliases()[0] if self._source_labware_aliases() else ""))
        self.dest_labware_alias_var.set(dest_alias if dest_alias in self._dest_labware_aliases() else (self._dest_labware_aliases()[0] if self._dest_labware_aliases() else ""))
        self.step_name_var.set(str(data.get("step_name", "") or ""))
        self.tip_policy_var.set(self._normalize_tip_policy(data.get("tip_policy")))
        self.blowout_location_var.set(str(data.get("blowout_location", "No blowout") or "No blowout"))
        self.blowout_labware_alias_var.set(str(data.get("blowout_labware_alias", "") or ""))
        self.blowout_well_var.set(str(data.get("blowout_well", "") or ""))
        self.eight_channel_mode_var.set(str(data.get("eight_channel_mode", "Auto from wells") or "Auto from wells"))
        self.aspirate_rate_var.set(str(data.get("aspirate_rate", "") or ""))
        self.dispense_rate_var.set(str(data.get("dispense_rate", "") or ""))
        self.aspirate_depth_mm_var.set(str(data.get("aspirate_depth_mm", "") or ""))
        self.aspirate_depth_reference_var.set(str(data.get("aspirate_depth_reference", "from bottom") or "from bottom"))
        self.dispense_depth_mm_var.set(str(data.get("dispense_depth_mm", "") or ""))
        self.dispense_depth_reference_var.set(str(data.get("dispense_depth_reference", "from top") or "from top"))
        self.multi_dispense_extra_percent_var.set(str(data.get("multi_dispense_extra_percent", "0") or "0"))
        self.tip_touch_var.set(bool(data.get("tip_touch", False)))
        self.pre_wet_tip_var.set(bool(data.get("pre_wet_tip", False)))
        self.mix_enabled_var.set(bool(data.get("mix_enabled", False)))
        self.mix_timing_var.set(str(data.get("mix_timing", "Before aspirating") or "Before aspirating"))
        self.mix_repetitions_var.set(str(data.get("mix_repetitions", "3") or "3"))
        self.mix_volume_var.set(str(data.get("mix_volume_ul", "") or ""))
        self.post_source_mix_delay_seconds_var.set(str(data.get("post_source_mix_delay_seconds", "") or ""))
        self.mix_aspirate_rate_var.set(str(data.get("mix_aspirate_rate", "") or ""))
        self.mix_dispense_rate_var.set(str(data.get("mix_dispense_rate", "") or ""))
        self.mix_aspirate_depth_mm_var.set(str(data.get("mix_aspirate_depth_mm", "") or ""))
        self.mix_aspirate_depth_reference_var.set(str(data.get("mix_aspirate_depth_reference", "from bottom") or "from bottom"))
        self.mix_dispense_depth_mm_var.set(str(data.get("mix_dispense_depth_mm", "") or ""))
        self.mix_dispense_depth_reference_var.set(str(data.get("mix_dispense_depth_reference", "from bottom") or "from bottom"))
        self.delay_air_gap_enabled_var.set(self._delay_air_gap_feature_enabled(data))
        self.post_aspirate_delay_seconds_var.set(str(data.get("post_aspirate_delay_seconds", "") or ""))
        self.post_dispense_delay_seconds_var.set(str(data.get("post_dispense_delay_seconds", "") or ""))
        self.pre_move_delay_seconds_var.set(str(data.get("pre_move_delay_seconds", "") or ""))
        self.air_gap_enabled_var.set(bool(data.get("air_gap_enabled", False)))
        self.air_gap_volume_var.set(str(data.get("air_gap_volume_ul", "") or ""))
        self.air_gap_height_var.set(str(data.get("air_gap_height_mm", "5") or "5"))
        self.air_gap_flow_rate_var.set(str(data.get("air_gap_flow_rate", "") or ""))
        self.rows = [dict(row) for row in data.get("rows", []) or [] if isinstance(row, dict)]
        self._normalize_imported_sequences()
        for row in self.rows:
            row.setdefault("step_name", "")
            row.setdefault("source_labware_alias", self.source_labware_alias_var.get() or "source1")
            row.setdefault("dest_labware_alias", self.dest_labware_alias_var.get() or "dest1")
            row["chemical"] = str(row.get("chemical", row.get("chemical_id", "")) or "").strip()
            row.setdefault("reaction_umol", "")
            row["is_building_block"] = coerce_bool(row.get("is_building_block", False))
            row["tip_policy"] = self._normalize_tip_policy(row.get("tip_policy"))
            row.setdefault("blowout_location", "No blowout")
            row.setdefault("blowout_labware_alias", "")
            row.setdefault("blowout_well", "")
            row.setdefault("mix_enabled", False)
            row.setdefault("mix_timing", "Before aspirating")
            row.setdefault("mix_repetitions", "3")
            row.setdefault("mix_volume_ul", "")
            row.setdefault("post_source_mix_delay_seconds", "")
            row.setdefault("mix_aspirate_rate", "")
            row.setdefault("mix_dispense_rate", "")
            row.setdefault("mix_aspirate_depth_mm", "")
            row.setdefault("mix_aspirate_depth_reference", "from bottom")
            row.setdefault("mix_dispense_depth_mm", "")
            row.setdefault("mix_dispense_depth_reference", "from bottom")
            row["delay_air_gap_enabled"] = self._delay_air_gap_feature_enabled(row)
            row.setdefault("post_aspirate_delay_seconds", "")
            row.setdefault("post_dispense_delay_seconds", "")
            row.setdefault("pre_move_delay_seconds", "")
            row.setdefault("air_gap_enabled", False)
            row.setdefault("air_gap_volume_ul", "")
            row.setdefault("air_gap_height_mm", "5")
            row.setdefault("air_gap_flow_rate", "")
            if self._row_is_batch(row):
                sources = self._batch_sources(row)
                if not sources:
                    source = str(row.get("source_well", "") or "").strip().upper()
                    sources = [source] if source else []
                    row["batch_source_wells"] = ",".join(sources)
                if not isinstance(row.get("batch_source_chemicals"), dict):
                    legacy_chemical = str(row.get("chemical", "") or "").strip()
                    row["batch_source_chemicals"] = {source: legacy_chemical for source in sources}
                chemical_map = self._batch_chemical_map(row)
                if not isinstance(row.get("batch_source_building_blocks"), dict):
                    legacy_building_block = coerce_bool(row.get("is_building_block", False))
                    row["batch_source_building_blocks"] = {
                        source: legacy_building_block if chemical_map.get(source, "") else False
                        for source in sources
                    }
                else:
                    imported_building_blocks = self._batch_building_block_map(row)
                    row["batch_source_building_blocks"] = {
                        source: imported_building_blocks.get(source, False) if chemical_map.get(source, "") else False
                        for source in sources
                    }
                if isinstance(row.get("batch_source_volume_modes"), dict):
                    imported_modes = self._batch_string_map(row, "batch_source_volume_modes")
                    row["batch_source_volume_modes"] = {
                        source: (
                            BATCH_VOLUME_MODE_UMOL
                            if imported_modes.get(source, "").lower() == BATCH_VOLUME_MODE_UMOL
                            else BATCH_VOLUME_MODE_UL
                        )
                        for source in sources
                    }
                else:
                    row["batch_source_volume_modes"] = {
                        source: BATCH_VOLUME_MODE_UL for source in sources
                    }
                imported_umol = self._batch_string_map(row, "batch_source_umol")
                row["batch_source_umol"] = {
                    source: imported_umol.get(source, "") for source in sources
                }
                if isinstance(row.get("batch_source_volumes_ul"), dict):
                    imported_volumes = self._batch_string_map(row, "batch_source_volumes_ul")
                    row["batch_source_volumes_ul"] = {
                        source: imported_volumes.get(source, "") for source in sources
                    }
                else:
                    legacy_volume = str(row.get("volume_ul", "") or "").strip()
                    row["batch_source_volumes_ul"] = {
                        source: legacy_volume for source in sources
                    }
                destination_sets = self._batch_destination_groups(row)
                if not destination_sets:
                    dest_labware = self._labware_by_alias(row.get("dest_labware_alias", "dest1")) or {}
                    try:
                        destination_wells = _parse_wells(
                            str(row.get("dest_wells", "")),
                            dest_labware.get("map_style", self.dest_style_var.get()),
                        )
                    except Exception:
                        destination_wells = []
                    if str(row.get("batch_transfer_kind", "") or "") == "8-channel":
                        destination_sets = _split_eight_channel_patterns(
                            destination_wells,
                            str(dest_labware.get("map_style", self.dest_style_var.get())),
                        )
                    elif len(sources) == 1:
                        destination_sets = [[well] for well in destination_wells]
                    elif sources and len(destination_wells) % len(sources) == 0:
                        destination_sets = [
                            destination_wells[index:index + len(sources)]
                            for index in range(0, len(destination_wells), len(sources))
                        ]
                    row["batch_destination_sets"] = destination_sets
                row["batch_transfer_version"] = 4
                row["chemical"] = ""
                row["reaction_umol"] = ""
                row["is_building_block"] = False
                if str(row.get("batch_transfer_kind", "") or "") == "8-channel":
                    row.setdefault("pipette_key", "Auto")
                    if not str(row.get("batch_pipette_mount", "") or "").strip():
                        try:
                            row["batch_pipette_mount"] = self._configured_batch_8_channel_mount(
                                str(row.get("pipette_key", "Auto") or "Auto")
                            )
                        except ValueError:
                            row["batch_pipette_mount"] = ""
                else:
                    row.setdefault("batch_pipette_mount", "")
        for row in self.rows:
            if self._basic_incomplete_row_reasons(row):
                row["_draft"] = True
        self._on_robot_changed(reset_api=False)
        self._refresh_table()
        self._start_new_transfer(announce=False, clear_step_name=False)
        self._set_transfer_type(str(data.get("transfer_type", "single") or "single") == "batch")
        self.status_var.set("Imported Opentrons tab state.")
