"""Indexed national activity must not remain active in zero-allocation regions."""
import pandas as pd


def zero_weight_activity(frame, sheet):
    if 'allocation_weight' not in frame:
        return frame,0
    zero=pd.to_numeric(frame.allocation_weight,errors='raise').eq(0)
    columns=[]
    if sheet=='Product_demand':
        zero &= frame.product_unit.ne('t_product')
        columns=[col for col in frame if str(col).isdigit()]
    elif sheet=='Process_data':
        zero &= frame.activity_unit.ne('t_product')
        columns=['reference_activity']
    if not columns or not zero.any():return frame,0
    changed=frame.loc[zero,columns].apply(pd.to_numeric,errors='raise').ne(0).any(axis=1)
    if not changed.any():return frame,0
    result=frame.copy()
    result.loc[zero,columns]=0.
    return result,int(changed.sum())


def synchronize(path):
    from model_input_bundle import replace_sheets
    patches={};notes=[]
    with pd.ExcelFile(path) as book:
        for sheet in ('Product_demand','Process_data'):
            frame=book.parse(sheet)
            updated,count=zero_weight_activity(frame,sheet)
            if count:
                patches[sheet]=updated
                notes.append(dict(sheet=sheet,rows=count,basis='zero industrial allocation implies no local indexed activity; national indices in positive-share regions are unchanged'))
    if patches:replace_sheets(path,patches)
    return notes
