Generating scenarios in `ReefModEngine.jl`
==========================================

Currently, this repository uses outputs from running a set of scenarios in ReefModEngine.jl
to generate economics modelling input files. An example of running a test set of scenarios
is provided here, but more detail on running scenarios in ReefModEngine.jl
is available at the repository : `<https://open-aims.github.io/ReefModEngine.jl/v1.4.1/getting_started>`_

Example running scenarios in `ReefModEngine.jl`
-----------------------------------------------
In the example here, we want to generate economics output files for a single intervention, outplanting
1000000 corals over Moore reef every year for 5 years (GBRMPA ID `16-071`). After running the scenarios
in `ReefModEngine.jl`, the key information that is used to generate economics input files from a set of
RME runs is the result set folder filepath, in this case the folder named `test_results_ext_moore_domain`.

.. literalinclude:: running_rme.jl
  :language: julia
