# Custom zones: format, examples and current limits

These examples use the package's **NUTS 2021** boundary IDs. They are editable input definitions, not generated country datasets. Open them in a text editor or import them into Excel as comma-separated UTF-8 data; save as CSV, not XLSX or a semicolon-separated file.

## What works in the current generator

| Configuration | Current status |
|---|---|
| Several countries in one run, with different numbers of zones per country | Supported mapping format; every selected country must be fully covered |
| Croatia grouped into three land zones, Slovenia grouped into one | Supported; source regions are aggregated rather than equally divided |
| Only northern Italy, with the rest of Italy omitted | Not supported yet by the complete sector pipeline |
| An offshore zone with no NUTS3 membership and zero demand | Not supported yet by the custom-map format |
| Splitting one NUTS3 region across several zones | Not supported by this one-to-one membership map |

The geographic configuration proposed here is reasonable for an H2RES study. The current generator needs additional handling for partial national coverage and independent offshore investment zones before it can generate that complete configuration. The examples below distinguish a map accepted by the current pipeline from the requested future layout. No new multi-country source download or model optimization was performed for these examples.

## CSV format

Each row maps **one source NUTS3 region** to **one target model zone**:

```csv
country,nuts3,zone
HR,HR050,HR_ZAGREB
HR,HR065,HR_ZAGREB
HR,HR021,HR_CONTINENTAL
HR,HR036,HR_COASTAL
SI,SI031,SI_ALL
IT,ITC11,IT_NORTH
```

This short extract illustrates the syntax; it is not a complete input file. Use the linked complete CSV for a run.

| Field | Meaning |
|---|---|
| `country` | Source country code, such as HR, SI or IT. Keep these countries as separate model systems in this example. |
| `nuts3` | Exact source-region ID from the chosen boundary vintage. Every selected country currently needs every NUTS3 region listed once. |
| `zone` | Your target-zone ID. Repeat it to combine source regions. Use unique names across countries; letters, digits and underscores are convenient. |

Do not put NUTS2 codes, country names, `ALL`, invented offshore IDs or blank values in `nuts3`. Expand a NUTS2 selection into its NUTS3 members. Do not repeat the same source region under two different target zones. An optional `system_new` field exists for advanced system remapping; it is not needed here and does not provide regional exclusion or offshore-zone support.

## Complete example that can be selected now

Use **[HR_SI_IT_complete.csv](custom_zones/HR_SI_IT_complete.csv)**. It contains 140 source-region rows: 21 for Croatia, 12 for Slovenia and 107 for Italy. It defines six modeled land zones:

| Model system | Target zone | Membership |
|---|---|---|
| HR | HR_ZAGREB | HR050, City of Zagreb, plus HR065, Zagreb County |
| HR | HR_COASTAL | HR031–HR037, all seven Adriatic NUTS3 counties |
| HR | HR_CONTINENTAL | The remaining twelve Croatian NUTS3 counties |
| SI | SI_ALL | All twelve Slovenian NUTS3 regions |
| IT | IT_NORTH | The 47 NUTS3 regions under ITC1, ITC2, ITC3, ITC4, ITH1, ITH2, ITH3, ITH4 and ITH5 |
| IT | IT_REST | The remaining sixty Italian NUTS3 regions |

The nine northern Italian NUTS2 groups used in this example are Piemonte, Valle d'Aosta, Liguria, Lombardia, Bolzano, Trento, Veneto, Friuli-Venezia Giulia and Emilia-Romagna. This is an explicit example selection; edit it if the study uses another definition of northern Italy.

**Zagreb includes both the city and surrounding county in this example.** To use the city alone, change the HR065 row to HR_CONTINENTAL. Coastal means the complete Adriatic NUTS2 area, including the whole Lika-Senj county, rather than a coastline-only polygon.

**IT_REST is modeled. It is not an exclusion flag or an outside-system label.** Do not use this complete example if the study must exclude central/southern Italy.

In the GUI, choose `custom`, select this CSV in **Custom zone map CSV**, and set Countries to `HR,SI,IT` or leave Countries blank to infer them from the map. The existing user-guide button opens a guide linking to this page and the examples. A CLI equivalent, using the preparation environment, is:

```powershell
python generate_all_sector_inputs.py --countries HR,SI,IT --spatial-level custom --zone-map docs/custom_zones/HR_SI_IT_complete.csv --sectors power,industry,transport,heating --out-root outputs_HR_SI_IT_custom --data-root cache_HR_SI_IT_custom
```

The normal source credentials, source coverage requirements and model-export settings still apply. This map groups existing NUTS3 observations; it does not allocate each country's data equally across its target zones.

## Requested northern-Italy-only layout

**[HR_SI_north_IT_PARTIAL_NOT_SUPPORTED.csv](custom_zones/HR_SI_north_IT_PARTIAL_NOT_SUPPORTED.csv)** contains exactly the requested terrestrial coverage: 21 Croatian regions in three land zones, all twelve Slovenian regions in SI_ALL, and only the 47 northern Italian regions in IT_NORTH. It has 80 mapping rows and five terrestrial zones.

**This is a design/example file, not a runnable complete-sector input in the current version.** The preflight now reports the sixty omitted Italian NUTS3 regions before starting sector downloads. Previously the sector paths handled omissions inconsistently: industry, transport and electricity rejected unmapped regions, while heating retained them and the single-zone power fallback could absorb them. Omitting a row was therefore not a reliable way to exclude a region.

Partial-country support must filter the same source territory in every sector, preserve the included regions' absolute quantities, and retain their original national allocation shares. For example, a selection containing 70% of national electricity weight should receive 70% of the national hourly load, not a renormalized 100%. Complex-industry calibration and policy defaults also need to distinguish an included fraction from a whole country. Shares must not be normalized to the full national industry total after the omitted regions have been removed.

## Croatia's fourth, offshore zone

HR_OFFSHORE should be a **separate synthetic network/investment zone**, not a NUTS3 aggregation. Do not map Istria or any other real county to it: that would transfer the county's population, industry, heating and transport demand offshore. A blank `nuts3` row is rejected; it does not create a zero-demand zone.

**[HR_offshore_DESIGN_ONLY.csv](custom_zones/HR_offshore_DESIGN_ONLY.csv)** illustrates a proposed separate zone-definition record:

```csv
country,zone,zone_type,connected_land_zone,existing_capacity_MW,electricity_demand_MWh,heating_demand_MWh,industry_demand_MWh,transport_activity,wind_technology,latitude,longitude,max_capacity_MW
HR,HR_OFFSHORE,offshore,HR_COASTAL,0,0,0,0,0,WTOF,,,
```

**The generator does not yet read this proposed schema.** Latitude, longitude and maximum capacity are intentionally blank: no offshore site, developable potential or investment allowance has been supplied. They must not be invented from a county's population or land demand.

A functioning offshore extension needs zero sector-demand series on the full model calendar, an offshore-wind candidate with zero initial stock, a valid wind availability profile for the chosen marine location/area, future build and capacity limits, matching cost/investment identifiers, and an electrical connection to the selected coastal zone. Zero demand must be allowed without requiring phantom industry or transport equipment. National demand allocation and default-stock allocation must assign the offshore zone no demand or inherited land assets. Existing sourced offshore assets, if included in a different study, need explicit treatment rather than an unconditional zero-stock assumption.

With that extension and partial-country support, the requested configuration would have **six zones**: HR_CONTINENTAL, HR_ZAGREB, HR_COASTAL, HR_OFFSHORE, SI_ALL and IT_NORTH. The two files above describe the intended land coverage and separate offshore role; they do not enable those unsupported features by themselves.

## Boundary reference

The examples are generated from the packaged `power/data/NUTS_RG_20M_2021_4326_LEVL_3.geojson`, distributed by [Eurostat GISCO](https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/NUTS_RG_20M_2021_4326_LEVL_3.geojson). Use the same vintage for mapping IDs and source-to-model conversion. Changing the CSV does not change the source boundary geometry or create a custom offshore polygon.
