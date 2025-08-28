import cost_calculations as cc
import process_RME_data as prd

# Filepath to RME runs to process
rme_files_path = "path to RME resultset"

# Number of sims for metrics sampling (default includes ecological and expert uncertainty in RCI calcs)
nsims = 10

# Create metric datafiles for economics modelling and extract filename for intervention key
# nbatches = nsims and ncores = 1 if not using parallelisation
int_keys_fn, filepaths = prd.create_economics_metric_files(rme_files_path, nsims, nsims, ncores=1)

# Create cost datafiles for the intervention run ids in ID_key
cc.calculate_costs(int_keys_fn, nsims)
