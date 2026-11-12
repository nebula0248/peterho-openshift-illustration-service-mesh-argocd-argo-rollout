"""Per-step configuration introductions and actor-attributed changes.

Reference dependencies remain in step['configs']; only config_items are shown.
Introductions are deterministic within each flow, independent of visit history.
"""
from copy import deepcopy
from difflib import unified_diff
from textwrap import dedent

from configurations import CONFIGS


def entry(key, title, actor, scope, purpose, code, *, kind="runtime", language="text", file=None):
    modes = {"diff": "Changed YAML fields · illustrative diff", "action": "Manual action", "runtime": "Runtime observation · simulated"}
    return dict(id=key, title=title, actor=actor, scope=scope, purpose=purpose,
                code=dedent(code).strip() + "\n", kind=kind, language=language,
                mode=modes[kind], file=file or f"observations/{key}.txt")


def diff(key, title, actor, scope, purpose, file, before, after):
    code = "".join(unified_diff(before.splitlines(True), after.splitlines(True),
                                fromfile=f"before/{file}", tofile=f"after/{file}", n=2))
    return entry(key, title, actor, scope, purpose, code, kind="diff", language="diff", file=file)


def runtime(key, title, actor, scope, purpose, *lines):
    return entry(key, title, actor, scope, purpose, "\n".join(lines))


def image_change(site, old, new, *, live=False):
    label = site.upper()
    if live:
        file = f"live/dc-{site}/orders-rollout.yaml"
        template = "spec:\n  template:\n    spec:\n      containers:\n      - name: orders\n        image: registry.example.com/shop/orders:{version}.0.0\n"
        before, after = (template.format(version=v) for v in (old, new))
        actor, title = f"System · Argo CD {label}", "Apply the image change to Rollout"
        purpose = "Only the pod-template image changes. The Rollout strategy remains as introduced at baseline. Tags represent the approved immutable digests in this teaching view."
    else:
        file = CONFIGS[f"image-{site}-v1"]["file"]
        before, after = (CONFIGS[f"image-{site}-v{v}"]["code"] for v in (old, new))
        actor, title = "Pipeline + human PR review", f"Git image patch · DC-{label}"
        purpose = f"The pipeline writes only DC-{label}'s image patch; a reviewer merges it. Readable tags represent the approved digests; the other overlay stays unchanged."
        if new == 1:
            actor = "Human · reviewed Git revert"
            purpose = f"An engineer restores DC-{label}'s known-good image in a revert PR; merge follows review. The other site's overlay is unchanged. Tags represent the approved digests."
    return diff(f"{'live' if live else 'git'}-image-{site}-{new}", title, actor, f"DC-{label}", purpose, file, before, after)


def route_change(site, old, new, *, promoted=False):
    def route(weight):
        return ("http:\n- name: primary\n  route:\n"
                f"  - destination: {{host: orders-stable}}\n    weight: {100-weight}\n"
                f"  - destination: {{host: orders-canary}}\n    weight: {weight}\n")
    purpose = "Argo Rollouts updates the live VirtualService. Istiod distributes the route to the caller's Envoy; Git's baseline weights stay unchanged."
    if promoted:
        purpose += " Stable now selects v2, so 100% stable means 100% v2."
    return diff(f"route-{site}-{old}-{new}", f"Live route · {100-old}/{old} → {100-new}/{new}",
                f"System · Argo Rollouts {site.upper()}", f"DC-{site.upper()}", purpose,
                f"live/dc-{site}/orders-virtualservice.yaml", route(old), route(new))


def selector_change(site, service, old, new):
    def selector(version):
        return f"metadata: {{name: orders-{service}, namespace: shop}}\nspec:\n  selector:\n    app: orders\n    rollouts-pod-template-hash: <{site}-v{version}-hash>\n"
    return diff(f"selector-{site}-{service}-{new}", f"{service.title()} Service → v{new} ReplicaSet",
                f"System · Argo Rollouts {site.upper()}", f"DC-{site.upper()}",
                "Only the controller-owned hash selector changes. Hashes are illustrative placeholders; the Service manifest in Git still selects app: orders.",
                f"live/dc-{site}/orders-{service}-service.yaml", selector(old), selector(new))


def delivery_changes(index):
    if index in (0, 12):
        return []
    if index == 1:
        return [entry("approve-a", "Approve the A pipeline run", "Human · release reviewer", "DC-A",
                      "The workflow and helper below are introduced once. Approval releases this run; it does not yet edit Git or call Argo CD.",
                      "Target environment: release-dc-a\nInput: verified Orders v2 image digest\nReviewer decision: pending → approved\nGit image: v1 (unchanged)", kind="action")]
    if index in (2, 7):
        site = "a" if index == 2 else "b"
        changes = []
        if site == "b":
            changes.append(entry("approve-b", "Approve B after verifying A", "Human + pipeline", "DC-B",
                                 "Reuse the workflow introduced in step 2. A must still be fully promoted on the same digest before B's merge.",
                                 "Target environment: release-dc-b\nApproval: pending → approved\nRead-only gate: A Healthy; current generation observed; stableRS = currentPodHash\nApproved image: exactly the digest promoted in A", kind="action"))
        return changes + [image_change(site, 1, 2)]
    site = "a" if index < 7 else "b"
    label = site.upper()
    if index in (3, 8):
        return [image_change(site, 1, 2, live=True), selector_change(site, "canary", 1, 2),
                runtime(f"replicas-{site}", "Prepare the candidate ReplicaSet", f"System · Rollouts {label}", f"DC-{label}",
                        "The controller derives the new ReplicaSet from the updated pod template. This is not another Git edit.",
                        "New candidate ReplicaSet: created from the v2 pod template",
                        "Candidate pods: start → pass readiness", "Stable Service: still selects the v1 ReplicaSet",
                        "Live route: still 100% stable / 0% canary until ready")]
    if index in (4, 9):
        return [route_change(site, 0, 10),
                runtime(f"analysis-start-{site}", "Create the 10% AnalysisRun", f"System · Rollouts {label}", f"DC-{label}",
                        "After the configured warm-up pause, create a local AnalysisRun from the existing AnalysisTemplate. No template edit is needed.",
                        "AnalysisRun: created → Running", f"canary-hash argument: <{site}-v2-hash>",
                        "Metrics: candidate request volume + success rate", "Routing delivery: Istiod → Frontend Envoy (xDS)")]
    if index in (5, 10):
        return [route_change(site, 10, 50),
                runtime(f"analysis-pass-{site}", "Pass analysis, then pause", f"System · Rollouts {label}", f"DC-{label}",
                        "The strategy and AnalysisTemplate are unchanged. The controller advances through the already-declared steps.",
                        "10% AnalysisRun: Running → Successful", "After 50% warm-up: create a second AnalysisRun → Successful",
                        "Simulated success rate: 99.8%; sufficient request volume", "Rollout: final indefinite pause; waiting for promotion",
                        "Completed inline runs stop measuring; inspect fresh telemetry before approving")]
    if index in (6, 11):
        return [entry(f"promote-{site}", "Resume the local approval pause", "Human / approved automation", f"DC-{label}",
                      "An approved operator action resumes this Rollout. It changes neither the Git image nor the other cluster.",
                      f"kubectl argo rollouts promote orders -n shop --context=dc-{site}", kind="action", language="shell", file=f"release/promote-dc-{site}.sh"),
                selector_change(site, "stable", 1, 2), route_change(site, 50, 0, promoted=True)]
    raise ValueError("Unknown delivery configuration step")


RESILIENCE_EVENTS = {
    1: ("Discover the remote endpoints", "System · both Istiod primaries", "Both clusters", "Endpoint discovery updates proxy configuration; no workload YAML is edited.",
        ["Istiod A watches API B → adds remote Catalog B destinations", "Istiod B watches API A → adds remote Catalog A destinations", "Each Istiod distributes endpoint/network information to its own proxies"]),
    2: ("Eject unhealthy local endpoints", "System · Orders A Envoy", "DC-A", "No YAML edit. The existing outlier-detection policy reacts to observed errors in this caller.",
        ["Local Catalog endpoints: healthy → returning errors → ejected", "Trigger: configured consecutive 5xx threshold reached", "Remote Catalog B: healthy; eligible for failover", "GTM: unchanged; A ingress is still available"]),
    3: ("Select the remote Catalog endpoint", "System · Orders A Envoy", "A → B", "No new VirtualService or DestinationRule. The existing locality policy selects a reachable remote destination.",
        ["Selected destination: Catalog A → Catalog B", "Transport: source sidecar → B east-west VIP:15443 → Catalog B", "Workload mTLS: preserved", "Orders location: A; application versions: v1"]),
    4: ("Make recovered local endpoints eligible", "System · endpoint discovery + Envoy", "DC-A", "No YAML edit. Recovery changes endpoint eligibility under the policy already shown.",
        ["Readiness-removed endpoints: advertised again when ready", "Ejected endpoints: eligible after ejection expiry", "Successful local calls: keep recovered endpoints available", "New eligible calls: prefer local Catalog A again"]),
    5: ("Detect the site outage", "System · F5 health monitoring", "DC-A", "Health status changes; the configured probe and DNS policy remain the same. This frame is the detection window.",
        ["A ingress: reachable → unreachable", "GTM monitor: detecting failure", "Cached DNS / existing connections: may still point to A"]),
    6: ("Withdraw A from new DNS answers", "System · F5 GTM", "Global entry", "No policy edit. F5 applies its existing health-based selection policy after detecting A's failure.",
        ["Eligible site VIPs: A + B → B only", "New/refreshed answers: B VIP 192.0.2.20", "Illustrated eventual site mix: A 0% / B 100%", "Cached answers and connections: do not move instantly"]),
    7: ("Restore and gradually re-enable A", "Operator + reconciliation + F5", "DC-A / global entry", "Repair infrastructure, reconcile the existing desired state and approve re-entry after validation. No release-image edit is made.",
        ["A infrastructure: restored; GitOps reconciles existing v1", "Validation: workloads, dependencies, synthetic requests, capacity", "Operator: re-enable A and gradually ramp DNS participation", "Final illustrated target: A 50% / B 50%"]),
}


def rollback_changes(index, site, weight):
    label = site.upper()
    if index == 0:
        return [runtime(f"failing-analysis-{site}-{weight}", "Observe the failing candidate", f"System · AnalysisRun in {label}", f"DC-{label}",
                        "Continue from the delivery canary. The Rollout and AnalysisTemplate were introduced there; only the new measurement is shown.",
                        f"Current canary exposure: {weight}%", "Candidate error rate: 4.8%; success rate: 95.2%",
                        "Configured success threshold: 99% → measurement fails",
                        "Traffic has not yet been restored in this frame")]
    if index == 1:
        return [runtime(f"abort-{site}", "Abort after the failure limit", f"System · Argo Rollouts {label}", f"DC-{label}",
                        "The inline analysis fails and aborts the local rollout automatically. No operator command or Git edit is required for this recovery.",
                        "AnalysisRun: Running → Failed after configured limit", "Rollout: aborted; stable v1 continues serving",
                        "Desired image in Git and Rollout: still v2"), route_change(site, weight, 0)]
    return [image_change(site, 2, 1), image_change(site, 2, 1, live=True),
            runtime(f"recovered-{site}", "Confirm the intended v1 state", f"System · Argo CD + Rollouts {label}", f"DC-{label}",
                    "A reviewed site-only revert closes the GitOps loop after runtime traffic recovery.",
                    "Rollout: degraded desired v2 → Healthy on v1", "Route: remains 100% stable / 0% canary",
                    "Other site's image and traffic: unchanged")]


def configure_flow(scenario, site="a", weight=10):
    """Attach just this step's changes and configurations first introduced here."""
    seen = set()
    flow = scenario["id"]
    for index, item in enumerate(scenario["steps"]):
        references = item["configs"]
        changes = []
        summary = "Existing configuration, introduced once as this flow reaches each component. No configuration is edited by this request."
        if flow == "delivery":
            # Put shared prerequisites at baseline; all later release frames are deltas.
            references = ({0: item["configs"] + ["namespace", "topology", "topology-b", "mtls"],
                           1: ["pipeline", "pipeline-script"], 4: ["verify-release"]}).get(index, [])
            changes = delivery_changes(index)
            summary = ("Baseline definitions, shown once for this flow. Later steps show only manual actions and controller changes."
                       if index == 0 else "Only this step's changes are shown. Earlier definitions remain in place."
                       if index < 12 else "No further configuration change. Both sites are verified on v2; all earlier Git and controller changes remain in effect.")
        elif flow == "resilience":
            if index in RESILIENCE_EVENTS:
                title, actor, scope, purpose, lines = RESILIENCE_EVENTS[index]
                changes = [runtime(f"resilience-{index}", title, actor, scope, purpose, *lines)]
            summary = ("Existing local-first policy and prerequisites. Later runtime changes are shown without repeating these definitions."
                       if index == 0 else "Runtime changes are shown first. Any newly introduced reference below is existing setup, not a configuration edit in this step.")
        elif flow == "rollback":
            references = []
            changes = rollback_changes(index, site, weight)
            summary = "Continue from the progressive-delivery configuration. Show only the failed site's measurement, recovery or Git changes."
        elif flow == "certificates":
            changes = item.pop("changes", [])
            summary = ("External-CA installation prerequisites, shown once. This flow starts after both sites are configured; it does not migrate a running mesh."
                       if index == 0 else "Only new runtime changes and first references are shown. The installed issuer, mesh and trust settings stay unchanged.")
        items = changes.copy()
        for key in references:
            if key in seen:
                continue
            seen.add(key)
            reference = deepcopy(CONFIGS[key])
            actor = "Read-only commands · first shown here" if key == "verify-release" else "Existing setup · first shown here"
            reference.update(id=key, kind="reference", actor=actor)
            if key == "cert-request":
                reference.update(actor="System · istio-csr A creates this resource", kind="runtime")
            elif key == "cert-verify":
                reference.update(actor="Operator · read-only inspection")
            items.append(reference)
        item["config_items"] = items
        item["config_summary"] = summary
    return scenario
