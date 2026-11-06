# Pure methods extracted from the supplied handoff: preparation_history/analysis/complex_electricity_review_2026_10_31/review_complex_electricity.py
# No installer, workbook migration, or historical entry point is executed.
import re
MATURE = {'common_low_enthalpy_heat', 'common_steam_or_drying_heat', 'electrical_nonthermal_service', 'electrical_or_mechanical_process', 'cooling_service', 'mechanical_fuel_service'}

def envelope(c, observed, baseline):
    """Full established-service coverage; partial unresolved furnace coverage."""
    if c['feedstock']:
        return (baseline, 'fixed_material', 0.0)
    if c['useful_ktoe'] <= 1e-12:
        return (baseline, 'inactive_placeholder', 0.0)
    text = ' / '.join((o['path'] for o in observed)).casefold()
    if re.search('blast /basic oxygen|sinter/pellet|aluminium electrolysis', text):
        return (baseline, 'reduction_chemistry_retained', 0.0)
    if 'clinker production' in c['component'].casefold():
        return (baseline, 'clinker_excluded', 0.0)
    service = c['service'].casefold()
    established_melting = c['branch'] == 'isi_electric_arc' and ('smelter' in service or 'electric arc' in service) or ('secondary aluminium' in service and 'remelting' in service)
    if established_melting:
        return (1.0, 'established_electric_melting', 1.0)
    non_e = [o for o in observed if o['fuel'] != 'Electricity']
    amount = sum((o['useful'] for o in non_e))
    mature = sum((o['useful'] for o in non_e if o['kind'] in MATURE)) / amount if amount > 1e-12 else 1.0
    maximum = baseline + (1.0 - baseline) * (mature + 0.5 * (1.0 - mature))
    return (min(1.0, max(baseline, maximum)), 'established_service' if mature > 1.0 - 1e-10 else 'mixed_or_process_furnace', mature)
