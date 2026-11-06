# Pure methods extracted from the supplied handoff: model/scripts/expand_complex_industry_sectors.py
# No installer, workbook migration, or historical entry point is executed.
"""Build process/fuel inputs for every Croatian JRC-IDEES industry sector.

Parse the workbook's actual indentation tree instead of treating subtotal and
fuel rows as independent energy services. All quoted numbers retain source
sheet/cell provenance. Model substitution options and cost proxies are marked
as assumptions, rather than attributed to JRC.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import shutil
from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter
ROOT = Path(__file__).resolve().parents[1]
SECTORS = {'ISI': 'Iron_steel', 'NFM': 'Non_ferrous_metals', 'CHI': 'Chemical_petrochemical', 'NMM': 'Non_metallic_minerals', 'PPA': 'Paper_pulp_printing', 'FBT': 'Food_beverages_tobacco', 'TRE': 'Transport_equipment', 'MAE': 'Machinery', 'TEL': 'Textile_leather', 'WWP': 'Wood_wood_products', 'OIS': 'Not_elsewhere_specified_(industry)'}
FUELS = {'Solids': 'Coal', 'Coke': 'Coal', 'Refinery gas': 'Gas', 'LPG': 'LPG', 'Diesel oil and liquid biofuels': 'diesel', 'Diesel oil': 'diesel', 'Fuel oil': 'fuel_oil', 'Other liquids': 'fuel_oil', 'Naphtha': 'fuel_oil', 'Natural gas and biogas': 'Gas', 'Natural gas': 'Gas', 'Derived gases': 'Gas', 'Biomass and waste': 'Biomass', 'Distributed steam': 'heat', 'Electricity': 'Electricity', 'Solar and geothermal': 'heat', 'Ambient heat': 'heat'}
UNITS = {'Coal': 'Coal_industry', 'Gas': 'Gas_industry', 'LPG': 'LPG_industry', 'diesel': 'diesel_industry', 'fuel_oil': 'Fuel_oil_industry', 'Biomass': 'Biomass_industry', 'heat': 'heat_industry', 'Electricity': 'Electricity_industry', 'Hydrogen': 'Hydrogen_industry', 'H2': 'Hydrogen_industry', 'non_energy_gas': 'non_energy_gas_industry', 'non_energy_oil': 'non_energy_oil_industry', 'ammonia': 'ammonia_industry', 'e_methane': 'e_methane_industry', 'e_diesel': 'e_diesel_industry', 'e_kerosene': 'e_kerosene_industry', 'methanol': 'methanol_industry', 'DME': 'DME_industry', 'lignin': 'lignin_industry'}
SYNTHETIC = {'H2', 'ammonia', 'e_methane', 'e_diesel', 'e_kerosene', 'methanol', 'DME', 'lignin'}
KTOE_TO_MWH = 11630.0
BASE_YEAR = 2020
MODEL_CO2 = {'Coal': 0.38, 'Gas': 0.23, 'Oil': 0.4, 'LPG': 0.4, 'diesel': 0.4, 'fuel_oil': 0.4}
AMMONIA_INVENTORY_REFERENCE = 'https://www.haop.hr/sites/default/files/uploads/dokumenti/012_klima/dostava_podataka/Izvjesca/Croatian%20NIR%202025.pdf'
AMMONIA_REFORMING_REFERENCE = 'https://www.haop.hr/sites/default/files/uploads/dokumenti/012_klima/dostava_podataka/Izvjesca/NIR_2020_eng.pdf'

def historical_h2_reforming_process_co2(component):
    """Identify the one historically observed term already in H2 supply.

    Croatia NIR 2025 table 4.3-1 reports 535.3 kt from ammonia production in
    2020, matching the JRC observation at the inventory's printed precision.
    NIR section 4.3.1 identifies catalytic steam reforming of natural gas as
    its origin. Under the user's H2-fed convention this emission belongs at
    the chosen H2 supplier, rather than remaining a second process charge.
    Other observations require their own evidence and remain untouched.
    """
    if component['Industry'] == 'Chemical_petrochemical' and component['branch'] == 'chi_basic_chemicals' and (component['source_year'] == 2020) and (abs(component['process_co2'] - 535320.11) < 1e-05):
        return component['process_co2']
    return 0.0

def fuel_observation():
    """Keep every source stream traceable after several leaves are grouped."""
    return dict(useful=0.0, final=0.0, co2=0.0, source_cells=[], final_source_cells=[], emissions_source_cells=[])

def read_fossil_waste_proof(source):
    """Read primary evidence permitting an exact fossil/renewable split.

    The industry workbook groups renewable biomass and fossil waste. For the
    calibrated Croatian years, its accounted waste CO2 comes from one fossil
    waste class only. That class's published factor makes its energy quantity
    identifiable for each process; several fossil waste types would not.
    """
    paths = {kind: source.with_name(source.name.replace('_Industry_', f'_{kind}_')) for kind in ('EnergyBalance', 'EmissionBalance')}
    if not all((path.exists() for path in paths.values())):
        return {}
    energy = load_workbook(paths['EnergyBalance'], read_only=True, data_only=True)
    emission = load_workbook(paths['EmissionBalance'], read_only=True, data_only=True)
    try:
        energy_rows = list(energy['FC_IND_E'].values)
        factor_rows = list(emission['ef'].values)
        energy_years = {int(v): i for i, v in enumerate(energy_rows[0]) if isinstance(v, (int, float)) and 2000 <= v <= 2050}
        factor_years = {int(v): i for i, v in enumerate(factor_rows[0]) if isinstance(v, (int, float)) and 2000 <= v <= 2050}
        energy_codes = {str(r[1]): (i + 1, r) for i, r in enumerate(energy_rows) if len(r) > 1 and r[1] is not None}
        factor_codes = {str(r[1]): (i + 1, r) for i, r in enumerate(factor_rows) if len(r) > 1 and r[1] is not None}
        proof = {}
        for year in energy_years.keys() & factor_years.keys():
            col = energy_years[year]
            fcol = factor_years[year]
            total = float(energy_codes['W6100_6220'][1][col] or 0.0)
            industrial = float(energy_codes['W6100'][1][col] or 0.0)
            municipal = float(energy_codes['W6220'][1][col] or 0.0)
            factor = float(factor_codes['W6100'][1][fcol] or 0.0)
            proof[year] = dict(single_fossil_class=abs(total - industrial) < 1e-10 and abs(municipal) < 1e-10, waste_factor_t_per_toe=factor, factor_cell='ef!' + get_column_letter(fcol + 1) + str(factor_codes['W6100'][0]), composition_cells='; '.join(('FC_IND_E!' + get_column_letter(col + 1) + str(energy_codes[code][0]) for code in ('W6100_6220', 'W6100', 'W6220'))))
        return proof
    finally:
        energy.close()
        emission.close()

def slug(value):
    return re.sub('[^a-z0-9]+', '_', str(value).casefold()).strip('_')

def read_tree(sheet):
    rows = list(sheet.iter_rows())
    years = {int(c.value): j for j, c in enumerate(rows[0]) if isinstance(c.value, (int, float)) and 2000 <= c.value <= 2050}
    nodes = []
    stack = []
    for row in rows[4:]:
        c = row[0]
        if c.value is None:
            continue
        indent = int(c.alignment.indent)
        if indent == 0:
            break
        while stack and stack[-1]['indent'] >= indent:
            stack.pop()
        node = dict(label=str(c.value).strip(), row=c.row, indent=indent, path=tuple((n['label'] for n in stack)) + (str(c.value).strip(),), values={y: float(row[j].value or 0.0) for y, j in years.items()}, children=[], years=years)
        if stack:
            stack[-1]['children'].append(node)
        nodes.append(node)
        stack.append(node)
    return nodes

def leaf_nodes(node):
    if not node['children']:
        return [node]
    return [leaf for child in node['children'] for leaf in leaf_nodes(child)]

def leaf_fuel(label):
    if label in FUELS:
        return FUELS[label]
    low = label.casefold()
    if 'natural gas' in low or 'thermal cooling' in low or 'thermal connection' in low:
        return 'Gas'
    if 'diesel' in low:
        return 'diesel'
    if any((x in low for x in ('electric', 'lighting', 'compressor', 'motor drives', 'fans and pumps', 'microwave', 'freeze drying', 'mechanical', 'grinding', 'mixing', 'forming', 'finishing processes', 'printing and publishing', 'general machinery', 'pulp: cleaning', 'product finishing'))):
        return 'Electricity'
    raise ValueError(f'Unclassified JRC energy leaf: {label!r}')

def output_rows(sheet, branches):
    rows = list(sheet.values)
    start = next((i for i, r in enumerate(rows) if str(r[0]).startswith('Physical output')))
    end = next((i for i in range(start + 1, len(rows)) if rows[i][0] is None), len(rows))
    if len(branches) == 1 and 'index' in str(rows[start][0]).casefold():
        return {branches[0]: (start, 'index', 1.0)}
    result = {}
    for branch in branches:
        key = slug(branch)
        matches = [i for i in range(start + 1, end) if slug(rows[i][0]).startswith(key)]
        if not matches:
            raise ValueError(f'{sheet.title}: no physical output row for {branch}')
        i = matches[0]
        result[branch] = (i, 't_product', 1000.0)
    return result

def extract_source(path, waste_proof_by_sector=None):
    book = load_workbook(path, read_only=True, data_only=True)
    waste_proof = read_fossil_waste_proof(path)
    components = []
    branches = []
    evidence = []
    try:
        for code, industry in SECTORS.items():
            trees = {suffix: read_tree(book[code + suffix]) for suffix in ('_ued', '_fec', '_emi')}
            lookup = {suffix: {n['path']: n for n in nodes} for suffix, nodes in trees.items()}
            roots = [n for n in trees['_ued'] if n['indent'] == 1]
            outputs = output_rows(book[code], [n['label'] for n in roots])
            summary = list(book[code].values)
            year_cols = {int(v): j for j, v in enumerate(summary[0]) if isinstance(v, (int, float)) and 2000 <= v <= 2050}
            for root in roots:
                label = root['label']
                row, activity_unit, factor = outputs[label]
                activity = {y: float(summary[row][j] or 0.0) * factor for y, j in year_cols.items()}
                branch = {'Cement': 'cemment', 'Ceramics & other NMM': 'ceramics', 'Glass production': 'glass'}.get(label) if code == 'NMM' else code.lower() + '_' + slug(label)
                reference_year = BASE_YEAR if activity.get(BASE_YEAR, 0) > 0 else next((y for y in sorted(activity, reverse=True) if activity[y] > 0), BASE_YEAR)
                direct = [n for n in trees['_emi'] if n['path'][0] == label and n['label'] == 'Process emissions']
                process_co2 = sum((n['values'][reference_year] for n in direct)) * 1000.0
                branch_components = []
                for node in root['children']:
                    if node['indent'] != 2:
                        raise ValueError(f"Unexpected JRC component indentation: {node['path']}")
                    feedstock = 'feedstock' in node['label'].casefold()
                    fuel_data = defaultdict(fuel_observation)
                    for leaf in leaf_nodes(node):
                        useful = leaf['values'][reference_year]
                        fec = lookup['_fec'].get(leaf['path'])
                        emi = lookup['_emi'].get(leaf['path'])
                        if fec is None:
                            raise ValueError(f"Unmatched final-energy path: {leaf['path']}")
                        final = fec['values'][reference_year]
                        if useful <= 1e-12 and final <= 1e-12:
                            continue
                        if emi is None:
                            raise ValueError(f"Unmatched combustion-emission path: {leaf['path']}")
                        fuel = leaf_fuel(leaf['label'])
                        if feedstock:
                            fuel = 'non_energy_gas' if fuel == 'Gas' else 'non_energy_oil'
                        values = fuel_data[fuel]
                        values['useful'] += useful
                        values['final'] += final
                        values['co2'] += 0.0 if feedstock or emi is None else emi['values'][reference_year] * 1000.0
                        values['source_cells'].append(code + '_ued!' + get_column_letter(leaf['years'][reference_year] + 1) + str(leaf['row']))
                        values['final_source_cells'].append(code + '_fec!' + get_column_letter(fec['years'][reference_year] + 1) + str(fec['row']))
                        values['emissions_source_cells'].append(code + '_emi!' + get_column_letter(emi['years'][reference_year] + 1) + str(emi['row']))
                    useful = node['values'][reference_year]
                    actual = sum((v['useful'] for v in fuel_data.values()))
                    if abs(actual - useful) > max(1e-08, abs(useful) * 1e-08):
                        raise ValueError(f"Fuel leaves do not close {code}/{node['path']}: {actual} != {useful}")
                    component = branch + '_basic_el_dem' if node['label'] in ('Lighting', 'Air compressors', 'Motor drives', 'Fans and pumps') else branch + '_Low-enthalpy_heat' if node['label'] == 'Low-enthalpy heat' else node['label'] if code == 'NMM' else code + '_' + branch + '__' + slug(node['label'])
                    existing = next((c for c in branch_components if c['component'] == component), None)
                    if existing:
                        existing['useful_ktoe'] += useful
                        for fuel, v in fuel_data.items():
                            dest = existing['fuels'].setdefault(fuel, fuel_observation())
                            for field in ('useful', 'final', 'co2'):
                                dest[field] += v[field]
                            for field in ('source_cells', 'final_source_cells', 'emissions_source_cells'):
                                dest[field] += v[field]
                        continue
                    branch_components.append(dict(Industry=industry, branch=branch, component=component, service=node['label'], useful_ktoe=useful, fuels=dict(fuel_data), feedstock=feedstock, activity_unit=activity_unit, output=activity[reference_year], source_year=reference_year, source_sheet=code + '_ued', source_row=node['row'], process_co2=0.0, process_co2_source_cells=[], code=code))
                total = sum((c['useful_ktoe'] for c in branch_components))
                assert abs(total - root['values'][reference_year]) < max(1e-08, total * 1e-08), (industry, label, total, root['values'][reference_year])
                if process_co2 and branch_components:
                    emitter = max(branch_components, key=lambda c: c['useful_ktoe'])
                    emitter['process_co2'] = process_co2
                    emitter['process_co2_source_cells'] = [code + '_emi!' + get_column_letter(n['years'][reference_year] + 1) + str(n['row']) for n in direct]
                branches.append(dict(Industry=industry, branch=branch, label=label, activity=activity, activity_unit=activity_unit, source_sheet=code, source_output_row=row + 1, source_year=reference_year, useful_MWh=total * KTOE_TO_MWH, process_CO2_t=process_co2))
                components += branch_components
                for c in branch_components:
                    for fuel, v in c['fuels'].items():
                        waste_share = 0.0
                        if fuel == 'Biomass' and v['co2'] > 1e-08:
                            proof = (waste_proof_by_sector or {}).get((code, reference_year), waste_proof.get(reference_year, {}))
                            if not proof.get('single_fossil_class') or proof.get('waste_factor_t_per_toe', 0.0) <= 0:
                                raise ValueError(f'Cannot uniquely split biomass/fossil waste for {reference_year}; matching single-class EnergyBalance/EmissionBalance evidence required')
                            waste_final = v['co2'] / (1000.0 * proof['waste_factor_t_per_toe'])
                            waste_share = waste_final / v['final']
                            if not -1e-10 <= waste_share <= 1.0 + 1e-10:
                                raise ValueError(f"Fossil waste energy exceeds observed mixed fuel in {c['component']}: {waste_share}")
                            waste_share = min(1.0, max(0.0, waste_share))
                            v['waste_split_source'] = proof.get('basis_note') or f"EmissionBalance {proof['factor_cell']}; EnergyBalance {proof['composition_cells']}; single industrial fossil-waste class verified."
                        v['fossil_waste_final_energy_share'] = waste_share
                        evidence.append(dict(Industry=industry, branch=branch, component=c['component'], fuel=fuel, source_year=reference_year, source_cells='; '.join(v['source_cells']), final_source_cells='; '.join(v['final_source_cells']), emissions_source_cells='; '.join(v['emissions_source_cells']), useful_ktoe=v['useful'], final_ktoe=v['final'], fuel_CO2_t=v['co2'], fossil_waste_final_energy_share=waste_share, fossil_waste_final_ktoe=v['final'] * waste_share, renewable_biomass_final_ktoe=v['final'] * (1.0 - waste_share) if fuel == 'Biomass' else None, source_waste_split=v.get('waste_split_source'), activity=activity[reference_year], activity_unit=activity_unit))
    finally:
        book.close()
    return (components, branches, evidence)
