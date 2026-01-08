Example workflow
================

```python
import cost_eco_model_linker as ceml

# Filepath to RME runs to process
rme_files_path = "./data/eco_linker_example"
deployment_model = "./3.5.5 CA Deployment Model"
production_model = "./3.7.0 CA Production Model"
output_path = "./results"
unc_config = ceml.default_uncertainty_dict()

# Change the entries in `unc_config` if needed
# unc_config["rti_uncert"] = 0

# Number of sims for metrics sampling (default includes ecological and expert uncertainty in RCI calcs)
nsims = 10

ceml.evaluate(
    rme_files_path,
    nsims,
    deployment_model,
    production_model,
    output_path,
    uncertainty_dict=unc_config,
)
```

For parallel runs:

```python
nsims = 10
ncores = 4

if __name__ == "__main__":
    ceml.parallel_evaluate(
        rme_files_path,
        nsims,
        ncores,
        deployment_model,
        production_model,
        output_path,
        uncertainty_dict=unc_config,
    )
```
