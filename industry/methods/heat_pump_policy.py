# Pure methods extracted from the supplied handoff: preparation_history/scripts/update_all_industry_share_limits.py
# No installer, workbook migration, or historical entry point is executed.
import re
HP_FIELDS = {60: 'hp_below60_share', 80: 'hp_below80_share', 125: 'hp_below125_share', 150: 'hp_below150_share', 'source': 'hp_source_heat_share'}

def hp_eligibility(low, mid, coefficients):
    c = coefficients
    result = {60: low * float(c['lt100_below60']), 80: low * float(c['lt100_below80']), 125: low + mid * float(c['heat100_400_below125']), 150: low + mid * float(c['heat100_400_below150'])}
    result['source'] = result[150] * float(c['source_heat_fraction'])
    return result
