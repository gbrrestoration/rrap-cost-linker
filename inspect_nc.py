import netCDF4 as nc
try:
    ds = nc.Dataset('C:/users/dtan/data/exported_rme_results/results.nc')
    print(f"timesteps: {len(ds.variables['timesteps'])}")
    print(f"locations: {len(ds.variables['locations'])}")
except Exception as e:
    print(f"Error: {e}")
