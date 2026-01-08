cost_eco_model_linker.runner
============================

.. py:module:: cost_eco_model_linker.runner


Functions
---------

.. autoapisummary::

   cost_eco_model_linker.runner.evaluate
   cost_eco_model_linker.runner.parallel_evaluate


Module Contents
---------------

.. py:function:: evaluate(rme_files_path: str, nsims: int, deploy_model_fn: str, prod_model_fn: str, results_dir: str, metrics: list = None, uncertainty_dict: dict = None) -> list[str]

   Evaluate costs of intervention scenarios.

   :param rme_files_path: Path to ReefMod Engine results.
   :type rme_files_path: str
   :param nsims: Number of simulations to evaluate.
   :type nsims: int
   :param deploy_model_fn: Path to deployment spreadsheet model, including filename but excluding file extension.
   :type deploy_model_fn: str
   :param prod_model_fn: Path to production spreadsheet model, including filename but excluding file extension.
   :type prod_model_fn: str
   :param results_dir: Path to directory for storing results.
   :type results_dir: str
   :param metrics: List of metrics to calculate. Default is None.
   :type metrics: list, optional
   :param uncertainty_dict: Dictionary specifying uncertainty parameters. Default is None.
   :type uncertainty_dict: dict, optional

   :returns: Paths to result files.
   :rtype: list[str]


.. py:function:: parallel_evaluate(rme_files_path: str, nsims: int, ncores: int, deploy_model_fn: str, prod_model_fn: str, results_dir: str, metrics: list = None, uncertainty_dict: dict = None)

