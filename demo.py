"""Technical content and deterministic, stateless simulation transitions.

The manifests are teaching excerpts, not a cluster installation bundle.
"""
from copy import deepcopy
from configurations import CONFIGS
from configuration_flow import configure_flow
from certificate_flow import make_certificate_flow

SOURCES = {
    "cert-csr": {"label": "cert-manager · Istio CSR integration", "url": "https://cert-manager.io/docs/usage/istio-csr/"},
    "cert-operator": {"label": "Red Hat · IstioCSR integration", "url": "https://docs.redhat.com/en/documentation/red_hat_openshift_service_mesh/3.3/html/installing/ossm-cert-manager"},
    "cert-trust": {"label": "Red Hat · Explicit CA bundle", "url": "https://docs.redhat.com/en/documentation/openshift_container_platform/4.19/html/security_and_compliance/cert-manager-operator-for-red-hat-openshift#cert-manager-istio-csr-config-ca-cert_cert-manager-operator-integrating-istio"},
    "cert-venafi": {"label": "cert-manager · Venafi / CyberArk Issuer", "url": "https://cert-manager.io/docs/configuration/venafi/"},
    "cert-agent": {"label": "Istio · Agent renewal settings", "url": "https://istio.io/latest/docs/reference/commands/pilot-agent/"},
    "cert-security": {"label": "Istio · Identity and certificate lifecycle", "url": "https://istio.io/latest/docs/concepts/security/"},
    "cert-request": {"label": "cert-manager · CertificateRequest lifecycle", "url": "https://cert-manager.io/docs/usage/certificaterequest/"},
    "cert-api": {"label": "cert-manager · Issuer API", "url": "https://cert-manager.io/docs/reference/api-docs/"},
    "architecture": {"label": "Istio · Control and data planes", "url": "https://istio.io/latest/docs/ops/deployment/architecture/"},
    "autosync": {"label": "Argo CD · Automated sync", "url": "https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/"},
    "pipeline": {"label": "GitHub Actions · Environment approval gates", "url": "https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments"},
    "mesh": {"label": "Red Hat · Service Mesh 3 multicluster", "url": "https://docs.redhat.com/en/documentation/red_hat_openshift_service_mesh/3.3/html/installing/ossm-multi-cluster-topologies"},
    "ingress": {"label": "Red Hat · Ingress gateways & Routes", "url": "https://docs.redhat.com/en/documentation/red_hat_openshift_service_mesh/3.3/html/gateways/ossm-getting-traffic-into-a-mesh"},
    "routing": {"label": "Argo Rollouts · Istio integration", "url": "https://argoproj.github.io/argo-rollouts/features/traffic-management/istio/"},
    "gitops": {"label": "Argo CD · Diff customization", "url": "https://argo-cd.readthedocs.io/en/stable/user-guide/diffing/"},
    "canary": {"label": "Argo Rollouts · Canary strategy", "url": "https://argoproj.github.io/argo-rollouts/features/canary/"},
    "analysis": {"label": "Argo Rollouts · Automated analysis", "url": "https://argoproj.github.io/argo-rollouts/features/analysis/"},
    "locality": {"label": "Istio · Locality failover", "url": "https://istio.io/latest/docs/tasks/traffic-management/locality-load-balancing/failover/"},
    "clusterlocal": {"label": "Istio · Multicluster traffic management", "url": "https://istio.io/latest/docs/ops/configuration/traffic-management/multicluster/"},
    "dns": {"label": "F5 · Global server load balancing", "url": "https://techdocs.f5.com/kb/en-us/products/big-ip-dns/manuals/product/bigip-dns-load-balancing-13-1-0/1.html"},
    "faq": {"label": "Argo Rollouts · GitOps and rollback FAQ", "url": "https://argoproj.github.io/argo-rollouts/FAQ/"},
}


def step(label, title, body, detail, config, nodes=(), edges=(), state=None, event="", note="", sources=()):
    return {"label": label, "title": title, "body": body, "detail": detail,
            "configs": list(config) if isinstance(config, (list, tuple)) else [config], "nodes": list(nodes), "edges": list(edges), "state": state or {},
            "event": event or title, "note": note, "sources": list(sources)}


def rollback_scenario(site="a", canary_weight=10):
    """Replay failure at either site's selected exposure without resetting its peer."""
    if site not in ("a", "b") or canary_weight not in (10, 50):
        raise ValueError("Choose site a/b and a 10/50 percent canary")
    label = site.upper()
    peer = "B stays on v1" if site == "a" else "A stays on its already promoted v2"
    application = "application" if site == "a" else "application-b"
    abort = "rollback" if site == "a" else "rollback-b"
    initial = {"weight_a": 0 if site == "a" else 100,
               "rollout_a": "Healthy · v1" if site == "a" else "Healthy · v2",
               "analysis": "Failure detected · 95.2%", "release_fault": True,
               "release_fault_site": site, "revision": f"v2 → DC-{label}",
               "gate": f"Contain DC-{label} release"}
    initial.update({f"weight_{site}": canary_weight, f"rollout_{site}": "Analysis failing"})
    scenario = {"id": "rollback", "name": "Canary rollback", "icon": "undo",
            "summary": f"Fail DC-{label} at {canary_weight}% exposure → restore its stable v1 → reconcile only its Git overlay. {peer}.",
            "steps": [
        step("Fail analysis", f"DC-{label}'s candidate breaks the health gate.",
             f"Orders v2 in {label} returns a simulated 4.8% error rate at {canary_weight}% exposure. Its 95.2% success rate is below the 99% threshold. {peer}.",
             "This frame captures the failing measurement before traffic recovery. When the configured failure limit is exceeded, the inline AnalysisRun fails and aborts this local rollout. At 50%, this replays a failed analysis instead of the successful result in the delivery flow.",
             ["analysis", "telemetry", f"rollout-{site}-v2", "services", "virtualservice" if canary_weight == 10 else "live-50", application, "verify-release"],
             [f"{site}-orders", f"{site}-rollouts", f"{site}-metrics"], [f"{site}-observe"], state=initial, sources=["analysis"]),
        step("Restore traffic", f"DC-{label}'s stable v1 takes traffic back.",
             f"Rollouts {label} restores 100% stable and 0% canary through the API. Istiod {label} distributes that change to Frontend {label}'s Envoy. Once applied, new matching calls reach stable v1. {peer}.",
             "Existing requests may finish. Route propagation is asynchronous; verify the proxy's route. Abort leaves the desired v2 template in place, so the rollout remains degraded until the release is corrected. GTM site shares do not change.",
             [abort, f"rollout-{site}-v2", "services", "stable-live", application, "topology" if site == "a" else "topology-b", "verify-release"],
             [f"{site}-rollouts", f"{site}-istiod", f"{site}-frontend", f"{site}-orders"],
             [f"{site}-route-weights", f"{site}-xds-client", f"{site}-orders"],
             state={f"weight_{site}": 0, f"rollout_{site}": "Aborted · v1 serving", "analysis": "Aborted", "release_fault": False},
             note="Argo Rollouts does not revert Git. Runtime traffic recovery and a reviewed Git revert are separate actions.", sources=["faq", "architecture"]),
        step("Reconcile Git", f"Revert only DC-{label}'s desired image.",
             f"A reviewed PR restores the DC-{label} image patch to known-good v1. After merge, its Argo CD reconciles that desired state. {peer}.",
             "Preserve the other site's overlay and traffic. Confirm the affected Rollout is healthy on v1, investigate the candidate failure, then use a new approved PR for a corrected image.",
             [f"image-{site}-v1", f"overlay-{site}", application, "rollout", "services", "baseline-routing", abort, "verify-release"],
             ["git", f"{site}-argo", f"{site}-rollouts", f"{site}-orders"], [f"git-{site}", f"{site}-reconcile", f"{site}-rollout"],
             state={f"rollout_{site}": "Healthy · v1", "analysis": "Idle", "revision": "v1 · reverted" if site == "a" else "A v2 · B v1 reverted", "gate": f"DC-{label} recovered"}, sources=["faq", "gitops"]),
    ]}
    return configure_flow(scenario, site, canary_weight)


SCENARIOS = [
    {"id": "traffic", "name": "Request journey", "icon": "route", "summary": "The initial request path: v1 in both sites, with no release in progress.", "steps": [
        step("Global entry", "A request enters through global steering.",
             "At the initial baseline, both datacenters serve v1. Users resolve shop.example.com and GTM selects a healthy site's LTM VIP.",
             "The diagram uses the logical chain Users → GTM → LTM. GTM represents DNS selection; the actual HTTPS connection goes to the selected VIP. No image, rollout or traffic-version weight changes in this flow.",
             ['dns', 'ltm'], ["client", "gtm"], ["dns"], note="All four steps retain v1 in A and v1 in B. Progressive delivery is a separate walkthrough.", sources=["dns"]),
        step("Site ingress", "The selected site accepts the request.",
             "For this request, GTM selects Datacenter A. Its F5 LTM forwards the connection to A's OpenShift HAProxy router.",
             "LTM forwards TCP/443. The OpenShift passthrough Route uses the hostname in TLS SNI to select the mesh gateway. B has the same independent entry path.",
             ['route', 'ltm', 'ingress-workload', 'gateway', 'tls-secret'], ["gtm", "a-ltm", "a-router"], ["request-a", "a-ingress"], sources=["ingress"]),
        step("Mesh ingress", "The mesh gateway routes to Frontend.",
             "HAProxy passes the encrypted connection to the local mesh ingress gateway. The gateway terminates external TLS and forwards the request to Frontend A.",
             "The Gateway and VirtualService define this north-south path. Frontend's local Envoy sidecar handles subsequent service calls inside the mesh.",
             ['gateway', 'ingress-workload', 'route', 'tls-secret', 'dependencies', 'namespace', 'mtls', 'topology'], ["a-router", "a-gateway", "a-frontend"], ["a-gateway", "a-frontend"], sources=["ingress"]),
        step("Local services", "Local services answer on v1.",
             "Frontend A calls Orders A, then Orders A calls the healthy local Catalog endpoint. Envoy applies service routing and mTLS on those calls.",
             "Orders is still 100% stable v1 in both datacenters. There is no new image, no active canary and no version split. The shared mesh prefers healthy local Catalog endpoints. Responses return over the established connections to the caller; GTM does not carry response traffic.",
             ['baseline-routing', 'services', 'rollout', 'dependencies', 'locality', 'namespace', 'mtls', 'topology', 'topology-b'], ["a-frontend", "a-orders", "a-catalog"], ["a-orders", "a-catalog"],
             note="This completes the initial request journey. Use Progressive delivery to introduce a new version.", sources=["routing", "locality"]),
    ]},
    {"id": "resilience", "name": "Local-first & failover", "icon": "mesh", "summary": "Prefer local endpoints, cross the mesh when the local service is unavailable, and steer away from a failed site.", "steps": [
        step("Prefer local", "Each site calls its own healthy endpoints.",
             "Both datacenters serve the same v1 release. Orders A prefers Catalog A; Orders B prefers Catalog B. Normal service calls stay inside their own datacenter.",
             "Catalog is discoverable across both networks, but locality preference selects healthy local endpoints first. Orders rollout hosts remain cluster-local; this example fails over the shared Catalog service.",
             ['locality', 'network-a', 'network-b', 'dependencies', 'topology', 'topology-b', 'namespace', 'mtls'], ["a-orders", "a-catalog", "b-orders", "b-catalog"], ["a-catalog", "b-catalog"], note="Availability changes here; application versions do not. Both sites remain on v1 throughout this walkthrough.", sources=["locality", "clusterlocal"]),
        step("Discover peers", "Both primaries discover remote endpoints.",
             "Each site has its own primary istiod. Istiod A watches cluster B’s Kubernetes API, and Istiod B watches cluster A’s Kubernetes API, using a remote credential in each direction.",
             "Both discovery paths are highlighted: A → API B and B → API A. The primaries discover services and endpoints through those APIs, rather than exchanging endpoints directly with each other. Each istiod then uses xDS to program its local Envoy proxies with local and remote destinations.",
             ['topology', 'topology-b', 'network-a', 'network-b', 'trust', 'discovery', 'eastwest-workload', 'eastwest', 'ltm'], ["a-istiod", "b-api", "b-istiod", "a-api"], ["discovery-a", "discovery-b"], note="The clusters have independent APIs, etcd and pod networks. Discovery traffic is separate from service data traffic.", sources=["mesh"]),
        step("Local failure", "All local Catalog A endpoints become unhealthy.",
             "In this example, every local Catalog A replica returns errors. Each calling Envoy observes its own failures and ejects those endpoints when its outlier threshold is reached.",
             "One failed replica does not force a cross-site call while enough healthy local capacity remains. Here all local endpoints are unavailable. Kubernetes readiness can also remove endpoints; passive Envoy ejection is a separate, per-proxy decision. GTM keeps routing to A's healthy ingress.",
             ['locality', 'dependencies', 'network-a', 'network-b'], ["a-orders", "a-catalog"], ["a-catalog"], state={"catalog_fault": True}, note="Failover depends on failure detection and healthy remote capacity. The first failed calls can still return errors.", sources=["locality"]),
        step("Cross-site call", "Orders A uses healthy Catalog B.",
             "With no healthy local Catalog endpoints remaining, the calling Envoy selects a healthy remote endpoint. The call crosses to B's east-west TCP/15443 gateway and reaches Catalog B.",
             "Workload mTLS is preserved across the networks. Users still enter A and Orders still runs in A; only the Catalog dependency call crosses the datacenter boundary.",
             ['eastwest', 'eastwest-workload', 'ltm', 'topology', 'topology-b', 'locality', 'discovery', 'trust', 'mtls', 'dependencies'], ["a-orders", "b-eastwest", "b-catalog"], ["cross-ab", "b-eastwest-catalog"], note="The source sidecar reaches only the destination east-west gateway. Failed in-flight calls are not automatically replayed: any retry policy must account for timeouts, capacity and request idempotency.", sources=["mesh", "locality"]),
        step("Return local", "A healthy local endpoint is preferred again.",
             "Catalog A recovers. Endpoints removed by readiness must be advertised again; endpoints ejected by Envoy must wait for their ejection period to expire. Eligible local endpoints can then receive new calls.",
             "This configuration uses passive outlier detection, not active mesh health probes. Successful calls keep recovered endpoints available; continued errors can eject them again. Discovery and connection reuse affect failback timing. Both sites remain on v1.",
             ['locality', 'dependencies', 'network-a', 'network-b'], ["a-orders", "a-catalog", "b-orders", "b-catalog"], ["a-catalog", "b-catalog"], state={"catalog_fault": False}, sources=["locality"]),
        step("Whole-site loss", "If all of A is lost, the entry path must move.",
             "Now consider a larger failure: Datacenter A becomes unreachable. Clients cannot reach its ingress, so an east-west service call cannot rescue that request.",
             "Health monitors detect A's failure while B's independent control plane keeps operating. Existing sessions and cached A records can fail during this detection window.",
             ['failover', 'dns', 'ltm'], ["gtm", "a-ltm", "b-istiod"], [], state={"failed_a": True, "sync_a": "Unreachable", "rollout_a": "Unavailable", "analysis": "Detecting A outage"}, sources=["dns", "mesh"]),
        step("Steer to B", "GTM selects B for new DNS answers.",
             "Global health checks withdraw A's VIP. New or refreshed clients follow the logical path GTM → LTM B → HAProxy B → mesh gateway B and local v1 services.",
             "This is north-south site failover, separate from the earlier east-west Catalog failover. DNS caches and existing connections need time to expire or retry. B needs full-load capacity and resilient data dependencies.",
             ['failover', 'dns', 'ltm', 'route', 'gateway', 'ingress-workload', 'tls-secret', 'dependencies'], ["client", "gtm", "b-ltm", "b-router", "b-gateway", "b-frontend", "b-orders", "b-catalog"], ["dns", "request-b", "b-ingress", "b-gateway", "b-frontend", "b-orders", "b-catalog"], state={"site_a": 0, "analysis": "B absorbing load"}, sources=["dns"]),
        step("Restore A", "Validate the recovered site before rejoining.",
             "Restore A, wait for Git reconciliation and healthy workloads, then verify synthetic requests and dependencies before re-enabling its VIP.",
             "The final frame shows the restored 50:50 target. Production recovery should ramp participation gradually, observing errors, latency, capacity and data consistency.",
             ['failover', 'dns', 'ltm', 'application', 'rollout', 'dependencies', 'locality'], ["gtm", "a-ltm", "b-ltm", "a-orders", "a-catalog", "b-orders", "b-catalog"], ["request-a", "request-b", "a-catalog", "b-catalog"], state={"failed_a": False, "site_a": 50, "sync_a": "Synced", "rollout_a": "Healthy · v1", "analysis": "Recovered"}, sources=["dns", "locality"]),
    ]},
    {"id": "delivery", "name": "Progressive delivery", "icon": "layers", "summary": "Approve → Git PR → merge → local auto-sync → local canary. Finish A before changing B.", "steps": [
        step("Baseline", "v1 is stable in both sites.",
             "Both sites are already deployed and serving. This frame is a snapshot of the starting state; no sync or release is in progress.",
             "The shared base contains the Rollout, Services, routing and analysis. A and B have independent image patches and Argo CD Applications. Changing only one overlay leaves the other site's rendered resources unchanged.",
             ["rollout", "services", "baseline-routing", "analysis", "base", "overlay-a", "image-a-v1", "overlay-b", "image-b-v1", "application", "application-b"],
             note="Highlights identify the current action. Healthy components in the other site remain visible without being highlighted.", sources=["routing", "autosync"]),
        step("Approve A", "Approve the pipeline for site A.",
             "CI has built, tested and published an immutable Orders v2 image. A release operator supplies that verified digest to a pipeline run targeting DC-A, then an authorized reviewer approves its protected environment.",
             "The configuration uses GitHub Actions as a concrete example. Required reviewers must be configured on release-dc-a; merely naming an environment does not create an approval gate. At this point Git and both clusters still declare v1.",
             ["pipeline", "pipeline-script", "overlay-a", "image-a-v1"], ["coordinator"], [], state={"gate": "Approve A Git change"}, sources=["pipeline"]),
        step("Merge A", "The approved pipeline proposes A's Git change.",
             "The job changes only overlays/dc-a/orders-image.yaml, commits it to a release branch and opens a pull request. After checks and review, an authorized reviewer merges it into main.",
             "The diagram shows the merged result. A branch commit or an unmerged PR cannot deploy because Argo CD tracks main. B's image patch and the shared base are unchanged. The pipeline does not call Argo CD to sync.",
             ["pipeline", "pipeline-script", "image-a-v2", "overlay-a", "application"], ["coordinator", "git"], ["pipeline-git"], state={"sync_a": "OutOfSync", "revision": "v2 → DC-A", "gate": "A PR merged"}, sources=["autosync", "pipeline"]),
        step("Sync A", "Argo CD A detects the merged change.",
             "Argo CD periodically refreshes Git; an optional repository webhook can shorten detection time. A renders overlays/dc-a and auto-syncs the changed Rollout CR to A’s Kubernetes API. Rollouts A watches that CR and creates the candidate ReplicaSet.",
             "B may refresh the same Git commit, but overlays/dc-b renders the same manifests, so there is no B rollout. Scoped ignore rules preserve Rollouts-owned weights and Service hash selectors. Synced describes desired resources, not release health.",
             ["rollout-a-v2", "application", "overlay-a", "image-a-v2", "base", "services", "baseline-routing", "analysis", "namespace", "topology"], ["git", "a-argo", "a-rollouts", "a-orders"], ["git-a", "a-reconcile", "a-rollout"], state={"sync_a": "Synced", "rollout_a": "Preparing v2"}, sources=["autosync", "gitops", "routing"]),
        step("A · 10%", "Only A receives a 10% canary.",
             "Rollouts A writes 90% stable and 10% canary to the VirtualService through A's API. Istiod watches that configuration and pushes xDS to Frontend A's Envoy. That proxy then routes Orders calls to the local ReplicaSets selected by the stable/canary Services.",
             "B continues on v1. Route propagation is asynchronous; verify the caller proxy has received it. At a 50:50 site mix, estimated global v2 share is 5%. Git still stores 100/0 initial route weights; the 90/10 YAML is explicitly a live observation owned by Rollouts.",
             ["rollout-a-v2", "services", "virtualservice", "baseline-routing", "analysis", "application", "topology", "mtls"], ["a-rollouts", "a-istiod", "a-frontend", "a-orders"], ["a-route-weights", "a-xds-client", "a-orders"], state={"weight_a": 10, "rollout_a": "Canary · 10%", "analysis": "A observing"}, sources=["routing", "analysis"]),
        step("A · 50%", "A passes analysis and pauses at 50%.",
             "The 10% analysis passes; Rollouts A raises traffic to 50% and checks the candidate again. The simulated success rate is 99.8%, above the 99% gate, with sufficient request volume.",
             "The AnalysisTemplate selects the candidate ReplicaSet and checks both traffic volume and success rate. Empty or NaN data does not pass. After the finite inline analyses, A stops at the final pause. Those completed runs do not keep measuring during the pause; inspect current telemetry before promotion. Inconclusive or errored analysis needs investigation, not forced promotion.",
             ["analysis", "rollout-a-v2", "services", "live-50", "application"], ["a-rollouts", "a-istiod", "a-frontend", "a-orders", "a-metrics"], ["a-route-weights", "a-xds-client", "a-orders", "a-observe"], state={"weight_a": 50, "rollout_a": "Paused · 50%", "analysis": "A passed · 99.8%"}, note="Simulate the alternate outcome where this 50% analysis fails. A aborts; B stays on v1.", sources=["analysis", "canary"]),
        step("Promote A", "Approve A's local rollout to finish.",
             "An authorized human or approval-gated job resumes A's final Rollout pause. Rollouts A promotes the candidate to stable; A now serves v2 for all Orders calls.",
             "Verify A is Healthy and fully promoted on the approved digest, then check full-load errors, latency, capacity and dependency requests before allowing B. This controller action needs scoped access to A's Rollout; it does not change B's Git overlay or invoke Argo CD. B still declares and serves v1.",
             ["promote-a", "rollout-a-v2", "analysis", "services", "stable-live", "image-b-v1"], ["coordinator", "a-rollouts", "a-istiod", "a-frontend", "a-orders"], ["approve-a", "a-route-weights", "a-xds-client", "a-orders"], state={"weight_a": 100, "rollout_a": "Healthy · v2", "analysis": "A passed", "gate": "A healthy · B gated"}, sources=["canary"]),
        step("Merge B", "Approve a separate Git change for B.",
             "With A verified, a reviewer approves the B pipeline run using the same immutable digest. Its read-only check verifies A's image, observed generation and fully promoted state before writing B's patch and opening a second PR.",
             "After B's PR is reviewed and merged, only B is OutOfSync. A's desired resources remain unchanged. If the PR waits, recheck A at the merge gate. Independent Argo CD instances do not provide this cross-site release approval.",
             ["pipeline", "pipeline-script", "image-b-v2", "overlay-b", "application-b"], ["coordinator", "git"], ["pipeline-git"], state={"sync_b": "OutOfSync", "revision": "v2 → DC-B", "gate": "B PR merged"}, sources=["pipeline", "autosync"]),
        step("Sync B", "Argo CD B reconciles its own overlay.",
             "B detects its merged overlay change and auto-syncs the Rollout CR to B’s Kubernetes API. Rollouts B watches that CR and prepares v2 while A stays healthy on v2.",
             "The same controller ownership rules apply in B: Argo CD declares the pod template, Services and routing objects; Rollouts controls runtime selectors, route weights and analysis. A is not resynchronized for a B-only image patch.",
             ["rollout-b-v2", "application-b", "overlay-b", "image-b-v2", "base", "services", "baseline-routing", "analysis", "namespace", "topology-b"], ["git", "b-argo", "b-rollouts", "b-orders"], ["git-b", "b-reconcile", "b-rollout"], state={"sync_b": "Synced", "rollout_b": "Preparing v2"}, sources=["autosync", "gitops", "routing"]),
        step("B · 10%", "B begins its own 10% canary.",
             "Rollouts B writes 90% stable and 10% canary through B's API. Istiod B pushes the updated route to Frontend B's Envoy, which sends matching Orders calls to local v1/v2 endpoints. A remains on v2.",
             "The estimated global v2 share is now 55% at a 50:50 incoming site mix. Cluster-local Orders hosts prevent either site's stable/canary endpoints from mixing with the other's independent release state.",
             ["rollout-b-v2", "services", "virtualservice", "baseline-routing", "analysis", "application-b", "topology-b", "mtls"], ["b-rollouts", "b-istiod", "b-frontend", "b-orders"], ["b-route-weights", "b-xds-client", "b-orders"], state={"weight_b": 10, "rollout_b": "Canary · 10%", "analysis": "B observing"}, sources=["routing", "clusterlocal"]),
        step("B · 50%", "B must pass its own health gates.",
             "B's 10% analysis passes, traffic advances to 50%, and its second inline analysis passes. B then pauses for final approval.",
             "B uses its own candidate metrics and traffic-volume threshold. Completed inline analyses stop measuring during the pause; check fresh telemetry before promotion. The failure button replays the alternate outcome of a failed 50% analysis. A stays on v2.",
             ["analysis", "rollout-b-v2", "services", "live-50", "application-b"], ["b-rollouts", "b-istiod", "b-frontend", "b-orders", "b-metrics"], ["b-route-weights", "b-xds-client", "b-orders", "b-observe"], state={"weight_b": 50, "rollout_b": "Paused · 50%", "analysis": "B passed · 99.8%"}, sources=["analysis", "canary"]),
        step("Promote B", "Approve B to finish the release.",
             "An authorized approver resumes B's final local pause. Rollouts B promotes its candidate to stable, and all B Orders calls now reach v2.",
             "Confirm B is Healthy on the approved digest, then check full-load errors, latency and dependencies. The canary's finite inline analyses have finished; ongoing monitoring is still needed. A remains healthy on v2.",
             ["promote-b", "rollout-b-v2", "analysis", "services", "stable-live"], ["coordinator", "b-rollouts", "b-istiod", "b-frontend", "b-orders"], ["approve-b", "b-route-weights", "b-xds-client", "b-orders"], state={"weight_b": 100, "rollout_b": "Healthy · v2", "analysis": "Both passed", "gate": "Both sites verified"}, sources=["canary"]),
        step("Complete", "Both sites now serve the approved v2.",
             "This is the final steady-state snapshot: both Applications are Synced and both local Rollouts are Healthy on v2. There is no simultaneous update or sync being triggered here.",
             "The chain was approved pipeline → A Git merge → A sync and canary → A promotion → separate B approval and Git merge → B sync and canary → B promotion. GTM's normal 50:50 target stayed unchanged throughout.",
             ["image-a-v2", "image-b-v2", "rollout-a-v2", "rollout-b-v2", "application", "application-b", "services", "stable-live"], state={"revision": "v2 · both sites", "gate": "Release complete"}, sources=["autosync", "canary"]),
    ]},
    rollback_scenario(),
    make_certificate_flow(step),
]

# Preserve complete reference dependencies; the UI presents incremental config_items.
for scenario in SCENARIOS:
    for item in scenario["steps"]:
        if "analysis" in item["configs"] and "telemetry" not in item["configs"]:
            item["configs"].append("telemetry")
        if any(edge.endswith("route-weights") for edge in item["edges"]):
            if "architecture" not in item["sources"]:
                item["sources"].append("architecture")
            if "verify-release" not in item["configs"]:
                item["configs"].append("verify-release")
        if "discovery" in item["configs"]:
            item["configs"].append("remote-secret")

    if scenario["id"] != "rollback":
        configure_flow(scenario)


BASE_STATE = {"weight_a": 0, "weight_b": 0, "site_a": 50, "failed_a": False,
              "catalog_fault": False, "release_fault": False, "release_fault_site": "a", "gate": "Approval gates", "sync_a": "Synced", "sync_b": "Synced",
              "rollout_a": "Healthy · v1", "rollout_b": "Healthy · v1", "analysis": "Idle", "revision": "v1 · both sites"}


def get_state(scenario_id, index, site="a", canary_weight=10):
    scenario = next((s for s in SCENARIOS if s["id"] == scenario_id), None)
    if scenario_id == "rollback":
        scenario = rollback_scenario(site, canary_weight)
    if scenario is None or not 0 <= index < len(scenario["steps"]):
        raise ValueError("Unknown scenario or step")
    state = deepcopy(BASE_STATE)
    for item in scenario["steps"][:index + 1]:
        state.update(item["state"])
    state["site_b"] = 100 - state["site_a"]
    state["global_v2"] = (state["site_a"] * state["weight_a"] + state["site_b"] * state["weight_b"]) / 100
    state["healthy_clusters"] = 1 if state["failed_a"] else 2
    return {"scenario": scenario_id, "step": index, "state": state,
            **({"flow": scenario, "rollback": {"site": site, "weight": canary_weight}} if scenario_id == "rollback" else {}),
            "active_nodes": scenario["steps"][index]["nodes"], "active_edges": scenario["steps"][index]["edges"],
            "events": [s["event"] for s in scenario["steps"][:index + 1]]}


DEMO = {"scenarios": SCENARIOS, "configs": CONFIGS, "sources": SOURCES}
