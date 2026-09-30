"""Backend capability only; not vehicle or physical verification.
Run using verify_command with repository='6dof_hopper' and python -B.
"""
import contextlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'


def test_numpy_scipy_analytic_decay():
    import numpy as np
    from scipy.integrate import solve_ivp
    solution = solve_ivp(lambda t, y: -y, (0.0, 1.0), [1.0],
                         rtol=1e-9, atol=1e-11, t_eval=[1.0])
    assert solution.success
    assert solution.y.shape == (1, 1)
    assert np.isfinite(solution.y).all()
    assert abs(float(solution.y[0, 0]) - float(np.exp(-1.0))) < 1e-8


class Reports:
    def __init__(self):
        self.calls = []
        self.errors = []

    def pytest_runtest_logreport(self, report):
        if report.when == 'call':
            self.calls.append(report)
        elif report.failed:
            self.errors.append(report)

    def pytest_collectreport(self, report):
        if report.failed:
            self.errors.append(report)


def main():
    checks = {'pytest_import': False, 'pytest_version_at_least_7': False,
              'exactly_one_test_executed': False,
              'analytic_numpy_scipy_test_passed': False,
              'no_collection_setup_teardown_errors': False,
              'pytest_exit_ok': False}
    details = {'python': sys.executable,
               'scope': 'Dependency and bounded numerical-library capability only; hopper and physical validation unperformed.'}
    try:
        with contextlib.redirect_stdout(sys.stderr):
            import pytest
            checks['pytest_import'] = True
            details['pytest_version'] = pytest.__version__
            checks['pytest_version_at_least_7'] = int(pytest.__version__.split('.')[0]) >= 7
            reports = Reports()
            code = pytest.main([
                str(Path(__file__).resolve()) + '::test_numpy_scipy_analytic_decay',
                '-q', '-p', 'no:cacheprovider', '--noconftest',
                '--override-ini', 'addopts=', '--override-ini', 'testpaths='
            ], plugins=[reports])
            checks['pytest_exit_ok'] = int(code) == 0
            checks['exactly_one_test_executed'] = len(reports.calls) == 1
            checks['analytic_numpy_scipy_test_passed'] = (
                len(reports.calls) == 1 and reports.calls[0].passed)
            checks['no_collection_setup_teardown_errors'] = not reports.errors
            details['test_outcomes'] = [r.outcome for r in reports.calls]
    except Exception as error:
        details['error'] = type(error).__name__ + ': ' + str(error)
    print(json.dumps({'outcome': 'passed' if all(checks.values()) else 'failed',
                      'explanation': json.dumps(details, sort_keys=True),
                      'checks': checks}, allow_nan=False))


if __name__ == '__main__':
    main()
