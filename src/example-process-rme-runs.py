import cost_calculations as cc
import process_RME_data as prd
import time
import math
import multiprocessing as mp

# Filepath to RME runs to process
rme_files_path = "C:\\Users\\rcrocker\\Documents\\Github\\ReefModEngine.jl\\sandbox\\test_results_econ_metrics"
# econ_test_results_eff_study_domain
# Number of sims for metrics sampling (default includes ecological and expert uncertainty in RCI calcs)
nsims = 100
# Create cost datafiles for the intervention run ids in ID_key
ncores = 4
nbatches = math.ceil(nsims/ncores)

# Create metric datafiles for economics modelling and extract filename for intervention key
#start = time.perf_counter()
int_keys_fn = prd.create_economics_metric_files(rme_files_path, nsims, nbatches, ncores=ncores, metrics=[prd.rci])
#end = time.perf_counter()
#elapsed_1 = end - start
#print(f'Time taken: {elapsed_1:.6f} seconds')

def calc_costs_para(it_num, int_keys_fn, n_sims):
    return cc.calculate_costs(int_keys_fn, n_sims, iter_id=it_num)

# calc_costs_para(0, int_keys_fn,  nbatches)
# breakpoint()
# start = time.perf_counter()
if __name__ == "__main__":
    pool = mp.Pool(ncores)
    result = [pool.apply(calc_costs_para, args=(iter_id, int_keys_fn, nbatches)) for iter_id in range(ncores)]
    pool.close()
    pool.join()

# end = time.perf_counter()
# elapsed_2 = end - start
# print(f'Time taken: {elapsed_2:.6f} seconds')
