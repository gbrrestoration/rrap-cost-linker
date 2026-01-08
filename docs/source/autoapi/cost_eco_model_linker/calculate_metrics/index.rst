cost_eco_model_linker.calculate_metrics
=======================================

.. py:module:: cost_eco_model_linker.calculate_metrics


Attributes
----------

.. autoapisummary::

   cost_eco_model_linker.calculate_metrics.THIS_DIR


Functions
---------

.. autoapisummary::

   cost_eco_model_linker.calculate_metrics.default_uncertainty_dict
   cost_eco_model_linker.calculate_metrics.indicator_params
   cost_eco_model_linker.calculate_metrics.reef_condition_rme
   cost_eco_model_linker.calculate_metrics.rti_rme
   cost_eco_model_linker.calculate_metrics.rfi_rme
   cost_eco_model_linker.calculate_metrics.extract_metrics


Module Contents
---------------

.. py:data:: THIS_DIR

.. py:function:: default_uncertainty_dict() -> dict

   Creates a dictionary containing default uncertainty parameter settings. Can be modified to control
   what sources of uncertainty are sampled when calculating metrics.

   :returns: **uncertainty_dict** -- Contains information on what uncertainty types to sample.

             - ecol_uncert : int (0 or 1)
                 If 1 includes ecological uncertainty by sampling metrics over climate replicates, if 0 just uses
                 mean of metrics over climate replicates.
             - shelt_uncert : int (0 or 1)
                 Placeholder to be implemented, will sampling uncertainty in shelter volume parameters.
             - expert_uncert : int (0 or 1)
                 If 1 includes expert uncertainty by sampling RCI condition thresholds over several expert opinions,
                 if 0 uses RCI condition thresholds averaged over experts considered.
             - rti_uncert : int (0 or 1)
                 If 1 includes rti uncertainty by sampling linear regression parameters used to convert RCI to continuous
                 form.
             - rfi uncert : (0 or 1)
                 If 1 includes RFI uncertainty by sampling linear regression parameters used to calculate RFI.
   :rtype: dict


.. py:function:: indicator_params(result_set, scen_ids, uncertainty_dict=None, juv_max_years=None, max_coral_juv=None)

   Calculates key parameters for shelter volume and RCI calculations given uncertainty sampling choices.

   :param result_set: ReefModEngine.jl resultset structure.
   :type result_set: dict
   :param scen_ids: List of scenario IDs to consider (e.g. only sample counterfactual/intervention etc.).
   :type scen_ids: np.array
   :param uncertainty_dict: Contains information of which types of uncertainty to sample when processing metrics.
   :type uncertainty_dict: dict
   :param juv_max_years: Indices of years to calculate Juveniles max baseline over.
   :type juv_max_years: list
   :param max_coral_juv: Max juveniles baseline (can be included instead of using hindcasting baseline).
   :type max_coral_juv: list[float]

   :returns: * **max_coral_juv** (*np.float*) -- Maximum juveniles baseline.
             * **sheltervolume_parameters** (*np.array*) -- Parameters for sheltervolume regression models.
             * **rci_crit** (*np.array*) -- Array of thresholds describing reef condition categories.


.. py:function:: reef_condition_rme(results_data, scen_ids, ecol_uncert, sheltervolume_parameters, rci_crit, maxcoraljuv, nsims)

   Calculates reef condition for a set of scenarios in the provided ReefModEngine.jl results_data.

   :param results_data: ReefModEngine.jl resultset structure.
   :type results_data: dict
   :param scen_ids: List of scenario IDs to consider (e.g. only sample counterfactual/intervention etc.).
   :type scen_ids: np.array
   :param ecol_uncert: If 1 includes ecological uncertainty by sampling metrics over climate replicates, if 0 just uses
                       mean of metrics over climate replicates.
   :type ecol_uncert: int (0 or 1)
   :param sheltervolume_parameters: Currently unused, but when implemented will allow sampling of uncertainty in shelter volume models
                                    to calculate shelter volume.
   :type sheltervolume_parameters: np.array
   :param rci_crit: Array of thresholds describing reef condition categories.
   :type rci_crit: np.array
   :param maxcoraljuv: Max juveniles baseline (can be included instead of using hindcasting baseline).
   :type maxcoraljuv: np.float
   :param nsims: Number of simulations to sample
   :type nsims: int

   :returns: * **reefcondition** (*np.array*) -- Array containing reef condition of size (nsims, nreefs, nyears).
             * **metrics_dict** (*np.array*) -- Structure containing each of the metrics comprising the RCI, each arrays of size (nsims, nreefs, nyears).


.. py:function:: rti_rme(ecol_indicators, rti_intercept)

.. py:function:: rfi_rme(total_cover, intercept1, slope1, intercept2, slope2)

.. py:function:: extract_metrics(results_data, scen_ids, nsims, uncertainty_dict=None)

   Calculates indicator metrics for a set of scenarios in the provided ReefModEngine.jl results_data and
   saves in a summary array of size (nsims, nreefs*nyears), suitable to be saved in the economics dataframe
   format.

   :param result_set: ReefModEngine.jl resultset structure.
   :type result_set: dict
   :param scen_ids: List of scenario IDs to consider (e.g. only sample counterfactual/intervention etc.).
   :type scen_ids: np.array
   :param nsims: Number of simulations to sample
   :type nsims: int
   :param uncertainty_dict: Contains information of which types of uncertainty to sample when processing metrics.
   :type uncertainty_dict: dict

   :returns: **save_metrics** -- Array containing the RCI and each of the metrics comprising the RCI, each arrays of size
             (nsims, nreefs*nyears, nmetrics). The nmetrics dimension indices correspond to:
             0 - RCI
             1 - total_cover
             2 - shelter_volume
             3 - coraljuv_relativecoral
             4 - COTSrel_complementary
             5 - rubble_complementary
   :rtype: np.array


