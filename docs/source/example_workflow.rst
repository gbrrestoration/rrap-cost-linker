Example workflow
================

With default settings, the following is an example workflow for generating files needed for CREAM modelling based
on a set of ReefModEngine.jl runs.

The following modules are first imported:

.. code-block:: python

    import src.cost_calculations as cc
    import src.process_RME_data as prd

The key metrics summary files for each intervention/counterfactual run can then be generated using
`prd.create_economics_metric_files()`. This can be run with default parameters with just the filepath
to the rme results and number of simulations, or with more detail specifications on types of uncertainty
to sample and which metrics to calculate. The total number of simulations `nsims` includes sampling the types
of uncertainty specified by the uncertainty flags `ecol_uncert`, `shelt_uncert` and `expert_uncert`,
which are captured in `uncertainty_dict`. The same number of samples will be drawn from the cost modelling, as the
number of samples must match across the metrics and cost files.

If `ecol_uncert=1`, ecological uncertainty is sampled in the results by sampling RME climate reps for a particular
set of results (stochastic samples within a single climate model). If `ecol_uncert=0` the mean over all
ecological reps is instead used. If `expert_uncert=1`, expert uncertainty is incorporated in the results
by sampling a set of expert opinons on what thresholds of the 5 metrics incorporated in the Reef Condition
Index should be considered as "Poor", "Good", "Very Good", etc. condition. If `expert_uncert=0` the mean of the
7 experts opions is used (see `./datasets/ExpertReefCondition_AllResults.csv`). Currently, shelter volume
uncertainty sampling has not been incorporated (`shelt_uncert=0` is the default), as it needs access to
number of corals in each taxa and size class in the RME resultset. This is currently not available in the resultsets
from ReefModEngine.jl, but could be incorporated in future versions.

Metric functions to include can be added using the optional parameter `metrics = [...]`.
The defaults to include are RCI, raw RTI and RFI. Other optional inputs to this function are detailed in the documenbtation
for `create_economics_metric_files()`.

.. code-block:: python

    # Filepath to RME runs to process
    rme_files_path = "path to ReefModEngine.jl results"
    # Number of sims for metrics sampling (default includes ecological and expert uncertainty in RCI calcs)
    nsims = 300
    # Create metric datafiles for economics modelling and extract filename for intervention key
    int_keys_fn = prd.create_economics_metric_files(rme_files_path, nsims)


After creating the metric summary files for CREAM, the cost files can be created by sampling the cost models
for the same scenarios run in the RME result set. The files are linked by an intervention ID key file,
which details the file names for the metric summary files and what intervention parameters they correspond to.
This contains key information for sampling the cost parameters, and also for interpreting any resulting economics
analyses. The filepath of this intervention ID key file is captured in the output of `prd.create_economics_metric_files()`.
The filename for the ID key files is then input to the cost sampling function `calculate_costs()`.

.. code-block:: python

    # Create cost datafiles for the intervention run ids in ID_key
    cc.calculate_costs(int_keys_fn, nsims)


Other optional inputs to `calculate_costs` include `deploy_model_filepath` and `prod_model_filepath`, which can be placed in a
`config.json` file in the src folder to be automatically loaded, or supplied directly in the function's optional arguments.
Other optional arguments are described in the documentation for `calculate_costs`.

The sampled cost files will be available in the `cost_outputs` folder and the metric summary files will be
saved in the `eco_outputs` folder.
