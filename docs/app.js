const $ = (id) => document.getElementById(id);

let rows = [];
function fmtDate(s){
  if(!s) return "";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return String(s);

  // Force UTC time + show hours/minutes/seconds
  const t = d.toLocaleTimeString('en-GB', {
    timeZone: 'UTC',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

  return t + " UTC";
}



function carrierText(r){
  // Prefer the friendly name; fallback to slug
  return r.courier_name || r.carrier_slug || "";
}

function renderTable(list){
  const tbody = $("tbody");
  if(!list.length){
    tbody.innerHTML = `<tr><td colspan="6" class="muted">No records to show.</td></tr>`;
    $("countText").textContent = "0 records";
    return;
  }

  const html = list.slice(0, 200).map(r => `
    <tr>
      <td>${r.tracking_number || ""}</td>
      <td>${carrierText(r)}</td>
      <td>${r.status_tag || ""}</td>
      <td>${r.order_id || ""}</td>
      <td>${fmtDate(r.last_checkpoint_time)}</td>
      <td>${fmtDate(r.updated_at)}</td>
    </tr>
  `).join("");

  tbody.innerHTML = html;
  $("countText").textContent = `${list.length} records (showing up to first 200 in table)`;
}

function applySearch(){
  const q = $("search").value.trim().toLowerCase();
  if(!q){
    renderTable(rows);
    return;
  }

  const filtered = rows.filter(r => {
    const hay = [
      r.tracking_number,
      r.order_id,
      r.courier_name,     // NEW: searchable
      r.carrier_slug,
      r.status_tag,
      r.updated_at
    ].join(" ").toLowerCase();

    return hay.includes(q);
  });

  renderTable(filtered);
}

async function loadMeta(){
  try{
    const res = await fetch("./data/meta.json", { cache: "no-store" });
    if(!res.ok) throw new Error("meta.json not found");
    return await res.json();
  }catch{
    return null;
  }
}

async function loadData(){
  $("pill").textContent = "Loading…";
  $("pill").className = "pill";
  $("metaText").textContent = "Fetching latest export";

  const meta = await loadMeta();

  try{
    const res = await fetch("./data/returns_intransit.json", { cache: "no-store" });
    if(!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    rows = data.items || [];
    renderTable(rows);

    const ts = meta?.generated_at || data.generated_at || null;
    const count = meta?.count ?? data.count ?? rows.length;

    $("pill").textContent = "OK";
    $("pill").className = "pill ok";
    $("metaText").textContent = `Last updated: ${fmtDate(ts)} • Count: ${count}`;

  }catch(err){
    rows = [];
    renderTable(rows);
    $("pill").textContent = "No data";
    $("pill").className = "pill warn";
    $("metaText").textContent =
      "Could not load JSON yet. Wait for the first successful workflow run to deploy data.";
    console.error(err);
  }
}

$("search").addEventListener("input", applySearch);
$("refresh").addEventListener("click", loadData);

loadData();
