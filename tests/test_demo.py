"""Tests for the educational model's important architecture guarantees."""
import unittest

from demo import CONFIGS, SCENARIOS, SOURCES, get_state, rollback_scenario


class ArchitectureSimulationTests(unittest.TestCase):
    def test_request_journey_never_introduces_a_release(self):
        initial = get_state("traffic", 0)["state"]
        for index in range(4):
            self.assertEqual(get_state("traffic", index)["state"], initial)
        self.assertEqual(initial["global_v2"], 0)
        self.assertEqual(initial["rollout_a"], "Healthy · v1")
        self.assertEqual(initial["rollout_b"], "Healthy · v1")

    def test_both_primaries_discover_remote_apis(self):
        discovery = get_state("resilience", 1)
        self.assertEqual(set(discovery["active_edges"]), {"discovery-a", "discovery-b"})
        self.assertEqual(set(discovery["active_nodes"]), {"a-istiod", "b-api", "b-istiod", "a-api"})
        commands = CONFIGS["discovery"]["code"]
        self.assertIn("--context=dc-a --name=dc-a", commands)
        self.assertIn("--context=dc-b --name=dc-b", commands)

    def test_staged_release_does_not_promote_b_with_a(self):
        expected = [(0,0,0), (0,0,0), (0,0,0), (0,0,0), (10,0,5),
                    (50,0,25), (100,0,50), (100,0,50), (100,0,50),
                    (100,10,55), (100,50,75), (100,100,100), (100,100,100)]
        for index, values in enumerate(expected):
            state = get_state("delivery", index)["state"]
            self.assertEqual((state["weight_a"], state["weight_b"], state["global_v2"]), values)

    def test_only_the_releasing_site_is_highlighted(self):
        for index in range(1, 7):
            frame = get_state("delivery", index)
            self.assertFalse(any(node.startswith("b-") for node in frame["active_nodes"]))
            self.assertFalse(any(edge.startswith("b-") or edge == "git-b" for edge in frame["active_edges"]))
            self.assertEqual(frame["state"]["sync_b"], "Synced")
        for index in range(7, 12):
            frame = get_state("delivery", index)
            self.assertFalse(any(node.startswith("a-") for node in frame["active_nodes"]))
            self.assertEqual(frame["state"]["weight_a"], 100)
        for index in (0, 12):
            self.assertEqual(get_state("delivery", index)["active_edges"], [])
            self.assertEqual(get_state("delivery", index)["active_nodes"], [])

    def test_git_approval_merge_and_sync_are_separate_actions(self):
        approval = get_state("delivery", 1)
        self.assertEqual(approval["state"]["revision"], "v1 · both sites")
        self.assertEqual(approval["active_edges"], [])
        merged = get_state("delivery", 2)
        self.assertEqual(merged["active_edges"], ["pipeline-git"])
        self.assertEqual(merged["state"]["sync_a"], "OutOfSync")
        synced = get_state("delivery", 3)
        self.assertEqual(synced["state"]["sync_a"], "Synced")
        self.assertIn("git-a", synced["active_edges"])
        promoted = get_state("delivery", 6)
        self.assertEqual(promoted["state"]["sync_b"], "Synced")
        self.assertEqual(promoted["state"]["revision"], "v2 → DC-A")
        self.assertEqual(get_state("delivery", 7)["state"]["sync_b"], "OutOfSync")

    def test_sync_is_distinct_from_rollout_health(self):
        preparing = get_state("delivery", 3)["state"]
        self.assertEqual(preparing["sync_a"], "Synced")
        self.assertNotIn("Healthy", preparing["rollout_a"])

    def test_routing_changes_reach_the_local_caller_through_istiod(self):
        for site, stages in [('a', (4, 5, 6)), ('b', (9, 10, 11))]:
            for index in stages:
                frame = get_state('delivery', index)
                self.assertIn(f'{site}-istiod', frame['active_nodes'])
                self.assertIn(f'{site}-frontend', frame['active_nodes'])
                self.assertIn(f'{site}-route-weights', frame['active_edges'])
                self.assertIn(f'{site}-xds-client', frame['active_edges'])
                self.assertNotIn(f'{site}-rollout', frame['active_edges'])

    def test_rollback_preserves_exposure_and_the_other_sites_release(self):
        for site in ('a', 'b'):
            peer = 'b' if site == 'a' else 'a'
            peer_weight = 0 if site == 'a' else 100
            for weight in (10, 50):
                before = get_state('rollback', 0, site, weight)
                self.assertEqual(before['state'][f'weight_{site}'], weight)
                self.assertEqual(before['state']['release_fault_site'], site)
                self.assertIn('virtualservice' if weight == 10 else 'live-50', before['flow']['steps'][0]['configs'])
                for index in range(3):
                    frame = get_state('rollback', index, site, weight)
                    self.assertEqual(frame['state'][f'weight_{peer}'], peer_weight)
                    self.assertFalse(any(node.startswith(peer+'-') for node in frame['active_nodes']))
                    self.assertEqual(frame['state']['site_a'], 50)
                    self.assertEqual(frame['rollback'], {'site': site, 'weight': weight})
                    if index > 0:
                        self.assertEqual(frame['state'][f'weight_{site}'], 0)
                self.assertEqual(get_state('rollback', 1, site, weight)['state']['revision'], before['state']['revision'])
                self.assertEqual(get_state('rollback', 2, site, weight)['state'][f'rollout_{site}'], 'Healthy · v1')

    def test_invalid_failure_context_is_rejected(self):
        for site, weight in [('c', 10), ('a', 0), ('b', 100), ('a', -10)]:
            with self.assertRaises(ValueError):
                get_state('rollback', 0, site, weight)

    def test_abort_restores_traffic_but_does_not_revert_git(self):
        before = get_state("rollback", 0)["state"]
        aborted = get_state("rollback", 1)["state"]
        self.assertEqual(before["weight_a"], 10)
        self.assertEqual(aborted["weight_a"], 0)
        self.assertEqual(aborted["weight_b"], 0)
        self.assertEqual(aborted["revision"], before["revision"])
        self.assertIn("Aborted", aborted["rollout_a"])
        reverted = get_state("rollback", 2)["state"]
        self.assertIn("reverted", reverted["revision"])
        self.assertEqual(reverted["rollout_a"], "Healthy · v1")

    def test_site_failure_has_a_detection_window(self):
        detecting = get_state("resilience", 5)["state"]
        self.assertTrue(detecting["failed_a"])
        self.assertEqual(detecting["site_a"], 50)
        shifted = get_state("resilience", 6)["state"]
        self.assertEqual(shifted["site_b"], 100)
        self.assertEqual(shifted["healthy_clusters"], 1)
        self.assertEqual(shifted["sync_b"], "Synced")

    def test_service_failure_is_not_a_site_failure(self):
        state = get_state("resilience", 3)["state"]
        self.assertTrue(state["catalog_fault"])
        self.assertFalse(state["failed_a"])
        self.assertEqual(state["healthy_clusters"], 2)
        self.assertEqual(state["site_a"], 50)

    def test_local_first_failover_and_failback_keep_the_same_release(self):
        self.assertEqual(get_state("resilience", 0)["active_edges"], ["a-catalog", "b-catalog"])
        self.assertEqual(get_state("resilience", 3)["active_edges"], ["cross-ab", "b-eastwest-catalog"])
        self.assertEqual(get_state("resilience", 4)["active_edges"], ["a-catalog", "b-catalog"])
        for index in range(8):
            state = get_state("resilience", index)["state"]
            self.assertEqual((state["weight_a"], state["weight_b"]), (0, 0))
            self.assertEqual(state["revision"], "v1 · both sites")

    def test_direct_step_selection_and_replays_are_isolated(self):
        baseline = get_state("delivery", 0)
        get_state("delivery", 7)
        get_state("resilience", 6)
        get_state("rollback", 0)
        self.assertEqual(get_state("delivery", 0), baseline)
        edited = get_state("delivery", 0)
        edited["state"]["weight_a"] = 99
        self.assertEqual(get_state("delivery", 0), baseline)

    def test_recovery_restores_both_sites(self):
        state = get_state("resilience", 7)["state"]
        self.assertFalse(state["failed_a"])
        self.assertEqual(state["healthy_clusters"], 2)
        self.assertEqual((state["site_a"], state["site_b"]), (50, 50))

    def test_all_steps_have_valid_config_and_references(self):
        for scenario in SCENARIOS + [rollback_scenario(site, weight) for site in ('a', 'b') for weight in (10, 50)]:
            for index, step in enumerate(scenario["steps"]):
                with self.subTest(scenario=scenario["id"], step=index):
                    self.assertGreater(len(step["configs"]), 1)
                    self.assertEqual(len(step["configs"]), len(set(step["configs"])))
                    self.assertTrue(all(key in CONFIGS for key in step["configs"]))
                    self.assertTrue(step["sources"])
                    self.assertTrue(all(source in SOURCES for source in step["sources"]))
                    state = get_state(scenario["id"], index)["state"]
                    self.assertEqual(state["site_a"] + state["site_b"], 100)
                    self.assertTrue(0 <= state["global_v2"] <= 100)

    def test_invalid_steps_do_not_silently_wrap(self):
        for scenario, step in [("missing", 0), ("delivery", -1), ("delivery", 13), ("resilience", 5000)]:
            with self.subTest(scenario=scenario, step=step), self.assertRaises(ValueError):
                get_state(scenario, step)


if __name__ == "__main__":
    unittest.main()
