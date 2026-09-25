class SolverRegistry:

    def __init__(self):
        self._solvers = {}

    def register(
        self,
        capability: str,
        backend: str,
        adapter
    ):
        key = (capability, backend)

        self._solvers[key] = adapter

    def get(
        self,
        capability: str,
        backend: str
    ):
        return self._solvers[
            (capability, backend)
        ]