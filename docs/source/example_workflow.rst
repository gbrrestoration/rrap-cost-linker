Example workflow
================

With default settings, the following is an example workflow for generating files needed for `CREAM` modelling based
on a set of `ReefModEngine.jl` runs. These examples are in the `src` folder in  the scripts `example-process-rme-runs.py` and `example-process-rme-runs-para.py`
respectively.

Non-parallelised workflow
-------------------------

In the case of non-parallelised runs, the following modules are first imported:

.. code-block:: python

    import src.cost_calculations as cc
    import src.process_RME_data as prd

The key metrics summary files for each intervention/counterfactual run can then be generated using
:meth:`process_RME_data.create_economics_metric_files`. This can be run with default parameters, providing just the filepath
to the `ReefModEngine.jl` results and number of simulations (`nsims`).  `nsims` includes sampling the types of uncertainty specified by the uncertainty
flags `ecol_uncert`, `shelt_uncert` and `expert_uncert`, which are captured in `uncertainty_dict`. The same number of
samples will be drawn from the cost models, as the number of samples must match across the metrics and cost files.
See the API documentation for more detail on specififying types of uncertainty to sample and other possible settings when generating the metrics tables.

.. code-block:: python

    # Filepath to RME runs to process
    rme_files_path = "path to ReefModEngine.jl results"
    # Number of sims for metrics sampling (default includes ecological and expert uncertainty in RCI calcs)
    nsims = 300
    # Create metric datafiles for economics modelling and extract filename for intervention key
    int_keys_fn, filepaths = prd.create_economics_metric_files(rme_files_path, nsims)


After creating the metric summary files for `CREAM`, the cost files can be created by sampling the cost models
for the same scenarios run in the `ReefModEngine.jl` result set. The metrics and cost files are linked by an intervention ID key file,
which details the file names for the metric summary files and what intervention parameters each intervention ID corresponds to.
These contains key information for sampling the cost parameters, and also for interpreting any resulting economics
analyses. The filepath of this intervention ID key file is captured in the output of :meth:`process_RME_data.create_economics_metric_files` and is then input to the cost sampling function :meth:`cost_calculations.calculate_costs`.

.. code-block:: python

    # Create cost datafiles for the intervention run ids in ID_key
    cc.calculate_costs(int_keys_fn, nsims)


Other optional arguments for the cost sampling are described in the documentation for :meth:`cost_calculations.calculate_costs`.

The sampled metric files will be saved in the folder `econ_outputs`, cost files will be available in the `cost_outputs`
folder and intervention ID key files will be saved in the `intervention_keys` folder.

Parallelised workflow
---------------------

Cost model sampling for a large number of samples can have large runtimes. Additionally, the metrics file creation code can take up a lot of
memory when a large number of samples is required. In this case, it is better to process the metrics samples in batches, and
sample the cost models in parallel.

This can be done using the following code:

.. code-block:: python

    import parallel_cost_sampling as pc
    import multiprocessing as mp

    # Filepath to RME runs to process
    rme_files_path = "path to RME result set"

    # Number of sims for metrics sampling (default includes ecological and expert uncertainty in RCI calcs)
    nsims = 500
    ncores = 5 # number of cores to use

    # Create economics metrics input files, get number of batches needed to complete nsims over ncores
    int_keys_fn, nbatches = pc.para_sample_econ(rme_files_path, nsims, ncores=ncores)

    # Delete global variables which cause memory errors when running parallelised cost sampling
    for var in list(globals().keys()):
        if var not in [ 'pc', 'mp', 'int_keys_fn', 'nsims', 'ncores', 'nbatches', '__name__', '__builtins__','__spec__']:
            del globals()[var]

    # Run cost sampling in parallel on ncores
    if __name__ == "__main__":
        pool = mp.Pool(ncores)
        result = [pool.apply(pc.calc_costs_para, args=(iter_id, int_keys_fn, nbatches)) for iter_id in range(ncores)]
        pool.close()
        pool.join()

        # Post-process saved samples to be in single file
        pc.post_process_costs(result, nbatches, nsims)

Outputs
-------

For a single unique intervention ID (a unique intervention scenario run for any number of reps and any number of climate models),
the above examples would generate 6 metric output files as CSVs. By default, this would include separate files for each of the 3 metrics (the RCI, RTI and RFI),
and separate files for counterfactual and intervention scenarios. The cost sampling output would be a single file, also a CSV,
as cost sampling is only done for intervention scenarios and all cost metrics are included in a single file.

See :doc:`output_file_format` for more on the expected format of the metrics and cost CSVs.
