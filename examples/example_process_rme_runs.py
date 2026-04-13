import cost_eco_model_linker as ceml

# Filepath to RME runs to process
rme_files_path = "C:/users/dtan/data/exported_rme_results"

# Number of sims for metrics sampling (default includes ecological and expert uncertainty in RCI calcs)
nsims = 10

ceml.evaluate(
    rme_files_path,
    nsims,
    "3.8.0_deploy_config.csv",
    "3.8.0_prod_config.csv",
    "./",
    coral_only=True
)
