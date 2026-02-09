const $ = (id) => document.getElementById(id);

let rows = [];

function fmtDate(s){
  if(!s) return "";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return String(s);

  const date = d.toLocaleDateString('en-CA', { timeZone: 'UTC' });
  const time = d.toLocaleTimeString('en-GB', {
    timeZone: 'UTC',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });

  return `${date} - ${time} UTC`;
}

function carrierText(r){
  return r.courier_name || r.carrier_slug || "";
}

// ✅ Fallback helpers (important!)
function getOrderId(r){
  return r.order_id || r.custom_fields?.external_order_id || r.custom_fields?.order_id || "";
}
function getSalesOffice(r){
  return r.sales_office_id || r.custom_fields?.sales_office_id || "";
}
function getSource(r){
  return r.source || r.custom_fields?.source || "";
}

function renderTable(list){
  const tbody = $("tbody");
  if(!list.length){
    tbody.innerHTML = `<tr><td colspan="8" class="muted">No records to show.</td></tr>`;
    $("countText").textContent = "0 records";
    return;
  }

  const html = list.slice(0, 200).map(r => `
    <tr>
      <td>${r.tracking_number || ""}</td>
      <td>${carrierText(r)}</td>
      <td>${r.status_tag || ""}</td>
      <td>${getOrderId(r)}</td>
      <td>${getSalesOffice(r)}</td>
      <td>${getSource(r)}</td>
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
      getOrderId(r),
      getSalesOffice(r),
      getSource(r),
      r.courier_name,
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
