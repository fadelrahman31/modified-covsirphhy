#!/usr/bin/env python
# -*- coding: utf-8 -*-

import numpy as np
from covsirphy.ode.mbase import ModelBase


class SIRV(ModelBase):
    """
    SIRV model.

    Args:
        population (int): total population
        rho (float)
        sigma (float)
    """
    # Model name
    NAME = "SIRV"
    # names of parameters
    PARAMETERS = ["rho", "sigma", "omega"]
    DAY_PARAMETERS = ["1/beta [day]", "1/gamma [day]", "Vaccination rate [day]"]
    # Variable names in (non-dim, dimensional) ODEs
    VAR_DICT = {
        "x": ModelBase.S,
        "y": ModelBase.CI,
        "z": ModelBase.FR
    }
    VARIABLES = list(VAR_DICT.values())
    # Weights of variables in parameter estimation error function
    WEIGHTS = np.array([1, 1, 1, 0])
    # Variables that increases monotonically
    VARS_INCLEASE = [ModelBase.FR]
    # Example set of parameters and initial values
    EXAMPLE = {
        ModelBase.STEP_N: 180,
        ModelBase.N.lower(): 1_000_000,
        ModelBase.PARAM_DICT: {
            "rho": 0.2, "sigma": 0.075, "omega": 0.001
        },
        ModelBase.Y0_DICT: {
            ModelBase.S: 999_000, ModelBase.CI: 1000, ModelBase.FR: 0
        },
    }

    def __init__(self, population, rho, sigma, omega=None):
        # Total population
        self.population = self._ensure_natural_int(
            population, name="population"
        )
        # Non-dim parameters
        self.rho = rho
        self.sigma = sigma
        self.omega = omega
        self.non_param_dict = {"rho": rho, "sigma": sigma, "omega": omega}

    def __call__(self, t, X):
        """
        Return the list of dS/dt (tau-free) etc.

        Args:
            t (int): time steps
            X (numpy.array): values of th model variables

        Returns:
            (np.array)
        """
        n = self.population
        s, i, *_ = X
        dsdt = 0 - self.rho * s * i / n - self.omega
        drdt = self.sigma * i + self.omega
        didt = 0 - dsdt - drdt
        return np.array([dsdt, didt, drdt])

    @classmethod
    def param_range(cls, taufree_df, population, quantiles=(0.1, 0.9)):
        """
        Define the value range of ODE parameters using (X, dX/dt) points.
        In SIR model, X is S, I and R here.

        Args:
            taufree_df (pandas.DataFrame):
                Index
                    reset index
                Columns
                    - t (int): time steps (tau-free)
                    - columns with dimensional variables
            population (int): total population
            quantiles (tuple(int, int)): quantiles to cut, like confidence interval

        Returns:
            dict(str, tuple(float, float)): minimum/maximum values
        """
        df = cls._ensure_dataframe(taufree_df, name="taufree_df", columns=[cls.TS, *cls.VARIABLES])
        df = df.loc[(df[cls.S] > 0) & (df[cls.CI] > 0)]
        n, t, s, i, r = population, df[cls.TS], df[cls.S], df[cls.CI], df[cls.FR]
        # rho = - n * (dS/dt) / S / I
        rho_series = 0 - n * s.diff() / t.diff() / s / i
        # sigma = (dR/dt) / I
        sigma_series = r.diff() / t.diff() / i
        # omega = 0 - (dS/dt + dI/dt + dR/dt)
        omega_series = (n - s + i + r).diff() / t.diff()
        # Calculate quantile
        _dict = {
            k: tuple(v.quantile(quantiles).clip(0, 1))
            for (k, v) in zip(["rho", "sigma","omega"], [rho_series, sigma_series, omega_series])
        }
        return _dict

    @classmethod
    def specialize(cls, data_df, population):
        """
        Specialize the dataset for this model.

        Args:
            data_df (pandas.DataFrame):
                Index
                    reset index
                Columns
                    - Confirmed (int): the number of confirmed cases
                    - Infected (int): the number of currently infected cases
                    - Fatal (int): the number of fatal cases
                    - Recovered (int): the number of recovered cases
                    - any columns
            population (int): total population in the place

        Returns:
            (pandas.DataFrame):
                    Index
                        reset index
                    Columns
                        - any columns @data_df has
                        - Susceptible (int): the number of susceptible cases
                        - Fatal or Recovered (int): total number of fatal/recovered cases
        """
        df = cls._ensure_dataframe(
            data_df, name="data_df", columns=cls.VALUE_COLUMNS)
        # Calculate dimensional variables
        df[cls.S] = population - df[cls.C]
        df[cls.FR] = df[cls.F] + df[cls.R]
        return df

    @classmethod
    def restore(cls, specialized_df):
        """
        Restore Confirmed/Infected/Recovered/Fatal.
         using a dataframe with the variables of the model.

        Args:
            specialized_df (pandas.DataFrame): dataframe with the variables

                Index
                    reset index
                Columns
                    - Susceptible (int): the number of susceptible cases
                    - Infected (int): the number of currently infected cases
                    - Fatal or Recovered (int): the number of fatal/recovered cases
                    - any columns

        Returns:
            (pandas.DataFrame):
                Index
                    reset index
                Columns
                    - Confirmed (int): the number of confirmed cases
                    - Infected (int): the number of currently infected cases
                    - Fatal (int): the number of fatal cases
                    - Recovered (int): the number of recovered cases
                    - the other columns @specialzed_df has
        """
        df = specialized_df.copy()
        other_cols = list(set(df.columns) - set(cls.VALUE_COLUMNS))
        df[cls.C] = df[cls.CI] + df[cls.FR]
        df[cls.F] = 0
        df[cls.R] = df[cls.FR]
        return df.loc[:, [*cls.VALUE_COLUMNS, *other_cols]]

    def calc_r0(self):
        """
        Calculate (basic) reproduction number.

        Returns:
            float
        """
        try:
            rt = self.rho / self.sigma
        except ZeroDivisionError:
            return None
        return round(rt, 2)

    def calc_days_dict(self, tau):
        """
        Calculate 1/beta [day] etc.

        Args:
            param tau (int): tau value [min]

        Returns:
            dict[str, int]
        """
        try:
            return {
                "1/beta [day]": int(tau / 24 / 60 / self.rho),
                "1/gamma [day]": int(tau / 24 / 60 / self.sigma),
                "Vaccination rate [day]": int(self.omega)
            }
        except ZeroDivisionError:
            return {p: None for p in self.DAY_PARAMETERS}
