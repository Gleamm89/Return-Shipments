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

// Fallback helpers (works whether fields are top-level or only in custom_fields)
function getOrderId(r){
  return r.order_id || r.custom_fields?.external_order_id || r.custom_fields?.order_id || "";
}
function getSalesOffice(r){
  return r.sales_office_id || r.custom_fields?.sales_office_id || "";
}
function getSource(r){
  return r.source || r.custom_fields?.source || "";
}

// ✅ Decide whether to show a row in the table
// Hide "tracking-excluded" rows (ParcelHub) unless they still carry business info
function shouldShowRow(r){
  const hasTrackingInfo = Boolean(
    (r.tracking_number && String(r.tracking_number).trim()) ||
    (r.status_tag && String(r.status_tag).trim()) ||
    (carrierText(r) && String(carrierText(r)).trim())
  );

  const hasBusinessInfo = Boolean(
    (getOrderId(r) && String(getOrderId(r)).trim()) ||
    (getSalesOffice(r) && String(getSalesOffice(r)).trim()) ||
    (getSource(r) && String(getSource(r)).trim())
  );

  // If it has tracking info -> show
  if (hasTrackingInfo) return true;

  // If no tracking info but has business info -> show
  if (hasBusinessInfo) return true;

  // Otherwise hide
  return false;
}

function renderTable(list){
  const tbody = $("tbody");

  // ✅ FILTER HERE: hide tracking-excluded / empty rows
  const visible = list.filter(shouldShowRow);

  if(!visible.length){
    tbody.innerHTML = `<tr><td colspan="8" class="muted">No records to show.</td></tr>`;
    $("countText").textContent = "0 records";
    return;
  }

  const html = visible.slice(0, 200).map(r => `
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
  $("countText").textContent =
    `${visible.length} records (showing up to first 200 in table)`;
}

function applySearch(){
  const q = $("search").value.trim().toLowerCase();

  // Always apply visibility filter first (so ParcelHub blanks remain hidden)
  const base = rows.filter(shouldShowRow);

  if(!q){
    renderTable(base);
    return;
  }

  const filtered = base.filter(r => {
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

    // render via applySearch so filtering is consistent
    applySearch();

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
