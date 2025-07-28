import parallel_cost_sampling as pc
import multiprocessing as mp

# Filepath to RME runs to process
rme_files_path = "C:\\Users\\rcrocker\\Documents\\Github\\ReefModEngine.jl\\sandbox\\test_results_econ_metrics"
# econ_test_results_eff_study_domain
# Number of sims for metrics sampling (default includes ecological and expert uncertainty in RCI calcs)
nsims = 10
ncores = 5 # number of cores to use

# Create economics metrics input files, get number of batches needed to complete nsims over ncores
int_keys_fn, nbatches = pc.para_sample_econ(rme_files_path, nsims, ncores=ncores)

if __name__ == "__main__":
    pool = mp.Pool(ncores)
    result = [pool.apply(pc.calc_costs_para, args=(iter_id, int_keys_fn, nbatches)) for iter_id in range(ncores)]

    pool.close()
    pool.join()

    pc.post_process_costs(result, nbatches, nsims)
