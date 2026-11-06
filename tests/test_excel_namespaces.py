"""Native worksheet patching must accept valid prefixed and empty Excel XML."""
from copy import copy
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED
import xml.etree.ElementTree as ET

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.table import Table

from default_model_inputs import complete_defaults
from excel_integrity import MAIN, patch_sheet_parts, workbook_errors
from model_input_bundle import replace_sheets, sheet_paths


def members(path):
    with ZipFile(path) as book:
        return {entry.filename: book.read(entry.filename) for entry in book.infolist()}


def rewrite_part(path, name, transform):
    with ZipFile(path) as book:
        parts = [(copy(entry), book.read(entry.filename)) for entry in book.infolist()]
    with ZipFile(path, 'w', ZIP_DEFLATED) as book:
        for entry, payload in parts:
            book.writestr(entry, transform(payload) if entry.filename == name else payload)


def prefix_sheet(path, sheet, prefix='ss'):
    with ZipFile(path) as book:
        name = sheet_paths(book)[sheet]
    def transform(payload):
        tree = ET.fromstring(payload)
        with patch.dict(ET._namespace_map, {MAIN: prefix}, clear=True):
            return ET.tostring(tree, encoding='utf-8', xml_declaration=True)
    rewrite_part(path, name, transform)


class ExcelNamespaceTests(unittest.TestCase):
    def make_workbook(self, path, empty=False, table=False):
        book = Workbook()
        sheet = book.active
        sheet.title = 'tech_cost_years'
        if not empty:
            sheet.append(['System', 'zone', 'year', 'capital_cost'])
            sheet.append(['HR', 'HR1', 2025, 12.5])
            if table:
                sheet.add_table(Table(displayName='TechnologyCosts', ref='A1:D2'))
        keep = book.create_sheet('unchanged')
        keep['A1'] = '=6*7'
        book.save(path)
        book.close()
        with ZipFile(path) as archive:
            name = sheet_paths(archive)['unchanged']
        rewrite_part(path, name, lambda b: re.sub(rb'<v\s*/>|<v>\s*</v>', b'<v>42</v>', b))

    def test_prefixed_native_cost_sheet_keeps_tables_caches_and_other_parts(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'costs.xlsx'
            self.make_workbook(path, table=True)
            prefix_sheet(path, 'tech_cost_years')
            before = members(path)
            with ZipFile(path) as archive:
                changed = sheet_paths(archive)['tech_cost_years']
            self.assertIn(b'<ss:sheetData>', before[changed])
            result = pd.DataFrame(dict(System=['HU', 'HU'], zone=['HU110', 'HU120'], year=[2025, 2030], capital_cost=[12.5, 11.25]))
            replace_sheets(path, {'tech_cost_years': result})
            self.assertEqual(workbook_errors(path), [])
            pd.testing.assert_frame_equal(pd.read_excel(path, 'tech_cost_years'), result)
            after = members(path)
            for name, value in before.items():
                if name != changed and not name.startswith('xl/tables/'):
                    self.assertEqual(after[name], value, name)
            book = load_workbook(path, read_only=False, data_only=True)
            self.assertEqual(book['unchanged']['A1'].value, 42)
            self.assertEqual(book['tech_cost_years'].tables['TechnologyCosts'].ref, 'A1:D3')
            book.close()

    def test_empty_native_sheet_supports_prefixed_and_default_namespace(self):
        for prefixed in (False, True):
            with self.subTest(prefixed=prefixed), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'empty.xlsx'
                self.make_workbook(path, empty=True)
                if prefixed:
                    prefix_sheet(path, 'tech_cost_years')
                with ZipFile(path) as archive:
                    part = sheet_paths(archive)['tech_cost_years']
                # Exercise the valid self-closing form explicitly.
                rewrite_part(path, part, lambda b: re.sub(rb'<((?:[\w.-]+:)?sheetData)>\s*</\1>', rb'<\1/>', b))
                result = pd.DataFrame(dict(year=[2025, 2030]))
                replace_sheets(path, {'tech_cost_years': result})
                pd.testing.assert_frame_equal(pd.read_excel(path, 'tech_cost_years'), result)
                self.assertEqual(workbook_errors(path), [])

    def test_prefixed_replacement_carries_namespace_into_unprefixed_target(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target, replacement = root / 'target.xlsx', root / 'incoming.xlsx'
            self.make_workbook(target)
            expected = pd.DataFrame(dict(year=[2025, 2030, 2035], System='HU'))
            expected.to_excel(replacement, sheet_name='tech_cost_years', index=False)
            prefix_sheet(replacement, 'tech_cost_years', prefix='incoming')
            with ZipFile(target) as old, ZipFile(replacement) as new:
                patches = patch_sheet_parts(old, new, sheet_paths(old), sheet_paths(new), {'tech_cost_years': expected})
            for name, payload in patches.items():
                rewrite_part(target, name, lambda _: payload)
            pd.testing.assert_frame_equal(pd.read_excel(target, 'tech_cost_years'), expected)
            self.assertEqual(workbook_errors(target), [])

    def test_prefixed_cost_sheet_regional_defaults_reproduce_reported_export_step(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'flex_tech_efuel.xlsx'
            self.make_workbook(path)
            prefix_sheet(path, 'tech_cost_years', prefix='ns0')
            pd.DataFrame(dict(System='HU', Zone=['HU110', 'HU120'], period=1, Power=[1., 3.])).to_csv(root / 'electricity_demand.csv', index=False)
            changes = complete_defaults(root, {('HU', 'HU110'), ('HU', 'HU120')}, ['electricity_demand.csv'], [], 'unused.xlsx', [])
            self.assertTrue(any(item.get('sheet') == 'tech_cost_years' for item in changes))
            result = pd.read_excel(path, 'tech_cost_years')
            local = result.loc[result.System.eq('HU')]
            self.assertEqual(set(local.zone), {'HU110', 'HU120'})
            self.assertTrue(local.capital_cost.eq(12.5).all())
            self.assertEqual(workbook_errors(path), [])

    def test_invalid_missing_sheet_data_fails_without_changing_original(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'broken.xlsx'
            self.make_workbook(path, empty=True)
            with ZipFile(path) as book:
                part = sheet_paths(book)['tech_cost_years']
            rewrite_part(path, part, lambda b: re.sub(rb'<sheetData\s*/>|<sheetData>\s*</sheetData>', b'', b))
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, 'Cannot locate native sheet data in tech_cost_years'):
                replace_sheets(path, {'tech_cost_years': pd.DataFrame(dict(year=[2025]))})
            self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
