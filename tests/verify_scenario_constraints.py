"""Small solved LPs verifying the renewable adapter; needs a Gurobi license."""
from pathlib import Path
import argparse
import json
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import gurobipy as gp
from scenario_runtime import add_renewable_constraints

SCENARIO = {"preset": "res100", "scope": "all-energy", "target_year": 2050}
OPTIONS = None


class ConstraintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = gp.Env(empty=True)
        cls.env.setParam("OutputFlag", 0)
        cls.env.start()

    @classmethod
    def tearDownClass(cls):
        cls.env.dispose()

    def setUp(self):
        self.model = gp.Model(env=self.env)
        self.ns = {"ucp": self.model, "years": [2045, 2050, 2055], "model_heating": True,
                   "model_transport_and_industry": True, "model_efuel": True,
                   "active_zones_system_df_list": {("HR1", "HR"): "Y", ("SI1", "SI"): "Y"},
                   "generation": {}, "generator_fuel_type": {}}

    def tearDown(self):
        self.model.dispose()

    def generator(self, unit, fuel, year=2050):
        variable = self.model.addVar(name=unit + str(year))
        self.ns["generation"][unit, "HR1", "HR", 1, year] = variable
        self.ns["generator_fuel_type"][unit, "HR1", "HR"] = fuel
        return variable

    def variable(self, dictionary, key):
        variable = self.model.addVar(name=dictionary + str(len(self.ns.get(dictionary, {}))))
        self.ns.setdefault(dictionary, {})[key] = variable
        return variable

    def test_energy_balance_cannot_use_cheap_fossil_or_nuclear(self):
        coal = self.generator("coal", "Coal")
        nuclear = self.generator("nuclear", "Nuclear")
        solar = self.generator("solar", "Solar")
        self.model.addConstr(coal + nuclear + solar >= 1)
        self.model.setObjective(coal + nuclear + 10 * solar)
        add_renewable_constraints(self.ns, SCENARIO)
        self.model.optimize()
        self.assertEqual(self.model.Status, gp.GRB.OPTIMAL)
        self.assertAlmostEqual(solar.X, 1.)
        self.assertAlmostEqual(coal.X + nuclear.X, 0.)

    def test_endpoint_blocks_each_fossil_service_and_unverified_import(self):
        self.generator("solar", "Solar")
        blocked = [self.variable("fuel_industry_hours", ("Gas", "HR1", "HR", 1, 2050)),
                   self.variable("boiler_ind_generation", ("gas", "Gas", "HR1", "HR", 1, 2050)),
                   self.variable("fuel_demand", ("diesel", "HR1", "HR", 1, 2050)),
                   self.variable("ICE_energy_transp_prim", ("diesel", "ICE_car", "HR1", "HR", 1, 2050)),
                   self.variable("generation_H2_steam", ("SMR", "HR1", "HR", 1, 2050)),
                   self.variable("import_outside", ("Electricity", 2050, 1, "HR1", "HR")),
                   self.variable("import_outside_H2", ("H2", 2050, 1, "HR1", "HR"))]
        allowed = self.variable("import_outside", ("CO2", 2050, 1, "HR1", "HR"))
        self.model.addConstr(allowed <= 1)
        self.model.setObjective(sum(blocked) + allowed, gp.GRB.MAXIMIZE)
        add_renewable_constraints(self.ns, SCENARIO)
        self.model.optimize()
        self.assertEqual(self.model.Status, gp.GRB.OPTIMAL)
        self.assertAlmostEqual(sum(v.X for v in blocked), 0.)
        self.assertAlmostEqual(allowed.X, 1.)

    def test_fossil_only_terminal_supply_is_infeasible(self):
        gas = self.generator("gas", "Gas")
        self.model.addConstr(gas >= 1)
        add_renewable_constraints(self.ns, SCENARIO)
        self.model.optimize()
        self.assertEqual(self.model.Status, gp.GRB.INFEASIBLE)

    def test_pre_target_fossil_and_internal_green_trade_remain_possible(self):
        gas = self.generator("gas", "Gas", 2045)
        internal = self.variable("import_zone_system", ("Electricity", 2050, 1, "HR1", "HR", "SI1", "SI"))
        external = self.variable("import_zone_system", ("Electricity", 2050, 1, "HR1", "HR", "OTHER", "OUT"))
        self.model.addConstr(gas <= 1)
        self.model.addConstr(internal <= 1)
        self.model.setObjective(gas + internal + external, gp.GRB.MAXIMIZE)
        add_renewable_constraints(self.ns, SCENARIO)
        self.model.optimize()
        self.assertEqual(self.model.Status, gp.GRB.OPTIMAL)
        self.assertAlmostEqual(gas.X + internal.X, 2.)
        self.assertAlmostEqual(external.X, 0.)

    def test_uncertified_boundary_stock_is_cleared_once(self):
        self.generator("solar", "Solar")
        boundary = self.variable("h2_sto_soc0", ("H2", 2050, "HR1", "HR"))
        later = self.variable("h2_sto_soc0", ("H2", 2055, "HR1", "HR"))
        self.model.addConstr(later <= 1)
        self.model.setObjective(boundary + later, gp.GRB.MAXIMIZE)
        first = add_renewable_constraints(self.ns, SCENARIO)
        second = add_renewable_constraints(self.ns, SCENARIO)
        self.assertIs(first, second)
        self.model.optimize()
        self.assertAlmostEqual(boundary.X, 0.)
        self.assertAlmostEqual(later.X, 1.)

    def test_native_model_variable_indices(self):
        if OPTIONS is None or OPTIONS.model_root is None:
            self.skipTest("Supply --model-root and --bundle for native index integration")
        from run_model_scenario import run
        root, bundle = OPTIONS.model_root.resolve(), OPTIONS.bundle.resolve()
        namespace = run(root, bundle)
        settings = json.loads((bundle / "scenario.json").read_text(encoding="utf-8"))
        previous = Path.cwd()
        old_bytecode = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(root))
        try:
            os.chdir(bundle)
            namespace.update(Myopic=False, partial_perfect_foresight=False,
                             periods=[1, 2], previous_years_list=[], previous_years_set=set())
            namespace["period_sets_by_year"] = {year: {1, 2} for year in namespace["years"]}
            namespace["_periods_for_year"] = lambda year: [1, 2]
            namespace["_years_for_period"] = lambda period: namespace["years"]
            namespace["_period_weight"] = lambda period: 4380.
            namespace["_scenario_execute"]("scripts/reading_prev_and_vars_def_dual_industry_categories1.py", namespace)
            rows = add_renewable_constraints(namespace, settings)
            namespace["ucp"].update()
            self.assertGreater(len(rows), 0)
            report = {"native_variable_indices_verified": True, "terminal_origin_constraints": len(rows),
                      "sample_periods": [1, 2], "years": [int(y) for y in namespace["years"]],
                      "optimization_solved": False}
            (bundle / "native_scenario_adapter_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(report)
        finally:
            if namespace.get("ucp") is not None:
                namespace["ucp"].dispose()
            os.chdir(previous)
            sys.path.pop(0)
            sys.dont_write_bytecode = old_bytecode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--model-root", type=Path)
    parser.add_argument("--bundle", type=Path)
    OPTIONS, remaining = parser.parse_known_args()
    unittest.main(argv=[sys.argv[0], *remaining])
