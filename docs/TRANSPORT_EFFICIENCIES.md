# Transport efficiency in generated H2RES inputs

The extractor uses the detailed transport assumptions in the 19 November 2026 H2RES model. The comparison workbook is `data/flex_tech_efuel_categories.xlsx`, sheet `transport_all`. Its `efficiency_primary` coefficient measures passenger-km or tonne-km delivered per kWh of primary vehicle energy. For the same service, multiplying an ICE coefficient by three divides the required vehicle energy by three. Charging efficiency (`EV_grid_eff`) remains a separate input.

| Technology | Model input rule |
|---|---|
| Battery truck, short-haul battery aircraft, short-route battery vessel | 3 times the corresponding ICE coefficient |
| Hybrid bus and truck | 1.5 times ICE |
| Fuel-cell car, bus, truck and short- or long-haul aircraft | 2 times ICE |
| Battery car and bus, hybrid car, electric freight rail | Keep a finite, positive source coefficient. If missing, multiply local ICE by the corresponding detailed reference ratio (approximately 4.22, 2.76, 1.66 and 1.38 respectively). |
| Electric passenger rail | Keep a finite, positive source coefficient, matching the regional model rows. If missing, use the 3 times ICE assumption found in the model's national HR1 row. |

The ICE donor must match the system, zone and service sector. If the local ICE coefficient is also missing or nonpositive, the detailed Croatian workbook supplies the same-mode ICE reference for model inputs. This is a scenario assumption. A zero fleet count alone does not invalidate a positive coefficient, which matters especially for rail. Applying a coefficient creates no vehicles or transport activity.

The simple reference workbook uses separate Croatian passenger-car coefficients (ICE 1.08, battery 5.40, hybrid 1.62 and fuel cell 3.24). Generated multi-mode fleets use the detailed convention consistently across native export variants. The refactored export converts the coefficient to service per MWh for the fleets represented on its prescribed pathway.

Historical energy reconstruction keeps usable source efficiencies, even where the model uses a scenario formula. If source activity is positive and an alternative drivetrain has no usable coefficient, the historical calculation can use the matching local ICE coefficient and factor. Existing explicit energy data follow the transport source table's existing accounting.

For an already prepared case, select **Export existing outputs** and the desired model formats. The native export applies the rules before creating compatibility and retrofit rows. Use **Generate** for fresh intermediate transport CSVs or workbooks. Both paths use the same model-input calculation.

## Croatian comparison

| Unit | Previously prepared HR coefficient | Revised coefficient | Service per kWh |
|---|---:|---:|---|
| EV_truck | 0.83837 | 5.37031 | tonne-km |
| HYBRID_truck | 0 | 2.68515 | tonne-km |
| HYBRID_BUS | 0 | 23.01378 | passenger-km |

The 24 Croatian base-technology coefficients matched all 24 in each of the detailed workbook's coast, cont and zag zones. The national HR1 row differed for electric passenger rail: the extractor retained 2.83725 passenger-km/kWh from the source, whereas that workbook cell sets it to 3 times 2.07782, or 6.23345. Fleet counts are a separate scenario input. For example the detailed HR1 row assigns 60 electric freight-rail units while the source fleet count is zero.
