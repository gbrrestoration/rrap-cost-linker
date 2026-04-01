cost_eco_model_linker.cost_calculations
=======================================

.. py:module:: cost_eco_model_linker.cost_calculations


Attributes
----------

.. autoapisummary::

   cost_eco_model_linker.cost_calculations.THIS_DIR


Functions
---------

.. autoapisummary::

   cost_eco_model_linker.cost_calculations.get_NK
   cost_eco_model_linker.cost_calculations.cost_types
   cost_eco_model_linker.cost_calculations.initialize_cost_df
   cost_eco_model_linker.cost_calculations.factors_dataframe_update
   cost_eco_model_linker.cost_calculations.update_factors
   cost_eco_model_linker.cost_calculations.update_capex_factors
   cost_eco_model_linker.cost_calculations.calculate_costs


Module Contents
---------------

.. py:data:: THIS_DIR

.. py:function:: get_NK(nsims, n_factors)

   Calculate number of input Sobol samples, N, given number of total simulations required and number of factors.
   Want an output number of samples, N*K , as close to the required number of sims as possible, where
   K = (2*n_factors + 2).
   See https://salib.readthedocs.io/en/latest/api.html#sobol-sensitivity-analysis


.. py:function:: cost_types(cost, contingency, nsims)

   Calculate key cost codes:
   - 1 : CAPEX,  sum of production and deployment cost
   - 2 : Contingency CAPEX,  % of CAPEX
   - 3 : OPEX,  sum of production and deployment cost
   - 4 : Sustaining capital OPEX, set to zero for now (assumed to be included in OPEX through contract)
   - 5 : Contingency OPEX, % of OPEX
   - 6 : Vessel fuel, only relevant if volunteer vessels are used - set to zero for now
   - 7 : CAPEX-monitoring, set to zero (assumed no monitoring cost)
   - 8 : Contingency CAPEX-monitoring, % of CAPEX-monitoring
   - 9 : OPEX-monitoring, set to zero (assumed no monitoring cost)
   - 10 : Sustaining capital OPEX-monitoring, set to zero (assumed no monitoring cost)
   - 11 : Contingency OPEX-monitoring, % of OPEX-monitoring

   :param cost: Dataframe containing 'capex' and 'opex'
   :type cost: dataframe
   :param contingency: Contingency proportion.
   :type contingency: float
   :param nsims: Total number of simulations (from metrics sampling)
   :type nsims: int


.. py:function:: initialize_cost_df(years, nsims)

   Initialize dataframe for storing sampled cost data.

   :param years: Intervention years
   :type years: np.array
   :param nsims: Total number of simulations (from metrics sampling)
   :type nsims: int

   :returns: **cost_df**
   :rtype: dataframe


.. py:function:: factors_dataframe_update(nsims)

   Sample cost model parameters.

   :param nsims: Total number of simulations (from metrics sampling)
   :type nsims: int

   :returns: * **factor_specs_dep** (*dict*) -- Factor specification for sampling factors in the deployment cost model.
             * **factors_df_dep** (*dataframe*) -- Sampled factors dataframe for the deployment cost model.
             * **factor_specs_prod** (*dict*) -- Factor specification for sampling factors in the production cost model.
             * **factors_df_prod** (*dataframe*) -- Sampled factors dataframe for the production cost model


.. py:function:: update_factors(factors_df_dep, factors_df_prod, ID_key, ecol_idx, nsims)

   Update sampled cost model parameter dataframes with intervention specific parameters.

   :param factors_df_dep: Factors dataframe for the deployment cost model.
   :type factors_df_dep: dataframe
   :param factors_df_prod: Factors dataframe for the production cost model
   :type factors_df_prod: dataframe
   :param ID_key: Intervention specification dataframe containing intervention parameters.
   :type ID_key: dataframe
   :param ecol_idx: Indices mapping scenario IDs in the RME results to samples in nsims.
   :type ecol_idx: int
   :param nsims: Number of simulations drawn (may be smaller than dataframe size to get correct number of samples
                 for Sobol Sampling).
   :type nsims: int


.. py:function:: update_capex_factors(factors_df_dep, factors_df_prod, ID_key, ecol_idx, nsims)

   Update number of corals to correctly calculate setup cost for years after the first intervention year.
   Setup costs are only accrued for additional corals deployed relative to the previous year.

   :param factors_df_dep: Factors dataframe for the deployment cost model.
   :type factors_df_dep: dataframe
   :param factors_df_prod: Factors dataframe for the production cost model
   :type factors_df_prod: dataframe
   :param ID_key: Intervention specification dataframe containing intervention parameters.
   :type ID_key: dataframe
   :param ecol_idx: Indices mapping scenario IDs in the RME results to samples in nsims.
   :type ecol_idx: int
   :param nsims: Number of simulations drawn (may be smaller than dataframe size to get correct number of samples
                 for Sobol Sampling).
   :type nsims: int


.. py:function:: calculate_costs(stores: cost_eco_model_linker.setup_results.OutputStores, ID_key_fn: str, nsims: int, deploy_model_filepath: str, prod_model_filepath: str, cont_p: float = 0.25, iter_id: int = 0)

   Sample costs for a set of interventions specified in ID_key, sampling nsims.

   :param stores: Data class holding output directory locations
   :type stores: OutputStores
   :param ID_key_fn: Target filename for output.
   :type ID_key_fn: str
   :param nsims: Total number of draws to sample cost models, should match ecological metrics sampling.
   :type nsims: int
   :param deploy_model_filepath: Path to deployment cost model.
   :type deploy_model_filepath: string
   :param prod_model_filepath: Path to production cost model.
   :type prod_model_filepath: string
   :param cont_p: Contingency cost proportion.
   :type cont_p: float
   :param iter_id: ID used for parallel sampling to keep track of batches for ordered recombination.
   :type iter_id: int
