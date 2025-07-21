import cost_calculations as cc
import process_RME_data as prd
import math
import multiprocessing as mp
import pandas as pd
import numpy as np

# Filepath to RME runs to process
rme_files_path = "C:\\Users\\rcrocker\\Documents\\Github\\ReefModEngine.jl\\sandbox\\test_results_econ_metrics"
# econ_test_results_eff_study_domain
# Number of sims for metrics sampling (default includes ecological and expert uncertainty in RCI calcs)
nsims = 10
# Create cost datafiles for the intervention run ids in ID_key
ncores = 5
nbatches = math.ceil(nsims/ncores)

# Create metric datafiles for economics modelling and extract filename for intervention key
int_keys_fn = prd.create_economics_metric_files(rme_files_path, nsims, nbatches, ncores=ncores, metrics=[prd.rci])

def calc_costs_para(it_num, int_keys_fn, n_sims):
    return cc.calculate_costs(int_keys_fn, n_sims, iter_id=it_num)

if __name__ == "__main__":
    pool = mp.Pool(ncores)
    result = [pool.apply(calc_costs_para, args=(iter_id, int_keys_fn, nbatches)) for iter_id in range(ncores)]

    pool.close()
    pool.join()

    for iv_id in range(len(result[0])):
        init_cost_df = pd.read_csv(result[0][iv_id])
        sim_cols = ["year", "component"] + ["draw"+str(i) for i in range(1, nsims+1)]

        cost_df = pd.DataFrame(np.zeros((init_cost_df.shape[0],2+nsims)), columns = sim_cols)
        cost_df.loc[:,["year", "component"]] = init_cost_df[["year", "component"]]

        save_fn = result[0][iv_id].split("id")[0][:-6]+".csv"

        for (idx_r, res) in enumerate(result):
            cost_temp = pd.read_csv(res[iv_id])
            cost_df.iloc[:, idx_r*nbatches+2:idx_r*nbatches+2+nbatches] = cost_temp.iloc[:, 2:nbatches+2]

        cost_df.to_csv(save_fn, index=False)
