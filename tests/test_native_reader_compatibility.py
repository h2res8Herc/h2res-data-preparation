import unittest

from run_model_scenario import prepare_reader_source


class NativeReaderCompatibilityTests(unittest.TestCase):
    def test_remainder_is_combined_after_every_region_is_read(self):
        source='''
Industry_demand_long_df={'a':2.,'b':3.,'c':5.}
excluded_sector_map={'a':['raw'],'b':['raw'],'c':['raw']}
remainder_rows=[]
for zone,excluded_sectors in excluded_sector_map.items():
    if zone in Industry_demand_long_df:
        remainder_rows.append((zone,Industry_demand_long_df[zone]))
    if remainder_rows:
        Industry_demand_long_df={'remainder_'+z:v for z,v in remainder_rows}
'''
        broken={};exec(source,broken)
        self.assertEqual(sum(broken['Industry_demand_long_df'].values()),2.)
        fixed,repairs=prepare_reader_source(source)
        namespace={};exec(compile(fixed,'native_reader','exec'),namespace)
        self.assertEqual(repairs,1)
        self.assertEqual(namespace['Industry_demand_long_df'],{'remainder_a':2.,'remainder_b':3.,'remainder_c':5.})
        self.assertEqual(sum(namespace['Industry_demand_long_df'].values()),10.)

    def test_already_corrected_reader_is_unchanged(self):
        source='''
excluded_sector_cat_map={'a':['raw'],'b':['raw']}
remainder_rows=[]
for zone,sectors in excluded_sector_cat_map.items():
    remainder_rows.append(zone)
if remainder_rows:
    Industry_demand_long_df=list(remainder_rows)
'''
        fixed,repairs=prepare_reader_source(source)
        namespace={};exec(compile(fixed,'native_reader','exec'),namespace)
        self.assertEqual(repairs,0)
        self.assertEqual(namespace['Industry_demand_long_df'],['a','b'])

    def test_concat_nested_in_nonempty_region_guard_also_moves_after_loop(self):
        source='''
excluded_sector_cat_map={'a':2.,'b':3.}
Industry_demand_long_df=dict(excluded_sector_cat_map)
remainder_rows=[]
for zone,amount in excluded_sector_cat_map.items():
    if zone in Industry_demand_long_df:
        remainder_rows.append((zone,amount))
        if remainder_rows:
            Industry_demand_long_df={'remainder_'+z:v for z,v in remainder_rows}
'''
        fixed,repairs=prepare_reader_source(source)
        namespace={};exec(compile(fixed,'native_reader','exec'),namespace)
        self.assertEqual(repairs,1)
        self.assertEqual(sum(namespace['Industry_demand_long_df'].values()),5.)


if __name__=='__main__':unittest.main()
