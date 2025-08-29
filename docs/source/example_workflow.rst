Example workflow
================

With default settings, the following is an example workflow for generating files needed for `CREAM` modelling based
on a set of `ReefModEngine.jl` runs.

The following modules are first imported:

.. code-block:: python

    import src.cost_calculations as cc
    import src.process_RME_data as prd

The key metrics summary files for each intervention/counterfactual run can then be generated using
`prd.create_economics_metric_files()`. This can be run with default parameters, providing just the filepath
to the `ReefModEngine.jl` results and number of simulations.  The total number of simulations `nsims` includes sampling the types of uncertainty specified by the uncertainty
flags `ecol_uncert`, `shelt_uncert` and `expert_uncert`, which are captured in `uncertainty_dict`. The same number of
samples will be drawn from the cost models, as the number of samples must match across the metrics and cost files.
See the API documentation for more detail on specififying types of uncertainty
to sample, metrics to calculate and other setting when generating the metrics tables.

.. code-block:: python

    # Filepath to RME runs to process
    rme_files_path = "path to ReefModEngine.jl results"
    # Number of sims for metrics sampling (default includes ecological and expert uncertainty in RCI calcs)
    nsims = 300
    # Create metric datafiles for economics modelling and extract filename for intervention key
    # nbatches = nsims and ncores = 1 if not using parallelisation
    int_keys_fn, filepaths = prd.create_economics_metric_files(rme_files_path, nsims, nsims, ncores=1)


After creating the metric summary files for `CREAM`, the cost files can be created by sampling the cost models
for the same scenarios run in the `ReefModEngine.jl` result set. The files are linked by an intervention ID key file,
which details the file names for the metric summary files and what intervention parameters they correspond to.
This contains key information for sampling the cost parameters, and also for interpreting any resulting economics
analyses. The filepath of this intervention ID key file is captured in the output of `prd.create_economics_metric_files()`.
The filename for the ID key files is then input to the cost sampling function `calculate_costs()`.

.. code-block:: python

    # Create cost datafiles for the intervention run ids in ID_key
    cc.calculate_costs(int_keys_fn, nsims)


Other optional arguments for the cost sampling are described in the documentation for `calculate_costs`.

The sampled metric files will be saved in the folder `econ_outputs`, cost files will be available in the `cost_outputs`
folder and intervention ID key files will be saved in the `intervention_keys` folder.

Cost model sampling for a large number of samples can have large runtimes, so it is better to sample the models in parallel.
This can be done using the following code:

.. code-block:: python

    import parallel_cost_sampling as pc
    import multiprocessing as mp

    # Filepath to RME runs to process
    rme_files_path = "path to RME result set"

    # Number of sims for metrics sampling (default includes ecological and expert uncertainty in RCI calcs)
    nsims = 10
    ncores = 5 # number of cores to use

    # Create economics metrics input files, get number of batches needed to complete nsims over ncores
    int_keys_fn, nbatches = pc.para_sample_econ(rme_files_path, nsims, ncores=ncores)

    # Run cost sampling in parallel on ncores
    if __name__ == "__main__":
        pool = mp.Pool(ncores)
        result = [pool.apply(pc.calc_costs_para, args=(iter_id, int_keys_fn, nbatches)) for iter_id in range(ncores)]
        pool.close()
        pool.join()

        # Post-process saved samples to be in single file
        pc.post_process_costs(result, nbatches, nsims)
