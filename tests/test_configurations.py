"""Validate the teaching manifests and site-isolation release contract."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from configurations import CONFIGS
from demo import SCENARIOS, rollback_scenario

try:
    import yaml
except ImportError:
    yaml = None


class PipelineExampleTests(unittest.TestCase):
    image = 'registry.example.com/shop/orders@sha256:' + 'a' * 64

    def run_script(self, site, status=None):
        rollout = {'metadata': {'generation': 7},
                   'spec': {'template': {'spec': {'containers': [{'image': self.image}]}}},
                   'status': status or {'phase': 'Healthy', 'observedGeneration': '7',
                                        'stableRS': 'abc', 'currentPodHash': 'abc'}}
        with patch.dict('os.environ', {'SITE': site, 'RELEASE_IMAGE': self.image}), \
             patch('subprocess.run') as command, \
             patch('subprocess.check_output', return_value=json.dumps(rollout).encode()), \
             patch.object(Path, 'write_text', autospec=True) as write:
            exec(compile(CONFIGS['pipeline-script']['code'], 'prepare-release.py', 'exec'), {})
            return command, write

    def test_a_only_changes_its_own_image_patch_without_cluster_calls(self):
        command, write = self.run_script('dc-a')
        command.assert_not_called()
        self.assertEqual(write.call_args.args[0], Path('overlays/dc-a/orders-image.yaml'))
        self.assertIn(self.image, write.call_args.args[1])

    def test_b_requires_a_fully_promoted_on_the_exact_image(self):
        command, write = self.run_script('dc-b')
        self.assertEqual(command.call_args.args[0][:4], ['kubectl', 'argo', 'rollouts', 'status'])
        self.assertEqual(write.call_args.args[0], Path('overlays/dc-b/orders-image.yaml'))
        for status in [
            {'phase':'Paused','observedGeneration':'7','stableRS':'old','currentPodHash':'new'},
            {'phase':'Healthy','observedGeneration':'6','stableRS':'abc','currentPodHash':'abc'},
            {'phase':'Healthy','observedGeneration':'7','stableRS':'old','currentPodHash':'new'},
        ]:
            with self.subTest(status=status), self.assertRaises(SystemExit):
                self.run_script('dc-b',status)


@unittest.skipUnless(yaml, 'Optional manifest checks require PyYAML')
class ManifestTests(unittest.TestCase):
    def documents(self,key):
        return list(yaml.safe_load_all(CONFIGS[key]['code']))

    def test_every_yaml_parses_and_every_config_is_reachable(self):
        flows = SCENARIOS + [rollback_scenario('b', 50)]
        referenced={key for scenario in flows for step in scenario['steps'] for key in step['configs']}
        self.assertEqual(referenced,set(CONFIGS))
        for key,config in CONFIGS.items():
            with self.subTest(file=key):
                for field in ('title','purpose','mode','scope','file','language','code'):
                    self.assertTrue(config[field])
                if config['language']=='yaml':
                    self.assertTrue(all(isinstance(doc,(dict,list)) for doc in self.documents(key)))

    def test_rollout_services_routes_and_analysis_are_connected(self):
        rollout=self.documents('rollout')[0]
        strategy=rollout['spec']['strategy']['canary']
        services={s['metadata']['name']:s for s in self.documents('services')}
        vs=self.documents('baseline-routing')[0]
        route=vs['spec']['http'][0]
        self.assertEqual(strategy['trafficRouting']['istio']['virtualService']['routes'],[route['name']])
        self.assertEqual([d['destination']['host'] for d in route['route']],
                         [strategy['stableService'],strategy['canaryService']])
        for name in [strategy['stableService'],strategy['canaryService'],'orders']:
            self.assertEqual(services[name]['spec']['selector'],rollout['spec']['selector']['matchLabels'])
        self.assertEqual([d['weight'] for d in route['route']],[100,0])
        analysis=self.documents('analysis')[0]
        self.assertEqual([s['setWeight'] for s in strategy['steps'] if 'setWeight' in s],[10,50])
        for step in strategy['steps']:
            if 'analysis' in step:
                self.assertEqual(step['analysis']['templates'][0]['templateName'],analysis['metadata']['name'])
        self.assertEqual(strategy['steps'][-1],{'pause':{}})
        self.assertEqual(len(analysis['spec']['metrics']),2)

    def test_gateway_services_match_routes_and_network_advertisements(self):
        ingress=self.documents('ingress-workload')[-1]
        route=self.documents('route')[0]
        gateway=self.documents('gateway')[0]
        self.assertEqual(route['spec']['to']['name'],ingress['metadata']['name'])
        self.assertEqual(route['spec']['port']['targetPort'],ingress['spec']['ports'][0]['name'])
        self.assertEqual(gateway['spec']['selector'],ingress['spec']['selector'])
        eastwest=self.documents('eastwest-workload')[-1]
        self.assertEqual(eastwest['spec']['ports'][0]['nodePort'],31443)
        for site in ('a','b'):
            mesh=self.documents('topology' if site=='a' else 'topology-b')[0]['spec']['values']['global']
            self.assertEqual(mesh['multiCluster']['clusterName'],f'dc-{site}')
            self.assertEqual(mesh['network'],f'network-{site}')
            for network,config in mesh['meshNetworks'].items():
                self.assertEqual(config['endpoints'][0]['fromRegistry'],network.replace('network','dc'))
                self.assertEqual(config['gateways'][0]['port'],15443)

    @unittest.skipUnless(shutil.which('kustomize'),'Optional overlay render check requires kustomize')
    def test_changing_a_does_not_change_rendered_b(self):
        keys=['base','namespace','dependencies','rollout','services','baseline-routing','analysis','mtls','locality',
              'overlay-a','overlay-b','image-a-v1','image-b-v1']
        with tempfile.TemporaryDirectory() as root:
            for key in keys:
                path=Path(root)/CONFIGS[key]['file']
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(CONFIGS[key]['code'])
            def render(site):
                return subprocess.check_output(['kustomize','build',f'{root}/overlays/dc-{site}'],text=True)
            before_a,before_b=render('a'),render('b')
            (Path(root)/CONFIGS['image-a-v2']['file']).write_text(CONFIGS['image-a-v2']['code'])
            after_a,after_b=render('a'),render('b')
            self.assertEqual(before_b,after_b)
            self.assertNotEqual(before_a,after_a)
            a_rollout=next(doc for doc in yaml.safe_load_all(after_a) if doc['kind']=='Rollout')
            self.assertEqual(a_rollout['spec']['template']['spec']['containers'][0]['image'],
                             'registry.example.com/shop/orders:2.0.0')
            self.assertEqual(a_rollout['spec']['template']['spec']['containers'][0]['ports'],[{'containerPort':8080}])
