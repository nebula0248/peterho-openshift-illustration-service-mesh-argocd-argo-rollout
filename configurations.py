"""Step-linked teaching manifests, with explicit scope and ownership."""
from textwrap import dedent

def yaml(text):
    return dedent(text).strip() + "\n"

CONFIGS = {
    "baseline-routing": {"file": "routing / orders-baseline.yaml", "language": "yaml", "code": yaml('''
        # Initial state: no release is in progress. Both sites run v1.
        apiVersion: networking.istio.io/v1
        kind: VirtualService
        metadata: {name: orders, namespace: shop}
        spec:
          hosts: [orders.shop.svc.cluster.local]
          gateways: [mesh]
          http:
          - name: primary
            route:
            - destination:
                host: orders-stable.shop.svc.cluster.local
              weight: 100
            - destination:
                host: orders-canary.shop.svc.cluster.local
              weight: 0
        # Stable points to v1. No v2 ReplicaSet is being introduced.
        # The same initial route exists independently in each site.
        # Orders calls local Catalog while that endpoint is healthy.
    ''')},
    "topology": {"file": "mesh / istio-dc-a.yaml", "language": "yaml", "code": yaml('''
        # Teaching excerpt; install operators, CNI and trust first.
        apiVersion: sailoperator.io/v1
        kind: Istio
        metadata:
          name: default
        spec:
          namespace: istio-system
          # Pin an Istio version supported by your OSSM release.
          values:
            global:
              meshID: commerce-mesh
              multiCluster:
                clusterName: dc-a
              network: network-a
            meshConfig:
              serviceSettings:
              - hosts:
                - frontend.shop.svc.cluster.local
                - orders.shop.svc.cluster.local
                - orders-stable.shop.svc.cluster.local
                - orders-canary.shop.svc.cluster.local
                settings:
                  clusterLocal: true
        # DC-B: same meshID, clusterName dc-b, network network-b.
        # Catalog remains discoverable across both clusters.
        # Use a common root CA with per-cluster intermediates.
    ''')},
    "dns": {"file": "edge / global-steering.yaml", "language": "yaml", "code": yaml('''
        # CONCEPTUAL model — not an F5 API or Kubernetes CRD.
        wideIP: shop.example.com
        recordType: A
        ttlSeconds: 30
        policy: ratio
        members:
          - site: dc-a
            virtualServer: 192.0.2.10:443
            ratio: 1
          - site: dc-b
            virtualServer: 192.0.2.20:443
            ratio: 1
        healthCheck:
          path: /readyz
          expectedStatus: 200
        # Documentation IPs only. DNS selects a site VIP.
        # DNS caching means 1:1 is not exact per-request balance.
    ''')},
    "route": {"file": "edge / openshift-route.yaml", "language": "yaml", "code": yaml('''
        apiVersion: route.openshift.io/v1
        kind: Route
        metadata:
          name: shop
          namespace: istio-ingress
        spec:
          host: shop.example.com
          to:
            kind: Service
            name: istio-ingressgateway
          port:
            targetPort: https
          tls:
            termination: passthrough
        # LTM forwards TCP/443 to the HAProxy router VIP.
        # SNI routes encrypted traffic to the mesh gateway.
        # Install this Route independently in both clusters.
    ''')},
    "gateway": {"file": "edge / gateway.yaml", "language": "yaml", "code": yaml('''
        apiVersion: networking.istio.io/v1
        kind: Gateway
        metadata:
          name: shop
          namespace: istio-ingress
        spec:
          selector:
            istio: ingressgateway
          servers:
          - port: {number: 443, name: https, protocol: HTTPS}
            hosts: [shop.example.com]
            tls:
              mode: SIMPLE
              credentialName: shop-tls
        ---
        apiVersion: networking.istio.io/v1
        kind: VirtualService
        metadata:
          name: storefront
          namespace: shop
        spec:
          hosts: [shop.example.com]
          gateways: [istio-ingress/shop]
          http:
          - route:
            - destination:
                host: frontend.shop.svc.cluster.local
                port: {number: 8080}
        # Gateway service/deployment and TLS secret are prerequisites.
    ''')},
    "mtls": {"file": "mesh / peer-authentication.yaml", "language": "yaml", "code": yaml('''
        apiVersion: security.istio.io/v1
        kind: PeerAuthentication
        metadata:
          name: default
          namespace: shop
        spec:
          mtls:
            mode: STRICT
        # Inject sidecars into frontend, orders and catalog.
        # Auto mTLS encrypts proxy-to-proxy traffic.
        # Add workload-scoped AuthorizationPolicies separately.
        # Trust is shared; authorization is still required.
    ''')},
    "discovery": {"file": "mesh / remote-discovery.sh", "language": "shell", "code": yaml('''
        # Requires secured Kubernetes API connectivity between sites.
        # Run with the Istio CLI matching the installed version.
        istioctl create-remote-secret \\
          --context=dc-a --name=dc-a | \\
          oc --context=dc-b apply -f -

        istioctl create-remote-secret \\
          --context=dc-b --name=dc-b | \\
          oc --context=dc-a apply -f -

        # istiod A watches API B; istiod B watches API A.
        # Protect discovery credentials; never commit them to Git.
        # Same Service name + namespace identifies shared catalog.
    ''')},
    "eastwest": {"file": "mesh / eastwest-gateway.yaml", "language": "yaml", "code": yaml('''
        apiVersion: networking.istio.io/v1
        kind: Gateway
        metadata:
          name: cross-network
          namespace: istio-system
        spec:
          selector:
            istio: eastwestgateway
          servers:
          - port:
              number: 15443
              name: tls
              protocol: TLS
            tls:
              mode: AUTO_PASSTHROUGH
            hosts: ["*.local"]
        # Excerpt: needs gateway pods + TCP LoadBalancer Service.
        # Each network advertises a reachable east-west VIP.
        # Here, dedicated F5 LTM TCP/15443 VIPs expose the gateways.
        # This path bypasses the HAProxy north-south router.
        # Source sidecar -> remote gateway -> destination sidecar.
    ''')},
    "locality": {"file": "mesh / catalog-locality.yaml", "language": "yaml", "code": yaml('''
        apiVersion: networking.istio.io/v1
        kind: DestinationRule
        metadata:
          name: catalog-locality
          namespace: shop
        spec:
          host: catalog.shop.svc.cluster.local
          trafficPolicy:
            connectionPool:
              http:
                maxRequestsPerConnection: 1
            loadBalancer:
              simple: ROUND_ROBIN
              localityLbSetting:
                enabled: true
                failover:
                - {from: dc-a, to: dc-b}
                - {from: dc-b, to: dc-a}
            outlierDetection:
              consecutive5xxErrors: 3
              interval: 5s
              baseEjectionTime: 30s
              maxEjectionPercent: 100
        # Nodes need topology.kubernetes.io/region = dc-a or dc-b.
        # Catalog is global; rollout stable/canary hosts are local.
        # Tune connection reuse/ejection settings for production.
    ''')},
    "commit": {"file": "git / overlays/dc-a/kustomization.yaml", "language": "yaml", "code": yaml('''
        apiVersion: kustomize.config.k8s.io/v1beta1
        kind: Kustomization
        namespace: shop
        resources:
          - ../../base
        patches:
          - target:
              group: argoproj.io
              version: v1alpha1
              kind: Rollout
              name: orders
            patch: |-
              - op: replace
                path: /spec/template/spec/containers/0/image
                value: registry.example.com/shop/orders:2.0.0
        # CI builds/tests the image and publishes it before this PR.
        # Use a verified immutable image digest in production.
        # overlays/dc-b remains on v1 until the site promotion gate.
    ''')},
    "application": {"file": "gitops / application-dc-a.yaml", "language": "yaml", "code": yaml('''
        apiVersion: argoproj.io/v1alpha1
        kind: Application
        metadata:
          name: shop-dc-a
          namespace: openshift-gitops
        spec:
          project: default
          source:
            repoURL: https://git.example.com/platform/commerce.git
            targetRevision: main
            path: overlays/dc-a
          destination:
            server: https://kubernetes.default.svc
            namespace: shop
          syncPolicy:
            automated: {prune: true, selfHeal: true}
            syncOptions:
              - RespectIgnoreDifferences=true
              - ApplyOutOfSyncOnly=true
          ignoreDifferences:
            - group: networking.istio.io
              kind: VirtualService
              name: orders
              namespace: shop
              jqPathExpressions:
                - '.spec.http[] | select(.name == "primary") | .route[].weight'
            - group: ""
              kind: Service
              name: orders-stable
              namespace: shop
              jsonPointers:
                - /spec/selector/rollouts-pod-template-hash
            - group: ""
              kind: Service
              name: orders-canary
              namespace: shop
              jsonPointers:
                - /spec/selector/rollouts-pod-template-hash
        # DC-B has its own Application pointing to overlays/dc-b.
    ''')},
    "rollout": {"file": "workloads / orders-rollout.yaml", "language": "yaml", "code": yaml('''
        apiVersion: argoproj.io/v1alpha1
        kind: Rollout
        metadata: {name: orders, namespace: shop}
        spec:
          replicas: 6
          selector:
            matchLabels: {app: orders}
          template:
            metadata:
              labels: {app: orders}
            spec:
              containers:
                - name: orders
                  image: registry.example.com/shop/orders:2.0.0
                  ports: [{containerPort: 8080}]
                  readinessProbe:
                    httpGet: {path: /readyz, port: 8080}
          strategy:
            canary:
              stableService: orders-stable
              canaryService: orders-canary
              trafficRouting:
                istio:
                  virtualService:
                    name: orders
                    routes: [primary]
              steps:
                - setWeight: 10
                - pause: {duration: 60s}
                - analysis:
                    templates: [{templateName: orders-success}]
                    args:
                      - name: canary-hash
                        valueFrom:
                          podTemplateHashValue: Latest
                - setWeight: 50
                - pause: {duration: 60s}
                - analysis:
                    templates: [{templateName: orders-success}]
                    args:
                      - name: canary-hash
                        valueFrom:
                          podTemplateHashValue: Latest
                - pause: {} # Explicit local promotion gate.
        # Inject sidecars using the selected Istio revision.
    ''')},
    "virtualservice": {"file": "routing / orders-virtualservice.yaml", "language": "yaml", "code": yaml('''
        apiVersion: networking.istio.io/v1
        kind: VirtualService
        metadata: {name: orders, namespace: shop}
        spec:
          hosts: [orders.shop.svc.cluster.local]
          gateways: [mesh]
          http:
            - name: primary
              route:
                - destination:
                    host: orders-stable.shop.svc.cluster.local
                  weight: 90
                - destination:
                    host: orders-canary.shop.svc.cluster.local
                  weight: 10
        # LIVE illustration at the 10% step; Git starts at 100/0.
        # The local Rollouts controller owns these route weights.
        # Frontend calls orders; its Envoy applies this route.
        # Each cluster has orders, orders-stable, orders-canary
        # Services on port 8080. Rollouts patches hash selectors
        # on stable/canary; orders supplies a resolvable hostname.
    ''')},
    "analysis": {"file": "analysis / orders-success.yaml", "language": "yaml", "code": yaml('''
        apiVersion: argoproj.io/v1alpha1
        kind: AnalysisTemplate
        metadata: {name: orders-success, namespace: shop}
        spec:
          args:
            - name: canary-hash
          metrics:
            - name: canary-success-rate
              interval: 30s
              count: 5
              failureLimit: 1
              successCondition: len(result) == 1 && result[0] >= 0.99
              failureCondition: len(result) != 1 || result[0] < 0.99
              provider:
                prometheus:
                  address: http://prometheus.monitoring.svc:9090
                  query: |
                    sum(rate(istio_requests_total{
                      reporter="destination",
                      destination_workload_namespace="shop",
                      destination_workload="orders-{{args.canary-hash}}",
                      response_code!~"5.."}[2m]))
                    /
                    sum(rate(istio_requests_total{
                      reporter="destination",
                      destination_workload_namespace="shop",
                      destination_workload="orders-{{args.canary-hash}}"}[2m]))
        # Per-site Prometheus; validate actual telemetry labels.
        # Supply canary test traffic. Empty/NaN must not promote.
        # Add a minimum request-volume gate before production use.
    ''')},
    "promote": {"file": "release / promote-site.sh", "language": "shell", "code": yaml('''
        # After successful analysis, resume DC-A's final pause.
        kubectl argo rollouts promote orders -n shop --context=dc-a
        kubectl argo rollouts status orders -n shop --context=dc-a

        # A separate human/CI gate now opens a Git PR to update
        # overlays/dc-b to the SAME approved image digest.
        # Argo CD B reconciles that change; Rollouts B runs its
        # own 10% -> analysis -> 50% -> analysis -> pause sequence.

        # After DC-B analysis passes, resume its final pause.
        kubectl argo rollouts promote orders -n shop --context=dc-b

        # Neither Argo CD instance coordinates the other by default.
        # This is staged delivery, not an atomic two-site commit.
    ''')},
    "rollback": {"file": "release / abort-and-reconcile.sh", "language": "shell", "code": yaml('''
        # Failed inline analysis automatically aborts the rollout.
        # Manual equivalent, if required:
        kubectl argo rollouts abort orders -n shop --context=dc-a

        # Runtime effect: stable=100%, canary=0% in DC-A.
        # The desired image in Git is STILL v2; abort does not
        # rewrite Git or automatically revert spec.template.

        # Revert only the failed DC-A image change through a PR.
        # Merge after review; Argo CD reconciles v1 again.
        # Keep DC-B's overlay unchanged and investigate v2.
    ''')},
    "failover": {"file": "operations / site-failover.yaml", "language": "yaml", "code": yaml('''
        # CONCEPTUAL runbook — not an executable F5 API object.
        trigger: dc-a application health probe fails
        globalDNS:
          dc-a: unavailable
          dc-b: available
          newAnswers: 192.0.2.20
          ttlSeconds: 30
        recovery:
          - restore dc-a network and control plane
          - wait for Argo CD sync and Rollout health
          - verify dependencies, capacity and synthetic requests
          - re-enable dc-a with a gradual DNS ratio increase
        # Cached DNS and existing connections do not migrate.
        # DC-B needs capacity for full load and resilient data.
    ''')},
}



def add(key, title, file, scope, purpose, code, language="yaml", mode="Git desired state"):
    CONFIGS[key] = dict(title=title, file=file, scope=scope, purpose=purpose,
                        code=yaml(code), language=language, mode=mode)


# Give every existing snippet a purpose and separate runtime examples from Git.
_DETAILS = {
    "baseline-routing": ("Orders route · 100/0", "Both sites", "Initial Git route. Rollouts owns live weights after reconciliation."),
    "topology": ("Mesh primary A", "DC-A", "Common mesh identity, distinct network and cluster-local rollout hosts."),
    "dns": ("Global DNS policy", "F5 GTM", "Health-based site selection; conceptual F5 policy, not a Kubernetes object."),
    "route": ("OpenShift Route", "Each site", "TLS passthrough from HAProxy to the local mesh ingress Service."),
    "gateway": ("Ingress routing", "Each site", "Terminate external TLS, then route to the local Frontend Service."),
    "mtls": ("Strict workload mTLS", "Each site", "Require mesh certificates for connections into shop workloads."),
    "discovery": ("Reciprocal API credentials", "Both sites", "Generate remote discovery credentials in both directions; keep them out of Git."),
    "eastwest": ("East-west TLS routing", "Each site", "Preserve workload mTLS through the destination gateway on port 15443."),
    "locality": ("Locality & outlier detection", "Each site", "Prefer the local region, eject unhealthy endpoints and fail over to the other region."),
    "application": ("Argo CD Application A", "DC-A", "Watch only A's overlay; auto-sync without overriding Rollouts-owned fields."),
    "rollout": ("Orders Rollout", "Each site", "The release controller's complete workload and canary strategy, referenced by each local rollout step."),
    "virtualservice": ("Orders live route · 90/10", "Active site", "Runtime observation at 10%; do not commit this weight snapshot to Git."),
    "analysis": ("Canary AnalysisTemplate", "Each site", "Evaluate the candidate ReplicaSet using local telemetry."),
    "rollback": ("Abort & Git recovery", "DC-A only", "Separate live traffic recovery from the reviewed Git revert."),
    "failover": ("Site failover runbook", "F5 GTM", "Detect outage, change new DNS answers and validate recovery; conceptual runbook."),
}
for key, (title, scope, purpose) in _DETAILS.items():
    CONFIGS[key].update(title=title, scope=scope, purpose=purpose, mode="Git desired state")
for key in ("dns", "failover"):
    CONFIGS[key]["mode"] = "Conceptual F5 policy"
for key in ("discovery", "rollback"):
    CONFIGS[key]["mode"] = "Operator commands"
CONFIGS["virtualservice"]["mode"] = "Live snapshot · do not apply"
# Short destination names exactly match the local Rollout's Service references.
for key in ("baseline-routing", "virtualservice"):
    for name in ("orders-stable", "orders-canary"):
        CONFIGS[key]["code"] = CONFIGS[key]["code"].replace(name+".shop.svc.cluster.local", name)
CONFIGS["baseline-routing"]["file"] = "base/orders-route.yaml"
CONFIGS["rollout"]["file"] = "base/orders-rollout.yaml"
CONFIGS["rollout"]["code"] = CONFIGS["rollout"]["code"].replace('orders:2.0.0', 'orders:1.0.0')
CONFIGS["rollout"]["code"] = '# Shared base stays on v1; each site image patch supplies its approved digest.\n' + CONFIGS["rollout"]["code"]
# Initial creation skips progressive steps; they run when the template changes.
CONFIGS["rollout"]["code"] += '# An initial Rollout creates the stable release; canary steps run on template updates.\n'
CONFIGS.pop("commit")
CONFIGS.pop("promote")

add("services", "Orders Services · all three", "base/orders-services.yaml", "Each site",
    "The orders DNS name plus the stable and canary Services required by host-level splitting. Rollouts injects hash selectors.", '''
    apiVersion: v1
    kind: Service
    metadata: {name: orders, namespace: shop}
    spec:
      selector: {app: orders}
      ports: [{name: http, port: 8080, targetPort: 8080}]
    ---
    apiVersion: v1
    kind: Service
    metadata: {name: orders-stable, namespace: shop}
    spec:
      selector: {app: orders}
      ports: [{name: http, port: 8080, targetPort: 8080}]
    ---
    apiVersion: v1
    kind: Service
    metadata: {name: orders-canary, namespace: shop}
    spec:
      selector: {app: orders}
      ports: [{name: http, port: 8080, targetPort: 8080}]
    # Rollouts adds rollouts-pod-template-hash to stable/canary.
    # Mesh clients call orders:8080; its VirtualService selects
    # orders-stable or orders-canary. Do not bypass the mesh.
''')
add("namespace", "Sidecar enrollment", "base/namespace.yaml", "Each site", "Enroll the application namespace in the installed sidecar revision.", '''
    apiVersion: v1
    kind: Namespace
    metadata:
      name: shop
      labels:
        istio.io/rev: default
    # Replace default with the installed IstioRevision label.
    # Enroll before creating workload pods; existing pods need restart.
    # Istio CNI and the supported OpenShift operators are prerequisites.
''')
add("dependencies", "Frontend & Catalog workloads", "base/dependencies.yaml", "Each site", "Identical service identities in both sites; Catalog can be discovered remotely. Images are illustrative application contracts.", '''
    apiVersion: v1
    kind: Service
    metadata: {name: frontend, namespace: shop}
    spec:
      selector: {app: frontend}
      ports: [{name: http, port: 8080, targetPort: 8080}]
    ---
    apiVersion: apps/v1
    kind: Deployment
    metadata: {name: frontend, namespace: shop}
    spec:
      replicas: 3
      selector: {matchLabels: {app: frontend}}
      template:
        metadata: {labels: {app: frontend}}
        spec:
          containers:
          - name: frontend
            image: registry.example.com/shop/frontend:1.0.0
            ports: [{containerPort: 8080}]
            env: [{name: ORDERS_URL, value: "http://orders:8080"}]
            readinessProbe: {httpGet: {path: /readyz, port: 8080}}
    ---
    apiVersion: v1
    kind: Service
    metadata: {name: catalog, namespace: shop}
    spec:
      selector: {app: catalog}
      ports: [{name: http, port: 8080, targetPort: 8080}]
    ---
    apiVersion: apps/v1
    kind: Deployment
    metadata: {name: catalog, namespace: shop}
    spec:
      replicas: 3
      selector: {matchLabels: {app: catalog}}
      template:
        metadata: {labels: {app: catalog}}
        spec:
          containers:
          - name: catalog
            image: registry.example.com/shop/catalog:1.0.0
            ports: [{containerPort: 8080}]
            readinessProbe: {httpGet: {path: /readyz, port: 8080}}
''')
CONFIGS["rollout"]["code"] = CONFIGS["rollout"]["code"].replace('ports: [{containerPort: 8080}]', 'ports: [{containerPort: 8080}]\n          env: [{name: CATALOG_URL, value: "http://catalog:8080"}]')
add("base", "Shared Kustomize base", "base/kustomization.yaml", "Shared Git", "All workload dependencies travel together. Platform and ingress manifests are managed separately.", '''
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
    - namespace.yaml
    - dependencies.yaml
    - orders-rollout.yaml
    - orders-services.yaml
    - orders-route.yaml
    - orders-success.yaml
    - peer-authentication.yaml
    - catalog-locality.yaml
    # Keep these shared resources unchanged during a site-only image release.
    # A change to this base would affect BOTH overlays.
''')
CONFIGS["analysis"]["file"] = "base/orders-success.yaml"
CONFIGS["mtls"]["file"] = "base/peer-authentication.yaml"
CONFIGS["locality"]["file"] = "base/catalog-locality.yaml"

for site in ("a", "b"):
    add(f"overlay-{site}", f"Kustomize overlay {site.upper()}", f"overlays/dc-{site}/kustomization.yaml", f"DC-{site.upper()}", "Isolate this site's image change from the other site's desired manifests.", f'''
        apiVersion: kustomize.config.k8s.io/v1beta1
        kind: Kustomization
        namespace: shop
        resources: [../../base]
        patches:
        - path: orders-image.yaml
          target:
            group: argoproj.io
            version: v1alpha1
            kind: Rollout
            name: orders
    ''')
    for version in (1, 2):
        add(f"image-{site}-v{version}", f"{site.upper()} image patch · v{version}", f"overlays/dc-{site}/orders-image.yaml", f"DC-{site.upper()} only", "The pipeline edits this one file and opens a reviewed PR. The demo uses tags for readability; the workflow requires an immutable digest.", f'''
            # State of this file at the selected release stage.
            - op: replace
              path: /spec/template/spec/containers/0/image
              value: registry.example.com/shop/orders:{version}.0.0
        ''')
    app = CONFIGS["application"]["code"].replace('dc-a',f'dc-{site}')
    app=app[:app.index('# DC-B has')] if '# DC-B has' in app else app
    if site == 'a':
        CONFIGS["application"]["code"] = app
    else:
        add("application-b", "Argo CD Application B", "gitops/application-dc-b.yaml", "DC-B", "Installed in B's Argo CD; B renders only overlays/dc-b even when A changes on the same branch.", app)
CONFIGS["application"]["file"] = "gitops/application-dc-a.yaml"

add("live-50", "Orders live route · 50/50", "observations/orders-route-50.yaml", "Active site", "Rollouts-owned runtime weights after the first analysis passes. Git remains 100/0.", CONFIGS["virtualservice"]["code"].replace('weight: 90','weight: 50').replace('weight: 10','weight: 50').replace('10% step','50% step'), mode="Live snapshot · do not apply")
add("stable-live", "Stable route after promotion/abort", "observations/orders-route-stable.yaml", "Active site", "Stable receives 100%. Stable means v2 after promotion, but v1 after abort; the Service hash identifies the ReplicaSet.", CONFIGS["baseline-routing"]["code"].split('# Stable points')[0].replace('# Initial state: no release is in progress. Both sites run v1.','# Runtime weights; stable identity depends on promotion or abort.'), mode="Live snapshot · do not apply")

add("analysis", "Canary AnalysisTemplate", "base/orders-success.yaml", "Each site", "Both sufficient request volume and candidate success rate must pass. Empty data and NaN fail instead of approving a release.", '''
    apiVersion: argoproj.io/v1alpha1
    kind: AnalysisTemplate
    metadata: {name: orders-success, namespace: shop}
    spec:
      args:
      - name: canary-hash
      metrics:
      - name: request-volume
        interval: 30s
        count: 5
        failureLimit: 1
        successCondition: len(result) == 1 && !isNaN(result[0]) && result[0] >= 100
        failureCondition: len(result) != 1 || isNaN(result[0]) || result[0] < 100
        provider:
          prometheus:
            address: http://prometheus.monitoring.svc:9090
            query: |
              sum(increase(istio_requests_total{
                reporter="destination",
                destination_workload_namespace="shop",
                destination_workload="orders-{{args.canary-hash}}"}[2m])) or vector(0)
      - name: canary-success-rate
        interval: 30s
        count: 5
        failureLimit: 1
        successCondition: len(result) == 1 && !isNaN(result[0]) && result[0] >= 0.99
        failureCondition: len(result) != 1 || isNaN(result[0]) || result[0] < 0.99
        provider:
          prometheus:
            address: http://prometheus.monitoring.svc:9090
            query: |
              (sum(rate(istio_requests_total{
                reporter="destination",
                destination_workload_namespace="shop",
                destination_workload="orders-{{args.canary-hash}}",
                response_code!~"5.."}[2m])) or vector(0))
              /
              sum(rate(istio_requests_total{
                reporter="destination",
                destination_workload_namespace="shop",
                destination_workload="orders-{{args.canary-hash}}"}[2m]))
    # Example threshold: >=100 candidate calls over 2 minutes.
    # Warm up the candidate before analysis; tune windows to traffic.
    # Configure the local telemetry backend, scrape targets and auth.
    # The address is illustrative, not the OpenShift managed endpoint.
    # Validate destination_workload labels in your actual telemetry.
''')
# Allow the illustrative two-minute telemetry window to fill before analysis.
CONFIGS["rollout"]["code"] = CONFIGS["rollout"]["code"].replace('duration: 60s','duration: 120s')

# Platform manifests are installed per site, separately from the release overlay.
_topology_template = CONFIGS["topology"]["code"]
for site in ("a", "b"):
    code = _topology_template.split('# DC-B:')[0]
    code=code.replace('dc-a',f'dc-{site}').replace('network-a',f'network-{site}')
    code=code.replace('    global:\n', """    global:
      meshNetworks:
        network-a:
          endpoints: [{fromRegistry: dc-a}]
          gateways: [{address: 192.0.2.11, port: 15443}]
        network-b:
          endpoints: [{fromRegistry: dc-b}]
          gateways: [{address: 192.0.2.21, port: 15443}]
""")
    add('topology' if site=='a' else 'topology-b', f"Mesh primary {site.upper()}", f"platform/dc-{site}/istio.yaml", f"DC-{site.upper()}", "Separate primary and network identity; explicit reachable F5 east-west VIPs and cluster-local rollout hosts.", code)
    add(f"network-{site}", f"Network & locality labels {site.upper()}", f"platform/dc-{site}/topology-labels.yaml", f"DC-{site.upper()}", "Namespace network labels and node region/zone labels supply locality metadata used by Envoy.", f'''
        apiVersion: v1
        kind: Namespace
        metadata:
          name: istio-system
          labels:
            topology.istio.io/network: network-{site}
        ---
        # Node metadata excerpt; apply to EVERY eligible node in this site.
        # Preserve cloud/provider labels; map the DestinationRule accordingly.
        apiVersion: v1
        kind: Node
        metadata:
          name: REPLACE_WITH_EXISTING_WORKER_NAME
          labels:
            topology.kubernetes.io/region: dc-{site}
            topology.kubernetes.io/zone: dc-{site}-zone-1
    ''', mode="Platform prerequisite")
add("trust", "Shared root · separate intermediates", "platform/cacerts-secret.yaml", "Each site", "Install a different intermediate key per cluster, signed by the same root. This is the required Secret shape, with placeholders only.", '''
    apiVersion: v1
    kind: Secret
    metadata: {name: cacerts, namespace: istio-system}
    type: Opaque
    stringData:
      ca-cert.pem: REPLACE_WITH_THIS_SITES_INTERMEDIATE_CERT
      ca-key.pem: REPLACE_WITH_THIS_SITES_INTERMEDIATE_PRIVATE_KEY
      root-cert.pem: REPLACE_WITH_COMMON_ROOT_CERT
      cert-chain.pem: REPLACE_WITH_THIS_SITES_CERT_CHAIN
    # Provision through your secret-management process BEFORE Istiod.
    # Never commit private keys or generated credentials to Git.
''', mode="Secret shape · placeholders")
add("tls-secret", "Ingress TLS certificate", "edge/shop-tls-secret.yaml", "Each site", "The Gateway credentialName must resolve to this certificate Secret in the gateway namespace.", '''
    apiVersion: v1
    kind: Secret
    metadata: {name: shop-tls, namespace: istio-ingress}
    type: kubernetes.io/tls
    stringData:
      tls.crt: REPLACE_WITH_SHOP_EXAMPLE_COM_CERT_CHAIN
      tls.key: REPLACE_WITH_PRIVATE_KEY
    # Provision through your certificate/secret manager, outside Git.
''', mode="Secret shape · placeholders")
for kind, namespace, selector, port, nodeport in [
    ('ingress','istio-ingress','ingressgateway',443, None),
    ('eastwest','istio-system','eastwestgateway',15443,31443),
]:
    service_type = 'NodePort' if nodeport else 'ClusterIP'
    add(f"{kind}-workload", f"{kind.title()} gateway pods & Service", f"platform/{kind}-gateway.yaml", "Each site", "Gateway routing rules need actual Envoy pods and a reachable Service. F5 east-west VIPs forward to worker NodePorts.", yaml(f'''
        apiVersion: v1
        kind: Namespace
        metadata:
          name: {namespace}
          labels: {{istio.io/rev: default}}
        ---
        apiVersion: apps/v1
        kind: Deployment
        metadata: {{name: istio-{selector}, namespace: {namespace}}}
        spec:
          replicas: 2
          selector: {{matchLabels: {{istio: {selector}}}}}
          template:
            metadata:
              labels:
                istio: {selector}
                sidecar.istio.io/inject: "true"
              annotations:
                inject.istio.io/templates: gateway
            spec:
              containers:
              - name: istio-proxy
                image: auto
                ports: [{{containerPort: {port}}}]
        ---
        apiVersion: v1
        kind: Service
        metadata: {{name: istio-{selector}, namespace: {namespace}}}
        spec:
          type: {service_type}
          selector: {{istio: {selector}}}
          ports:
          - name: {'tls' if nodeport else 'https'}
            port: {port}
            targetPort: {port}
    ''') + ('    nodePort: 31443\n' if nodeport else '') + '''
# image: auto is replaced by the gateway injection webhook.
# Use the installed revision; verify supported gateway installation
# settings and security context for your OpenShift/OSSM versions.
''')
add("ltm", "Site LTM pools & VIPs", "edge/ltm-policy.yaml", "Each F5 LTM", "Two independent paths: north-south VIP to HAProxy; east-west VIP directly to the mesh gateway NodePort.", '''
    # CONCEPTUAL model, not an F5 API object or Kubernetes CRD.
    dc-a:
      publicVIP: {address: 192.0.2.10, port: 443}
      publicPool: {targets: "HAProxy router endpoints:443", mode: tcp-passthrough}
      eastWestVIP: {address: 192.0.2.11, port: 15443}
      eastWestPool: {targets: "DC-A worker IPs:31443", mode: tcp-passthrough}
    dc-b:
      publicVIP: {address: 192.0.2.20, port: 443}
      publicPool: {targets: "HAProxy router endpoints:443", mode: tcp-passthrough}
      eastWestVIP: {address: 192.0.2.21, port: 15443}
      eastWestPool: {targets: "DC-B worker IPs:31443", mode: tcp-passthrough}
    probes:
      public: {tlsSNI: shop.example.com, host: shop.example.com, path: /readyz}
      eastWest: {transport: tcp, port: 15443}
    # Translate into your F5 management interface and network addresses.
    # Permit cross-site TCP/15443 and secured Kubernetes API access.
    # An application probe must reflect dependency readiness, not just TCP.
''', mode="Conceptual F5 policy")

add("pipeline", "Approved Git update workflow", ".github/workflows/propose-release.yaml", "Release pipeline", "Concrete GitHub Actions example: an approved job edits one site overlay and opens a PR. Review/merge makes the change visible to Argo CD. Other CI systems can implement the same contract.", '''
    name: Propose one-site Orders release
    on:
      workflow_dispatch:
        inputs:
          site:
            type: choice
            options: [dc-a, dc-b]
            required: true
          image:
            description: Verified CI output, registry.example.com/shop/orders@sha256:...
            type: string
            required: true
    permissions: {contents: read}
    concurrency:
      group: orders-git-proposal
      cancel-in-progress: false
    jobs:
      propose:
        # Configure REQUIRED REVIEWERS on these environments in GitHub.
        # An environment name alone does NOT enable approval protection.
        environment: release-${{ inputs.site }}
        runs-on: self-hosted
        env:
          SITE: ${{ inputs.site }}
          RELEASE_IMAGE: ${{ inputs.image }}
          GH_TOKEN: ${{ secrets.GITOPS_PR_TOKEN }}
          KUBECONFIG: ${{ vars.READ_ONLY_KUBECONFIG_PATH }}
        steps:
        - uses: actions/checkout@v4
          with:
            ref: main
            token: ${{ secrets.GITOPS_PR_TOKEN }}
        - name: Verify sequencing and edit one overlay
          run: python3 ci/prepare-release.py
        - name: Commit, push branch, open reviewed PR
          shell: bash
          run: |
            set -euo pipefail
            branch="release/$SITE/$GITHUB_RUN_ID"
            git config user.name "release-bot"
            git config user.email "release-bot@example.com"
            git switch -c "$branch"
            git add "overlays/$SITE/orders-image.yaml"
            git commit -m "Promote Orders in $SITE"
            git push origin "$branch"
            gh pr create --base main --head "$branch" \
              --title "Orders release: $SITE" \
              --body "CI image: $RELEASE_IMAGE. Only $SITE changes; review before merge."
    # Run this in the GitOps repository. CI build/test/image signing is
    # upstream; pass its verified immutable digest, not an arbitrary image.
    # Protect main with PR review and rendered-manifest checks.
    # Preprovision an authenticated runner with git, gh, Python, kubectl
    # and the Rollouts plugin. Read-only cluster credentials check A.
    # GitHub App/PAT must be scoped to this GitOps repository.
    # No argocd app sync call or Argo CD credentials are needed.
''', mode="Pipeline example · configure approvals")
add("pipeline-script", "Edit one overlay & guard site B", "ci/prepare-release.py", "Release pipeline", "Validate the image, verify A is healthy on that exact digest before proposing B, and change only the selected site's image patch.", '''
    import json
    import os
    from pathlib import Path
    import re
    import subprocess

    site = os.environ["SITE"]
    image = os.environ["RELEASE_IMAGE"]
    if site not in {"dc-a", "dc-b"}:
        raise SystemExit("Unknown site")
    if not re.fullmatch(r"registry\\.example\\.com/shop/orders@sha256:[a-f0-9]{64}", image):
        raise SystemExit("Use the verified immutable digest from CI")
    if site == "dc-b":
        # Read-only credential: get/watch rollout status in DC-A.
        subprocess.run([
            "kubectl", "argo", "rollouts", "status", "orders",
            "-n", "shop", "--context=dc-a", "--timeout", "120s"
        ], check=True)
        rollout = json.loads(subprocess.check_output([
            "kubectl", "--context=dc-a", "get", "rollout", "orders",
            "-n", "shop", "-o", "json"
        ]))
        status = rollout["status"]
        desired = rollout["spec"]["template"]["spec"]["containers"][0]["image"]
        if (desired != image or status.get("phase") != "Healthy"
                or str(status.get("observedGeneration")) != str(rollout["metadata"]["generation"])
                or not status.get("stableRS")
                or status.get("stableRS") != status.get("currentPodHash")):
            raise SystemExit("A must be healthy and fully promoted on this exact digest")
    path = Path("overlays") / site / "orders-image.yaml"
    path.write_text("- op: replace\\n"
                    "  path: /spec/template/spec/containers/0/image\\n"
                    f"  value: {image}\\n")
    # PR checks must also reject unexpected shared-base/other-site changes.
    # Recheck A's release health at B's merge gate if the PR waits.
''', language="python", mode="Pipeline helper")
for site in ("a", "b"):
    add(f"promote-{site}", f"Approve local promotion {site.upper()}", f"release/promote-dc-{site}.sh", f"DC-{site.upper()} only", "After inline analyses pass, an authorized approver resumes this site's final pause. The pipeline uses a separate scoped rollout action credential for this step.", f'''
        # Check this site's analysis and current image before approving.
        kubectl argo rollouts get rollout orders -n shop --context=dc-{site}
        kubectl get analysisruns -n shop --context=dc-{site}
        # Resume the final pause; do not use --full to skip analysis.
        kubectl argo rollouts promote orders -n shop --context=dc-{site}
        kubectl argo rollouts status orders -n shop --context=dc-{site} --timeout 10m
        # Confirm Healthy, observedGeneration and exact image digest.
        # This is a local controller action, not an Argo CD sync trigger.
    ''', language="shell", mode="Approved controller action")

for site in ("a", "b"):
    add(f"rollout-{site}-v2", f"Effective Rollout {site.upper()} · v2", f"rendered/dc-{site}/orders-rollout.yaml", f"DC-{site.upper()} only", "Full Rollout after this site's v2 image patch is applied to the shared base. This is what its Argo CD renders.", CONFIGS["rollout"]["code"].replace('# Shared base stays on v1; each site image patch supplies its approved digest.', '# Rendered from base + this site overlay; image shown as a readable tag.').replace('orders:1.0.0','orders:2.0.0'), mode="Rendered desired state")

add("telemetry", "Candidate metrics scrape", "observability/orders-pod-monitor.yaml", "Each site", "Scrape the local Envoy metrics used by AnalysisTemplate. Assumes a local Prometheus Operator backend selecting this PodMonitor.", '''
    apiVersion: monitoring.coreos.com/v1
    kind: PodMonitor
    metadata:
      name: orders-envoy
      namespace: monitoring
      labels: {team: mesh}
    spec:
      namespaceSelector:
        matchNames: [shop]
      selector:
        matchLabels: {app: orders}
      podMetricsEndpoints:
      - port: http-envoy-prom
        path: /stats/prometheus
        interval: 15s
    # Local Prometheus must select this PodMonitor and be allowed to
    # discover shop pods. The injected Envoy exposes this named port.
    # The demo assumes a standalone Prometheus endpoint; if using
    # OpenShift user-workload monitoring, configure supported discovery,
    # authenticated query URL and AnalysisTemplate provider credentials.
    # Verify actual Istio metric labels before using the analysis query.
''', mode="Telemetry integration")
add("remote-secret", "Remote discovery Secret shapes", "platform/remote-secrets.yaml", "Opposite clusters", "The two generated credentials are installed in the opposite primary's namespace. Use the paired commands to create the real version-matched objects.", '''
    # Generated by istioctl; placeholders below are not usable credentials.
    # Install THIS secret in DC-B, so Istiod B can read API A.
    apiVersion: v1
    kind: Secret
    metadata:
      name: istio-remote-secret-dc-a
      namespace: istio-system
      labels: {istio/multiCluster: "true"}
    type: Opaque
    stringData:
      dc-a: |
        apiVersion: v1
        kind: Config
        clusters:
        - name: dc-a
          cluster:
            server: https://api.dc-a.example.com:6443
            certificate-authority-data: REPLACE_CA_BASE64
        users:
        - name: dc-a
          user: {token: REPLACE_READER_TOKEN}
        contexts:
        - name: dc-a
          context: {cluster: dc-a, user: dc-a}
        current-context: dc-a
    ---
    # Install THIS secret in DC-A, so Istiod A can read API B.
    apiVersion: v1
    kind: Secret
    metadata:
      name: istio-remote-secret-dc-b
      namespace: istio-system
      labels: {istio/multiCluster: "true"}
    type: Opaque
    stringData:
      dc-b: |
        apiVersion: v1
        kind: Config
        clusters:
        - name: dc-b
          cluster:
            server: https://api.dc-b.example.com:6443
            certificate-authority-data: REPLACE_CA_BASE64
        users:
        - name: dc-b
          user: {token: REPLACE_READER_TOKEN}
        contexts:
        - name: dc-b
          context: {cluster: dc-b, user: dc-b}
        current-context: dc-b
    # Never commit generated credentials to Git. Use version-matched
    # istioctl create-remote-secret to create the discovery SA/RBAC
    # and serialize the correct kubeconfig for your cluster.
''', mode="Generated secret shape · placeholders")
CONFIGS["namespace"]["code"] = CONFIGS["namespace"]["code"].replace('    istio.io/rev:', '    argocd.argoproj.io/managed-by: openshift-gitops\n    istio.io/rev:')

add("rollback-b", "Abort & Git recovery B", "release/abort-and-reconcile-dc-b.sh", "DC-B only", "Abort B and revert only its image patch; A keeps its already promoted v2.", CONFIGS["rollback"]["code"].replace("dc-a", "dc-b").replace("DC-A", "DC-B").replace("# Keep DC-B's overlay unchanged and investigate v2.", "# Keep DC-A's v2 overlay unchanged and investigate the failure in B."), language="shell", mode="Operator commands")
add("verify-release", "Inspect rollout & Envoy route", "operations/verify-release.sh", "Selected site · read only", "Confirm the Rollout, inline analysis, Service selectors and the caller proxy's actual route. An API update alone does not prove xDS propagation.", '''
    # Select the site being released. Use dc-b for B's stages.
    SITE=dc-a
    kubectl argo rollouts get rollout orders -n shop --context="$SITE"
    kubectl get analysisruns -n shop --context="$SITE"
    kubectl get rollout orders -n shop --context="$SITE" -o yaml
    kubectl get virtualservice orders -n shop --context="$SITE" -o yaml
    kubectl get service orders-stable orders-canary -n shop --context="$SITE" -o yaml

    # Check ALL caller proxies for xDS sync; inspect each Frontend pod.
    istioctl proxy-status --context="$SITE"
    for FRONTEND in $(kubectl get pods -n shop --context="$SITE" \\
        -l app=frontend -o jsonpath='{.items[*].metadata.name}'); do
      istioctl proxy-config routes "$FRONTEND" -n shop --context="$SITE" -o json
    done
    # Verify orders.shop.svc.cluster.local and the current weighted route.
    # Stable/canary Service selectors must match the intended ReplicaSets.
    # An inconclusive/errored analysis requires investigation; do not skip it.
    # Finished inline runs do not continuously monitor the final pause.
    # Before promotion and B's merge, inspect fresh errors, latency, volume,
    # capacity and synthetic end-to-end/dependency checks in local telemetry.
''', language="shell", mode="Read-only verification")
CONFIGS["locality"]["code"] += '''# Ejection is passive and local to each calling Envoy, not a global switch.
# This demo loses all local Catalog endpoints before showing remote calls.
# Recovery needs endpoint re-advertisement/ejection expiry and successful calls.
'''
