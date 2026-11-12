# Mesh Lab

A black-background, interactive architecture demo of two independent OpenShift 4.22 clusters using Service Mesh 3, Argo CD / OpenShift GitOps and Argo Rollouts for active-active progressive delivery.

## Run locally

Python 3.10 or newer is sufficient. No pip packages, npm packages, build step, CDN, or external fonts are needed.

```sh
./start.sh
```

The executable script works from any directory when invoked by its path. Press **Ctrl+C** to stop the server. You can also run `python3 app.py` directly.

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The initial tab is Request journey. To use another port:

```sh
./start.sh --port 8080
```

The server binds to loopback by default. For an intentionally network-accessible demo, use `--host 0.0.0.0`. This is a local teaching server, not a production application server.

## Explore

- **Request journey:** the initial logical Users → GTM → LTM → HAProxy → mesh gateway → Frontend → Orders → Catalog path. Both sites stay on v1; no release occurs.
- **Local-first & failover:** local Catalog preference → discovery prerequisites → local endpoint failure → remote Catalog through the destination east-west gateway → local failback → whole-site loss → DNS failover → recovery.
- **Progressive delivery:** v1 baseline → approve A pipeline → merge A PR → auto-sync A → 10% / 50% analysis → promote A → approve and merge B PR → auto-sync B → 10% / 50% analysis → promote B → steady-state v2.
- **Canary rollback:** failed analysis in A or B → that site’s stable traffic restored → its reviewed Git revert. B failures preserve A’s promoted v2.
- **Mesh cert rotation:** seven architecture discussion stages: shared trust → renew in A → activate in A → independent B renewal → verify cross-site trust → shared issuer outage → recovery. The diagram groups cert-manager and istio-csr into each site's certificate management role. Walkthrough text explains responsibilities and resilience; YAML, request status, agent settings and verification commands remain in Configuration. Open directly at `/#certificates/1`.

The full-width diagram separates ingress, Service Mesh data plane and platform layers. Shared Git and the approved release pipeline sit between the two datacenters. The logical Users → GTM → LTM chain represents DNS selection; actual HTTPS connects to the selected VIP. Only the current step’s control and east-west connections are drawn, keeping the layers readable. Delivery highlights only the action in the site currently being released; the initial and completed snapshots have no active release highlights.

Click any numbered step to jump directly, or play the walkthrough at seven seconds per step. Previous/next and reset buttons are available. Left/right arrow keys navigate; Space plays or pauses when focus is outside an interactive control. The app respects reduced-motion preferences.

Component hover popups are removed. The Configuration tab follows changes through each flow. Full definitions are introduced once; subsequent steps show only the changed YAML fields, manual actions or simulated runtime transitions, with the responsible human, pipeline or controller identified. Progressive delivery starts with its baseline Rollout, Services, routing, analysis and site overlays, then shows image patches, live Rollout updates, Service hash changes and traffic-weight diffs. Failover shows runtime decisions without pretending they require YAML edits. The final steady state explicitly has no further changes. Introductions follow step order, so direct links and backward navigation remain consistent. Copy, expand and step download use the displayed change; the Architecture notes download retains the complete configuration catalog. “Simulate failed analysis” at either site’s 10% or 50% stage opens rollback with the same site and exposure. The rollback tab also lets you select the failed site. At 50%, this replays an alternate failed analysis, rather than implying that a completed analysis keeps running during the pause. The global Orders v2 metric opens a traffic explorer with independent sliders for site request share and local v2 weights. Architecture notes include a download of all teaching configurations.

On desktop, the whole right panel stays pinned while the left column scrolls, including down to the activity log. Long descriptions and configurations scroll inside that panel; previous/next controls remain available. All 13 progressive-delivery steps have connector lines, including the transition between rows. On small screens, the detail panel stacks below the diagram and the canvas can scroll horizontally. URL fragments preserve/share a scenario and step, for example `/#delivery/4`. Failure context is preserved too: `/#rollback/1/b/50`.

## Architecture decisions

1. **Two real cluster boundaries.** Separate APIs, etcd quorums, nodes and pod networks. Service Mesh is multi-primary/multi-network in **sidecar mode**, with common mesh identity, common root trust and distinct cluster/network IDs. “Federation” here means an Istio multicluster mesh, not the legacy Service Mesh 2 federation API.
2. **DNS is separate from application traffic.** The user's “L5 GTM” is interpreted as **F5 GTM / BIG-IP DNS**. It returns a site VIP. Client HTTPS then goes directly to LTM, HAProxy and the mesh ingress gateway. LTM and the OpenShift Route use TLS passthrough; the mesh gateway terminates external TLS.
3. **Cross-network data uses the destination gateway.** Dedicated LTM TCP/15443 VIPs expose east-west gateways. A source sidecar can reach the remote gateway directly. This path bypasses north-south HAProxy. Remote Kubernetes API discovery is separate control-plane traffic: Istiod A watches API B, and Istiod B watches API A. Step 2 highlights both directions on separate labeled paths.
4. **Canary cohorts are site-local.** Frontend and Orders hostnames, including orders-stable and orders-canary, use `clusterLocal`. Catalog is shared and can use locality failover. This avoids independently promoted stable/canary endpoints mixing across sites.
5. **Controller ownership is explicit.** Argo CD owns desired manifests; Argo Rollouts owns route weights and hash selectors. Scoped ignore rules and sync options prevent them fighting. Rollouts writes the VirtualService through the API; local Istiod distributes xDS to the calling Frontend Envoy, which implements the route. The animation shows this logical control path and includes verification commands. Argo CD being Synced does not imply a healthy, finished rollout.
6. **Site sequencing is external.** Separate repository overlays permit A-first rollout. The approved pipeline opens a PR for one image patch. After review and merge, that site’s Argo CD detects Git changes and auto-syncs; it requires no pipeline call to the Argo CD API. A separate approved B run verifies A is Healthy, at the current generation and fully promoted on the same digest before proposing B. Local promotion resumes each Rollout’s final pause through a separately authorized controller action. These independent controllers do not implement an atomic global release.
7. **Rollback is not a Git rewrite.** An aborted rollout sends new traffic back to stable but keeps the failed desired template. A reviewed Git revert restores the intended desired state.
8. **Failover is observed by each caller.** Passive outlier ejection is per Envoy. The example loses all local Catalog endpoints before showing a remote call. Readiness removal and Envoy ejection are separate mechanisms. Recovery depends on endpoint advertisement, ejection expiry and successful calls; active mesh health probes are not configured here.
9. **Analysis is finite.** Inline runs stop measuring when completed. Check fresh telemetry during the approval pause and validate full-load behavior after promotion, including latency, capacity and dependency checks. Inconclusive or errored results need investigation, not forced promotion.
10. **DNS ratios are not exact request ratios.** The global exposure calculation uses an illustrative incoming request mix. It assumes equal matching Orders call volume per incoming request. Cached DNS and existing connections do not instantly move on failure.
11. **Certificate issuance has its own diagram.** Venafi/private PKI sits between the sites. Service communication, grouped local certificate management and the mesh control plane have separate layers. Only the current step's paths are visible; request and response directions never overlap. The cross-site verification path includes B's east-west gateway. The status card emphasizes valid, renewing and renewed credentials; illustrative certificate serials stay in the technical configuration view.
12. **Mesh leaf rotation is independent of application delivery.** This alternative starts with cert-manager/istio-csr installed before Istio, a pinned shared public root, external signing and explicit workload ServiceAccounts. It is not a live migration from the built-in CA shown in other flows. Workload keys remain in the pod; the agent drives renewal and loads the result through SDS. Workload leaves do not use per-pod Certificate resources or Kubernetes TLS Secrets. The operator manages Istiod serving TLS separately. Applications, site weights and root trust remain unchanged.
13. **Choose a SPIFFE-capable issuer.** The cert-manager ACME issuer cannot issue the arbitrary URI SANs required by istio-csr. The flow therefore uses Venafi TPP with a private signing CA; external HTTPS certificates may use ACME independently. Provision scoped per-site API credentials, allow user-provided CSRs and required SANs/EKUs/lifetimes, and validate supported operator versions. The Venafi API transport CA is distinct from the mesh trust anchor.
14. **Leaf renewal is not root rollover.** Root rotation requires staged overlapping trust and coordinated issuer/leaf changes before old trust is retired. A central issuer outage does not instantly invalidate loaded leaves, but prolonged failure can break new connections at expiry and prevent new workloads from obtaining identities. Monitor issuance, loaded certificates, expiry and credential lifetime; do not assume automatic cross-cluster signer failover.

## Scope and prerequisites

All traffic, metrics, events, health states, certificate serials and release outcomes are deterministic teaching simulations. The app never contacts Kubernetes, F5, Argo CD, Venafi, a registry or a Git service.

The examples assume stateless applications, compatible APIs, independent data-tier resilience and failover capacity. The catalog includes gateway Deployments and Services, network/locality labels, mesh trust and remote-secret shapes, sidecar enrollment, workload manifests and a PodMonitor. Operators/CRDs, supported version selection, real network addresses, certificate provisioning, credentials and authenticated telemetry access remain environment prerequisites. The AnalysisTemplate checks both candidate success rate and request volume; tune its windows and verify metric labels against your telemetry.

**OpenShift 4.22 is the requested target architecture.** Pin Service Mesh, Istio, GitOps and Rollouts versions against Red Hat's supported compatibility matrix. The demo does not certify a particular version combination. F5 YAML is explicitly conceptual; other manifests are teaching excerpts rather than a deployment bundle.

## Files and validation

- `start.sh`: executable server launcher; forwards `--host`, `--port` and `--help` to the Python server.
- `app.py`: Python standard-library HTTP server; `/api/demo`, `/api/state`, `/healthz`.
- `demo.py`: technical narratives, step-to-file mappings, references and deterministic state transitions.
- `configuration_flow.py`: first introductions, actor-attributed YAML diffs and runtime changes for each flow step.
- `configurations.py`: 46 related YAML, shell and Python examples, with explicit ownership and scope.
- `certificate_flow.py`: certificate narratives and 9 additional configuration examples, including issuer, trust, IstioCSR, mesh overlays, workload identities, timer settings and verification.
- `static/index.html`, `static/styles.css`, `static/app.js`: responsive UI, accessible controls and animated SVG.
- `tests/test_demo.py`: initial v1 request state, reciprocal discovery, failover, approval/merge/sync sequencing, one-site highlights, local xDS propagation, A/B rollback at both exposure levels and state determinism.
- `tests/test_configuration_flow.py`: no repeated definitions, correct before/after weights, promotion identity and site-specific rollback deltas.
- `tests/test_certificates.py`: issuance versus SDS activation, independent site renewal, constant trust/application state, outage recovery and configuration references.
- `tests/test_configurations.py`: pipeline guard behavior, YAML relationships and Kustomize rendering that proves A-only changes leave B unchanged. YAML checks use optional PyYAML; the render check uses optional Kustomize. Neither is required by the demo server.

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile app.py demo.py configurations.py configuration_flow.py certificate_flow.py
node --check static/app.js   # Optional syntax check; Node is not needed to run.
```


## Concrete pipeline example

The configuration panel includes a GitHub Actions workflow and Python helper. This is one implementation of the generic approval → Git PR → merge contract; it is not a required OpenShift component. Configure required reviewers on `release-dc-a` and `release-dc-b`, protected-branch review/checks, a repository-scoped bot credential and a preprovisioned runner. The job consumes a verified immutable image digest from upstream CI. It never builds an unverified image or calls Argo CD sync.

The B proposal additionally uses read-only access to verify A’s exact image and fully promoted status. Recheck A at merge if a B PR waits. Promotion commands use separately scoped access to the target Rollout. Shared-base changes are outside this one-site image release: PR checks must reject unrelated file changes, because editing the base can affect both sites.

## Primary references

- [cert-manager Istio CSR integration and issuer constraints](https://cert-manager.io/docs/usage/istio-csr/)
- [Red Hat IstioCSR integration](https://docs.redhat.com/en/documentation/red_hat_openshift_service_mesh/3.3/html/installing/ossm-cert-manager)
- [cert-manager Venafi / CyberArk issuer](https://cert-manager.io/docs/configuration/venafi/)
- [Istio identity and certificate lifecycle](https://istio.io/latest/docs/concepts/security/)
- [Red Hat Service Mesh 3 multicluster](https://docs.redhat.com/en/documentation/red_hat_openshift_service_mesh/3.3/html/installing/ossm-multi-cluster-topologies)
- [Red Hat ingress gateways and Routes](https://docs.redhat.com/en/documentation/red_hat_openshift_service_mesh/3.3/html/gateways/ossm-getting-traffic-into-a-mesh)
- [Argo Rollouts Istio integration](https://argoproj.github.io/argo-rollouts/features/traffic-management/istio/)
- [Argo CD automated sync](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/)
- [GitHub environment approval gates](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)
- [Argo CD diff customization](https://argo-cd.readthedocs.io/en/stable/user-guide/diffing/)
- [Argo Rollouts analysis](https://argoproj.github.io/argo-rollouts/features/analysis/)
- [Istio multicluster traffic management](https://istio.io/latest/docs/ops/configuration/traffic-management/multicluster/)
- [Istio locality failover](https://istio.io/latest/docs/tasks/traffic-management/locality-load-balancing/failover/)
- [F5 global server load balancing](https://techdocs.f5.com/kb/en-us/products/big-ip-dns/manuals/product/bigip-dns-load-balancing-13-1-0/1.html)
