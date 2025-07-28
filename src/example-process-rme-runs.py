import parallel_cost_sampling as pc
import multiprocessing as mp

# Filepath to RME runs to process
rme_files_path = "filepath to RME resultset"

# Number of sims for metrics sampling (default includes ecological and expert uncertainty in RCI calcs)
nsims = 10
ncores = 5 # number of cores to use

# Create economics metrics input files, get number of batches needed to complete nsims over ncores
int_keys_fn, nbatches = pc.para_sample_econ(rme_files_path, nsims, ncores=ncores)

# Run cost sampling in parallel on ncores
if __name__ == "__main__":
    pool = mp.Pool(ncores)
    result = [pool.apply(pc.calc_costs_para, args=(iter_id, int_keys_fn, nbatches)) for iter_id in range(ncores)]

    pool.close()
    pool.join()

    # Post-process saved samples to be in single file
    pc.post_process_costs(result, nbatches, nsims)
