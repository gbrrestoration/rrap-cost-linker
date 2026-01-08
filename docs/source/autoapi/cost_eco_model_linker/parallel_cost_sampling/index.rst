cost_eco_model_linker.parallel_cost_sampling
============================================

.. py:module:: cost_eco_model_linker.parallel_cost_sampling


Attributes
----------

.. autoapisummary::

   cost_eco_model_linker.parallel_cost_sampling.THIS_DIR


Functions
---------

.. autoapisummary::

   cost_eco_model_linker.parallel_cost_sampling.para_sample_econ
   cost_eco_model_linker.parallel_cost_sampling.post_process_metrics
   cost_eco_model_linker.parallel_cost_sampling.post_process_costs


Module Contents
---------------

.. py:data:: THIS_DIR

.. py:function:: para_sample_econ(rme_files_path: str, nsims: int, stores: cost_eco_model_linker.setup_results.OutputStores, ncores=5, uncertainty_dict=None, metrics=None, max_dist=25.0)

   Run economics metrics data creation files so that corresponding cost data can be sampled in parallel.
   Saves ID key files so that these are available for all cores while sampling cost models in parallel.
   Also saves scenario references so that parallel samples process the correct scenario sims.

   :param rme_files_path: String giving the path to resultset folder.
   :type rme_files_path: string
   :param nsims: Number of simulations to sampling (including uncertainty types as specified)
   :type nsims: int
   :param stores: Data class holding output file paths where economic metric files will be stored.
   :type stores: OutputStores
   :param ncores: Number of cores to sample cost models over.
   :type ncores: int
   :param uncertainty_dict: Contains information on what uncertainty types to sample.
   :type uncertainty_dict: dict
   :param max_dist: Maximum distance between reefs within a "cluster". Total distance to port is calculated as distance
                    to port for closest reef cluster + distance between each additional further cluster where distance between
                    clusters is calculated as distance between the reefs furthest from port in each cluster.
   :type max_dist: float


.. py:function:: post_process_metrics(stores: cost_eco_model_linker.setup_results.OutputStores, metric_filepaths: list[str], metrics: list, nsims: int)

   When running multiple cores for cost sampling, metrics calculations are also broken into batches
   to avoid memory issues when creating large metrics datacubes (have shape nsims*nyears*nreefs)

   Writes metric results NOT as a "large metrics datacubes" but as a flat CSV.

   :param stores: Data class defining output directories
   :type stores: OutputStore
   :param metric_filepaths: List of all filepaths where metrics are saved.
   :type metric_filepaths: list{string}
   :param metrics: List of metric functions which were calculated.
   :type metrics: list{function}
   :param nsims: Total number of simulations runs
   :type nsims: int

   :rtype: None


.. py:function:: post_process_costs(result, nsims)

   Save cost samples run in parallel in a single file which is in the correct format for the economics modelling.

   :param result: List of filenames for saved parallel cost data runs.
   :type result: list
   :param nsims: Total number of draws to sample cost models, should match ecological metrics sampling.
   :type nsims: int


