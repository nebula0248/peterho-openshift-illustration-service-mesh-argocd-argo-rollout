"""Configuration views must explain actual changes without repeating manifests."""
import unittest

from demo import SCENARIOS, get_state


class IncrementalConfigurationTests(unittest.TestCase):
    def flow(self, name):
        return next(flow for flow in SCENARIOS if flow['id'] == name)

    def test_definitions_are_introduced_once_per_flow(self):
        for flow in SCENARIOS:
            seen = set()
            for step in flow['steps']:
                self.assertTrue(step['config_summary'])
                ids = [item['id'] for item in step['config_items']]
                self.assertEqual(len(ids), len(set(ids)))
                for item in step['config_items']:
                    self.assertTrue(item['actor'])
                    self.assertTrue(item['code'])
                    if item['kind'] == 'reference':
                        self.assertNotIn(item['id'], seen, flow['id'])
                        seen.add(item['id'])

    def test_release_steps_show_deltas_after_the_baseline(self):
        steps = self.flow('delivery')['steps']
        self.assertIn('rollout', [item['id'] for item in steps[0]['config_items']])
        for index in range(2, 13):
            references = [item['id'] for item in steps[index]['config_items'] if item['kind'] == 'reference']
            self.assertEqual(references, ['verify-release'] if index == 4 else [])
        for index, site in [(2, 'a'), (7, 'b')]:
            changes = [item for item in steps[index]['config_items'] if item['kind'] == 'diff']
            self.assertEqual(len(changes), 1)
            self.assertIn(f'overlays/dc-{site}/orders-image.yaml', changes[0]['file'])
            self.assertIn('-  value: registry.example.com/shop/orders:1.0.0', changes[0]['code'])
            self.assertIn('+  value: registry.example.com/shop/orders:2.0.0', changes[0]['code'])

    def test_canary_diffs_show_only_controller_owned_weight_changes(self):
        steps = self.flow('delivery')['steps']
        for index, site, old, new in [(4,'a',0,10), (5,'a',10,50), (9,'b',0,10), (10,'b',10,50)]:
            route = next(item for item in steps[index]['config_items'] if item['id'].startswith('route-'))
            self.assertIn(f'System · Argo Rollouts {site.upper()}', route['actor'])
            self.assertIn(f'live/dc-{site}/', route['file'])
            self.assertIn(f'-    weight: {100-old}', route['code'])
            self.assertIn(f'+    weight: {100-new}', route['code'])
            self.assertIn(f'-    weight: {old}', route['code'])
            self.assertIn(f'+    weight: {new}', route['code'])
            self.assertEqual(get_state('delivery',index)['state'][f'weight_{site}'], new)

    def test_promotion_changes_stable_identity_and_returns_to_stable_route(self):
        steps = self.flow('delivery')['steps']
        for index, site in [(6,'a'),(11,'b')]:
            items = steps[index]['config_items']
            self.assertIn(f'--context=dc-{site}',items[0]['code'])
            selector = next(item for item in items if item['id'].startswith('selector-'))
            self.assertIn(f'+    rollouts-pod-template-hash: <{site}-v2-hash>',selector['code'])
            route = next(item for item in items if item['id'].startswith('route-'))
            self.assertIn('+    weight: 100',route['code'])
            self.assertIn('+    weight: 0',route['code'])
            self.assertEqual(get_state('delivery',index)['state'][f'weight_{site}'],100)

    def test_failover_and_completion_do_not_invent_yaml_edits(self):
        for index in (2,3,4):
            items = self.flow('resilience')['steps'][index]['config_items']
            self.assertEqual([item['kind'] for item in items], ['runtime'])
        self.assertEqual(self.flow('delivery')['steps'][-1]['config_items'], [])

    def test_rollback_diffs_follow_failure_site_and_exposure(self):
        for site in ('a','b'):
            for weight in (10,50):
                flow = get_state('rollback',1,site,weight)['flow']
                self.assertTrue(all(item['kind'] != 'reference' for step in flow['steps'] for item in step['config_items']))
                route = next(item for item in flow['steps'][1]['config_items'] if item['kind'] == 'diff')
                self.assertIn(f'-    weight: {weight}',route['code'])
                self.assertIn('+    weight: 0',route['code'])
                self.assertIn(f'live/dc-{site}/',route['file'])
                revert = flow['steps'][2]['config_items'][0]
                self.assertEqual(revert['actor'], 'Human · reviewed Git revert')
                self.assertIn(f'overlays/dc-{site}/',revert['file'])
                self.assertIn('-  value: registry.example.com/shop/orders:2.0.0',revert['code'])
                self.assertIn('+  value: registry.example.com/shop/orders:1.0.0',revert['code'])
