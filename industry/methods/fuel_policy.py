# Pure methods extracted from the supplied handoff: model/scripts/update_industry_fuel_compatibility.py
# No installer, workbook migration, or historical entry point is executed.
import re
LIGNIN_ADDITIONAL_SHARE = 0.02
COMMON = {'common_low_enthalpy_heat', 'common_steam_or_drying_heat'}
HEAT = COMMON | {'process_specific_heat_or_mixed_service'}
SOLID = {'Coal', 'Lignite', 'Biomass'}
LIQUID = {'diesel', 'fuel_oil', 'kerosene', 'petrol', 'Oil', 'bitumen'}
COMBUSTIBLE = SOLID | LIQUID | {'Gas', 'LPG'}
ALTERNATIVE = {'H2', 'Hydrogen', 'ammonia', 'DME', 'methanol', 'e_methane', 'e_diesel', 'e_kerosene'}
FAMILIES = {'H2': COMBUSTIBLE, 'Hydrogen': COMBUSTIBLE, 'ammonia': LIQUID | {'Gas', 'LPG'}, 'methanol': COMBUSTIBLE, 'DME': LIQUID | {'LPG'}, 'e_methane': {'Gas', 'LPG'}, 'e_diesel': LIQUID, 'e_kerosene': LIQUID}
BLOCKED = re.compile('smelters|blast\\s*/\\s*basic oxygen|sinter\\s*/\\s*pellet|aluminium electrolysis', re.I)
CHEMICAL_ROUTE = re.compile('blast\\s*/\\s*basic oxygen|sinter\\s*/\\s*pellet|aluminium electrolysis', re.I)
OIL_SOURCE = {'diesel', 'fuel_oil', 'LPG', 'kerosene', 'petrol', 'Oil', 'bitumen'}

def classify(path):
    process = path[1]
    text = ' / '.join(path[1:]).casefold()
    if 'feedstock' in text:
        return 'material_feedstock'
    if 'cooling' in text or 'refrigeration' in text:
        return 'cooling_service'
    if 'diesel motors' in text:
        return 'mechanical_fuel_service'
    if process in {'Lighting', 'Air compressors', 'Motor drives', 'Fans and pumps'}:
        return 'electrical_nonthermal_service'
    if 'low-enthalpy' in text:
        return 'common_low_enthalpy_heat'
    if 'sinter' not in text and ('steam' in text or 'drying' in text):
        return 'common_steam_or_drying_heat'
    if any((x in text for x in ('electric machinery', 'general machinery', 'electric mechanical', 'generic electric process', 'finishing electric', 'printing and publishing', 'grinding', 'mixing of raw material', 'glass: forming', 'glass: finishing', 'pulp: cleaning', 'stock preparation - mechanical'))):
        return 'electrical_or_mechanical_process'
    return 'process_specific_heat_or_mixed_service'

def fractions(observed, basis, fuels):
    rows = [r for r in observed if r['fuel'] in fuels and r['kind'] != 'material_feedstock']
    total = sum((r[basis] for r in rows))
    valid = [r for r in rows if r['kind'] in HEAT and (not CHEMICAL_ROUTE.search(r['path'])) and (not (r['fuel'] in SOLID and BLOCKED.search(r['path'])))]
    common = [r for r in valid if r['kind'] in COMMON]
    return (sum((r[basis] for r in valid)) / total if total else 0.0, sum((r[basis] for r in common)) / total if total else 0.0)

def service_pools(group, observed, basis, band=None):
    """Within-fuel weights preserve each model row's own historical denominator."""
    heat = {}
    common = {}
    base = {}
    for r in group.itertuples():
        b = float(r.share_fuel_2020)
        fuel = r.fuel_type
        base[r.unit_name] = b
        if fuel not in COMBUSTIBLE | {'heat'}:
            continue
        source_fuels = OIL_SOURCE if fuel == 'Oil' else {'fuel_oil'} if fuel == 'kerosene' else {fuel}
        h, c = fractions(observed, basis, source_fuels)
        if band in {'<100C', '100_400C'}:
            h = c = 1.0
        elif band in {'400_1000C', '>1000C'}:
            h = h if fuel in SOLID else 1.0
            c = 0.0
        heat[fuel] = heat.get(fuel, 0.0) + b * h
        common[fuel] = common.get(fuel, 0.0) + b * c
    pools = {}
    for target, family in FAMILIES.items():
        pools[target] = sum((heat.get(f, 0.0) if f in family else common.get(f, 0.0) for f in COMBUSTIBLE | {'heat'}))
    diesel = sum((float(r.share_fuel_2020) for r in group.itertuples() if r.fuel_type == 'diesel'))
    pools['e_diesel'] += max(0.0, diesel - heat.get('diesel', 0.0))
    pools['solid'] = sum((heat.get(f, 0.0) for f in SOLID))
    return (base, pools, heat, common)

def ceiling(row, base, pools, band=None, feedstock=False):
    b = float(row.share_fuel_2020)
    fuel = row.fuel_type
    clip = lambda v: min(1.0, max(b, float(v)))
    if fuel == 'Biomass':
        return (b, 'Biomass: baseline share ceiling; no expansion')
    if feedstock:
        return (b, 'Fixed material/feedstock service')
    if band == 'NON_HEAT':
        if fuel == 'e_methane':
            return (clip(base.get('Gas_industry', 0.0)), 'NON_HEAT: identical gas service only')
        if fuel == 'e_diesel':
            return (clip(base.get('diesel_industry', 0.0)), 'NON_HEAT: identical diesel service only')
        return (b, 'NON_HEAT: original fixed service; no new combustion route')
    if fuel in ALTERNATIVE:
        return (clip(pools[fuel]), 'Compatible fuel family heat plus replacement of common boiler heat')
    if fuel == 'lignin':
        return (clip(min(b + LIGNIN_ADDITIONAL_SHARE, pools['solid'])), 'Lignin: at most +2 percentage points, within eligible solid heat')
    return (float(row.max_share_fuel), 'Retained input')
