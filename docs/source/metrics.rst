Available metrics
=================

The available metrics include the Reef Condition Index  (RCI), the Reef Tourism Index (RTI) and
Reef Fishing Index (RFI). There are also several versions of the RCI available, including raw
RCI and RCI, which measures the total reef area in good or very good condition.

Raw RCI
-------

The RCI can be calculated using :meth:`process_RME_data.raw_rci`. This metric comprises 5 reef metrics,
    * Relative coral cover
    * Relative shelter volume
    * Relative abundance of juveniles
    * Complementary relative crown of thorns population (relative to outbreak levels)
    * Complementary rubble cover

These values are categorised as within Very Good, Good, Fair, Poor or Very Poor condition depending on their
values and a set of categories compiled by expert elicitation. Each reef is categorised into the highest category for The expert elicitation process was carried out
at a workshop in October 2021 with 8 coral reef experts elicited.

.. csv-table:: Expert elicitated reef condition metrics
   :header-rows: 1
   :file: Heneghan_RCI.csv

The raw RCI is calculated by asessing the condition of a reef at each timestep for each metric according
to the above categories. The reef is assigned the condition of the highest category for which 3 or more metrics satisfy
that category's threshold. The raw expert condition categories of data collected from 8 experts can also be sampled
when calculating metrics by setting `expert_uncert=1`.

RTI
---

The RTI, or Reef Tourism Index, is a continuous version of the RCI condition categories. RTI can be calculated using
:meth:`process_RME_data.raw_rti`.

RFI
---

The RFI or Reef Fishing Index, estimates the total fish biomas in kg km^2, based on a linear regression of total
cover. This is based on digitisation of Fig 4A and 6B in Graham and Nash, 2012 `<https://doi.org/10.1007/s00338-012-0984-y>`_
The RFI can be calculated using :meth:`process_RME_data.rfi`.

RCI
---
The RCI looks at the total area of reef for which the condition is within the Good or Very Good categories.
RCI can be calculated using :meth:`process_RME_data.rci`.

Uncertainty sampling
--------------------
If `ecol_uncert=1`, ecological uncertainty is sampled in the results by sampling climate model repetitions for a particular
set of results (stochastic samples within a one or more climate model). If `ecol_uncert=0` the mean over all
ecological reps is instead used. If `expert_uncert=1`, expert uncertainty is incorporated in the results
by sampling a set of expert opinons on what thresholds of the 5 metrics incorporated in the Reef Condition
Index should be considered as "Poor", "Good", "Very Good", etc. condition. If `expert_uncert=0` the mean of the
7 experts opions is used (see `./datasets/ExpertReefCondition_AllResults.csv`). Currently, shelter volume
uncertainty sampling has not been incorporated (`shelt_uncert=0` is the default), as it needs access to
number of corals in each taxa and size class in the RME resultset. This is currently not available in the resultsets
from ReefModEngine.jl, but could be incorporated in future versions.
