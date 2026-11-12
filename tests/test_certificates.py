"""Certificate lifecycle and trust boundaries of the external-CA walkthrough."""
import unittest

from demo import CONFIGS, SCENARIOS, get_state

try:
    import yaml
except ImportError:
    yaml = None


class CertificateFlowTests(unittest.TestCase):
    def setUp(self):
        self.flow = next(flow for flow in SCENARIOS if flow['id'] == 'certificates')

    def test_renewal_never_changes_application_release_or_global_steering(self):
        for index in range(len(self.flow['steps'])):
            state = get_state('certificates', index)['state']
            self.assertEqual((state['weight_a'], state['weight_b'], state['site_a']), (0, 0, 50))
            self.assertEqual(state['cert_root'], 'R1 · unchanged')
            self.assertEqual(state['healthy_clusters'], 2)
            self.assertEqual(state['revision'], 'v1 · both sites')

    def test_issuance_precedes_loading_and_sites_rotate_independently(self):
        requested = get_state('certificates', 1)['state']
        self.assertEqual(requested['cert_request'], 'Approved · awaiting CA')
        self.assertEqual(requested['cert_loaded_a'], 'A1')
        loaded = get_state('certificates', 2)['state']
        self.assertEqual((loaded['cert_loaded_a'], loaded['cert_loaded_b']), ('A2', 'B1'))
        requesting_b = get_state('certificates', 3)['state']
        self.assertEqual(requesting_b['cert_loaded_b'], 'B1')
        both = get_state('certificates', 4)['state']
        self.assertEqual((both['cert_loaded_a'], both['cert_loaded_b']), ('A2', 'B2'))

    def test_certificate_paths_do_not_activate_the_other_site(self):
        for index in (1, 2):
            frame = get_state('certificates', index)
            self.assertFalse(any(value.startswith('cert-b-') for value in frame['active_nodes'] + frame['active_edges']))
        for index in (3,):
            frame = get_state('certificates', index)
            self.assertFalse(any(value.startswith('cert-a-') for value in frame['active_nodes'] + frame['active_edges']))
        verify = get_state('certificates', 4)
        self.assertEqual(verify['active_edges'], ['cert-mtls-out', 'cert-mtls-in'])
        self.assertIn('cert-b-gateway', verify['active_nodes'])

    def test_issuer_outage_keeps_loaded_valid_leaves_until_recovery(self):
        failed = get_state('certificates', 5)['state']
        self.assertEqual(failed['cert_issuer'], 'Unavailable')
        self.assertEqual((failed['cert_loaded_a'], failed['cert_loaded_b']), ('A2', 'B2'))
        recovered = get_state('certificates', 6)['state']
        self.assertEqual(recovered['cert_issuer'], 'Available')
        self.assertEqual((recovered['cert_loaded_a'], recovered['cert_loaded_b']), ('A3', 'B3'))
        self.assertEqual(get_state('certificates', 0)['state']['cert_loaded_a'], 'A1')

    def test_generated_requests_are_labeled_runtime_and_not_repeated(self):
        requests = [item for step in self.flow['steps'] for item in step['config_items'] if item['id'] == 'cert-request']
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]['kind'], 'runtime')
        for step in self.flow['steps'][2:]:
            self.assertNotIn('cert-issuer', [item['id'] for item in step['config_items']])

    @unittest.skipUnless(yaml, 'Optional manifest checks require PyYAML')
    def test_issuer_trust_and_csr_namespaces_match(self):
        documents = lambda key: list(yaml.safe_load_all(CONFIGS[key]['code']))
        secret, issuer = documents('cert-issuer')
        root = documents('cert-trust')[1]
        csr = documents('cert-csr')[0]
        request = documents('cert-request')[0]
        manager = csr['spec']['istioCSRConfig']['certManager']
        self.assertEqual(manager['issuerRef'], request['spec']['issuerRef'])
        self.assertEqual(manager['issuerRef']['name'], issuer['metadata']['name'])
        self.assertEqual(request['metadata']['namespace'], issuer['metadata']['namespace'])
        self.assertEqual(secret['metadata']['namespace'], issuer['metadata']['namespace'])
        self.assertEqual(issuer['spec']['venafi']['tpp']['credentialsRef']['name'], secret['metadata']['name'])
        self.assertEqual(manager['istioCACertificate']['name'], root['metadata']['name'])
        self.assertIn(manager['istioCACertificate']['key'], root['data'])
        self.assertNotIn('tls.key', root['data'])
        for site in ('a', 'b'):
            values = documents(f'cert-mesh-{site}')[0]['spec']['values']
            self.assertEqual(values['global']['multiCluster']['clusterName'], f'dc-{site}')
            self.assertEqual(values['global']['network'], f'network-{site}')
            self.assertEqual(values['pilot']['env']['ENABLE_CA_SERVER'], 'false')
            self.assertEqual(values['global']['caAddress'], 'cert-manager-istio-csr.istio-csr.svc:443')
        accounts = documents('cert-identities')
        for account, patch in zip(accounts[:2], accounts[2:]):
            self.assertEqual(account['metadata']['name'], patch['spec']['template']['spec']['serviceAccountName'])
