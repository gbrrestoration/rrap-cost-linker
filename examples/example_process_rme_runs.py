import cost_eco_model_linker as ceml

# Filepath to RME runs to process
rme_files_path = "path to RME results"

# Number of sims for metrics sampling (default includes ecological and expert uncertainty in RCI calcs)
nsims = 10

# Create metric data files for economics modelling and extract filename for intervention key
int_keys_fn, filepaths = ceml.create_economics_metric_files(rme_files_path, nsims)

# Create cost data files for the intervention run ids in ID_key
# Assumes Cost Model spreadsheets are in same directory as this script.
result_paths = ceml.calculate_costs(int_keys_fn, nsims, "3.5.5 CA Deployment Model", "3.7.0 CA Production Model")


ceml.evaluate(rme_files_path, nsims, "3.5.5 CA Deployment Model", "3.7.0 CA Production Model", "./")