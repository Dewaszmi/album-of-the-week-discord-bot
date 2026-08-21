const KEY = "aotw_token";
let token = sessionStorage.getItem(KEY) || "";

const $ = (id) => document.getElementById(id);

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...opts.headers },
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) {
    logout();
    throw new Error("Unauthorized");
  }
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function logout() {
  token = "";
  sessionStorage.removeItem(KEY);
  $("app").classList.add("hidden");
  $("login").classList.remove("hidden");
}

async function login() {
  token = $("token").value.trim();
  if (!token) return;
  try {
    await api("/api/queues");
    sessionStorage.setItem(KEY, token);
    $("login").classList.add("hidden");
    $("app").classList.remove("hidden");
    $("login-error").classList.add("hidden");
    await render();
  } catch {
    $("login-error").textContent = "Invalid token.";
    $("login-error").classList.remove("hidden");
  }
}

function cover(item) {
  return item.image
    ? `<img src="${item.image}" alt="">`
    : `<div class="ph">♪</div>`;
}

function albumRow(item, i, queue) {
  return `<li class="row">
    ${cover(item)}
    <div class="info">
      <strong>${item.artist || "?"} — ${item.title || "?"}</strong>
      <span>${item.user_name || ""}</span>
    </div>
    <div class="actions">
      <button class="secondary" onclick="move('${queue}',${i},-1)">↑</button>
      <button class="secondary" onclick="move('${queue}',${i},1)">↓</button>
      <button class="danger" onclick="removeAlbum('${queue}',${i})">Remove</button>
    </div>
  </li>`;
}

async function render() {
  const data = await api("/api/queues");
  for (const q of ["main", "bonus"]) {
    const items = data[q] || [];
    $(q).innerHTML = items.length
      ? items.map((item, i) => albumRow(item, i, q)).join("")
      : `<p class="muted">Empty.</p>`;
    $(`${q}-count`).textContent = items.length;
  }
}

async function move(queue, index, dir) {
  await api(`/api/queues/${queue}/move`, { method: "POST", body: JSON.stringify({ index, dir }) });
  await render();
}

async function removeAlbum(queue, index) {
  if (!confirm("Remove this album?")) return;
  await api(`/api/queues/${queue}/${index}`, { method: "DELETE" });
  await render();
}

async function search(e) {
  e.preventDefault();
  const q = $("query").value.trim();
  $("search-status").textContent = "Searching…";
  $("results").innerHTML = "";
  try {
    const { results = [] } = await api(`/api/search?q=${encodeURIComponent(q)}`);
    $("search-status").textContent = results.length ? `${results.length} result(s)` : "No albums found.";
    $("results").innerHTML = results.map((r, i) => `
      <li class="row">
        ${cover(r)}
        <div class="info"><strong>${r.artist} — ${r.title}</strong></div>
        <button onclick="add(${i})">Add</button>
      </li>`).join("");
    search._results = results;
  } catch (err) {
    $("search-status").textContent = err.message;
  }
}

async function add(i) {
  const r = search._results[i];
  await api(`/api/queues/${$("target").value}/add`, {
    method: "POST",
    body: JSON.stringify({ artist: r.artist, title: r.title, user_name: $("suggester").value }),
  });
  $("search-status").textContent = "Added.";
  await render();
}

$("login-btn").onclick = login;
$("token").addEventListener("keydown", (e) => e.key === "Enter" && login());
$("logout-btn").onclick = logout;
$("search-form").onsubmit = search;

if (token) {
  api("/api/queues").then(() => {
    $("login").classList.add("hidden");
    $("app").classList.remove("hidden");
    return render();
  }).catch(logout);
}

window.move = move;
window.removeAlbum = removeAlbum;
window.add = add;
