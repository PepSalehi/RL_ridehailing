import numpy as np
import pandas as pd
from lib.Constants import (
    ZONE_IDS,
    DEMAND_UPDATE_INTERVAL,
    POLICY_UPDATE_INTERVAL,
    MIN_DEMAND,
    MAX_BONUS
)
from pathlib import Path


class Operator:
    """
    Represents the actions of the company operating the ride-share vehicles.
    """

    def __init__(
            self,
            report,
            bonus_policy,
            bonus,
            surge_multiplier,
            budget,
            which_day_numerical=2,
            name="Uber",

    ):
        """
        Creates an operator instance.
        @param report: (df)
        @param which_day_numerical: (int)
        @param name: (str) name of operator
        @param BONUS: (float)
        @param SURGE_MULTIPLIER: (float)
        """
        self.name = name

        parent_path = Path(__file__).parent
        self.demand_fare_stats_prior = pd.read_csv(
            parent_path / "../Data/stats_over_all_days.csv"
        )

        self.demand_fare_stats_of_the_day = pd.read_csv(
            parent_path / "../Data/Daily_stats/stats_for_day_{}.csv".format(which_day_numerical)
        )

        self.live_data = None
        self.revenues = []
        # these should be probably enums, and accessed via functions
        self.SHOULD_SURGE = True
        self.SHOULD_BONUS = False
        self.SHOULD_LIE_DEMAND = False
        self.SURGE_MULTIPLIER = surge_multiplier
        self.BONUS = bonus
        self.BONUS_POLICY = bonus_policy
        self.budget = budget

        self.report = report

    @staticmethod
    def random_bonus_function(ratio):
        if ratio >= 1.2:
            return np.around(np.random.uniform(0, MAX_BONUS), decimals=1)
        else:
            return 0

    def return_bonus_value(self, ratio):
        if self.BONUS_POLICY == "random":
            return self.random_bonus_function(ratio)
        if self.BONUS_POLICY == "const":
            return 5


    @staticmethod
    def surge_step_function(ratio):
        """
        Calculates the surge charge based on an assumed step-wise function
        0.9-1 : 1.2
        1-1.2 : 1.5
        1.2-2: 2
        >2: 3
        @param ratio: (float)
        @return: the surge charge according to the function.
        """
        if ratio < 0.9:
            return 1
        if 1 >= ratio >= 0.9:
            return 1.1
        if 1.2 >= ratio > 1:
            return 1.2
        # if 2 > ratio > 1.2:
        #     return 1.5
        else:
            return 1.5

    def true_zonal_info_over_t(self, t):
        """
        TODO: modify for 15 min
        Returns the correct zone demand.
        @param t: time
        @return: (df) zonal demand over t
        """
        # The below does not fill missing time periods per zone, i.e., the length is not fixed s
        df = self.demand_fare_stats_of_the_day[self.demand_fare_stats_of_the_day["time_of_day_index_15m"] == t]
        df = df.assign(surge=1)
        df = df.assign(bonus=0)
        df = df.assign(match_prob=1)
        # df = df.assign(match_prob=df['total_pickup']/60)  # pax/min just the default
        # For professional drivers
        # if self.report is not None:
        #     # get the avg # of drivers per zone per price
        #     df = pd.merge(df, self.report, left_on="Origin", right_on="zone_id")
        #
        self.live_data = df
        return df

    def false_zonal_info_over_t(self, t):
        """
        Calculates the false zonal info over t
        @param t
        @return: (df) false zonal info
        """
        False_mult = 3
        zone_ids = np.loadtxt("outputs/zones_los_less_50_f_2500.csv")
        df = self.demand_fare_stats_of_the_day.query("Hour == {hour}".format(hour=t))
        #
        df.loc[df["Origin"].isin(zone_ids), "total_pickup"] = (
                df[df["Origin"].isin(zone_ids)]["total_pickup"] * False_mult
        )
        df.loc[~df["Origin"].isin(zone_ids), "total_pickup"] = (
                df[~df["Origin"].isin(zone_ids)]["total_pickup"] / False_mult
        )
        df = df.assign(surge=1)
        df = df.assign(bonus=0)
        df = df.assign(match_prob=df["total_pickup"] / 60)  # pax/min just the default
        #        df = df.assign(match_prob=df['total_pickup']/df.total_pickup.sum())  # pax/min just the default

        self.live_data_false = df
        return df

    def update_zonal_info(self, t):
        """
        Updates the zonal information if it's a new demand update interval.
        @param t: current time
        """
        if t % DEMAND_UPDATE_INTERVAL == 0:
            self.get_zonal_info(t)

    def zonal_info_for_veh(self, true_demand):
        """
        Gets the zonal info for vehicles.
        @param true_demand: (bool)
        @return: (df)
        """
        if true_demand:
            return self.live_data
        else:
            return self.live_data_false

    def get_zonal_info(self, t):
        """

        @param t:
        @return:
        """
        hour = int(np.floor(t / 3600))
        fifteen_min = int(np.floor(t / 900))
        self.true_zonal_info_over_t(fifteen_min)
        # self.false_zonal_info_over_t(hour)
        assert self.live_data is not None
        return self.live_data

    def update_zone_policy(self, t, zones, WARMUP_PHASE):
        """
        TODO this is doing two things: surge and bonus. Should be disentangled.

        This is meant to be called with the main simulation.
        It automatically sets pricing policies for each zone.
        e.g., surge pricing
        @param t:
        @param zones:
        @param WARMUP_PHASE:
        @return:
        """
        if t % POLICY_UPDATE_INTERVAL == 0:
            budget_left = False
            if self.budget > 0 :
                budget_left = True
            for z in zones:
                ratio = len(z.demand) / (
                        len(z.idle_vehicles) + len(z.incoming_vehicles) + 1
                )
                if len(z.demand) > MIN_DEMAND:
                    m = self.surge_step_function(ratio)
                    if not WARMUP_PHASE :
                        z.set_surge_multiplier(m)
                        if m > 1:
                            z.num_surge += 1
                    if budget_left:
                        bonus = self.return_bonus_value(ratio)
                        if not WARMUP_PHASE :
                            z.set_bonus(bonus)
                            print("bonus of ", bonus, " for zone ", z.id)

                else:
                    z.set_surge_multiplier(1)  # resets surge
                    z.set_bonus(0)  # reset bonus
                if not budget_left:
                    z.bonus = 0



    def set_surge_multipliers_for_zones(self, t, zones, target_zone_ids, surge):
        """
        self.zones, coming from model. NOT USED!
        @param t:
        @param zones:
        @param target_zone_ids:
        @param surge:
        @return:
        """
        df = self.get_zonal_info(t)

        for zid in target_zone_ids:
            df.loc[df["Origin"] == zid, "surge"] = surge
            for zone in zones:
                if zone.id == zid:
                    zone.surge = surge

    def set_bonus_for_zones(self, t, zones, target_zone_ids, bonus):
        """
        Sets bonus for the zones
        self.zones, coming from model
        @param t: time
        @param zones: list of zones
        @param target_zone_ids: list of target zone ids (int)
        @param bonus: (float)
        """
        df = self.get_zonal_info(t)

        for zid in target_zone_ids:
            df.loc[df["Origin"] == zid, "bonus"] = bonus
            for zone in zones:
                if zone.id == zid:
                    zone.bonus = bonus

    # def disseminate_zonal_demand_info(self, t, tell_truth=True):
    #     """
    #     Drivers will use this function to access the demand data. 
    #     #TODO this can be potentially updated to include supply as well. An Uber driver told me that he would switch to pax mode
    #     # and see how many cars were around, to get a sense of what would be the odds of getting a match  
    #     """

    #     if tell_truth:
    #         self.true_zonal_info(t)

    def expected_fare_total_demand_per_zone_over_days(self, t):
        """
        A professional driver will query this one time per (hour) to use as prior
        @param t: time
        @return: (df) demand fare prior dataframe for the given time
        """
        df = self.demand_fare_stats_prior.query("time_of_day_index_15m == {t_15}".format(t_15=t))
        return df
