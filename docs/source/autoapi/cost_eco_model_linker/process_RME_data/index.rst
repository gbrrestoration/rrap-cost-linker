cost_eco_model_linker.process_RME_data
======================================

.. py:module:: cost_eco_model_linker.process_RME_data


Attributes
----------

.. autoapisummary::

   cost_eco_model_linker.process_RME_data.THIS_DIR


Functions
---------

.. autoapisummary::

   cost_eco_model_linker.process_RME_data.load_reef_data
   cost_eco_model_linker.process_RME_data.load_regions_data
   cost_eco_model_linker.process_RME_data.load_result_files
   cost_eco_model_linker.process_RME_data.create_base_economics_dataframe
   cost_eco_model_linker.process_RME_data.area_weighted_rti
   cost_eco_model_linker.process_RME_data.rci
   cost_eco_model_linker.process_RME_data.coral_area_saved
   cost_eco_model_linker.process_RME_data.rfi
   cost_eco_model_linker.process_RME_data.raw_rci
   cost_eco_model_linker.process_RME_data.raw_rti
   cost_eco_model_linker.process_RME_data.create_economics_metric_files


Module Contents
---------------

.. py:data:: THIS_DIR

.. py:function:: load_reef_data()

   Loads key reef spatial data.


.. py:function:: load_regions_data(economics_spatial_filepath: str)

   Loads key economics spatial data.

   :param economics_spatial_filepath: String giving the path to economics spatial data.
   :type economics_spatial_filepath: string

   :returns: **regions_data**
   :rtype: dataframe


.. py:function:: load_result_files(rme_files_path: str)

   Loads results files generated from running scenarios in ReefModEngine.jl.

   :param rme_files_path: String giving the path to resultset folder.
   :type rme_files_path: string

   :returns: * **results_data** (*dict*) -- Dict containing numpy arrays of results data from running ReefModEngine.jl.
             * **scens_df** (*dataframe*) -- Describes scenario parameters year-by-year, including rep, year and intervention levels.
             * **iv_dict** (*dict*) -- Contains other key scenario info, such as whether the scenario is counterfactual or intervention.


.. py:function:: create_base_economics_dataframe(regions_data: pandas.DataFrame, reef_spatial_data: pandas.DataFrame, years: list)

   Creates base structure for metrics summary files input to economics modelling.

   :param regions_data: A dataframe with key spatial and economics data for each reef in the GBR (loaded from econ_spatial.csv).
   :type regions_data: dataframe
   :param reef_spatial_data: A dataframe from the RME specified key reef IDs and spatial information (loaded from reefmod_gbr.gpkg).
   :type reef_spatial_data: dataframe
   :param years: Years to be included in the economics output file from the ecological modelling.
   :type years: list

   :returns: **data_store** -- Basic economics file structure to save for each intervention/counterfactual scenario.
   :rtype: dataframe


.. py:function:: area_weighted_rti(metrics_dict: dict, metrics_df: pandas.DataFrame)

   Processes metrics dict into continuous reef condition weighted by reef area.

   :param metrics_dict: Dict containing key sampled metrics and the RCI
   :type metrics_dict: dict
   :param metrics_df: Dataframe containing scenario summary dataframe
   :type metrics_df: dataframe


.. py:function:: rci(metrics_dict: dict, metrics_df: pandas.DataFrame, rci_threshold=0.6)

   Processes metrics dict into area at threshold RCI and above.

   :param metrics_dict: Dict containing key sampled metrics and the RCI
   :type metrics_dict: dict
   :param metrics_df: Dataframe containing scenario summary dataframe
   :type metrics_df: dataframe
   :param rci_threshold: RCI threshold (in (0.0, 1.0)) above which to calculate area saved for.
   :type rci_threshold: float


.. py:function:: coral_area_saved(metrics_dict: dict, metrics_df: pandas.DataFrame)

   Processes metrics dict into total area of coral cover in hectares.

   :param metrics_dict: Dict containing key sampled metrics and the RCI
   :type metrics_dict: dict
   :param metrics_df: Dataframe containing scenario summary dataframe
   :type metrics_df: dataframe


.. py:function:: rfi(metrics_dict: dict, metrics_df: pandas.DataFrame, rfi_thresholds=[0.74, 29.91])

   Processes metrics dict into area at threshold RFI and above.
   Minimum fish biomass is 0.74 kg km2. This was the minimum observation in the Graham and Nash,
   2012 dataset. Similarly, max fish biomass is 29.91kg km2.

   :param metrics_dict: Dict containing key sampled metrics and the RFI
   :type metrics_dict: dict
   :param metrics_df: Dataframe containing scenario summary dataframe
   :type metrics_df: dataframe
   :param rfi_thresholds: RFI thresholds (min and max fish biomass)
   :type rfi_thresholds: float


.. py:function:: raw_rci(metrics_dict: dict, metrics_df: pandas.DataFrame)

   Processes metrics dict into raw RCI for table storage.

   :param metrics_dict: Array containing key sampled metrics and the RCI
   :type metrics_dict: dict
   :param metrics_df: Dataframe containing scenario summary dataframe
   :type metrics_df: dataframe


.. py:function:: raw_rti(metrics_dict: dict, metrics_df: pandas.DataFrame)

   Processes metrics dict into raw RTI for table storage.

   :param metrics_dict: Array containing key sampled metrics and the RTI
   :type metrics_dict: dict
   :param metrics_df: Dataframe containing scenario summary dataframe
   :type metrics_df: dataframe


.. py:function:: create_economics_metric_files(rme_files_path: str, nsims: int, stores, nbatches=None, uncertainty_dict: dict = None, ncores: int = 1, metrics=None, max_dist=25.0, economics_spatial_filepath=None) -> tuple[str, list[str]]

   Main function for creating metric file summaries for input to economics modelling.

   :param rme_files_path: Path to resultset folder.
   :type rme_files_path: str
   :param nsims: Number of simulations to sample (including uncertainty types as specified).
   :type nsims: int
   :param stores: Storage paths object with econ_dir and intervention_keys_dir attributes.
   :type stores: object
   :param nbatches: Number of batches. If None, defaults to nsims (single batch).
   :type nbatches: int, optional
   :param uncertainty_dict: Information on uncertainty types to sample.
   :type uncertainty_dict: dict, optional
   :param ncores: Number of cores for output file generation.
   :type ncores: int, default=1
   :param metrics: List of metric functions to calculate. Defaults to [rci, raw_rti, rfi].
   :type metrics: list, optional
   :param max_dist: Maximum distance (NM) between reefs within a cluster for distance calculations.
   :type max_dist: float, default=25.0
   :param economics_spatial_filepath: Path to economics spatial data (econ_spatial.csv).
   :type economics_spatial_filepath: str, optional

   :returns: * **run_id** (*str*) -- Base filename identifier for this run.
             * **metric_filepaths** (*list*) -- List of generated metric file paths for each intervention.


