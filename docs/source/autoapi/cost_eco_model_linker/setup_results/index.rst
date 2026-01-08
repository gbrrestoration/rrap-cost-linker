cost_eco_model_linker.setup_results
===================================

.. py:module:: cost_eco_model_linker.setup_results


Attributes
----------

.. autoapisummary::

   cost_eco_model_linker.setup_results.RESULT_DIRS


Classes
-------

.. autoapisummary::

   cost_eco_model_linker.setup_results.OutputStores


Functions
---------

.. autoapisummary::

   cost_eco_model_linker.setup_results.setup_dirs


Module Contents
---------------

.. py:data:: RESULT_DIRS

.. py:class:: OutputStores

   .. py:attribute:: cost_dir
      :type:  str


   .. py:attribute:: econ_dir
      :type:  str


   .. py:attribute:: intervention_keys_dir
      :type:  str


.. py:function:: setup_dirs(base_dir) -> OutputStores

   Create output directories at specified location.

   :param base_dir: Base directory for all output folders.
   :type base_dir: str

   :returns: Named collection of output directory paths.
   :rtype: OutputStores


