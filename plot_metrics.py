import pandas as pd
import matplotlib.pyplot as plt
import os
import numpy as np
def load_and_aggregate(pattern):
    files = glob.glob(pattern)
    if not files:
        return None

    filepath = files[0]
    df = pd.read_parquet(filepath)

    sim_cols = [c for c in df.columns if c.startswith('sim_')]

    if np.any(df[sim_cols] > 1.0):
        print("Error")
    mean_across_sims = df[sim_cols].mean(axis=1).values
    reshaped = mean_across_sims.reshape(NUM_LOCATIONS, NUM_TIMESTEPS)
    return np.mean(reshaped, axis=0)

metric_patterns = {
    'RCI_3 (Intervention)': 'econ_outputs/*intervention*raw_reefcond*.parq',
    'RCI_3 (Counterfactual)': 'econ_outputs/*counterfactual*raw_reefcond*.parq',
    'RFI (Intervention)': 'econ_outputs/*intervention*rfi.parq',
    'RFI (Counterfactual)': 'econ_outputs/*counterfactual*rfi.parq'
}

fig, ax1 = plt.subplots(figsize=(12, 7))
ax2 = ax1.twinx()

for label, pattern in metric_patterns.items():
    print(pattern)
    data = load_and_aggregate(pattern)
    print(data)
    if data is not None:
        if 'RCI' in label:
            ax1.plot(range(NUM_TIMESTEPS), data, label=label, 
                     marker='o', linestyle='--' if 'Counterfactual' in label else '-')
        else:
            ax2.plot(range(NUM_TIMESTEPS), data, label=label, 
                     linestyle=':' if 'Counterfactual' in label else '-.', alpha=0.7)
    else:
        print(f"Warning: No files found for pattern {pattern}")

ax1.set_xlabel('Year')
ax1.set_ylabel('Mean RCI Value (Condition)', color='blue')
ax1.set_ylim(0, 1.0) # Ensure we verify the [0, 1] range
ax1.tick_params(axis='y', labelcolor='blue')

ax2.set_ylabel('Mean RFI Value (Biomass kg/km2)', color='green')
ax2.tick_params(axis='y', labelcolor='green')

plt.title('Verification of Metrics (Coral-Only Mode)')
fig.tight_layout()

lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', bbox_to_anchor=(1.15, 1))

plt.grid(True, which='both', linestyle='--', alpha=0.5)
plt.savefig('metrics_verification.png', bbox_inches='tight')
print("Verification plot saved to metrics_verification.png")
