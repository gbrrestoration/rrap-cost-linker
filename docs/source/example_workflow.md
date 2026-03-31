# Example workflow

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

## Sensitivity analysis

```python
import cost_eco_model_linker as ceml

prod_cost_model = "./models/3.8.0 CA Production Model.xlsx"
deploy_cost_model = "./models/3.8.0 CA Deployment Model.xlsx"

# Number of samples to take (must be power of 2)
N = 2**7

# Samples model and returns an SALib problem specification with results under the
# `cost_model_results` key.
prod_sp = ceml.run_production_model(prod_cost_model, N)
deploy_sp = ceml.run_deployment_model(deploy_cost_model, N)

# Conduct and save sensitivity analysis results
ceml.extract_sa_results(prod_sp, "./figs/prod/")
ceml.extract_sa_results(deploy_sp, "./figs/deploy/")
```

The above will generate a set of figures (for production or deployment costs).

Example PAWN analysis results:

![PAWN SA barplot](./_static/figs/prod/operational_cost_pawn_barplot_SA.png)


## Running models directly

```python
import cost_eco_model_linker as ceml

production_model = "./models/3.8.0 CA Production Model.xlsx"

# Factors not specified by arguments use whatever values are found in the Excel spreadsheet
# Method below returns CAPEX and OPEX (setup costs and operational costs)
costs = ceml.evaluate_production_cost(production_model, num_1yoec=1000000)

print(sum(x))
```


## Questions and Answers

### How are deployment distances determined?

For a given simulation, a set of reefs where interventions occur are determined a priori,
or as part of a simulated dynamic decision making process.

The mean longitude and latitude is determined for a defined set of intervention locations.
From this, the distance to the closest port is determined.

While CEML does not currently support assessment of deployment scenarios that change
deployment locations throughout a simulation, the determined costs should still be
representative/indicative so long as the intervention reefs are confined within a
given area.
