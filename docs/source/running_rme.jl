using ReefModEngine
using DataFrames

# Initialize RME (may take a minute or two)
init_rme("path to rme datapackage")

set_option("thread_count", 2)  # Set to use two threads
set_option("use_fixed_seed", 1)  # Turn on use of a fixed seed value
set_option("fixed_seed", 123.0)  # Set the fixed seed value
set_option("initial_set_fixed", 1)  # Fix initial cover, so not randomised at each rep
set_option("recovery_value_enabled", 0)  # Don't save recovery value to save runtime

# Reef indices and IDs
target_reef_ids = ["16-071"]
n_target_reefs = length(target_reef_ids)

run_name = "Test Moore runs"       # Name to associate with this set of runs
start_year = 2007
end_year = 2099
years = collect(start_year:end_year)
n_years = (end_year-start_year) + 1
RCP_scen = "SSP 2.45"  # RCP/SSP scenario to use
reps =  20 # Number of repeats: number of random environmental sequences to run

# Get list of areas for the target reefs
reef_areas_km² = reef_areas(target_reef_ids)

# Define coral outplanting density (per m²)
d_density_m² = 6.0/6 # 6/m2 over all 6 species

# Initialize result store
result_store = ResultStore(start_year, end_year)

gcm = @RME gcmName(1::Cint)::Cstring # Use first climate model

iv_years = collect(2026:2030)
n_corals_per_year = 10000000

reset_rme()  # Reset RME to clear any previous runs

@RME runCreate(run_name::Cstring, start_year::Cint, end_year::Cint, RCP_scen::Cstring, gcm::Cstring, reps::Cint)::Cint

@RME reefSetAddFromIdList("moore_ext_set"::Cstring, target_reef_ids::Ptr{Cstring}, length(target_reef_ids)::Cint)::Cint

for (iv_yr_idx, iv_year) in enumerate(iv_years)
    set_outplant_deployment!("outplant_moore_iv_$(iv_yr_idx)", "moore_ext_set", n_corals_per_year, iv_year, reef_areas_km², fill(d_density_m², 6))
end

# Initialize RME runs as defined above
run_init()
@time @RME runProcess()::Cint

# Collect and store results
concat_results!(result_store, start_year, end_year, reps)
save_result_store("test_results_ext_moore_domain", result_store)
