Output file format
==================

The functions in this library generate two key output file types for the economics modelling,

* A metrics summary file (saved by default in `econ_outputs` as a CSV)
* A cost summary file (saved by default in `cost_outputs` as a CSV)

By default, for a single unique intervention ID (a unique intervention scenario run for any number of reps and any number of climate models),
the above examples would generate 6 metric output files. This would include separate files for each of the 3 metrics (the RCI, RTI and RFI),
and separate files for counterfactual and intervention scenarios. The cost sampling output would be a single file,
as cost sampling is only done for intervention scenarios and all cost metrics are included in a single file.

Economics metric summary file structure
---------------------------------------

The following is an example metrics summary file generated to input to `CREAM`, for the RCI metric :

.. csv-table:: Part of an eample economics metrics input file
   :header-rows: 1
   :file: interventionID_ecol0_intervention_var_rci.csv

A file such as the above is generated for *each intervention run*, i.e. for each unique combination of deployment
volume, enhancement level, deployment years etc. run in `ReefModEngine.jl`, for each metric and for each counterfactual
and intervention.

The outputs in the columns `sim_1`, `sim_2` etc. represent different draws for the same intervention scenario, which can be across multiple climate models. Each draw may sample ecological, expert and other forms of
uncertainty depending on the uncertainty settings when the files were generated (see :meth:`calculate_metrics.default_uncertainty_dict`).
The other columns summarize key information such year, year relative to the first intervention year, reef name,
distance to port, reef area in different management zones and other spatial information.

Each intervention is identifiable through an intervention ID captured in the file name. For a set of runs, an intervention
ID key file (as a CSV) is also generated and saved in `intervention_keys`, which links key intervention parameters to an intervention ID.
An example intervention ID key file is included below. Note that the number of 1YO corals reported is the actual number of outplants recorded in `ReefModEngine.jl`, so it varies
slightly between climate model replicates due to slightly different space available for coral growth in different climate scenarios. The input value for deployment volume will not vary for the same intervention ID.
The functions here treat the varying number of outplants for a single intervention as a stochastic sample for that intervention in the
cost model sampling. The intervention ID key files are necessary to assure scenario sampling IDs match between the cost and metrics samples,
but also for future reference as a record of the intervention scenarios which were run for a particular set of economics input files.

.. csv-table:: Part of an example intervention ID key file
   :header-rows: 1
   :file: intervention_ID_key_test_results_econ_metrics.csv

Cost summary file structure
---------------------------

The cost files generated have the stucture shown in the example below. The `component` column refers to 11 key cost codes:
    1. CAPEX - sum of production and deployment cost
    2. Contingency CAPEX - % of CAPEX
    3. OPEX - sum of production and deployment cost
    4. Sustaining capital OPEX - set to zero for now (assumed to be included in OPEX through contract)
    5. Contingency OPEX - % of OPEX
    6. Vessel fuel - only relevant if volunteer vessels are used - set to zero for now
    7. CAPEX-monitoring - set to zero (assumed no monitoring cost)
    8. Contingency CAPEX-monitoring - % of CAPEX-monitoring
    9. OPEX-monitoring - set to zero (assumed no monitoring cost)
    10. Sustaining capital OPEX-monitoring - set to zero (assumed no monitoring cost)
    11. Contingency OPEX-monitoring - % of OPEX-monitoring

Each of the columns `draw1`, `draw2` etc refer to unique samples drawn from the cost models for a particular
intervention scenario by varying key cost model parameters (specified in `config.csv`). The cost files and
metric summary files are linked by their intervention ID, as described in the intervention ID key file generated
when the metric summary files are produced. Cost files are only generated for the intervention scenarios, as counterfactual
scenario will have zero cost, so for a given unique intervention ID, one cost file is generated.

.. csv-table:: Part of an example cost output file
   :header-rows: 1
   :file: cost_output_template.csv
