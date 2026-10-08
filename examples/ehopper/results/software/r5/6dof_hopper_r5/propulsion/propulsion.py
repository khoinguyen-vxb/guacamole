from enum import Enum, auto, unique
from abc import ABC, abstractmethod


class PropulsionType(Enum):
    LIQUID = auto()
    PROPELLER = auto()


class Propulsion(ABC):
    def __init__(self, type: PropulsionType):
        self.type = type

    @abstractmethod
    def get_mass(t):
        pass

    @abstractmethod
    def get_local_cg():
        pass

    @abstractmethod
    def get_thrust_and_moment(t):
        pass
