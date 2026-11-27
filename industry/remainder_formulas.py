"""Attach Excel formulas to the calculated pool, preserving numeric reader caches."""
import re
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

import pandas as pd
from openpyxl.utils import get_column_letter as letter


def link(path, profiles):
    from model_input_bundle import sheet_paths
    with pd.ExcelFile(path) as book:
        source = book.parse("Industry_data")
        pool = book.parse("simple_industry")
    if pool.empty:
        return
    annual = profiles.groupby(["System","zone"]).sum(numeric_only=True)
    def col(name):
        return letter(source.columns.get_loc(name)+1)
    end = len(source)+1
    def rng(c):
        return f"${c}$2:${c}${end}"
    def src(name):
        return "Industry_data!"+rng(col(name))
    def cell(c,i,val,formula=None):
        if formula is None and isinstance(val,str):
            return f'<c r="{c}{i}" t="inlineStr"><is><t>{escape(val)}</t></is></c>'
        f = f"<f>{escape(formula)}</f>" if formula else ""
        typ = ' t="str"' if isinstance(val,str) else ''
        return f'<c r="{c}{i}"{typ}>{f}<v>{escape(str(val))}</v></c>'
    keys=["System","zone","Industry","category"]
    source=source.copy()
    has_category="category" in source
    if not has_category:
        source["category"]="all"
    active=set(source.loc[source.include_in_the_model.astype(str).str.strip().str.upper().isin(["Y","YES","TRUE","1","1.0"]),keys].itertuples(index=False,name=None))
    weights={}
    for s,z,b,k in source[keys].drop_duplicates().itertuples(index=False,name=None):
        name=b if k=="all" else f"{b}[{k}]"
        weights[s,z,b,k]=float(annual.at[(s,z),name]) if name in annual and (s,z) in annual.index else 0.
    labels=keys+["unit_name","fuel_type","excluded","service_MWh","pool_service_MWh","baseline_MWh","maximum_MWh","fuel_MWh","CO2","eligible","weight_system","weight_zone","weight_industry","weight_category","annual_MWh"]
    rows=['<row r="1">'+''.join(cell(letter(j),1,v) for j,v in enumerate(labels,1))+'</row>']
    seen=set()
    entries=list(weights.items())
    for i,row in enumerate(source.to_dict("records"),2):
        key=tuple(row[k] for k in keys)
        valid=key not in active and not row["unit_name"].startswith("HP_industry_")
        weight=weights[key]; first=key not in seen
        seen.add(key)
        vals=[]
        for c,k in zip("ABCDEF",keys+["unit_name","fuel_type"]):
            vals.append(cell(c,i,row[k],None if k=="category" and not has_category else f"Industry_data!{col(k)}{i}"))
        crit=",".join(f'{src(k)},"="&{c}{i}' for k,c in zip(keys,"ABCD") if k!="category" or has_category)
        flag_range=src("include_in_the_model")
        counts="+".join(f'COUNTIFS({crit},{flag_range},"{f}")' for f in ("Y","YES","TRUE","1"))
        vals.append(cell("G",i,int(key not in active),f"--(({counts})=0)"))
        match=",".join(f'${a}$2:${a}${len(weights)+1},"="&{b}{i}' for a,b in zip("OPQR","ABCD"))
        vals.append(cell("H",i,weight,f"SUMIFS($S$2:$S${len(weights)+1},{match})"))
        crit=",".join(f'${c}$2:{c}{i},"="&{c}{i}' for c in "ABCD")
        vals.append(cell("I",i,weight if first and key not in active else 0,f"IF(AND(G{i}=1,COUNTIFS({crit})=1),H{i},0)"))
        vals.append(cell("N",i,int(valid),f'--AND(G{i}=1,LEFT(E{i},12)<>"HP_industry_")'))
        base=float(row["share_fuel_2020"])*weight if valid else 0.
        for c,name in [("J","share_fuel_2020"),("K","max_share_fuel")]:
            vals.append(cell(c,i,float(row[name])*weight if valid else 0,f"N{i}*H{i}*Industry_data!{col(name)}{i}"))
        fuel=base/float(row["efficiency"]) if base else 0.
        vals.append(cell("L",i,fuel,f"IF(J{i}=0,0,J{i}/Industry_data!{col('efficiency')}{i})"))
        vals.append(cell("M",i,fuel*float(row["CO2Intensity"]),f"L{i}*Industry_data!{col('CO2Intensity')}{i}"))
        if i-2<len(entries):
            identity,value=entries[i-2]
            vals.extend(cell(c,i,v) for c,v in zip("OPQRS",[*identity,value]))
        vals.sort(key=lambda x: re.match(r'<c r="([A-Z]+)',x)[1])
        rows.append(f'<row r="{i}">'+''.join(vals)+'</row>')
    helper=('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+''.join(rows)+'</sheetData></worksheet>').encode()
    prefix="'_remainder_calc'!"
    formulas={}
    for i,row in enumerate(pool.to_dict("records"),2):
        def addr(k):
            return f"${letter(pool.columns.get_loc(k)+1)}{i}"
        criteria=",".join(f"{prefix}{rng(c)},{addr(k)}" for c,k in zip("ABEF",["System","zone","unit_name","fuel_type"]))
        zone_criteria=",".join(criteria.split(",")[:4])
        def add(c):
            return f"SUMIFS({prefix}{rng(c)},{criteria})"
        den=f"SUMIFS({prefix}{rng('I')},{zone_criteria})"
        expr={"share_fuel_2020":f"IFERROR({add('J')}/{den},0)",
              "max_share_fuel":f"IFERROR(MAX({add('J')},{add('K')})/{den},0)",
              "efficiency":f"IFERROR({add('J')}/{add('L')},{float(row['efficiency'])})",
              "CO2Intensity":f"IFERROR({add('M')}/{add('L')},{float(row['CO2Intensity'])})"}
        for k in pool:
            if k in source and (k in ("cap_mw","max_cap","CC_cap","Reboiler_cap","Tank_stor_cap") or re.fullmatch(r"(?:CC_|Reboiler_|Tank_stor_)?max_inv_period(?:_\d{4})?",str(k))):
                expr[k]=f"SUMIFS({src(k)},{criteria},{prefix}{rng('N')},1)"
        for k,f in expr.items():
            if k in pool and pd.notna(row[k]):
                formulas[addr(k).replace("$","").encode()]=escape(f).encode()
    with ZipFile(path) as old:
        paths=sheet_paths(old)
        def attach(m):
            f=formulas.pop(m[2],None)
            return m[1]+(b"<f>"+f+b"</f>" if f else b"")+m[3]
        simple=re.sub(rb'(<c r="([A-Z]+[0-9]+)"[^>]*>)(<v>[^<]+</v></c>)',attach,old.read(paths["simple_industry"]))
        if formulas:
            raise ValueError(f"Missing cached simple_industry cells in {path}: {list(formulas)[:3]}")
        tmp=Path(path).with_suffix(".formula.tmp.xlsx")
        changes={paths["simple_industry"]:simple,paths["_remainder_calc"]:helper}
        with ZipFile(tmp,"w",ZIP_DEFLATED) as out:
            for info in old.infolist():
                out.writestr(info,changes[info.filename] if info.filename in changes else old.read(info))
    tmp.replace(path)
