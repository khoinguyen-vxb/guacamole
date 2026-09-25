from abc import ABC, abstractmethod

class SolverAdapter(ABC):

    @abstractmethod
    async def validate(self, request):
        pass

    @abstractmethod
    async def submit(self, request):
        pass

    @abstractmethod
    async def status(self, job_id):
        pass

    @abstractmethod
    async def collect(self, job_id):
        pass