"""An external-CA variant of the mesh, installed before the renewal walkthrough.

Workload leaves use agent CSRs and SDS, not a Certificate/Secret per workload.
"""
from configurations import add
from configuration_flow import diff, runtime


add("cert-trust", "Pinned public mesh trust", "identity/mesh-root.yaml", "Both clusters · same public root",
    "PKI administrators distribute the verified public root before installing istio-csr. The CA private key stays in the external PKI. Replace the PEM placeholder; this is separate from the CA used to verify Venafi's HTTPS endpoint.", """
    apiVersion: v1
    kind: Namespace
    metadata:
      name: istio-csr
    ---
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: mesh-root
      namespace: istio-csr
    data:
      root-cert.pem: |
        -----BEGIN CERTIFICATE-----
        <verified-public-mesh-root-CA-PEM>
        -----END CERTIFICATE-----
    """)

add("cert-issuer", "Local Venafi Issuer + credential reference", "identity/venafi-issuer.yaml", "Each cluster · istio-system",
    "Create independent local objects in A and B. Supply different scoped access tokens through secret management, never plaintext Git. Venafi must allow user-provided CSRs, SPIFFE URI SANs, client/server authentication and the requested lifetime. The HTTPS caBundle verifies the Venafi API, not mesh peers.", r"""
    # Each site's cert-manager and istio-csr installation is a prerequisite.
    # istio-system must exist before these objects are created.
    apiVersion: v1
    kind: Secret
    metadata:
      name: venafi-credentials
      namespace: istio-system
    type: Opaque
    stringData:
      access-token: <provision-this-sites-token-outside-Git>
    ---
    apiVersion: cert-manager.io/v1
    kind: Issuer
    metadata:
      name: venafi-mesh
      namespace: istio-system
    spec:
      venafi:
        zone: 'mesh\cluster-local'
        tpp:
          url: https://venafi.example.com/vedsdk
          caBundle: <base64-PEM-of-Venafi-HTTPS-CA>
          credentialsRef:
            name: venafi-credentials
    """, mode="Issuer: Git · credential Secret: provisioned outside Git")

add("cert-csr", "Operator-managed istio-csr", "identity/istio-csr.yaml", "Each cluster · install before Istio",
    "Use an operator release exposing this IstioCSR API and verify the supported OCP/OSSM combination. The operator deploys istio-csr and provisions Istiod TLS material. Its trust controller distributes istio-ca-root-cert ConfigMaps; do not let Argo CD prune or own generated certificate objects.", """
    apiVersion: operator.openshift.io/v1alpha1
    kind: IstioCSR
    metadata:
      name: default
      namespace: istio-csr
    spec:
      istioCSRConfig:
        certManager:
          issuerRef:
            name: venafi-mesh
            kind: Issuer
            group: cert-manager.io
          istioCACertificate:
            name: mesh-root
            namespace: istio-csr
            key: root-cert.pem
        istiodTLSConfig:
          trustDomain: cluster.local
        istio:
          namespace: istio-system
    """)

for site in ("a", "b"):
    add(f"cert-mesh-{site}", f"DC-{site.upper()} external-CA integration", f"identity/dc-{site}/istio-overlay.yaml", f"DC-{site.upper()} · installation overlay",
        "Merge these fields into this site's existing Sail Istio resource at installation. Preserve its meshNetworks, locality, discovery and cluster-local settings. This alternative uses istio-csr instead of the built-in signing CA/cacerts setup. It is not a live migration recipe.", f"""
        apiVersion: sailoperator.io/v1
        kind: Istio
        metadata:
          name: default
        spec:
          namespace: istio-system
          values:
            global:
              meshID: commerce-mesh
              multiCluster:
                clusterName: dc-{site}
              network: network-{site}
              caAddress: cert-manager-istio-csr.istio-csr.svc:443
            meshConfig:
              trustDomain: cluster.local
            pilot:
              env:
                ENABLE_CA_SERVER: "false"
        """)

add("cert-identities", "Workload service-account identities", "identity/workload-identity-overlay.yaml", "Both clusters · installation overlay",
    "Create these ServiceAccounts and merge the pod-template fields into the existing Orders Rollout and Catalog Deployment before starting this flow. The base demo otherwise uses the default account. Keep all existing images, selectors and rollout steps. Service-account names must match the SPIFFE identities shown here.", """
    apiVersion: v1
    kind: ServiceAccount
    metadata: {name: orders, namespace: shop}
    ---
    apiVersion: v1
    kind: ServiceAccount
    metadata: {name: catalog, namespace: shop}
    ---
    # Strategic merge overlay; not a standalone Rollout.
    apiVersion: argoproj.io/v1alpha1
    kind: Rollout
    metadata: {name: orders, namespace: shop}
    spec:
      template:
        spec:
          serviceAccountName: orders
    ---
    # Strategic merge overlay; not a standalone Deployment.
    apiVersion: apps/v1
    kind: Deployment
    metadata: {name: catalog, namespace: shop}
    spec:
      template:
        spec:
          serviceAccountName: catalog
    """)

add("cert-timer", "Workload renewal settings", "identity/agent-renewal-overlay.yaml", "Each cluster · installation overlay",
    "Merge with the existing Istio values at setup, before injecting workloads. The agent schedules renewal using the actual certificate lifetime. 24h is a requested lifetime; the issuer/CA can constrain it. Defaults or changes must be checked against the installed Istio version. Existing proxies do not receive new environment variables by magic.", """
    apiVersion: sailoperator.io/v1
    kind: Istio
    metadata:
      name: default
    spec:
      values:
        meshConfig:
          defaultConfig:
            proxyMetadata:
              SECRET_TTL: "24h"
              SECRET_GRACE_PERIOD_RATIO: "0.5"
              SECRET_GRACE_PERIOD_RATIO_JITTER: "0.01"
    """)

add("cert-request", "Generated workload CertificateRequest", "observed/dc-a/workload-request.yaml", "DC-A · generated, do not apply",
    "Illustrative object created by istio-csr after validating the caller. The request contains a base64 PEM CSR with the workload's URI SAN and public key; no private key. A configured approver must approve it before the issuer signs. Successful ephemeral requests may be deleted by istio-csr.", """
    apiVersion: cert-manager.io/v1
    kind: CertificateRequest
    metadata:
      name: istio-csr-example-a
      namespace: istio-system
    spec:
      request: <base64-PEM-CSR-for-spiffe-cluster.local-ns-shop-sa-orders>
      duration: 24h
      isCA: false
      usages:
      - digital signature
      - key encipherment
      - server auth
      - client auth
      issuerRef:
        name: venafi-mesh
        kind: Issuer
        group: cert-manager.io
    """, mode="Generated resource shape · simulated, not Git")

add("cert-verify", "Inspect certificates in both sites", "identity/verify.sh", "Both clusters · read-only",
    "Use the installed istioctl version. Compare loaded serials, expiry, SPIFFE SANs and ROOTCA across sites, then test fresh application connections. Inspect Certificate resources for control-plane renewal; workload leaves are served through SDS. Names below are placeholders.", """
    # No certificate or private-key changes are made by these commands.
    istioctl --context=dc-a proxy-config secret <orders-pod-a> -n shop
    istioctl --context=dc-b proxy-config secret <catalog-pod-b> -n shop
    oc --context=dc-a -n shop get configmap istio-ca-root-cert -o yaml
    oc --context=dc-b -n shop get configmap istio-ca-root-cert -o yaml
    oc --context=dc-a -n istio-system get issuer venafi-mesh
    oc --context=dc-b -n istio-system get issuer venafi-mesh
    oc --context=dc-a -n istio-system get certificaterequests -w
    # In a separate terminal; short-lived requests may already be cleaned up.
    oc --context=dc-b -n istio-system get certificaterequests -w
    # The operator / cert-manager own control-plane Certificate + TLS Secret resources.
    oc --context=dc-a get certificates -A
    oc --context=dc-b get certificates -A
    """, language="shell", mode="Read-only verification commands")


def make_certificate_flow(step):
    common = ["cert-csr", "cert-issuer"]
    flow = {"id": "certificates", "name": "Mesh cert rotation", "icon": "shield",
            "summary": "Shared trust, local renewal. Keep service communication secure across both sites without an application release.", "steps": []}

    def frame(label, title, body, detail, *, refs=common, nodes=(), edges=(), state=None, changes=(), note="", sources=("cert-csr",)):
        item = step(label, title, body, detail, refs, nodes, edges, state, note=note, sources=sources)
        item["changes"] = list(changes)
        flow["steps"].append(item)

    frame("Shared trust", "One trust foundation. Two independent sites.",
          "Both clusters trust the same private certificate authority behind Venafi. This lets services authenticate each other with mutual TLS, including across datacenters.",
          "Each site has local cert-manager and istio-csr components for certificate renewal. Istiod continues to control mesh routing. This flow assumes that integration is already installed.",
          refs=["cert-trust", "cert-issuer", "cert-csr", "cert-mesh-a", "cert-mesh-b", "cert-identities", "mtls"],
          nodes=["cert-root", "cert-issuer"],
          state={"cert_a": "Valid", "cert_b": "Valid", "cert_root": "R1 · unchanged", "cert_issuer": "Available", "cert_phase": "Shared trust established", "cert_request": "None", "cert_loaded_a": "A1", "cert_loaded_b": "B1"},
          note="Venafi/private PKI supplies mesh identities. ACME is suited to a separate external HTTPS certificate use case.",
          sources=["cert-csr", "cert-operator"])
    frame("Renew in A", "Site A requests a replacement before expiry.",
          "A workload in A starts automatic renewal while its current certificate remains valid. Local istio-csr validates its identity, and cert-manager requests a new certificate through Venafi.",
          "Venafi applies the organization's certificate policy and uses its private CA to sign. Workload private keys stay in the workload; application traffic continues on its existing route.",
          refs=["cert-timer", "cert-request", "cert-issuer"],
          nodes=["cert-a-envoy", "cert-a-manager", "cert-issuer"], edges=["cert-a-renew", "cert-a-sign"],
          state={"cert_a": "Renewing · still valid", "cert_phase": "A renewal in progress", "cert_request": "Approved · awaiting CA"},
          changes=[runtime("cert-renew-a", "Request and authorize a replacement", "System · A workload agent + local certificate components", "DC-A", "No Git change. The agent starts renewal; istio-csr validates the caller and creates an approved CertificateRequest for the existing Issuer.",
                           "Workload identity: spiffe://cluster.local/ns/shop/sa/orders", "Current loaded leaf: A1, still valid", "New key: generated inside the workload", "CertificateRequest: created → approved → sent to Venafi")],
          sources=["cert-csr", "cert-venafi"])
    frame("Activate in A", "A adopts the new certificate while services keep running.",
          "The signed certificate returns through A's local certificate components. The workload's Envoy proxy loads it dynamically through SDS, Istio's certificate delivery mechanism.",
          "New connections use the renewed certificate. No application rollout is needed, and B can keep using its current valid certificate because both share the same trust root.",
          nodes=["cert-issuer", "cert-a-manager", "cert-a-envoy"], edges=["cert-a-signed", "cert-a-activate"],
          state={"cert_a": "Renewed · serving", "cert_loaded_a": "A2", "cert_request": "Ready · activated", "cert_phase": "A renewed; B unchanged"},
          changes=[diff("cert-ready", "Record the issued certificate", "System · cert-manager A", "DC-A · runtime status", "Changed fields on the generated CertificateRequest. Issuance is followed by separate validation and SDS activation.", "observed/dc-a/request-status.yaml",
                        'status:\n  conditions:\n  - type: Ready\n    status: "False"\n',
                        'status:\n  certificate: <base64-PEM-leaf-A2-and-issuer-chain>\n  conditions:\n  - type: Ready\n    status: "True"\n'),
                   runtime("cert-sds-a", "Load the renewed certificate", "System · Istio agent + Envoy A", "Orders workload in A", "The agent validates the chain and supplies the certificate/key through local SDS. Existing connections are not all renegotiated.",
                           "Loaded leaf: A1 → A2 after Envoy accepts the update", "Trust root: R1 unchanged", "B loaded leaf: B1 unchanged", "Application image and traffic weights: unchanged")],
          sources=["cert-security", "cert-csr"])
    frame("Renew in B", "B renews independently through the same PKI.",
          "B's workloads follow their own renewal schedule, using B's local cert-manager and istio-csr. They contact the shared Venafi service without depending on A's control plane.",
          "The A-then-B order is for the walkthrough. In operation, renewals can overlap; certificate rotation does not follow the site-by-site Argo Rollouts release sequence.",
          nodes=["cert-b-envoy", "cert-b-manager", "cert-issuer"], edges=["cert-b-renew", "cert-b-sign"],
          state={"cert_b": "Renewing · still valid", "cert_phase": "B renewal in progress", "cert_request": "B approved · awaiting CA"},
          changes=[runtime("cert-renew-b", "Repeat the existing renewal policy in B", "System · B workload agent + local certificate components", "DC-B", "Reuse the definitions already shown; the caller and generated request belong to B.",
                           "Identity: spiffe://cluster.local/ns/shop/sa/catalog", "B request: created → approved → signing", "B loaded leaf: still B1", "A stays on A2; common root remains R1")],
          sources=["cert-csr", "cert-security"])
    frame("Verify trust", "Both sites keep communicating securely.",
          "B completes the same local activation process. Both sites now use renewed certificates, and their shared trust allows services to authenticate across the datacenters.",
          "Verify fresh mTLS connections over the existing east-west gateway path. Rotation changes credentials; local-first routing and failover policy continue to choose the destination.",
          refs=["cert-verify", "eastwest", "mtls"],
          nodes=["cert-a-envoy", "cert-b-gateway", "cert-b-envoy"], edges=["cert-mtls-out", "cert-mtls-in"],
          state={"cert_b": "Renewed · serving", "cert_loaded_b": "B2", "cert_phase": "Both sites renewed", "cert_request": "B ready · activated"},
          changes=[runtime("cert-verified", "Complete B renewal and verify both sites", "System · B components; operator verifies", "A ↔ B", "B's signed chain returns locally and SDS loads B2. Read-only checks confirm the issued certificates are actually in use.",
                           "B loaded leaf: B1 → B2; A remains on A2", "Root: matching R1 in both sites", "Verification route: Orders A → B east-west gateway → Catalog B", "Use an existing remote-selected route; renewal itself does not trigger failover")],
          note="This renews workload certificates under the same root. Changing the root CA requires a separate, coordinated trust transition.",
          sources=["cert-security", "mesh"])
    frame("Issuer outage", "The shared issuer is a dependency for both sites.",
          "If Venafi becomes unavailable, new certificate issuance and renewal are blocked in both sites. Already loaded, valid certificates can continue to support service traffic.",
          "The recovery window is bounded by certificate expiry. A prolonged outage can break new mTLS connections, and new workloads may be unable to start securely. Monitor renewal failures and remaining validity.",
          nodes=["cert-a-manager", "cert-b-manager", "cert-issuer"], edges=["cert-a-sign", "cert-b-sign"],
          state={"cert_issuer": "Unavailable", "cert_phase": "Renewal blocked; traffic still serving", "cert_request": "Retrying · no new leaf"},
          changes=[runtime("cert-outage", "Observe a shared issuance outage", "System · both local certificate services", "Shared PKI dependency", "Existing valid certificates are retained. This fault does not immediately move application traffic or weaken mTLS.",
                           "Venafi: available → unreachable", "Replacement certificates: not issued", "Loaded A2 / B2: still valid in this frame", "Monitor issuance errors, certificate expiry and new-workload readiness")],
          note="Provide resilient PKI connectivity and capacity. Moving traffic to the other datacenter does not repair this shared dependency.",
          sources=["cert-security", "cert-request"])
    frame("Recover", "Restore issuance and confirm renewal resumes.",
          "Once Venafi and its connectivity recover, each site's local components retry renewal and activate valid replacement certificates. Verify both sites before closing the incident.",
          "GitOps manages the issuer and trust configuration. Runtime renewal is automatic; it needs neither a Git commit nor an Argo Rollouts release. Certificate lifetime and PKI availability belong in the architecture's resilience plan.",
          refs=["cert-verify", "cert-issuer"],
          nodes=["cert-issuer", "cert-a-manager", "cert-b-manager", "cert-a-envoy", "cert-b-envoy"],
          edges=["cert-a-signed", "cert-a-activate", "cert-b-signed", "cert-b-activate"],
          state={"cert_issuer": "Available", "cert_a": "Renewed · serving", "cert_b": "Renewed · serving", "cert_loaded_a": "A3", "cert_loaded_b": "B3", "cert_phase": "Renewal restored in both sites", "cert_request": "Ready · activated"},
          changes=[runtime("cert-recover", "Complete the independent renewal retries", "PKI operator, then both sites' local controllers", "Shared service / both clusters", "This frame summarizes successful independent retries, not a simultaneous coordinated release. Check issued and loaded certificates separately.",
                           "Venafi: unreachable → available", "A loaded leaf: A2 → A3; B loaded leaf: B2 → B3", "Root: R1 unchanged; application image: v1 unchanged", "Monitor issuer credentials; Venafi access-token refresh is managed separately")],
          sources=["cert-venafi", "cert-security"])
    return flow
