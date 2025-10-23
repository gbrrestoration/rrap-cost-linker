import cost_eco_model_linker as ceml

# Filepath to RME runs to process
rme_files_path = "path to RME results"

# Number of sims for metrics sampling (default includes ecological and expert uncertainty in RCI calcs)
nsims = 10

ceml.evaluate(rme_files_path, nsims, "3.5.5 CA Deployment Model", "3.7.0 CA Production Model", "./")
