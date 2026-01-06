import os
from os.path import join as path_join

from collections import OrderedDict
from dataclasses import dataclass

RESULT_DIRS = OrderedDict(
    {
        "cost_dir": "cost_outputs",
        "econ_dir": "econ_outputs",
        "intervention_keys_dir": "intervention_keys",
    }
)


# Create immutable instances
@dataclass(frozen=True)
class OutputStores:
    cost_dir: str
    econ_dir: str
    intervention_keys_dir: str


def setup_dirs(base_dir) -> OutputStores:
    """
    Prep directories to store outputs at user-defined location.
    """
    # Create output directories (at current location by default)
    output_paths = []
    for d in RESULT_DIRS.values():
        output_paths.append(path_join(base_dir, d))
        os.makedirs(path_join(base_dir, d), exist_ok=True)

    stores = OutputStores(*output_paths)

    return stores
