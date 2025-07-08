Environment setup
=================

Cost-eco-model-linker uses uv to manage and maintain a consistent Python environment.
To initialise the environment, uv needs to be installed and available in the location
where the environment is being initialised.

One option is to install uv directly in VS code using pip:

.. code-block:: console

    $ pip install uv

The virtual environment can then be initialised by syncing the uv.lock file:

.. code-block:: console

    uv sync
