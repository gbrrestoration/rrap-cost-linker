import pandas as pd
import numpy as np
import os

NUM_TIMESTEPS = 78
NUM_LOCATIONS = 3806

def load_data(filepath):
    df = pd.read_parquet(filepath)
    sim_cols = [c for c in df.columns if c.startswith('sim_')]
    mean_across_sims = df[sim_cols].mean(axis=1).values
    return mean_across_sims.reshape(NUM_LOCATIONS, NUM_TIMESTEPS).mean(axis=0)

rci_path = 'econ_outputs/ID1_intervention_uncertainty_ecol1_indicator1_var_rci.parq'
rci_3_path = 'econ_outputs/ID1_intervention_uncertainty_ecol1_indicator1_var_rci_3.parq'

if os.path.exists(rci_path) and os.path.exists(rci_3_path):
    rci_data = load_data(rci_path)
    rci_3_data = load_data(rci_3_path)
    
    print(f"{'Year':<6} | {'RCI (Std)':<15} | {'RCI_3 (Coral)':<15} | {'Difference':<10}")
    print("-" * 55)
    
    for yr in [0, 10, 25, 50, 77]:
        diff = rci_3_data[yr] - rci_data[yr]
        print(f"{yr:<6} | {rci_data[yr]:<15.4f} | {rci_3_data[yr]:<15.4f} | {diff:<10.4f}")
    
    avg_diff = np.mean(rci_3_data - rci_data)
    print("-" * 55)
    print(f"Average difference across all years: {avg_diff:.4f}")
else:
    print("Files not found for quantitative check.")
