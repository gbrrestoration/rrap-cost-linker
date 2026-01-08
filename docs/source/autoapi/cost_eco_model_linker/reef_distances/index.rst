cost_eco_model_linker.reef_distances
====================================

.. py:module:: cost_eco_model_linker.reef_distances


Functions
---------

.. autoapisummary::

   cost_eco_model_linker.reef_distances.haversine
   cost_eco_model_linker.reef_distances.find_representative_reefs
   cost_eco_model_linker.reef_distances.find_max_reef_distance


Module Contents
---------------

.. py:function:: haversine(x, y)

   Calculate the great circle distance in kilometers between two points
   on the earth (specified in decimal degrees)



.. py:function:: find_representative_reefs(iv_reef_spatial, regions_data, max_dist=25.0)

   Find clusters of reefs within max_dist of each other. These represent the furthest a ship would travel
   between reefs to implement interventions before going back to port. For reefs in unique clusters, the reef
   furthest from port is selected to represent the maximum travel distance from port, which is used to estimate
   the logistical cost of the intervention.

   :param reef_spatial_data: A dataframe from the RME specified key reef IDs and spatial information (loaded from reefmod_gbr.gpkg).
   :type reef_spatial_data: dataframe
   :param regions_data: A dataframe with key spatial and economics data for each reef in the GBR (loaded from econ_spatial.csv).
   :type regions_data: dataframe
   :param iv_reefs: GBRMPA IDs of all reefs intervened at in the intervention
   :type iv_reefs: np.array(str)
   :param max_dist: Maximum allowable distance between reefs in a cluster.
   :type max_dist: float

   :returns: List of GBRMPA IDs which represent a subset of iv_reefs which give the reefs furthest
             from port for each cluster.
   :rtype: representative_reefs


.. py:function:: find_max_reef_distance(reef_spatial_data, regions_data, iv_reefs, max_dist=25.0)

   Finds the total estimated travel distance from port via the max distance to port from the closest reef cluster
   plus the sum of distances between that cluster and any other clsuters.

   :param iv_reefs: List of reef IDs intervened at for a particular intervention
   :type iv_reefs: list
   :param data_store: Storage dataframe for creating economics metric files
   :type data_store: dataframe


