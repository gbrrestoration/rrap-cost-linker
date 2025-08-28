import parallel_cost_sampling as pc
import multiprocessing as mp
import time

# Filepath to RME runs to process
rme_files_path = "path to RME resultset"

# Number of sims for metrics sampling (default includes ecological and expert uncertainty in RCI calcs)
nsims = 10
ncores = 5 # number of cores to use

start = time.perf_counter()
# Create economics metrics input files, get number of batches needed to complete nsims over ncores
int_keys_fn, nbatches = pc.para_sample_econ(rme_files_path, nsims, ncores=ncores)

end = time.perf_counter()
elapsed_1 = end - start
print(f'Time metrics : {elapsed_1:.6f} seconds')

# Run cost sampling in parallel on ncores
if __name__ == "__main__":
    start = time.perf_counter()
    pool = mp.Pool(ncores)
    result = [pool.apply(pc.calc_costs_para, args=(iter_id, int_keys_fn, nbatches)) for iter_id in range(ncores)]
    end = time.perf_counter()
    elapsed_2 = end - start
    pool.close()
    pool.join()

    print(f'Time cost sampling : {elapsed_2:.6f} seconds')
    start = time.perf_counter()
    # Post-process saved samples to be in single file
    pc.post_process_costs(result, nbatches, nsims)
    end = time.perf_counter()
    elapsed_3 = end - start
    print(f'Time cost processing : {elapsed_3:.6f} seconds')
