cost_eco_model_linker.sampling
==============================

.. py:module:: cost_eco_model_linker.sampling


Functions
---------

.. autoapisummary::

   cost_eco_model_linker.sampling.calculate_deployment_cost
   cost_eco_model_linker.sampling.calculate_production_cost
   cost_eco_model_linker.sampling.load_config
   cost_eco_model_linker.sampling.problem_spec
   cost_eco_model_linker.sampling.convert_factor_types
   cost_eco_model_linker.sampling.sample_deployment_cost
   cost_eco_model_linker.sampling.sample_production_cost


Module Contents
---------------

.. py:function:: calculate_deployment_cost(wb, factor_spec, factors)

   Calculates set up and operational costs in the deployment cost model (wb), given a set of parameters to sample.

   :param wb: The cost model as an excel workbook
   :type wb: Workbook
   :param factor_spec: The factor specification, as loaded from the config.csv
   :type factor_spec: dataframe
   :param factors: Row of a pandas dataframe with factors to sample
   :type factors: dataframerow

   :returns: * **opex** (*float*) -- Operational cost
             * **capex** (*float*) -- Setup cost


.. py:function:: calculate_production_cost(wb, factor_spec, factors)

   Calculates set up and operational costs in the production cost model (wb), given a set of parameters to sample.

   :param wb: The cost model as an excel workbook
   :type wb: Workbook
   :param factor_spec: factor specification, as loaded from the config.csv
   :type factor_spec: dataframe
   :param factors: Row of a pandas dataframe with factors to sample
   :type factors: dataframerow

   :returns: * **opex** (*float*) -- Operational cost
             * **capex** (*float*) -- Setup cost


.. py:function:: load_config(config_filepath='config.csv')

   Load configuration file for model sampling

   :param config_filepath: String specifying filepath of config file, default is the default package config file
   :type config_filepath: str


.. py:function:: problem_spec(cost_type, config_filepath='config.csv')

   Create a problem specification for sampling using SALib.

   :param cost_type: String specifying cost model type, "production_params" or "deployment_params"
   :type cost_type: str
   :param config_filepath: String specifying filepath of config file, default is the default package config file
   :type config_filepath: str

   :returns: * **sp** (*dict*) -- ProblemSpec for sampling with SALib
             * **factor_spec** (*dataframe*) -- factor specification, as loaded from the config.csv


.. py:function:: convert_factor_types(factors_df, is_cat)

   SALib samples floats, so convert categorical variables to integers by taking the ceiling.

   :param factors_df: A dataframe of sampled factors
   :type factors_df: dataframe
   :param is_cat: Boolian vector specifian whether each factor is categorical
   :type is_cat: list{bool}

   :returns: Updated sampled factor dataframe with categorical factors as integers
   :rtype: factors_df


.. py:function:: sample_deployment_cost(wb_file_path, factors_df, factor_spec)

   Sample the deployment cost model.

   :param wb_file_path: Filepath to a cost model as an excel workbook
   :type wb_file_path: str
   :param factors_df: Dataframe of factors to input in the cost model
   :type factors_df: dataframe
   :param factor_spec: factor specification, as loaded from the config.csv
   :type factor_spec: dataframe

   :returns: **factors_df** -- Updated sampled factor dataframe with costs added
   :rtype: dataframe


.. py:function:: sample_production_cost(wb_file_path, factors_df, factor_spec)

   Sample the production cost model.

   :param wb_file_path: A cost model as an excel workbook
   :type wb_file_path: Workbook file path
   :param factors_df: Dataframe of factors to input in the cost model
   :type factors_df: dataframe
   :param factor_spec: Factor specification, as loaded from the config.csv
   :type factor_spec: dataframe

   :returns: **factors_df** -- Updated sampled factor dataframe with costs added
   :rtype: dataframe
