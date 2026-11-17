# Regional electricity demand: fixed shares and sector-weighted shapes

Implemented 16 November 2026. This option belongs to the data-preparation application; it does not change the optimization equations in H2RES.

## Selecting the method

Start `START_DATA_PREPARATION.bat`. In **Power & profiles**, set **Regional electricity profiles** to:

| Value | Calculation |
|---|---|
| `national-scaled` | Existing method and default: the same national normalized curve in every NUTS3 region, scaled by its JRC annual share. |
| `sector-weighted` | Different regional shapes based on economic composition and published representative sector profiles; national hourly demand and JRC annual regional shares remain hard constraints. |

Keep **Skip electricity-demand profiles** unchecked. On **Output format**, use **Data task: generate**, rather than **export existing outputs**, when changing the profile method. Keep the same download/cache directory and leave **Refresh downloaded source data** unchecked to reuse observations. ENTSO-E still requires its normal token. Eurostat and the public holiday source require no token. The additional method does not request Open-Meteo data or require a neural-network package.

The optional **Tourism share of service electricity** is the assumed national fraction of commercial/public-service electricity assigned to visitor accommodation. The default is **0.1**, meaning 10% of the service electricity budget, not 10% of total electricity. This is an editable modeling assumption, **not a measured Eurostat electricity statistic**. Set it to zero to disable the separate tourism component. Values must satisfy `0 <= share < 1`. Test its sensitivity when tourism affects the scenario.

The same generated gross regional curves feed native H2RES and the optional refactored export. Enabling both formats does not calculate a second regional distribution. The refactored case includes the selected preparation sectors with electricity as its core. It applies national annual residual-electricity adjustment only for industry, heating or mobility represented explicitly. Its residual/basic demand is therefore smaller when those components are included; a power-only case retains gross demand. The regional shapes are preserved, but adding explicit services is not claimed to reconstruct historical gross hourly demand exactly.

## Annual targets and the national boundary

Let `A_r` be the packaged JRC EIGL electricity total for region `r`, derived from the 2019 electricity-demand atlas, and `N_t` the selected ENTSO-E national hourly MW:

```text
w_r = A_r / sum_r A_r
E_r = w_r * sum_t N_t * 1 hour
sum_r D_tr = N_t                  for every hour
sum_t D_tr * 1 hour = E_r         for every NUTS3 region
D_tr >= 0
```

The method preserves the **JRC annual regional ratios**, exactly as the existing preparer does. A different national total or observation year requires a common national scaling factor. It cannot simultaneously impose unscaled 2019 JRC GWh and a different selected ENTSO-E national annual total. The method report states the original atlas total, selected-year totals, scale factor and each regional target/result explicitly.

The source-year files retain all hours, including February 29. H2RES inputs use 8,760 hours and exclude February 29. The algorithm balances the model hours and February 29 separately with the same annual regional/sector proportions. Therefore **both calendars preserve the JRC regional ratios**, while each retained hour still sums to the corresponding observed national value. It does not discard the last 24 hours of a leap year.

## Inputs and the sector mix

The application bundles compact, attributed representative profiles. Additional composition observations are downloaded and cached under `<Download/cache directory>/entsoe_load/electricity_composition`.

| Input | Source and role |
|---|---|
| Regional annual electricity | Existing packaged `power/demand/eigl_nuts3_2019_correct/*_NUTS3_2019_tot.csv`; fixes regional annual shares. |
| National hourly load | Existing monthly ENTSO-E A65/A16 actual-total-load downloads/cache. |
| Regional employment | Eurostat `nama_10r_3empers`, persons employed, `unit=THS`, `wstatus=EMP`; economic activity proxy. |
| Regional GVA | Eurostat `nama_10r_3gva`, `unit=CP_MEUR`; complementary economic activity proxy. |
| Population | Eurostat `demo_r_pjanaggr3`, total population, sex/age total, persons; household allocation proxy. |
| National electricity by sector | Eurostat `nrg_bal_c`, electricity `E7000`, `GWH`; scales economic proxies to sector electricity budgets. |
| Visitor nights | Eurostat `tour_occ_nin3`, all residence countries, accommodation `I551-I553`; spatial tourism proxy. |
| Monthly visitor nights | Eurostat `tour_occ_nin2m`; complete local NUTS3 series where available, otherwise NUTS2, then national. |
| Public holidays | Nager.Date country/year national public holidays; local clock calendar. |

The requested electricity year is also the composition observation year. The application does not silently substitute a different economic year. Missing regional observations can use the same-year parent NUTS2, NUTS1 or country observation, apportioned using JRC shares and recorded as a fallback. If only employment or GVA is usable, the available proxy is used. Remaining missing regional features use an explicitly recorded average-intensity/JRC-share proxy. If both economic sources are entirely unavailable, or required national sector electricity is unavailable, the method stops with an explanation; it does not silently switch the selected method. Select another supported year or `national-scaled` in that situation.

Employment and GVA are normalized separately and blended equally where both are available. Their percentages are **not directly interpreted as electricity percentages**. National electricity consumption supplies the sector proportions:

- Households: `FC_OTH_HH_E`, distributed using population.
- Industry: `FC_IND_E`, spatial proxy from NACE `B-E` plus construction `F`.
- Commercial/public services: `FC_OTH_CP_E`, distributed using the disjoint A10 service groups.
- Agriculture/forestry and fishing: `FC_OTH_AF_E` plus `FC_OTH_FISH_E`, proxy from NACE `A`.
- Tourism: the selected fraction of `FC_OTH_CP_E`, **subtracted from the remaining service budget**, distributed using visitor nights.
- Other final electricity: `FC_E` less those observed main-sector totals; uses the national load shape and JRC spatial prior.

Within services, the separate groups are `G-I`, `J`, `K`, `L`, `M_N`, `O-Q` and `R-U`. The parent groups `G-J`, `K-N` and `O-U` are not added again. Manufacturing `C` is not added on top of `B-E`. A region remains a mixture; it is not assigned a single industrial, residential or tourist label.

The national final-sector proportions are rescaled to the national ENTSO-E grid-load budget. These observations can have different coverage of losses, own use and autoproduction. They serve as composition priors, not additional grid demand or proof of identical statistical boundaries. A first matrix-balancing step makes regional sector budgets satisfy both the fixed JRC regional shares and national sector fractions. A `1e-6` positive JRC-weighted regularization of the spatial prior supports compatible margins despite sparse or rounded economic observations; it adds no final energy.

## Representative curves and calendars

**Households and agriculture:** BDEW H25 and L25 from the 2025 official workbook. Four quarter-hour energy values are summed into each hourly template. The monthly weekday/Saturday/Sunday tables are applied to the local country clock, including daylight-saving conversion from the UTC observation index. National public holidays use Sunday profiles; the BDEW December 24/31 Saturday convention is retained unless Sunday/holiday. Regional holidays are not modeled. The household profile uses the published dynamization factor, where `d` is the local day of year:

```text
f(d) = -3.92e-10*d^4 + 3.20e-7*d^3 - 7.02e-5*d^2 + 2.10e-3*d + 1.24
H25(t) = H25_table(month, daytype, hour) * f(d)
```

H25 contains the modest historical prosumer effect acknowledged by BDEW; it is not a reconstructed gross behind-the-meter household series. PV-specific P25 and PV/storage S25 are excluded. L25 derives from the older agricultural L0 profiles and does not represent newly measured farm weather responses. G25 is retained in the compact library for traceability; the current service mixture uses the branch-specific research profiles below.

**Industry, services and accommodation:** Seim et al., TU Berlin, *Regression-based electricity load profiles of 32 industrial and commercial sub-sectors in Germany*, DOI `10.5281/zenodo.4576494`, CC BY 4.0. The compact library uses the published weighted German mean profiles for 2018, normalized per branch and averaged into month/weekday/hour templates. The downloaded source archive checksum is checked during library construction. Only derived data are reused; the GPL disaggregator code is not copied.

The industry template averages normalized WZ10, 11, 12, 17, 21, 22, 26, 28, 29 and 32 profiles. The service templates use the corresponding available trade/logistics, information, business, public-service and recreation branches. Their mapping is explicit in `power/demand/sector_profiles.py`. WZ64-71 is an aggregate source proxy for the relevant finance/property/business groups; it is not presented as separately measured profiles for each A10 group.

Accommodation uses WZ55. Its original German between-month energy pattern is removed before assigning local visitor-night fractions. The within-month calendar/hour pattern is retained. Missing complete monthly tourism observations use the documented geographic parent. If no complete series exists, constant daily occupancy is used and recorded, rather than inventing a local summer multiplier. Zero reported occupancy months receive only the small positive numerical prior required for balancing. A zero tourism budget remains exactly zero.

All annual sector curves are energy-normalized before mixing. Peak normalization is not used to determine annual sector shares. The published templates supply typical timing; they do not provide measured hourly NUTS3 truth for other countries or years. German weather/holiday effects remain in the averaged templates. The observed national curve carries selected-year national weather and exceptional events; this implementation does **not** estimate additional local temperature responses.

The compact library occupies approximately 1.7 MB and is included in portable-package builds. The original 153 MB research archive is not required on the receiving computer. Original source attribution, transformations and checksums are in `power/demand/profile_library/manifest.json`. Library checksums are verified before use. `build_profile_library.py` reproduces the compact CSVs from the original official workbook and verified archive.

## Reconciliation equations

Let `B_rs` be the reconciled regional-sector annual energy budget and `p_trs` the normalized positive sector curve. Initialize `Q_t,rs = B_rs * p_trs`. Each component is a region/sector pair, so the final balancing preserves the sector budget as well as each regional total:

```text
sum_rs D_t,rs = N_t
sum_t D_t,rs = B_rs
D_tr = sum_s D_t,rs
```

Iterative proportional fitting alternates:

```text
hour step:       D_t,rs <- D_t,rs * N_t / sum_rs D_t,rs
component step:  D_t,rs <- D_t,rs * B_rs / sum_t D_t,rs
```

This is a relative-entropy/KL projection of the positive prior onto compatible margins. Stopping checks both margins; a single hourly normalization would not preserve regional annual totals. Zero national-load hours and zero-budget components remain zero. Negative/non-finite values, incompatible totals, unsupported targets or nonconvergence cause a clear error before prepared demand files are replaced. Balancing can change the prior substantially; its relative L1 adjustment is reported and should be inspected.

Custom model zones sum the already balanced NUTS3 curves. Their annual targets are sums of constituent JRC-based targets. Country aggregation reproduces the national curve. An offshore zone with no source demand remains subject to the existing zero-demand/custom-zone preparation rules; this option creates no new offshore demand or imaginary economic features.

## Outputs and checks

Existing model-readable filenames and columns are retained:

- `power/demand/electricity_demand.csv`: canonical `period,Power,System,Zone`, 8,760 periods.
- `electricity_demand_<year>.csv`, `electricity_demand_nuts3_<year>.csv`, `electricity_demand_wide_<year>.csv` and `national_load_<year>.csv`: existing source-year views.
- `electricity_demand_method.json`: method, source hashes/URLs/year, composition assumptions, fallbacks, holiday calendar, regional targets/results, balancing errors and prior adjustments.
- `electricity_sector_budgets_<year>.csv`: model-year MWh per NUTS3 and component, for `sector-weighted` only. Its sum agrees with the prepared national model-year energy.

The audit sidecars are also included at the native validation-package root, **outside** the exact H2RES `data` layout. Refactored `export_report.json` includes the incoming profile provenance and its residual-demand accounting. Switching back to `national-scaled` replaces method metadata and removes the stale sector-budget sidecar. Exporting existing outputs checks the prepared method, source year and source-file checksum. It does not redownload observations or calculate a newly selected method.

Regression tests cover hourly/annual conservation, leap-year handling, differing shapes, true zeros, incompatible support, missing economic coverage, tourism accounting, custom aggregation, unchanged fixed-share behavior, source-library integrity and refactored residual shape preservation. A check using the existing Croatian 2020 ENTSO-E observations and public composition data covered 21 regions, with maximum hourly error below `1e-8 MW` and model annual regional error below `1e-6 MWh`. Italian source coverage was checked for all 107 packaged JRC regions; its numerical check used an explicitly synthetic national curve, not Italian hourly observations. These checks establish conservation and source coverage, **not measured regional prediction accuracy**.

## Command line

Full preparation, retaining the chosen other sector options:

```powershell
python generate_all_sector_inputs.py --countries HR --spatial-level nuts3 --electricity-demand-year 2020 --electricity-demand-method sector-weighted --electricity-tourism-share 0.1 --out-root outputs_all_HR --data-root data_all_HR --model-export
```

Demand-only generation, using the usual environment token and the same cache:

```powershell
python power/demand/generate_electricity_demand_standalone.py --countries HR --year 2020 --demand-method sector-weighted --tourism-share 0.1 --out-dir outputs_all_HR/power/demand --cache-dir data_all_HR/entsoe_load
```

Pass `--zone-map <shared mapping CSV>` to demand-only generation when the complete run uses custom or aggregated zones. Otherwise it writes NUTS3 zones. After demand-only generation, use **export existing outputs** with matching country, geography, year and method to rebuild the model folders. Other prepared sectors must still match the selected configuration.

## References

- [JRC Energy and Industry Geography Lab](https://energy-industry-geolab.jrc.ec.europa.eu/), existing packaged annual-electricity weights.
- [ENTSO-E Transparency Platform API](https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html).
- [Eurostat regional GVA, nama_10r_3gva](https://ec.europa.eu/eurostat/databrowser/view/nama_10r_3gva/default/table).
- [Eurostat regional employment, nama_10r_3empers](https://ec.europa.eu/eurostat/databrowser/view/nama_10r_3empers/default/table).
- [Eurostat regional population, demo_r_pjanaggr3](https://ec.europa.eu/eurostat/databrowser/view/demo_r_pjanaggr3/default/table).
- [Eurostat complete energy balances, nrg_bal_c](https://ec.europa.eu/eurostat/databrowser/view/nrg_bal_c/default/table).
- [Eurostat regional tourist nights, tour_occ_nin3](https://ec.europa.eu/eurostat/databrowser/view/tour_occ_nin3/default/table), [monthly tourism, tour_occ_nin2m](https://ec.europa.eu/eurostat/databrowser/view/tour_occ_nin2m/default/table).
- [BDEW Standardlastprofile Strom](https://www.bdew.de/energie/standardlastprofile-strom/), [official 2025 application guidance, household formula on page 4](https://www.bdew.de/media/documents/2025-03-17_AWH_Aktualisierte_SLP_Strom_2025_Ver%C3%B6ffentlichung.pdf).
- [Seim et al. profile data and attribution, DOI 10.5281/zenodo.4576494](https://doi.org/10.5281/zenodo.4576494).
- [Nager.Date API documentation](https://date.nager.at/Api).
