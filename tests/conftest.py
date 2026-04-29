from pathlib import Path

import pytest

# Default output directory produced by example_simple_assessment.py.
# Override with --cost-output-dir on the pytest command line.
_DEFAULT_OUTPUT_DIR = (
    Path(__file__).parents[2]
    / "sandbox"
    / "two_region_example"
    / "data"
    / "cost_simple_cost_check_w_LM"
    / "Costs"
)


def pytest_addoption(parser):
    parser.addoption(
        "--cost-output-dir",
        default=None,
        help="Path to cost output directory to validate (default: sandbox example outputs)",
    )
    parser.addoption(
        "--scenario-id",
        default="1",
        help="Scenario ID used in output filenames (default: 1)",
    )
@pytest.fixture
def cost_output_dir(request):
    opt = request.config.getoption("--cost-output-dir")
    path = Path(opt) if opt else _DEFAULT_OUTPUT_DIR
    if not path.exists():
        pytest.skip(f"Cost output directory not found: {path}")
    return path


@pytest.fixture
def scenario_id(request):
    return request.config.getoption("--scenario-id")
