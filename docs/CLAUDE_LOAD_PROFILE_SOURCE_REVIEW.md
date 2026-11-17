# Assessment of supplied load-shape recommendations

**Date:** 16 November 2026. **Scope:** historical assessment of the supplied load-shape discussion and its references, preceding implementation. The attachment contained text descriptions, not the actual plotted curves or numeric arrays. No production generator was changed during this assessment and no claim of measured NUTS3 accuracy is made. The production option is now implemented: see the [current method, sources and equations](REGIONAL_ELECTRICITY_PROFILES.md).

## 1. Overall assessment

The supplied discussion correctly distinguishes its illustrative curves from measured data and supports combining sector profiles. Its strongest additional lead is the Electricity Authority of Cyprus (EAC) catalogue, which explicitly lists a metering-derived hotel customer class. The quoted numerical shape factors remain assumptions. Most other references either provide customer-sector profiles, describe a decomposition method, or support broad tendencies; they do not establish four universal measured regional curves.

For this project, region types should be descriptive summaries of a continuous sector mixture, not the four exclusive templates used to generate demand. Two industry-heavy regions can differ because of their process mix, shifts, heating, calendar and other consumers. Likewise a coastal tourist region and a winter-resort region need different seasonality.

## 2. Assessment of the actual sources

| Source | What was verified | Role in the proposed pipeline |
|---|---|---|
| BDEW | Official downloadable household/commercial/agricultural profile sets and accompanying instructions; updated 2025 and legacy sets are distinct | Direct customer-profile candidate, with correct vintage, normalization and calendar |
| Cyprus EAC | Indexed official catalogue explicitly lists large commercial hotel units and metering-derived profile classes; it names profile workbooks | Strong hotel-profile candidate, pending successful workbook retrieval and inspection |
| EIA | Official US article discusses sector seasonality using monthly electricity sales | Qualitative background; not a European hourly profile dataset |
| Italian source-separation study | Public paper/repository describe constrained nonnegative matrix factorization and sector decomposition; a monthly indicator is not shareable | Research/validation reference; not a fully self-contained automatic source for all inputs |
| Danish customer study | Original research describes about 4,500 representative customers across sectors | Evidence supporting sector differences; downloadable reusable arrays were not established in this review |
| Conditional-GAN study | Research generates synthetic week-long transmission-load series using a neural generative model | Outside the selected non-neural implementation; not a direct regional template source |
| KiNESYS | Documentation provides explicit shape/decomposition assumptions rather than a measured NUTS3 template library | Method comparison; do not copy its numerical assumptions as measured European parameters |

### BDEW

The legacy seasonal/day-type description is broadly appropriate, but it must not be applied to every edition: the 2025 profiles use a monthly formulation. They are customer-group profiles, not a complete large-industry or tourist-region library. Avoid embedding PV/storage-adjusted net-consumption profiles when H2RES accounts for these technologies separately. BDEW says its updated agricultural profile builds on the older agricultural profile because suitable specific measurements were unavailable.

References: [official profile downloads](https://www.bdew.de/energie/standardlastprofile-strom/), [2025 application guide](https://www.bdew.de/media/documents/2025-03-17_AWH_Aktualisierte_SLP_Strom_2025_Ver%C3%B6ffentlichung.pdf).

### Cyprus EAC

The official catalogue includes hotel and non-hotel large commerce, industrial sizes, households and water pumps. It distinguishes ordinary consumption from PV-related offtake and injection. This is a useful Mediterranean comparison. During this review, the indexed pilot page redirected to maintenance, so workbook contents, units, annual coverage and redistribution terms were not verified. A hotel class does not establish an entire tourist-region profile or a Croatian summer/winter ratio. [Official indexed EAC catalogue](https://pilot.eac.com.cy/en/distribution/useful-information/).

### EIA, Denmark and the two modeling papers

The [EIA article](https://www.eia.gov/todayinenergy/detail.php?id=10211) supports qualitative US sector seasonality. Its monthly sales comparison does not calibrate Croatian hourly shapes or a specific nighttime base-load percentage.

The Danish reference can be identified directly as Andersen, Larsen and Boomsma (2013), *Long-term forecasting of hourly electricity load: Identification of consumption profiles and segmentation of customers*, Energy Conversion and Management 68, 244–252. Its abstract describes roughly 4,500 representative customers. A paper is not automatically an openly downloadable profile archive. [Original publisher record](https://www.sciencedirect.com/science/article/abs/pii/S0196890413000381).

The [Italian paper](https://arxiv.org/html/2512.15232v1) is relevant, but explicitly excludes a monthly sector indicator from public data for privacy reasons. The [repository](https://github.com/gkchln/load-bss) also identifies inputs provided by Terna and manually compiled annual demand. It is not a turnkey, public-data-only replacement. Its NMF method is distinct from a neural network. The [conditional-GAN paper](https://arxiv.org/abs/2107.03545) studies synthetic weekly loads and would reintroduce neural modeling; it is not needed for the selected sector-template approach.

### KiNESYS

[KiNESYS load-shape documentation](https://kanors-emr.github.io/Kinesys-documentation/electricity-load-shapes/) is useful as a method example. It assigns industrial damping and commercial hour factors, and obtains residential demand as a residual. These are modeling choices, not observed NUTS3 templates. A residual construction also requires explicit nonnegativity checks. Several industrial references on the inspected page are generic descriptions without complete bibliographic identifiers. ERA5 itself supplies weather, not measured electricity demand; derived electricity curves need their own provenance. We should not inherit these parameters without calibration.

## 3. Claims that should not become default numerical parameters

The proposed 65–70% industrial nighttime-to-peak ratio, 2.5–3 times summer/winter coastal demand, and 8–10-week capacity requirement were acknowledged as invented illustrations. They should not be transferred into model inputs as sourced observations.

The comparison must also define whether a ratio concerns monthly MWh, average MW, daily energy or a peak. Months have different lengths; tourism, cooling and resident demand overlap. A national Croatian ratio cannot establish a coastal NUTS3 ratio. Coastal observations or independent distribution-area evidence would be needed.

High load factor does not universally mean easiest to supply. At equal annual energy it can reduce peak capacity requirements, but a continuous industrial load can also require substantial firm or stored energy during renewable deficits. Adequacy depends on timing, weather, flexibility and the supply mix.

Industry is not universally flat: continuous, batch and shift processes differ. Commercial/public services include continuous hospitals, refrigeration and weekend activities. Rural economies can contain irrigation and industrial loads. Seasonal behavior depends on the observation year and actual heating/cooling mix.

## 4. Profile normalization needs a correction

Peak normalization is appropriate for visual comparisons but not for combining curves using annual electricity shares. First normalize every component to unit annual energy, then multiply by its annual MWh allocation:

```text
p[r,s,t] = q[r,s,t] / sum_t(q[r,s,t] * delta_t)
Q[r,t] = sum_s(E[r,s] * p[r,s,t])
```

The annual sector budgets sum to the fixed regional budget. Economic GVA/employment shares need electricity-intensity calibration before they determine these budgets. After combining profiles, enforce both national hourly loads and regional annual shares through two-margin reconciliation. Tourism must be a defined subdivision/adjustment of services, not an additional demand counted on top of unchanged services.

## 5. A stronger additional candidate: ELMAS

The cited literature points to **ELMAS**, based on 424 French industrial/tertiary NACE classes, with derived profiles and annual metadata. Its article links a public Figshare dataset. Raw individual customer data remain private. Standardized series need appropriate de-standardization before physical use; they are not nonnegative normalized demand directly. Climate transfer and calendar coverage must be checked. This is a useful complement to DemandRegio, not proof of universal French-profile transferability. [Primary paper](https://doi.org/10.1038/s41597-023-02542-z), [dataset DOI](https://doi.org/10.6084/m9.figshare.23889780).

## 6. Recommended source hierarchy

Retain national customer profiles where suitable, such as HEP ODS for Croatia. Use DemandRegio and potentially ELMAS for differentiated industry/services; evaluate EAC hotel data if retrieval succeeds. Supplement residential/agricultural gaps with suitable BDEW profiles. Apply local calendar, weather and tourism information with source-specific coverage flags.

Use the Danish and EIA material to substantiate qualitative choices, and KiNESYS/source-separation research for methodological comparison. Do not use invented archetype ratios or a GAN as mandatory components. Preserve source versions, profile units, transformation steps and calibration status. Country profiles are transfer assumptions outside their source area until independent evidence establishes accuracy.

The existing [feasibility assessment](NUTS3_ELECTRICITY_PROFILE_FEASIBILITY.md) remains applicable: fixed regional annual electricity ratios, exact national hourly reconciliation, transparent sector mixtures, explicit residual accounting in both H2RES formats and validation against independent regional observations.
