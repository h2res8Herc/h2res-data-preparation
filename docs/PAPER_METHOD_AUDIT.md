# Spatial allocation and automatic source downloads

This audit follows the supplied paper `SEE.SDEWES2026.0044.docx`, read on 3 November 2026. It distinguishes the paper's method, implementation choices where the paper gives no numerical rule, and unavailable observations replaced by explicit assumptions. It does not certify the feasibility of an H2RES optimization scenario.

## What changed

The previous regional outputs were insufficient to reproduce the paper. Industry had no usable installation evidence, heating did not pass the CHP source into the calculator and used representative centroids, and transport could silently continue after failing to find the external `osmium` executable. Those results must be regenerated. The updated generators download missing public sources, use the spatial calculations below and bind successful calculations to their source files with SHA-256 hashes. Exporting old outputs does not reconstruct missing spatial evidence.

## Industry

Paper paragraphs 86–132 distribute national JRC-IDEES sector/fuel/temperature totals according to sector-filtered industrial installations, activity and capacity evidence from ETS, IEP/E-PRTR/IED and EIGL. The updated pipeline joins the public EUTL installation, location, compliance and NACE tables, selects positive verified emissions in the chosen national energy year, and spatially intersects installation coordinates with the requested GISCO regions. Operator headquarters are not geocoded as factory sites.

The paper does not supply an exact numerical blend across overlapping inventories. This implementation therefore uses a recorded source priority within each industrial branch:

1. Selected-year ETS verified emissions as an activity proxy.
2. Otherwise sector-specific EEA IED facility counts.
3. Otherwise sector-specific JRC EIGL installation counts.
4. If no branch-specific records exist, all-industrial-site density, explicitly marked as an assumption.

Emissions are not a measurement of fuel demand or installed thermal capacity. Using the same within-branch activity shares for each national category/fuel total is a proportional disaggregation assumption. Inventories are alternatives; their overlapping records and unlike units are not added together. No population prior or industrial fuel-raster margin determines the default industry geography. Genuine zero allocations are retained rather than replaced with invented factories.

The mapping follows Eurostat industrial final-consumption definitions. Chemical/petrochemical demand uses NACE 20/21. Refineries (19), electricity generation/transformation (35) and energy-fuel extraction are excluded. Rubber/plastics (22) belongs to other industry. Non-ferrous casting is distinguished from iron/steel casting. See the official [coal](https://ec.europa.eu/eurostat/documents/38154/16135593/Coal_Questionnaire_Instructions.pdf) and [oil questionnaire instructions](https://ec.europa.eu/eurostat/documents/38154/16135593/Oil_Questionnaire_Instructions.pdf).

The allocation conserves every national sector × temperature category × fuel energy margin. The feedstock treatment in paper paragraphs 156–171 moves the appropriate chemical gas/oil demand between heat and NON_HEAT categories and corrects their hourly curves. The existing capacity formula in paragraphs 145–150 is retained: `capacity_MW = annual_energy_MWh / (efficiency * capacity_factor * 8760)`. Those capacities are estimates, not plant nameplates.

Regular, category and automatically generated complex representations use the same recorded branch weights. The complex process compiler uses its separate JRC-IDEES-2023 observations at the selected calibration year; it does not reinterpret the legacy national tables as process observations. User-supplied complex weights remain an explicit override. The automatic HR/2020 source records include Petrokemija installation `HR_204107`, NACE 20.15, Kutina, with 1,264,009 t verified emissions. Its installation coordinate (16.798853 E, 45.466088 N) intersects **HR028**, rather than Zagreb city HR050. The generated `non_energy_gas` estimate is about **623.27 MW**, entirely in HR028 for this activity proxy. This is a calibration result for this source year, not a claim that every Croatian chemical activity is observed by ETS.

The automatic HR/2020 source selection lacks branch-specific coverage for transport equipment, machinery, wood products, construction and textiles/leather; those branches are marked with the industrial-site-density assumption. They represent about **11.37%** of the legacy selected-year national industrial input-energy margins in this run. Registry reporting thresholds and generic site classifications prevent treating the inventory as a complete industrial census.

Sources download into `<data-root>/industry/facility_sources/`:

| Source | Automatic access | Use and cache |
|---|---|---|
| [Public EUTL compilation, pinned v2](https://zenodo.org/records/21414185) | [499 MB archive](https://zenodo.org/api/records/21414185/files/eutl_data_package_2026-07-21.zip/content) | Download once, verify published MD5 `629595320851d20bd1b610878a2ecd1e`, extract only the required installation/location/NACE/compliance/link tables. The original archive covers multiple countries; calculations filter the selected country/year. |
| [EEA Industrial Emissions Portal](https://industry.eea.europa.eu/industrial-emissions/dataset) | [EEA public site layer](https://air.discomap.eea.europa.eu/arcgis/rest/services/Air/IED_SiteMap/MapServer/0) | Paginated queries restricted to selected country and reporting year; site activity labels and facility counts. Site records do not provide a complete facility-level NACE census. |
| [JRC EIGL industrial infrastructure](https://arcgis.jrc.ec.europa.eu/server/rest/services/eigl/EIGL_SERVICES_Industrial_infrastructure_PUB/MapServer) | Public paginated ArcGIS query | Query the country's bounding box, then spatially filter actual NUTS polygons. This inventory is supplemental and its vintage is not represented as the selected-year observation. |
| [JRC-IDEES-2021](https://zenodo.org/records/15895830) | Existing country/archive downloader | National sector/category/fuel totals for the selected base year. Shared archives can contain unselected countries. |

`industry/<country>/01_allocated/regional_allocation.json` records the source priority, coverage, year, hashes and energy conservation. `facility_observations.csv` lists the supporting installations. `industry/combined/regional_generation.json` binds these records to prepared CSV files; `regional_branch_weights.csv` feeds the complex compiler.

## Heating

Paper paragraphs 27–31 and 61–65 use regional population, multiple weather samples, heat density, fuel prevalence and CHP locations. The implementation now:

1. Selects eight random inhabited Eurostat population-grid cells per NUTS3 region. A fixed seed of zero combined with the region ID makes the points reproducible. The paper does not prescribe this seed or precise sampling algorithm.
2. Requests hourly temperatures for each point from Open-Meteo's historical-weather service (or reads an explicitly supplied weather NetCDF), combines temperatures with the sampled cells' population weights, and calculates heating degree hours.
3. Combines the population/degree-hour distribution with Hotmaps heat-density information and JRC residential/tertiary national energy and fuel shares.
4. Supplies actual PowerPlantMatching CHP locations and capacities to district-heating allocation. The inherited CHP blend coefficient is `dh_chp_lambda=0.9`, configurable through the heating CLI. The paper gives no numerical coefficient for this blend.
5. Uses five EIGL residential/tertiary fuel-prevalence maps: gas, oil, solid fuel, renewables/biomass and electricity. Electric heating and heat pumps use the electricity map.
6. Reconciles hourly heat demand against the annual regional fuel totals and checks the resulting 8,760-period H2RES tables.

The rebuilt HR example has **168 weather samples: eight in each of 21 counties**. Temperature point caches and source rasters are reused. A provider error stops calculation rather than silently switching to a centroid. Missing inhabited grid cells require an explicit assumption. The loader's existing non-leap 8,760-hour calendar convention is retained.

| Source | Reference |
|---|---|
| GISCO NUTS polygons | [Official distribution](https://gisco-services.ec.europa.eu/distribution/v2/nuts/) |
| Eurostat population grid | [Official population grids](https://ec.europa.eu/eurostat/web/gisco/geodata/population-distribution/population-grids), [versioned raster mirror used by the loader](https://zenodo.org/records/17913230) |
| Hotmaps heat-density raster | [Primary data repository](https://gitlab.com/hotmaps/buildings/heat/heat_tot_curr_density) |
| JRC fuel-prevalence rasters | [EIGL raster distribution](https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/EIGL-Data/RASTER/) |
| CHP records | [PowerPlantMatching primary repository](https://github.com/PyPSA/powerplantmatching), [downloaded CSV](https://raw.githubusercontent.com/PyPSA/powerplantmatching/master/powerplants.csv) |
| Weather | [Open-Meteo historical weather documentation](https://open-meteo.com/en/docs/historical-weather-api) |

`<data-root>/heating_raw/<country>_<year>_.../paper_weather_samples.csv` lists coordinates, populations and weights. The adjacent `paper_method_details.json` records whether CHP and all five maps were used. The raw `paper_generation.json` fingerprints sources, sampling configuration and outputs. The prepared heating folder has a second `paper_generation.json` binding that calculation to its model tables. Changing a required source or sampling parameter invalidates the raw cache.

## Transport

Paper paragraphs 200–245 keep passenger and freight allocation separate and use EIGL road-energy maps alongside rail, port and airport infrastructure. The loader now reads the actual country PBF through the Python [PyOsmium bindings](https://docs.osmcode.org/pyosmium/latest/), rather than depending on an external command-line executable. Read or parser errors propagate; they cannot be interpreted as zero infrastructure.

Rail indicators distinguish mainline/urban lines and electrification and include railway stations. Shipping indicators include port points/polygons, cargo indicators and quays. Aviation indicators include runways and aerodromes. Lines and polygons are clipped to each county before length/area calculations; boundary points are counted once. Airports can serve inland counties, while **maritime weights are zero for GISCO inland regions**. GISCO coastal types 1/2 are allowed; type 3 is inland. Aviation is excluded from freight allocation.

The 5 November 2026 navigation correction distinguishes **sea shipping from inland navigation in landlocked countries**. JRC domestic navigation includes coastal shipping and inland waterways; see the [JRC transport structure](https://publications.jrc.ec.europa.eu/repository/bitstream/JRC144707/JRC144707_01.pdf). Hungary's bundled domestic-navigation activity, 1,998 million tonne-km, matches the 2020 inland-waterways value in `JRC-IDEES-2021_Transport_HU.xlsx`, `TrNavi_act!V5`; coastal shipping in `V4` and international maritime activity are zero. This inland activity must be retained. In a country with no coastal NUTS3 regions, domestic navigation uses the unmasked OSM port/quay indicators, with zero allocation to regions without those indicators. This is an infrastructure proxy, not observed regional waterway traffic. Native H2RES domestic-shipping sector and unit names remain unchanged.

Sea shipping retains the coastal restriction. If a coastal country has positive sea activity but no OSM coastal port proxy, the explicitly recorded default distributes it only across coastal regions. Positive inland activity with no port/quay evidence fails with a specific source error; it never falls back to every county. Positive international sea activity in a landlocked country is also rejected. Source totals are conserved for activity, fleet and energy. Navigation kind, eligible regions and the proxy/default used are recorded in `paper_spatial_calculation.json`; `debug_weights_NUTS3.csv` includes separate `ship_inland_freight` and `ship_inland_passenger` columns. Spatial checks run before the model workbooks and hourly profiles are created.

The inherited indicator coefficients are implementation assumptions: electric passenger rail uses mainline length + 8 × urban length; non-electric passenger rail uses 5 × mainline + 2 × urban + 0.2 × stations; freight rail uses 2 × mainline + 0.5 × urban. Freight shipping uses 20 × quay km + 50 × cargo points + 50 × port km² + 0.5 × port points; passenger shipping uses 30 × quay km + 2 × port points + 5 × port km². Aviation uses 100 × runway km + 50 × aerodromes. The paper describes these feature families but does not publish these coefficients. Parallel tracks, incomplete electrification tags and airport point/area representations can affect the proxy.

The HR extraction used 6,409 rail lines, 1,339 station features, 193 port polygons, 467 port points, 48 quays, 70 runways and 49 aerodrome features. Features outside the actual country polygons are excluded in regional measurement. National activity, vehicle and energy totals are distributed with normalized mode-specific shares and checked separately for each mode/technology, excluding freight aviation. The bundled activity tables are in **millions of passenger-km or tonne-km**. Native H2RES `total_load` retains that convention; the raw diagnostic `energy_MWh` correctly converts it as `total_load * 1000 / efficiency_primary`, where efficiency is activity per kWh. This also corrects a legacy diagnostic column that had omitted the million-activity scaling. Normalized hourly transport curves can be shared between counties; absolute fleets and activity carry their regional scale.

Sources: [Geofabrik country extracts](https://download.geofabrik.de/europe.html), [OpenStreetMap attribution and licence](https://www.openstreetmap.org/copyright), [JRC EIGL rasters](https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/EIGL-Data/RASTER/), [Eurostat coastal typology](https://ec.europa.eu/eurostat/en/web/coastal-island-outermost-regions/methodology). PBFs and extracted GeoJSON layers are cached under `<data-root>/transport/osm/`. `paper_spatial_calculation.json` records source/output hashes and parser counts; `transport/combined/paper_generation.json` binds that calculation to canonical model tables.

## Running and checking

Start `START_DATA_PREPARATION.bat`, select the country and spatial detail, enable Industry, Heating and Transport, and set **Data task** to **generate**. Leave **Refresh downloaded source data** off to reuse the downloaded files. Keep missing-source downloads enabled and leave **Reuse existing raw heating files** off for the first corrected calculation; the generator independently reuses a verified matching raw cache. The required extra transport package is listed in `requirements.txt` and checked before preparation. On first use, source downloads and weather requests can take time. Country selection restricts the generated outputs; shared European archives and rasters can still be downloaded in full.

For the saved HR NUTS3 configuration, historical inputs use industry 2020, heating 2021 and bundled JRC-derived transport national tables, with EIGL prevalence rasters for 2019 and GISCO NUTS 2021 boundaries. The legacy national transport CSVs do not declare a selectable source year; they must not all be labelled 2019. The Hungary navigation observation checked above matches 2020. These sources are not observations of one common year. Refreshing spatial sources does not recalculate the bundled national transport snapshot; refreshing OSM/CHP inventories can change those inventories' vintages. Provenance records show the actual files and hashes used.

After successful generation, use `<output-root>/data` as the native H2RES data directory. It retains the model reference's 43 filenames and directory layout, including all seven technology workbook paths and four complex-industry companions. Reports remain outside `data`. The export checks file coverage, model keys, calendar coverage, workbook integrity, regional methods and national conservation. It does not run the optimization or prove scenario feasibility. Technology costs, efficiencies, lifetimes, scenario investment limits and unsourced default national stocks remain documented assumptions; default national stock quantities are distributed across regions without multiplying their national total.

`regional_input_quality.json`, `validation.json`, `H2RES_DATA_manifest.json` and the sector method records provide the audit trail. A failed rebuild retains the previously published native folder; a fully validated build that cannot be published is preserved for retry. For the checked HR example, `validation/HR_NUTS3_regional_delivery_verification.json` records the final native-file and archive checks once publication has succeeded.

The 5 November native-contract update reconciles `simple_industry` with the same variant's detailed source table and annual demand, preserving baseline capacity, useful service, fuel input and combustion emissions. A fully detailed representation needs no pooled remainder. Generated plant names are linked exactly to yearly costs, home-zone investment budgets and maintenance values; national build budgets are divided over matching plants by existing capacity. The financial donor/proxy assumptions appear in `generator_input_links.json`.

The paper's spatial allocation methods do not provide a physical NUTS3 transmission network. Where no connected active regional network was supplied, this exporter adds explicitly assumed virtual exchange connections with zero distance/loss and reference carrier capacity ceilings. Existing active connections are retained. External national transfer envelopes are distributed once with regional electricity demand shares. `network_input_assumptions.json` identifies these defaults. They enable regional input connectivity but must be replaced for a study of actual grid bottlenecks. See [native input assumptions and launcher](MODEL_DATA_2_11_2026.html).

Regional reader validation also checks the loaded regular/category industry demand against the prepared profiles for every region. The generated launcher corrects a premature remainder-concatenation loop in the supplied H2RES reader in memory; otherwise it can discard earlier regions' demand. This compatibility correction changes neither the prepared source profiles nor the model installation. Regional runs using that reader must use the supplied launcher or an equivalently corrected model reader. Complex companions also zero indexed activity where their explicit facility-allocation weight is zero, avoiding spurious activity in a region with no allocated service. National indices remain unchanged in positive-share regions and physical tonnes retain their allocation shares.

If Windows locks the original staging folder, the exporter automatically retries from a checksum-verified preserved copy. If that retry also fails, `model_export_failure.json` identifies the preserved `_unpublished_model_inputs_...` folder. After the exporting process has exited, retry its publication without regenerating data:

```powershell
python native_data_delivery.py --out-root "sve_za_HR_NUTS3" --recovery-bundle "sve_za_HR_NUTS3\_unpublished_model_inputs_<identifier>"
```

Use the actual recovery path from the failure record. The retry requires a passed coverage report, the exact native file layout and matching native/package SHA-256 checksums. It preserves both the old published folder and the completed recovery bundle if publication still fails.
