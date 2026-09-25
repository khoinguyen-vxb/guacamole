"""
here the diffrent materlails and their properties are stored
they should be accessable for all the difrrent components
this is used to calcuate density,mass,inertia,cg
"""

import math

from CoolProp.CoolProp import PropsSI

from .units import MolarMass, Pressure, SI_Unit, Temperature

# global variables
GAS_CONSTANT = 8314.46261815324
R = GAS_CONSTANT


#
# parent classes
#
class Material_Solid:
    name = "Material_Solid"
    density = SI_Unit(0.0, "kg/m^3")  # kg/m³


class Material_Fluid:
    name = "Material_LiquidVapour"
    density_liquid = SI_Unit(0.0, "kg/m^3")
    density_vapour = SI_Unit(0.0, "kg/m^3")


#
#   keep wet masses resposibility of the propulsion solver
#
# class N20(Material_Fluid):
#     name = "N2O"
#     molar_mass: MolarMass = PropsSI("M", "N2O")  # kg/mol
#
#     @staticmethod
#     def density_liquid(T: Temperature) -> SI_Unit:
#         """Saturated liquid density at temperature T [K]."""
#         return SI_Unit(PropsSI("D", "T", float(T), "Q", 0, "N2O"), "kg/m^3")
#
#     @staticmethod
#     def density_vapour(T: Temperature) -> SI_Unit:
#         """Saturated vapour density at temperature T [K]."""
#         return SI_Unit(PropsSI("D", "T", float(T), "Q", 1, "N2O"), "kg/m^3")
#
#     @staticmethod
#     def saturation_pressure(T: Temperature) -> SI_Unit:
#         """Saturation pressure at temperature T [K]."""
#         return SI_Unit(PropsSI("P", "T", float(T), "Q", 0, "N2O"), "Pa")
#
#     @staticmethod
#     def saturation_temperature(P: Pressure) -> float:
#         """Saturation temperature at pressure P [Pa]. Returns K."""
#         return PropsSI("T", "P", float(P), "Q", 0, "N2O")
#
#     @staticmethod
#     def enthalpy_liquid(T: Temperature) -> float:
#         """Specific enthalpy of saturated liquid at temperature T [K]. Returns J/kg."""
#         return PropsSI("H", "T", float(T), "Q", 0, "N2O")
#
#     @staticmethod
#     def enthalpy_vapour(T: Temperature) -> float:
#         """Specific enthalpy of saturated vapour at temperature T [K]. Returns J/kg."""
#         return PropsSI("H", "T", float(T), "Q", 1, "N2O")
#
#     @staticmethod
#     def viscosity_liquid(T: Temperature) -> float:
#         """Dynamic viscosity of saturated liquid at temperature T [K]. Returns Pa·s."""
#         return PropsSI("V", "T", float(T), "Q", 0, "N2O")
#
#     @staticmethod
#     def specific_heat_vapour(temp: float) -> float:
#         """$C_v = C_p - R$. $C_p$ from 📍Perry. 2-153
#
#         Args:
#             temp: Range $[100, 1500] \\mathrm K$
#         """
#         C1 = 0.29338e5
#         C2 = 0.3236e5
#         C3 = 1.1238e3
#         C4 = 0.2177e5
#         C5 = 479.4
#         return (
#             C1
#             + C2 * (C3 / temp / math.sinh(C3 / temp)) ** 2
#             + C4 * (C5 / temp / math.cosh(C5 / temp)) ** 2
#             - R
#         )
#
#     @staticmethod
#     def specific_heat_liquid(temp: float) -> float:
#         """Heat Capacity Coefficients (Liquid at Constant Pressure [J/kmolK])
#         Adapted from Perry
#
#         Args:
#             temp: Range $[182.3, 200] \\mathrm K$
#         """
#         E1 = 6.7556e4
#         E2 = 5.4373e1
#         E3 = 0
#         E4 = 0
#         E5 = 0
#         return E1 + E2 * temp + E3 * temp**2 + E4 * temp**3 + E5 * temp**4
#
#     @staticmethod
#     def molar_volume_liquid(temp: float) -> float:
#         """📍Perry. 2-97
#
#         Args:
#             temp: Range $[182.3, 309.57] \\mathrm K$
#         """
#         Q1 = 2.781
#         Q2 = 0.27244
#         Q3 = 309.57
#         Q4 = 0.2882
#         return Q2 ** (1 + (1 - temp / Q3) ** Q4) / Q1


class Aluminum(Material_Solid):
    name = "Aluminum"
    density = SI_Unit(2720, "kg/m^3")


class Phenolic(Material_Solid):
    name = "Phenolic"
    density = SI_Unit(1400, "kg/m^3")


class Fiberglass(Material_Solid):
    name = "Fiberglass"
    density = SI_Unit(1800, "kg/m^3")


class Cardboard(Material_Solid):
    name = "Cardboard"
    density = SI_Unit(689, "kg/m^3")


class Steel(Material_Solid):
    name = "Steel"
    density = SI_Unit(7850, "kg/m^3")


class CarbonFiber(Material_Solid):
    name = "Carbon Fiber"
    density = SI_Unit(1600, "kg/m^3")


class Graphite(Material_Solid):
    name = "Graphite"
    density = SI_Unit(1200, "kg/m^3")


# 100%-infill ABS — the HybridFuelGrain effective density is
# self.material.density * self.infill_factor (printed at <100% infill).
class ABS(Material_Solid):
    name = "ABS"
    density = SI_Unit(1036.48, "kg/m^3")


# Tightly-packed nylon ripstop bundle (cloth + suspension lines + deployment
# bag).  Reasonable default for parachute packed-bundle mass; users can
# substitute a measured-density Material_Solid if they have one.
class Nylon(Material_Solid):
    name = "Nylon (packed)"
    density = SI_Unit(300, "kg/m^3")
