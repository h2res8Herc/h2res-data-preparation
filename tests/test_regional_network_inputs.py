"""Merged native network headers and regional transfer completeness."""
from pathlib import Path
import tempfile
import unittest

import pandas as pd
from openpyxl import Workbook,load_workbook

from regional_network_inputs import blocks,complete_blocks,internal_regions,outside_regions,checks
from model_input_bundle import replace_sheets
from excel_integrity import workbook_errors


class RegionalNetworkTests(unittest.TestCase):
    def fixture(self,outside=False):
        base=['System','zone','km'] if outside else ['zone','System','zoneTo','To','km']
        fields=['cap_mw','max_cap','max_cap_period','var_cost','loss','el_dem','life_time','decom_start_new','decom_start_existing_cap','final_life_cap']
        columns=[f'Unnamed: {i}' for i in range(len(base))]
        headers=[None]*len(base)
        for unit in ['400kV_AC','petrol']:
            columns.extend([unit]+[f'Unnamed: {len(columns)+i}' for i in range(1,len(fields))])
            headers.extend([unit]+[None]*(len(fields)-1))
        columns.append('e_petrol');headers.append('e_petrol')
        values=[10.,1000.,20.,1.,.01,0.,50.,40.,30.,.1]
        identifiers=['HR','HR1',100.] if outside else ['HR1','HR','SI1','SI',100.]
        frame=pd.DataFrame([base+fields+fields+['cap_mw'],identifiers+values+values+[0.]],columns=columns)
        return frame,headers

    def test_incomplete_synthetic_carrier_gets_compatible_reference_fields(self):
        frame,headers=self.fixture()
        frame,notes=complete_blocks(frame,headers)
        _,units=blocks(frame)
        self.assertEqual(set(units['e_petrol']),set(units['petrol']))
        self.assertEqual(frame.iloc[1][units['e_petrol']['cap_mw']],0.)
        self.assertEqual(frame.iloc[1][units['e_petrol']['max_cap']],1000.)
        self.assertEqual(len(frame.attrs['native_header_cells']),len(frame.columns))
        self.assertTrue(notes)

    def test_external_national_capacities_are_split_once_not_duplicated(self):
        frame,headers=self.fixture(True)
        frame,_=complete_blocks(frame,headers)
        result,notes=outside_regions(frame,{('HR','a'),('HR','b')},{('HR','a'):.25,('HR','b'):.75})
        base,units=blocks(result)
        self.assertEqual(set(result.iloc[1:][base['zone']]),{'a','b'})
        for field in ['cap_mw','max_cap','max_cap_period']:
            self.assertAlmostEqual(result.iloc[1:][units['400kV_AC'][field]].astype(float).sum(),float(frame.iloc[1][units['400kV_AC'][field]]))
        self.assertEqual(len(notes),2)

    def test_internal_defaults_connect_all_regions_and_are_recorded_as_assumptions(self):
        frame,headers=self.fixture();frame,_=complete_blocks(frame,headers)
        targets={('HR','a'),('HR','b'),('HR','c')};weights={('HR','a'):.2,('HR','b'):.6,('HR','c'):.2}
        internal,notes=internal_regions(frame,targets,weights)
        external,headers=self.fixture(True);external,_=complete_blocks(external,headers)
        external,_=outside_regions(external,targets,weights)
        errors,audit=checks(internal,external,targets)
        self.assertEqual(errors,[])
        self.assertTrue(audit['national_electric_network_connected'])
        self.assertEqual(len(notes),4)
        self.assertTrue(all(not r['observed_line'] for r in notes))
        self.assertTrue(all(r['km']==0 for r in notes))
        self.assertTrue(all('b' in {r['zone'],r['zoneTo']} for r in notes))

    def test_existing_connected_regional_network_is_preserved(self):
        frame,headers=self.fixture();frame,_=complete_blocks(frame,headers)
        base,_=blocks(frame)
        frame.loc[1,base['zone']]='a';frame.loc[1,base['zoneTo']]='b';frame.loc[1,base['To']]='HR'
        result,notes=internal_regions(frame,{('HR','a'),('HR','b')},{('HR','a'):.5,('HR','b'):.5})
        self.assertEqual(notes,[])
        pd.testing.assert_frame_equal(result,frame)

    def test_writer_preserves_native_two_row_headers_and_merged_cells(self):
        frame,headers=self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'network.xlsx'
            book=Workbook();sheet=book.active;sheet.title='transmission'
            sheet.append(headers)
            for row in frame.itertuples(index=False,name=None):sheet.append(row)
            sheet.merge_cells('F1:O1');sheet.merge_cells('P1:Y1')
            book.save(path);book.close()
            frame,_=complete_blocks(frame,headers)
            result,_=internal_regions(frame,{('HR','a'),('HR','b')},{('HR','a'):.5,('HR','b'):.5})
            replace_sheets(path,{'transmission':result})
            self.assertEqual(workbook_errors(path),[])
            restored=pd.read_excel(path,'transmission')
            base,units=blocks(restored)
            self.assertEqual(set(restored.iloc[1:][base['zone']]),{'a','b'})
            self.assertIn('max_cap',units['e_petrol'])
            book=load_workbook(path)
            self.assertIsNone(book['transmission']['G1'].value)
            self.assertIn('F1:O1',{str(r) for r in book['transmission'].merged_cells.ranges})
            book.close()

    def test_checker_rejects_original_national_only_inputs_for_regional_run(self):
        internal,h=self.fixture();internal,_=complete_blocks(internal,h)
        external,h=self.fixture(True);external,_=complete_blocks(external,h)
        errors,_=checks(internal,external,{('HR','a'),('HR','b')})
        self.assertTrue(any('disconnected' in e for e in errors))
        self.assertTrue(any('lack active regions' in e for e in errors))

    def test_regular_long_tables_connect_regions_and_preserve_external_total(self):
        internal=pd.DataFrame(dict(unit_name=['400kV_AC'],System='HR',zone='HR1',To='SI',zoneTo='SI1',
                          cap_mw=10.,max_cap=1000.,max_cap_period=20.,km=100.,var_cost=1.,loss=.01,final_life_cap=.1))
        outside=internal.drop(columns=['To','zoneTo'])
        targets={('HR','a'),('HR','b')};weights={('HR','a'):.25,('HR','b'):.75}
        result,notes=internal_regions(internal,targets,weights)
        external,_=outside_regions(outside,targets,weights)
        self.assertEqual(len(notes),2)
        self.assertEqual(result.cap_mw.tolist(),[1000.,1000.])
        self.assertTrue(result.km.eq(0).all())
        self.assertTrue(result.max_cap_period.eq(0).all())
        self.assertEqual(external.cap_mw.sum(),10.)
        self.assertEqual(checks(result,external,targets)[0],[])


if __name__=='__main__':unittest.main()
