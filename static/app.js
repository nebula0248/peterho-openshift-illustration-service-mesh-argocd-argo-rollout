"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHTML = value => String(value).replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
const icons = {
  layers: '<path d="m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5"/>',
  route: '<circle cx="5" cy="5" r="2"/><circle cx="19" cy="19" r="2"/><path d="M5 7v8a4 4 0 0 0 4 4h8M9 5h10v8m-4-4 4 4 4-4"/>',
  mesh: '<path d="m5 6 7-3 7 3v11l-7 4-7-4V6Zm0 0 7 5 7-5M12 11v10M5 17l14-11M5 6l14 11"/>',
  undo: '<path d="M4 10a8 8 0 1 1 2 9M4 4v6h6"/>',
  shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
  server: '<rect x="4" y="3" width="16" height="7" rx="2"/><rect x="4" y="14" width="16" height="7" rx="2"/><path d="M8 6.5h.01M8 17.5h.01M12 6.5h5M12 17.5h5"/>',
  chart: '<path d="M4 4v16h17M8 15l4-5 4 3 5-8"/>',
  git: '<circle cx="7" cy="5" r="2"/><circle cx="7" cy="19" r="2"/><circle cx="17" cy="7" r="2"/><path d="M7 7v10M17 9v3a3 3 0 0 1-3 3H7"/>',
  globe: '<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>',
  user: '<circle cx="12" cy="7" r="3"/><path d="M5 21v-3a7 7 0 0 1 14 0v3M4 21h16"/>',
  gateway: '<path d="M4 21V4h16v17M8 21V9h8v12M2 21h20M11 5h2"/>',
  box: '<path d="m12 3 9 5v9l-9 5-9-5V8l9-5Zm-9 5 9 5 9-5M12 13v9M7 5l10 6"/>',
  code: '<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-15-2 18"/>',
  argo: '<path d="M6 16a8 8 0 1 1 12 0M6 16v4h12v-4M8 10h2m4 0h2M10 15h4M5 20l-2 2m16-2 2 2"/>',
  rollout: '<path d="m4 7 8-4 8 4-8 4-8-4Zm0 5 8 4 8-4M4 17l8 4 8-4"/>',
  api: '<path d="m7 6-5 6 5 6m10-12 5 6-5 6M13 4l-2 16"/>',
  exchange: '<path d="M3 8h17m-4-4 4 4-4 4M21 16H4m4-4-4 4 4 4"/>',
};
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.box}</svg>`;

let demo, current = null, selectedTab = "explanation", playing = false, playTimer, requestID = 0;
let selectedConfig = null, toastTimer;
const categories = {traffic:"BASELINE", resilience:"AVAILABILITY", delivery:"LOCAL ROLLOUT", rollback:"RECOVERY", certificates:"MESH IDENTITY"};
// Layered coordinates: two independent site columns and a shared center column.
const nodes = [
  {id:"client",x:550,y:20,w:180,h:48,title:"Users & clients",sub:"shop.example.com",icon:"user",kind:"default"},
  {id:"gtm",x:530,y:100,w:220,h:56,title:"F5 GTM / BIG-IP DNS",sub:"Global site selection",icon:"globe",kind:"edge"},
  {id:"git",x:530,y:756,w:220,h:56,title:"Shared Git repository",sub:"base + per-site overlays",icon:"git",kind:"git"},
  {id:"coordinator",x:530,y:846,w:220,h:48,title:"Release pipeline",sub:"Human approval → Git PR",icon:"shield",kind:"control"},
];
for (const [site, offset] of [["a",0],["b",730]]) {
  const add = (suffix,x,y,w,h,title,sub,symbol,kind="default") => nodes.push({id:`${site}-${suffix}`,site,x:x+offset,y,w,h,title,sub,icon:symbol,kind});
  add("ltm",170,234,210,52,"F5 LTM","Site VIP · TCP/443","route","edge");
  add("router",80,366,180,50,"HAProxy router","OpenShift Route","route","edge");
  add("gateway",290,366,180,50,"Mesh ingress","Gateway · Envoy","gateway","mesh");
  add("frontend",80,502,110,56,"Frontend","+ Envoy","box");
  add("orders",220,502,140,56,"Orders · v1","v1 100% / v2 0%","box");
  add("catalog",390,502,80,56,"Catalog","+ Envoy","box");
  add("eastwest",290,618,180,50,"East–west gateway","LTM VIP · TCP/15443","exchange","mesh");
  add("argo",80,756,110,56,"Argo CD","Synced","argo","control");
  add("rollouts",220,756,140,56,"Argo Rollouts","Healthy · v1","rollout","control");
  add("istiod",390,756,80,56,"Istiod","Primary","mesh","mesh");
  add("api",80,846,110,48,"Cluster API","Local etcd","api","control");
  add("metrics",220,846,140,48,"Prometheus","Local analysis","chart");
}

const edges = [
  ["dns","M640 68 V100","dns"],
  ["request-a","M530 128 H275 V234","dns"],
  ["request-b","M750 128 H1005 V234","dns"],
  ["pipeline-git","M640 846 V812","control"],
  ["approve-a","M530 870 H508 V824 H290 V812","control"],
  ["approve-b","M750 870 H772 V824 H1020 V812","control"],
  ["git-a","M530 784 H515 V742 H135 V756","control"],
  ["git-b","M750 784 H765 V742 H865 V756","control"],
  ["cross-ab","M290 558 V582 H990 V643 H1020","mesh"],
  ["cross-ba","M1020 558 V596 H528 V643 H470","mesh"],
  // Separate lanes keep reciprocal API watches clear of nodes and each other.
  ["discovery-a","M430 756 V698 H770 V870 H810","control"],
  ["discovery-b","M1200 784 H1252 V938 H66 V870 H80","control"],
];
for (const [site, o] of [["a",0],["b",730]]) {
  edges.push(
    [`${site}-ingress`, `M${275+o} 286 V352 H${170+o} V366`, "traffic"],
    [`${site}-gateway`, `M${260+o} 391 H${290+o}`, "traffic"],
    [`${site}-frontend`, `M${380+o} 416 V488 H${135+o} V502`, "traffic"],
    [`${site}-orders`, `M${190+o} 530 H${220+o}`, "traffic"],
    [`${site}-catalog`, `M${360+o} 530 H${390+o}`, "traffic"],
    [`${site}-eastwest-catalog`, `M${380+o} 618 V600 H${430+o} V558`, "mesh"],
    [`${site}-reconcile`, `M${190+o} 784 H${220+o}`, "control"],
    [`${site}-rollout`, `M${290+o} 756 V692 H${240+o} V578 H${260+o} V558`, "control"],
    [`${site}-observe`, `M${290+o} 812 V846`, "control"],
    [`${site}-xds`, `M${430+o} 756 V688 H${484+o} V442 H${380+o} V416`, "control"],
    [`${site}-route-weights`, `M${360+o} 784 H${390+o}`, "control"],
    [`${site}-xds-client`, `M${470+o} 784 H${484+o} V574 H${135+o} V558`, "control"],
  );
}

function nodeSVG(node) {
  const compact = node.w < 150;
  const textX = compact ? 12 : 40;
  const symbol = compact ? "" : `<g class="node-symbol" transform="translate(11 13) scale(.8)">${icons[node.icon]}</g>`;
  const small = node.w <= 110 || node.id.endsWith("eastwest");
  return `<g class="node kind-${node.kind}${small?' small-node':''}" data-node="${node.id}" transform="translate(${node.x} ${node.y})" role="group" aria-label="${escapeHTML(node.title.replace(" · v1", ""))}${node.site ? ` in datacenter ${node.site.toUpperCase()}` : ""}"><rect width="${node.w}" height="${node.h}" rx="7"/>${symbol}<text class="node-title" data-title="${node.id}" x="${textX}" y="22">${escapeHTML(node.title)}</text><text class="node-subtitle" x="${textX}" y="${node.h-12}" data-subtitle="${node.id}">${escapeHTML(node.sub)}</text></g>`;
}

function drawDiagram() {
  let svg = `<svg class="architecture-svg" viewBox="0 0 1280 962" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Layered active-active OpenShift architecture" aria-describedby="diagram-desc"><desc id="diagram-desc">A logical Users to GTM to site LTM entry path. Each datacenter has an ingress layer, service mesh data plane and platform controllers. Shared Git and release automation sit between the independent clusters. Only the current step's control and cross-network connections are displayed.</desc><defs>`;
  for (const [name,color] of [["traffic","#54ffab"],["control","#bd96ff"],["mesh","#35ddff"],["dns","#ffc34d"]]) {
    svg += `<marker id="arrow-${name}" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto" markerUnits="userSpaceOnUse"><path d="m0 0 7 3.5-7 3.5" fill="${color}"/></marker>`;
  }
  svg += `</defs>`;
  for (const [site,o] of [["a",0],["b",730]]) {
    svg += `<g data-cluster="${site}">
      <text class="site-title" x="${80+o}" y="203">DATACENTER ${site.toUpperCase()}</text>
      <text class="site-subtitle" x="${80+o}" y="220">Independent cluster · network-${site}</text>
      <circle data-health-dot="${site}" cx="${415+o}" cy="199" r="3.5" fill="#a6edbf"/>
      <text class="site-tag" data-site-status="${site}" x="${426+o}" y="203">ACTIVE</text>
      <text class="site-share" data-site-share="${site}" x="${285+o}" y="181">50% site share</text>
      <rect class="site-boundary ${site}" x="${50+o}" y="324" width="450" height="584" rx="12"/>
      <path class="layer-rule" d="M${50+o} 454 H${500+o} M${50+o} 710 H${500+o}"/>
      <text class="layer-label" x="${70+o}" y="347"><tspan>01</tspan> INGRESS <tspan class="layer-meta">/ OpenShift 4.22</tspan></text>
      <text class="layer-label" x="${70+o}" y="477"><tspan>02</tspan> SERVICE MESH DATA PLANE</text>
      <text class="layer-label" x="${70+o}" y="733"><tspan>03</tspan> PLATFORM COMPONENTS</text>
      <text class="locality-label" x="${275+o}" y="687" text-anchor="middle">Local primary · local rollout control</text>
    </g>`;
  }
  svg += `<text class="shared-label center-label" x="640" y="10" text-anchor="middle">GLOBAL ENTRY</text>
    <text class="shared-label center-label" x="640" y="730" text-anchor="middle">SHARED RELEASE INPUTS</text>
    <g class="network-caption"><text x="640" y="629" text-anchor="middle">CROSS-NETWORK mTLS</text><text class="network-subtitle" x="640" y="648" text-anchor="middle">Destination gateway · :15443</text></g>`;
  for (const [id,path,type] of edges) svg += `<path class="connection ${type}" data-edge="${id}" d="${path}" marker-end="url(#arrow-${type})"/>`;
  svg += `<g class="discovery-caption"><text x="610" y="687" text-anchor="middle">Istiod A → API B</text><text x="640" y="928" text-anchor="middle">Istiod B → API A</text></g>`;
  for (const [site,o] of [["a",0],["b",730]]) svg += `<text class="routing-caption" data-routing="${site}" x="${275+o}" y="704" text-anchor="middle">VirtualService via API → Istiod → xDS</text>`;
  svg += nodes.filter(n=>!n.site).map(nodeSVG).join("");
  for (const site of ["a","b"]) svg += `<g data-cluster-nodes="${site}">${nodes.filter(n=>n.site===site).map(nodeSVG).join("")}</g>`;
  svg += `</svg>`;
  $("#diagram").innerHTML=svg + certificateDiagram();
}

function certificateDiagram() {
  // Architectural roles: the workload and local certificate stack are grouped.
  const identityNodes = [
    {id:"cert-root", x:530,y:240,w:220,h:60,title:"Shared trust root",sub:"Trusted by both clusters",icon:"shield",kind:"git"},
    {id:"cert-issuer", x:530,y:495,w:220,h:60,title:"Venafi / private PKI",sub:"Shared signing service",icon:"shield",kind:"edge"},
    {id:"cert-b-gateway",site:"b",x:850,y:105,w:320,h:60,title:"B east–west gateway",sub:"Preserves workload mTLS",icon:"gateway",kind:"mesh"},
  ];
  for (const [site,offset,app] of [["a",0,"Orders"],["b",740,"Catalog"]]) {
    const add = (id,y,title,sub,symbol,kind="control") => identityNodes.push({id:`cert-${site}-${id}`,site,x:150+offset,y,w:240,h:60,title,sub,icon:symbol,kind});
    add("envoy",240,`${app} service`,"Envoy · valid certificate","box","mesh");
    add("manager",495,"Certificate management","cert-manager + istio-csr","shield");
    add("istiod",650,"Istiod · local primary","Mesh routing and discovery","mesh","mesh");
  }
  const paths = [
    ["cert-mtls-out","M390 270 H450 V135 H850","mesh",640,118,"Cross-site service traffic · mTLS"],
    ["cert-mtls-in","M1110 165 V240","mesh",1125,198,"mTLS"],
  ];
  for (const [site,o] of [["a",0],["b",740]]) {
    paths.push(
      [`cert-${site}-renew`, `M${270+o} 300 V495`, "control",286+o,388,"Renewal request"],
      [`cert-${site}-activate`, `M${270+o} 495 V300`, "traffic",286+o,388,"Activate locally"],
    );
  }
  paths.push(
    ["cert-a-sign","M390 525 H530","dns",460,512,"Request signing"],
    ["cert-a-signed","M530 525 H390","dns",460,512,"New certificate"],
    ["cert-b-sign","M890 525 H750","dns",820,512,"Request signing"],
    ["cert-b-signed","M750 525 H890","dns",820,512,"New certificate"],
  );
  let svg = `<svg class="certificate-svg" hidden viewBox="0 0 1280 780" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Certificate architecture with shared trust and independent local renewal"><defs>`;
  for (const [type,color] of [["traffic","#54ffab"],["control","#bd96ff"],["mesh","#35ddff"],["dns","#ffc34d"]]) {
    svg += `<marker id="cert-arrow-${type}" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="userSpaceOnUse"><path d="m0 0 8 4-8 4" fill="${color}"/></marker>`;
  }
  svg += `</defs>`;
  for (const [site,o,app] of [["a",0,"ORDERS"],["b",740,"CATALOG"]]) {
    svg += `<text class="site-title" x="${80+o}" y="32">DATACENTER ${site.toUpperCase()}</text>
      <text class="site-subtitle" x="${80+o}" y="49">OpenShift 4.22 · local renewal</text>
      <rect class="site-boundary" x="${50+o}" y="65" width="440" height="670" rx="12"/>
      <path class="layer-rule" d="M${50+o} 414 H${490+o} M${50+o} 600 H${490+o}"/>
      <text class="layer-label" x="${70+o}" y="86">01 SERVICE COMMUNICATION</text>
      <text class="cert-pod-label" x="${150+o}" y="224">${app} WORKLOAD</text>
      <text class="layer-label" x="${70+o}" y="442">02 CERTIFICATE MANAGEMENT</text>
      <text class="layer-label" x="${70+o}" y="624">03 MESH CONTROL PLANE</text>`;
  }
  svg += `<text class="shared-label center-label" x="640" y="218" text-anchor="middle">COMMON TRUST</text>
    <text class="cert-context-label" x="640" y="330" text-anchor="middle">Same root throughout renewal</text>
    <text class="shared-label center-label" x="640" y="474" text-anchor="middle">SHARED BETWEEN DATACENTERS</text>
    <text class="cert-context-label" x="640" y="580" text-anchor="middle">Certificate policy and signing</text>
    <text class="cert-footnote" x="640" y="763" text-anchor="middle">Renew certificates locally. Keep application releases and traffic routing unchanged.</text>`;
  for (const [id,path,type,x,y,label] of paths) {
    svg += `<g class="cert-link" data-cert-link="${id}"><path class="connection ${type}" data-edge="${id}" d="${path}" marker-end="url(#cert-arrow-${type})"/><text class="cert-edge-label" x="${x}" y="${y}" ${type==="dns"||id==="cert-mtls-out"?'text-anchor="middle"':''}>${label}</text></g>`;
  }
  return svg + identityNodes.map(nodeSVG).join("") + `</svg>`;
}

function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(()=>$("#toast").hidden=true, 2500);
}

function getScenario(id = current?.scenario || "traffic") {
  return current?.flow?.id === id ? current.flow : demo.scenarios.find(s=>s.id===id);
}

async function goTo(scenario, index, manual = true, failure = null) {
  if (manual) stopPlay();
  const sequence = ++requestID;
  try {
    const context = scenario === "rollback" ? failure || current?.rollback || {site:"a",weight:10} : null;
    const query = context ? `&site=${encodeURIComponent(context.site)}&weight=${context.weight}` : "";
    const response = await fetch(`/api/state?scenario=${encodeURIComponent(scenario)}&step=${index}${query}`);
    if (!response.ok) throw new Error("The simulation state could not be loaded.");
    const next = await response.json();
    if (sequence !== requestID) return;
    current = next;
    history.replaceState(null, "", `#${scenario}/${index + 1}${context?`/${context.site}/${context.weight}`:""}`);
    render();
    $(".detail-scroll").scrollTop = 0;
  } catch (error) {
    if (sequence !== requestID) return;
    stopPlay();
    toast("Unable to load the step. Check that the Python server is running.");
    console.error(error);
  }
}

function drawStepConnectors() {
  const stepper = $("#stepper");
  $(".step-connectors",stepper)?.remove();
  if (!stepper.classList.contains("many-steps")) return;
  const bounds = stepper.getBoundingClientRect();
  const circles = $$(".step-circle",stepper).map(el=>el.getBoundingClientRect());
  const buttons = $$(".step-button",stepper);
  const paths = circles.slice(0,-1).map((circle,i)=>{
    const next = circles[i+1];
    const x = circle.left-bounds.left+circle.width/2, y = circle.top-bounds.top+circle.height/2;
    const nx = next.left-bounds.left+next.width/2, ny = next.top-bounds.top+next.height/2;
    const wraps = Math.abs(ny-y)>2;
    // The return lane sits between rows, clear of the labels and circles.
    const rowBottom = Math.max(...buttons.slice(0,i+1).filter((_,j)=>Math.abs(circles[j].top-circle.top)<2).map(b=>b.getBoundingClientRect().bottom));
    const laneY = (rowBottom+next.top)/2-bounds.top;
    const d = wraps ? `M${x} ${y} H${bounds.width-1} V${laneY} H-7 V${ny} H${nx}` : `M${x} ${y} H${nx}`;
    return `<path class="step-connector${i<current.step?' complete':''}" data-between="${i+1}-${i+2}" d="${d}"/>`;
  }).join("");
  stepper.insertAdjacentHTML("afterbegin",`<svg class="step-connectors" viewBox="0 0 ${bounds.width} ${bounds.height}" aria-hidden="true" focusable="false">${paths}</svg>`);
}

function highlightCode(code, language = "yaml") {
  return code.split("\n").map(line => {
    const safe = escapeHTML(line);
    if (language === "diff") {
      const kind = line.startsWith("---") || line.startsWith("+++") || line.startsWith("@@") ? "meta" : line.startsWith("+") ? "added" : line.startsWith("-") ? "removed" : "context";
      return `<span class="diff-line diff-${kind}">${safe || " "}</span>`;
    }
    if (line.trim().startsWith("#")) return `<span class="code-comment">${safe}</span>`;
    return safe.replace(/^(\s*(?:- )?)([\w.-]+)(:)/, '$1<span class="code-key">$2</span>$3');
  }).join(language === "diff" ? "" : "\n");
}

function stepConfigs() { return getScenario().steps[current.step].config_items; }

function render() {
  const scenario = getScenario();
  const step = scenario.steps[current.step];
  const state = current.state;
  const number = String(current.step+1).padStart(2,"0");
  const total = String(scenario.steps.length).padStart(2,"0");
  $$(".scenario-button").forEach(button => {
    const active = button.dataset.scenario === current.scenario;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  $("#canvas-scenario").textContent = scenario.name;
  $("#scenario-summary").textContent = scenario.summary;
  $("#diagram").dataset.scenario = current.scenario;
  const identityView = current.scenario === "certificates";
  $(".architecture-svg").toggleAttribute("hidden", identityView);
  $(".certificate-svg").toggleAttribute("hidden", !identityView);
  $(".traffic-card").hidden = identityView;
  $("#certificate-card").hidden = !identityView;
  $("#traffic-legend").hidden = identityView;
  $("#certificate-legend").hidden = !identityView;
  if (identityView) {
    $("#certificate-status").textContent = state.cert_phase;
    $("#certificate-values").innerHTML = [["Orders A",state.cert_a],["Catalog B",state.cert_b],["Trust root","Shared · unchanged"],["Venafi",state.cert_issuer]].map(([label,value])=>`<div><span>${escapeHTML(label)}</span><strong>${escapeHTML(value)}</strong></div>`).join("");
    for (const site of ["a","b"]) $(`[data-subtitle="cert-${site}-envoy"]`).textContent = `Envoy · ${state[`cert_${site}`]}`;
    $('[data-subtitle="cert-issuer"]').textContent = state.cert_issuer === "Unavailable" ? "Unavailable · retries pending" : "Shared signing service";
    $('[data-node="cert-issuer"]').classList.toggle("cert-unavailable", state.cert_issuer === "Unavailable");
  }
  $("#cluster-health").textContent = `${state.healthy_clusters} / 2`;
  $("#health-caption").innerHTML = `<i class="status-dot"${state.failed_a?' style="background:var(--red)"':''}></i>${state.failed_a ? "DC-A offline" : "Healthy"}`;
  $("#global-weight").textContent = `${state.global_v2}%`;
  $("#step-count").textContent = `${number} / ${total}`;
  $("#step-eyebrow").innerHTML = `STEP ${number}<span> / ${total}</span>`;
  $("#step-category").textContent = categories[current.scenario];
  $("#step-title").textContent = step.title;
  $("#step-body").textContent = step.body;
  $("#step-detail").textContent = step.detail;
  $("#step-note").textContent = step.note;
  $("#stepper").classList.toggle("many-steps",scenario.steps.length>8);
  $("#stepper").innerHTML = scenario.steps.map((item, i) => `<button class="step-button ${i===current.step?'active':i<current.step?'complete':''}" data-step="${i}" ${i===current.step?'aria-current="step"':''} aria-label="Step ${i+1}: ${escapeHTML(item.label)}"><span class="step-circle">${i<current.step?'✓':String(i+1).padStart(2,"0")}</span><span class="step-label">${escapeHTML(item.label)}</span></button>`).join("");
  drawStepConnectors();
  $("#rollback-options").hidden = current.scenario !== "rollback";
  $$('[data-failure-site]').forEach(button=>button.setAttribute("aria-pressed",String(button.dataset.failureSite===current.rollback?.site)));
  $("#traffic-bars").innerHTML = ["a","b"].map(site => {
    const down = site==="a" && state.failed_a;
    return `<div class="traffic-bar-row ${down?'down':''}"><div class="traffic-bar-label"><span>Datacenter ${site.toUpperCase()}</span><strong>${down?'UNREACHABLE':`${state[`weight_${site}`]}% v2`}</strong></div><div class="traffic-bar" role="img" aria-label="DC-${site.toUpperCase()}: ${down?'unreachable':`${state[`weight_${site}`]} percent version 2`}"><span class="traffic-bar-v2" style="width:${down?0:state[`weight_${site}`]}%"></span></div></div>`;
  }).join("");
  const configs = step.config_items;
  const changeCount = configs.filter(c=>c.kind!=="reference").length;
  const referenceCount = configs.length-changeCount;
  $("#config-link-label").textContent = changeCount ? `Inspect ${changeCount} step ${changeCount===1?'change':'changes'}` : referenceCount ? `Inspect ${referenceCount} first ${referenceCount===1?'reference':'references'}` : "Configuration · no further changes";
  $("#config-summary").textContent = step.config_summary;
  $("#config-count").textContent = [changeCount ? `${changeCount} ${changeCount===1?'change':'changes'}` : "",referenceCount ? `${referenceCount} first shown` : ""].filter(Boolean).join(" · ") || "No new changes";
  $("#config-empty").hidden = configs.length>0;
  $("#config-content").hidden = !configs.length;
  $("#config-list").hidden = !configs.length;
  $("#config-list").innerHTML = configs.map(c => {
    const type = c.kind==="reference" ? "FIRST SHOWN" : c.kind==="diff" ? "YAML DIFF" : c.kind==="action" ? "ACTION" : "RUNTIME";
    return `<button class="config-file config-kind-${c.kind}" data-config="${c.id}" aria-pressed="false"><span>${escapeHTML(c.title)}</span><small>${type} · ${escapeHTML(c.scope)}</small></button>`;
  }).join("");
  selectedConfig = null;
  if(configs.length) selectConfig(configs[0].id);
  $("#step-sources").innerHTML = step.sources.map(key=>`<a href="${demo.sources[key].url}" target="_blank" rel="noopener noreferrer">${escapeHTML(demo.sources[key].label)} <span aria-hidden="true">↗</span></a>`).join("");
  $("#prev-button").disabled = current.step === 0;
  $("#next-label").textContent = current.step === scenario.steps.length-1 ? "Replay this flow" : "Next step";
  $("#failure-button").hidden = !(current.scenario === "delivery" && [4,5,9,10].includes(current.step));
  const failingSite = current.step < 7 ? "a" : "b";
  $("#failure-button").textContent = `⚡ Simulate failed ${state[`weight_${failingSite}`]}% analysis in ${failingSite.toUpperCase()}`;
  $("#activity-log").innerHTML = current.events.slice(-3).map((event,i,arr) => `<li><span class="activity-index">${String(current.events.length-arr.length+i+1).padStart(2,"0")} <span aria-hidden="true">${i===arr.length-1?'→':'✓'}</span></span><span>${escapeHTML(event)}</span></li>`).join("");
  $$("[data-node]").forEach(node => node.classList.toggle("active", current.active_nodes.includes(node.dataset.node)));
  $$("[data-edge]").forEach(edge => edge.classList.toggle("active", current.active_edges.includes(edge.dataset.edge)));
  $$("[data-cert-link]").forEach(link => {
    link.classList.toggle("active",current.active_edges.includes(link.dataset.certLink));
    link.classList.toggle("cert-failed-link",identityView && state.cert_issuer === "Unavailable" && ["cert-a-sign","cert-b-sign"].includes(link.dataset.certLink));
  });
  for (const site of ["a","b"]) {
    const down = site==="a" && state.failed_a;
    $(`[data-cluster="${site}"]`).classList.toggle("cluster-down", down);
    $(`[data-cluster-nodes="${site}"]`).classList.toggle("cluster-down", down);
    $(`[data-site-status="${site}"]`).textContent = down ? "DOWN" : "ACTIVE";
    $(`[data-health-dot="${site}"]`).setAttribute("fill",down ? "#ff7068" : "#54ffab");
    $(`[data-subtitle="${site}-argo"]`).textContent = state[`sync_${site}`];
    $(`[data-subtitle="${site}-rollouts"]`).textContent = down ? "Unavailable" : state[`rollout_${site}`].replace(" · v1 serving", " · v1");
    $(`[data-subtitle="${site}-orders"]`).textContent = down ? "Unavailable" : `v1 ${100-state[`weight_${site}`]}% / v2 ${state[`weight_${site}`]}%`;
    $(`[data-title="${site}-orders"]`).textContent = state[`weight_${site}`] === 100 ? "Orders · v2" : state[`weight_${site}`] === 0 && !state[`rollout_${site}`].startsWith("Preparing") ? "Orders · v1" : "Orders · v1/v2";
    $(`[data-site-share="${site}"]`).textContent = `${state[`site_${site}`]}% site share`;
    $(`[data-node="${site}-orders"]`).classList.toggle("fault",state.release_fault && state.release_fault_site===site);
    $(`[data-routing="${site}"]`).classList.toggle("visible",current.active_edges.includes(`${site}-route-weights`));
  }
  $('[data-node="a-catalog"]').classList.toggle("fault",state.catalog_fault);
  $('[data-subtitle="a-catalog"]').textContent = state.catalog_fault ? "Unhealthy" : "+ Envoy";
  $('[data-edge="a-catalog"]').classList.toggle("fault",state.catalog_fault);
  $('[data-subtitle="gtm"]').textContent = `Site mix · A ${state.site_a}% / B ${state.site_b}%`;
  $('[data-subtitle="coordinator"]').textContent = state.gate;
  $(".network-caption").classList.toggle("visible",current.active_edges.some(e=>e.startsWith("cross-")));
  $(".discovery-caption").classList.toggle("visible",current.active_edges.includes("discovery-a") && current.active_edges.includes("discovery-b"));
  const activeStep = $(".step-button.active");
  if (activeStep && $("#stepper").scrollWidth > $("#stepper").clientWidth) {
    $("#stepper").scrollTo({left:Math.max(0,activeStep.offsetLeft-30),behavior:"smooth"});
  }
}

function setTab(tab, focus = false) {
  selectedTab = tab;
  for (const name of ["explanation","config"]) {
    const active = name === tab;
    const button = $(`#${name}-tab`);
    button.classList.toggle("active",active);
    button.setAttribute("aria-selected",String(active));
    button.tabIndex = active ? 0 : -1;
    $(`#${name}-panel`).hidden = !active;
    if (active && focus) button.focus();
  }
}

function stopPlay() {
  playing = false;
  clearTimeout(playTimer);
  $("#play-label").textContent = "Play walkthrough";
  $(".play-icon").textContent = "▶";
  $("#play-button").setAttribute("aria-pressed","false");
}

function scheduleNext() {
  clearTimeout(playTimer);
  if (!playing) return;
  playTimer = setTimeout(async () => {
    if (!playing) return;
    if (current.step >= getScenario().steps.length-1) {stopPlay(); return;}
    await goTo(current.scenario,current.step+1,false);
    if (current.step >= getScenario().steps.length-1) stopPlay();
    else scheduleNext();
  },7000);
}

async function togglePlay() {
  if (!current) return;
  if (playing) {stopPlay(); return;}
  if (current.step === getScenario().steps.length-1) await goTo(current.scenario,0);
  playing = true;
  $("#play-label").textContent = "Pause walkthrough";
  $(".play-icon").textContent = "Ⅱ";
  $("#play-button").setAttribute("aria-pressed","true");
  scheduleNext();
}

function openDialog(id) { stopPlay(); $(id).showModal(); }

function resetLab() {
  if (!current) return;
  $("#site-share").value = current.state.site_a;
  $("#canary-a").value = current.state.weight_a;
  $("#canary-b").value = current.state.weight_b;
  updateLab();
}

function updateLab() {
  const share = Number($("#site-share").value), a = Number($("#canary-a").value), b = Number($("#canary-b").value);
  const total = Math.round((share*a+(100-share)*b)/10)/10;
  for (const id of ["site-share","canary-a","canary-b"]) $(`#${id}-value`).textContent = `${$(`#${id}`).value}%`;
  $("#lab-result").textContent = `${total}%`;
  $("#lab-formula").textContent = `(${share}% × ${a}%) + (${100-share}% × ${b}%) = ${total}%`;
  $("#lab-bar-fill").style.width = `${total}%`;
}

function selectConfig(key) {
  const config = stepConfigs().find(c=>c.id===key);
  if(!config) return;
  selectedConfig = config;
  $$(".config-file").forEach(button => {
    button.classList.toggle("active",button.dataset.config===key);
    button.setAttribute("aria-pressed",String(button.dataset.config===key));
  });
  $("#config-filename").textContent = config.file;
  $("#config-purpose").textContent = config.purpose;
  $("#config-actor").textContent = config.actor;
  $("#config-mode").textContent = `${config.mode} · ${config.scope}`;
  $("#config-code").innerHTML = highlightCode(config.code,config.language);
  $("#copy-button").textContent = "Copy";
  $("#expanded-filename").textContent = config.file;
  $("#expanded-purpose").textContent = `${config.actor} · ${config.mode} · ${config.scope} — ${config.purpose}`;
  $("#expanded-code").innerHTML = highlightCode(config.code,config.language);
}

function downloadConfigs(configs,filename,summary = "") {
  const content = "MESH LAB — TEACHING CONFIGURATIONS\n\nGit files, changes, runtime observations and commands are labeled separately.\nNot a cluster installation bundle.\n\n" + (summary?summary+"\n\n":"") + configs.map(c=>{
    return `===== ${c.file} (${c.language}) =====\n${c.actor?c.actor+' | ':''}${c.mode} | ${c.scope}\n${c.purpose}\n\n${c.code}`;
  }).join("\n") + "\nREFERENCES\n" + Object.values(demo.sources).map(s=>`${s.label}\n${s.url}`).join("\n");
  const url=URL.createObjectURL(new Blob([content],{type:"text/plain"}));
  const a=document.createElement("a");a.href=url;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  toast("Teaching configurations downloaded");
}

function wireEvents() {
  $("#config-list").addEventListener("click",event=>{
    const button=event.target.closest("[data-config]");
    if(button)selectConfig(button.dataset.config);
  });
  $("#expand-config").addEventListener("click",()=>openDialog("#config-dialog"));
  $("#download-step").addEventListener("click",()=>downloadConfigs(stepConfigs(),`mesh-lab-${current.scenario}-step-${current.step+1}.txt`,getScenario().steps[current.step].config_summary));
  $("#scenario-nav").addEventListener("click", event => {
    const button = event.target.closest("[data-scenario]");
    if(button) goTo(button.dataset.scenario,0);
  });
  $("#stepper").addEventListener("click", event => {
    const button = event.target.closest("[data-step]");
    if(button) goTo(current.scenario,Number(button.dataset.step));
  });
  $("#prev-button").addEventListener("click",()=>{if(current.step>0) goTo(current.scenario,current.step-1);});
  $("#next-button").addEventListener("click",()=>goTo(current.scenario,(current.step+1)%getScenario().steps.length));
  $("#reset-button").addEventListener("click",()=>goTo(current.scenario,0));
  $("#play-button").addEventListener("click",togglePlay);
  $("#explanation-tab").addEventListener("click",()=>setTab("explanation"));
  $("#config-tab").addEventListener("click",()=>setTab("config"));
  $("#show-config").addEventListener("click",()=>setTab("config",true));
  $(".detail-tabs").addEventListener("keydown",event=>{
    if(["ArrowLeft","ArrowRight","Home","End"].includes(event.key)) {
      event.preventDefault(); event.stopPropagation();
      setTab(event.key==="Home"?"explanation":event.key==="End"?"config":selectedTab==="explanation"?"config":"explanation",true);
    }
  });
  $("#failure-button").addEventListener("click",()=>{
    const site=current.step<7?"a":"b";
    setTab("explanation");goTo("rollback",0,true,{site,weight:current.state[`weight_${site}`]});
  });
  $("#rollback-options").addEventListener("click",event=>{
    const button=event.target.closest("[data-failure-site]");
    if(button)goTo("rollback",0,true,{site:button.dataset.failureSite,weight:current.rollback?.weight||10});
  });
  for(const id of ["about-button","sources-button"]) $(`#${id}`).addEventListener("click",()=>openDialog("#about-dialog"));
  for(const id of ["traffic-lab-button","traffic-inline-button"]) $(`#${id}`).addEventListener("click",()=>{resetLab();openDialog("#traffic-dialog");});
  $$(".close-dialog").forEach(button=>button.addEventListener("click",()=>button.closest("dialog").close()));
  $$("dialog").forEach(dialog=>dialog.addEventListener("click",event=>{
    if (event.target!==dialog) return;
    const rect = dialog.getBoundingClientRect();
    if(event.clientX<rect.left || event.clientX>rect.right || event.clientY<rect.top || event.clientY>rect.bottom) dialog.close();
  }));
  for(const id of ["site-share","canary-a","canary-b"]) $(`#${id}`).addEventListener("input",updateLab);
  $("#lab-reset").addEventListener("click",resetLab);
  $("#copy-button").addEventListener("click",async()=>{
    const config = selectedConfig;
    if(!config)return;
    try {
      await Promise.race([
        navigator.clipboard.writeText(config.code),
        new Promise((_,reject)=>setTimeout(()=>reject(new Error("Clipboard unavailable")),1200)),
      ]);
      $("#copy-button").textContent = "Copied ✓";
      toast("Configuration copied");
    } catch {
      const temporary = document.createElement("textarea");
      temporary.value = config.code;
      temporary.style.cssText = "position:fixed;left:-9999px;top:0";
      document.body.append(temporary);temporary.select();
      let copied = false;
      try {copied = document.execCommand("copy");} catch { /* Manual selection below. */ }
      temporary.remove();
      $("#copy-button").focus();
      if(copied) {$("#copy-button").textContent="Copied ✓";toast("Configuration copied");}
      else {
        const range = document.createRange(); range.selectNodeContents($("#config-code"));
        const selection=window.getSelection(); selection.removeAllRanges();selection.addRange(range);
        toast("Configuration selected. Press ⌘C or Ctrl+C to copy.");
      }
    }
  });
  $("#download-button").addEventListener("click",()=>downloadConfigs(Object.values(demo.configs),"mesh-lab-teaching-configurations.txt"));
  document.addEventListener("visibilitychange",()=>{if(document.hidden)stopPlay();});
  document.addEventListener("keydown",event=>{
    if(!current || event.altKey || event.ctrlKey || event.metaKey || $("dialog[open]") || event.target.closest("input,textarea,select,[role=tab],pre"))return;
    if(event.key==="ArrowRight"){event.preventDefault();if(current.step<getScenario().steps.length-1)goTo(current.scenario,current.step+1);}
    else if(event.key==="ArrowLeft"){event.preventDefault();if(current.step>0)goTo(current.scenario,current.step-1);}
    else if(event.key===" " && !event.target.closest("button,a,[role=button]")){event.preventDefault();togglePlay();}
  });
  window.addEventListener("hashchange",()=>{
    const [id,raw,site,weight]=location.hash.slice(1).split("/");
    const s=demo.scenarios.find(s=>s.id===id);const index=Number(raw)-1;
    if(s && Number.isInteger(index) && index>=0 && index<s.steps.length)goTo(id,index,true,parseFailure(site,weight));
  });
  new ResizeObserver(drawStepConnectors).observe($("#stepper"));
}

function parseFailure(site,weight) {
  return {site:site==="b"?"b":"a",weight:Number(weight)===50?50:10};
}

async function init() {
  try {
    const response = await fetch("/api/demo");
    if(!response.ok)throw new Error("Demo data unavailable");
    demo=await response.json();
    $$("[data-icon]").forEach(el=>el.innerHTML=icon(el.dataset.icon));
    $("#scenario-nav").innerHTML=demo.scenarios.map((scenario,i)=>`<button class="scenario-button" data-scenario="${scenario.id}" aria-pressed="false">${icon(scenario.icon)}${escapeHTML(scenario.name)}<span class="scenario-number">0${i+1}</span></button>`).join("");
    $("#all-sources").innerHTML=Object.values(demo.sources).map(s=>`<a href="${s.url}" target="_blank" rel="noopener noreferrer">${escapeHTML(s.label)} ↗</a>`).join("");
    const failure=document.createElement("button");failure.id="failure-button";failure.className="failure-button";failure.textContent="⚡ Inject bad release";failure.hidden=true;$("#explanation-panel").append(failure);
    drawDiagram();wireEvents();
    const [id,raw,site,weight]=location.hash.slice(1).split("/");
    const scenario=demo.scenarios.find(s=>s.id===id) || getScenario("traffic");
    const parsed=Number(raw)-1;
    const index=Number.isInteger(parsed) && parsed>=0 && parsed<scenario.steps.length?parsed:0;
    await goTo(scenario.id,index,true,parseFailure(site,weight));
  } catch(error) {
    $("#step-title").textContent="The demo couldn't load.";
    $("#step-body").textContent="Run python3 app.py, then open http://127.0.0.1:8000. This demo needs its local Python server.";
    const banner=document.createElement("div");banner.className="error-banner";banner.textContent="Unable to load the architecture. ";const retry=document.createElement("button");retry.textContent="Retry";retry.onclick=()=>location.reload();banner.append(retry);document.body.prepend(banner);
    console.error(error);
  }
}

init();
