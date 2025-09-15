Environment setup
=================

`Cost-eco-model-linker` uses `uv` to manage and maintain a consistent Python environment.
To initialise the environment, `uv` needs to be installed and available in the location
where the environment is being initialised.

One option is to install `uv` directly in VS code using pip:

.. code-block:: console

    $ pip install uv

Other options for installing `uv`, and information on environment maintainance can be found
at the `uv` - Astral website, `https://docs.astral.sh/uv/getting-started/installation/`_.

The virtual environment can then be initialised by syncing the `uv.lock` file:

.. code-block:: console

    uv sync


Run the commands below to create and activate the project environment

.. code-block:: console

    uv init
    uv venv
    .venv\Scripts\activate  # this command will differ slightly on *nix
