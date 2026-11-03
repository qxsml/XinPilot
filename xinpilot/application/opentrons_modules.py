"""Module stacking checks using the installed Opentrons definitions and rules.

Dependencies are loaded only when a Heater-Shaker adapter is actually used.
Definition versions follow the selected protocol API, just as robot loading does.
"""
from functools import lru_cache


@lru_cache(maxsize=128)
def _definition(load_name, api_level):
    from opentrons.protocol_api.core.engine.load_labware_params import resolve
    from opentrons.protocols.api_support.types import APIVersion
    from opentrons_shared_data.labware import load_definition
    from opentrons_shared_data.labware.labware_definition import labware_definition_type_adapter

    major, minor = (int(part) for part in api_level.split('.'))
    _, version = resolve(load_name, None, None, [], APIVersion(major, minor))
    return labware_definition_type_adapter.validate_python(load_definition(load_name, version))


def validate_heater_shaker_stack(module, labware, api_level):
    """Reject unsupported plate/adapter stacks before writing a protocol."""
    if module.get('key') != 'heater_shaker' and module.get('load_name') != 'heaterShakerModuleV1':
        return
    adapter = str(module.get('adapter') or '').strip()
    if not adapter:
        return  # Legacy combined adapter/labware definitions use direct module loading.
    try:
        from opentrons.protocol_engine.resources.labware_validation import (
            validate_definition_is_adapter, validate_legacy_labware_can_be_stacked,
        )
        from opentrons_shared_data.labware.labware_definition import LabwareDefinition2

        parent = _definition(adapter, api_level)
        if not validate_definition_is_adapter(parent):
            raise ValueError(f'{adapter} is not an Opentrons adapter definition.')
        if labware is None:
            return  # Empty module; any later plate movement is checked separately.
        load_name = str(labware.get('load_name') or '').strip()
        child = _definition(load_name, api_level)
        if not isinstance(child, LabwareDefinition2):
            raise ValueError(f'Cannot verify the stacking schema for {load_name}.')
        if not validate_legacy_labware_can_be_stacked(child, adapter):
            raise ValueError(f'{load_name} cannot be loaded onto {adapter} according to the '
                             f'Opentrons definitions for API {api_level}. Select a compatible pair.')
    except (ImportError, OSError, KeyError) as exc:
        raise ValueError(f'Cannot verify Heater-Shaker labware/adapter compatibility: {exc}') from exc
