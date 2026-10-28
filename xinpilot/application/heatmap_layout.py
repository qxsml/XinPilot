"""Reaction heat-map geometry from the recorded synthesis inputs."""
from .tecan_domain import mode_dims_order, row_number_to_label


def reaction_mode(records):
    modes = []
    for record in records:
        mode = str(record.get('dest_mode') or '').strip()
        style = str(record.get('dest_map_style') or '')
        if not mode and style:
            size = next((n for n in ('384', '48', '24') if n in style), '96')
            mode = f'{size}-well horizontal'
        if mode:
            modes.append(mode)
    if not modes:
        return '96-well horizontal'
    # Orientation changes Tecan numeric addressing, not physical well identity.
    # Keep source modes on transfers; only the shared reaction view is horizontal.
    geometry = {mode_dims_order(m)[:2] for m in modes}
    if len(geometry) > 1:
        raise ValueError('The recorded reaction inputs have conflicting destination plate sizes. Check the synthesis plans and push the corrected inputs again.')
    return modes[0].replace('vertical', 'horizontal')


def heatmap_layout(mode='96-well horizontal'):
    rows, cols, _ = mode_dims_order(mode)
    letters = [row_number_to_label(r) for r in range(1, rows + 1)]
    numbers = [str(c) for c in range(1, cols + 1)]
    if 'vertical' in mode.lower():
        return numbers[::-1], letters, [[r + c for r in letters] for c in numbers[::-1]]
    return letters, numbers, [[r + c for c in numbers] for r in letters]
