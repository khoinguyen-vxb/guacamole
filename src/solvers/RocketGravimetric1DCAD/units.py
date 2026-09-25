SI_UNITS = {
    "kg/m^3",
    "m^3",
    "g",
    "K", # kelvin
    "s",
    "m",
    "kg/mol",
    "Pa",
    "m/s",
    "N",
    "deg", # scary to have deg and radians
    "rad",
    "nondim", # non dimentional, for like coefficents
    "%/100" # decimal percentage
}

class SI_Unit:
    def __init__(self, value, units):
        if units not in SI_UNITS:
            raise ValueError(f"Unknown unit '{units}'. Valid units: {SI_UNITS}")
        self.value = value
        self.units = units
        self.print = f"{self.value} {self.units}"

    # default behaviour if:
    # aluminium.density is accessed
    # where density is a SI_Unit class
    # so:
    # aluminum.density -> 1.0
    def __repr__(self):
        return self.value

    # this is some magic claude gave me,
    # apparently this will trick python
    # to treat SI_UNIT objects as a float
    # crazy
    def __float__(self):
        return float(self.value)
    def __int__(self):
        return int(self.value)

    # arithmetic — always return plain float so results compose naturally
    def __mul__(self, other):   return float(self) * float(other)
    def __rmul__(self, other):  return float(other) * float(self)
    def __truediv__(self, other): return float(self) / float(other)
    def __rtruediv__(self, other): return float(other) / float(self)
    def __floordiv__(self, other): return float(self) // float(other)
    def __add__(self, other):   return float(self) + float(other)
    def __radd__(self, other):  return float(other) + float(self)
    def __sub__(self, other):   return float(self) - float(other)
    def __rsub__(self, other):  return float(other) - float(self)
    def __pow__(self, exp):     return float(self) ** float(exp)
    def __neg__(self):          return -float(self)
    def __abs__(self):          return abs(float(self))

    # comparisons
    def __lt__(self, other): return float(self) < float(other)
    def __le__(self, other): return float(self) <= float(other)
    def __gt__(self, other): return float(self) > float(other)
    def __ge__(self, other): return float(self) >= float(other)
    def __eq__(self, other): return float(self) == float(other)
    def __ne__(self, other): return float(self) != float(other)


# super() is confusing,
# but basically, it uses
# the SI_Unit's __init__ instead,
# but we force it to use 'm'
class Meters(SI_Unit):
    def __init__(self, value):
        super().__init__(value, "m")

    def __repr__(self):
        return self.value

class Time(SI_Unit):
    def __init__(self, value):
        super().__init__(value, "s")

    def __repr__(self):
        return self.value

class Volume(SI_Unit):
    def __init__(self, value):
        super().__init__(value, "m^3")

    def __repr__(self):
        return self.value

class Temperature(SI_Unit):
    def __init__(self, value):
        super().__init__(value, "K")

    def __repr__(self):
        return self.value

class Degrees(SI_Unit):
    def __init__(self, value):
        super().__init__(value, "deg")

    def __repr__(self):
        return self.value

class Radians(SI_Unit):
    def __init__(self, value):
        super().__init__(value, "rad")

    def __repr__(self):
        return self.value

class Mass(SI_Unit):
    def __init__(self, value):
        super().__init__(value, "g")

    def __repr__(self):
        return self.value

class Pressure(SI_Unit):
    def __init__(self, value):
        super().__init__(value, "Pa")

    def __repr__(self):
        return self.value

class Velocity(SI_Unit):
    def __init__(self, value):
        super().__init__(value, "m/s")

    def __repr__(self):
        return self.value

class Force(SI_Unit):
    def __init__(self, value):
        super().__init__(value, "N")

    def __repr__(self):
        return self.value

class NonDimensional(SI_Unit):
    def __init__(self, value):
        super().__init__(value, "nondim")

    def __repr__(self):
        return self.value

class Percent(SI_Unit):
    def __init__(self, value):
        super().__init__(value, "%")

    def __repr__(self):
        return self.value

class DecimalPercent(SI_Unit):
    '''
        percent but between 0 and 1.
        decimal percentage
    '''
    def __init__(self, value):
        super().__init__(value, "%/100")

    def __repr__(self):
        return self.value

class Density(SI_Unit):
    def __init__(self, value):
        super().__init__(value, "kg/m^3")

    def __repr__(self):
        return self.value

class MolarMass(SI_Unit):
    def __init__(self, value):
        super().__init__(value, "kg/mol")

    def __repr__(self):
        return self.value