const TOKEN_KEY = "aotw_admin_token";

let token = sessionStorage.getItem(TOKEN_KEY) || "";
let sortables = {};

const loginScreen = document.getElementById("login-screen");
const app = document.getElementById("app");
const tokenInput = document.getElementById("token-input");
const loginBtn = document.getElementById("login-btn");
const loginError = document.getElementById("login-error");
const refreshBtn = document.getElementById("refresh-btn");
const logoutBtn = document.getElementById("logout-btn");
const backlogForm = document.getElementById("backlog-form");
const searchForm = document.getElementById("search-form");
const searchResults = document.getElementById("search-results");
const searchStatus = document.getElementById("search-status");
const searchBtn = document.getElementById("search-btn");
const toast = document.getElementById("toast");

function showToast(message, type = "success") {
  toast.textContent = message;
  toast.className = `toast ${type}`;
  setTimeout(() => toast.classList.add("hidden"), 3000);
}

async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
    ...options.headers,
  };
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401) {
    logout();
    throw new Error("Unauthorized");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `Request failed (${response.status})`);
  }
  return data;
}

function logout() {
  token = "";
  sessionStorage.removeItem(TOKEN_KEY);
  app.classList.add("hidden");
  loginScreen.classList.remove("hidden");
  loginError.classList.add("hidden");
}

async function tryLogin() {
  token = tokenInput.value.trim();
  if (!token) return;

  try {
    await api("/api/queues");
    sessionStorage.setItem(TOKEN_KEY, token);
    loginScreen.classList.add("hidden");
    app.classList.remove("hidden");
    loginError.classList.add("hidden");
    await loadQueues();
  } catch {
    loginError.textContent = "Invalid token or server unreachable.";
    loginError.classList.remove("hidden");
  }
}

function formatDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString();
}

function renderAlbumItem(item, index, queueName) {
  const li = document.createElement("li");
  li.className = "album-item";
  li.dataset.index = index;

  const position = document.createElement("span");
  position.className = "album-position";
  position.textContent = index + 1;

  let cover;
  if (item.image) {
    cover = document.createElement("img");
    cover.className = "album-cover";
    cover.src = item.image;
    cover.alt = "";
  } else {
    cover = document.createElement("div");
    cover.className = "album-cover placeholder";
    cover.textContent = "♪";
  }

  const info = document.createElement("div");
  info.className = "album-info";

  const title = document.createElement("div");
  title.className = "album-title";
  title.textContent = `${item.artist || "Unknown"} — ${item.title || "Unknown"}`;

  const meta = document.createElement("div");
  meta.className = "album-meta";
  meta.textContent = `Suggested by ${item.user_name || "Unknown"}`;

  info.append(title, meta);

  const removeBtn = document.createElement("button");
  removeBtn.className = "btn-danger";
  removeBtn.textContent = "Remove";
  removeBtn.addEventListener("click", async (e) => {
    e.stopPropagation();
    if (!confirm(`Remove "${item.artist} — ${item.title}" from the queue?`)) return;
    try {
      await api(`/api/queues/${queueName}/${index}`, { method: "DELETE" });
      showToast("Album removed");
      await loadQueues();
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  li.append(position, cover, info, removeBtn);
  return li;
}

function renderBacklogItem(note, index) {
  const li = document.createElement("li");
  li.className = "backlog-item";

  const text = document.createElement("div");
  text.className = "backlog-text";
  text.textContent = note.text;

  const meta = document.createElement("div");
  meta.className = "backlog-meta";
  const parts = [];
  if (note.added_by) parts.push(note.added_by);
  if (note.created_at) parts.push(formatDate(note.created_at));
  meta.textContent = parts.join(" · ");

  const actions = document.createElement("div");
  actions.className = "backlog-actions";

  const editBtn = document.createElement("button");
  editBtn.className = "btn-secondary";
  editBtn.textContent = "Edit";
  editBtn.addEventListener("click", () => startEditBacklog(li, note, index));

  const deleteBtn = document.createElement("button");
  deleteBtn.className = "btn-danger";
  deleteBtn.textContent = "Delete";
  deleteBtn.addEventListener("click", async () => {
    if (!confirm("Delete this backlog note?")) return;
    try {
      await api(`/api/backlog/${index}`, { method: "DELETE" });
      showToast("Note deleted");
      await loadQueues();
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  actions.append(editBtn, deleteBtn);
  li.append(text, meta, actions);
  return li;
}

function startEditBacklog(li, note, index) {
  li.innerHTML = "";

  const textarea = document.createElement("textarea");
  textarea.className = "backlog-edit";
  textarea.rows = 3;
  textarea.value = note.text;

  const actions = document.createElement("div");
  actions.className = "backlog-actions";

  const saveBtn = document.createElement("button");
  saveBtn.className = "btn-primary";
  saveBtn.textContent = "Save";
  saveBtn.addEventListener("click", async () => {
    try {
      await api(`/api/backlog/${index}`, {
        method: "PUT",
        body: JSON.stringify({ text: textarea.value }),
      });
      showToast("Note updated");
      await loadQueues();
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  const cancelBtn = document.createElement("button");
  cancelBtn.className = "btn-secondary";
  cancelBtn.textContent = "Cancel";
  cancelBtn.addEventListener("click", () => loadQueues());

  actions.append(saveBtn, cancelBtn);
  li.append(textarea, actions);
}

function setupSortable(listEl, queueName) {
  if (sortables[queueName]) {
    sortables[queueName].destroy();
  }
  sortables[queueName] = Sortable.create(listEl, {
    animation: 150,
    ghostClass: "sortable-ghost",
    onEnd: async () => {
      const order = [...listEl.children].map((el) => parseInt(el.dataset.index, 10));
      const newOrder = [];
      const seen = new Set();
      for (const oldIdx of order) {
        if (!seen.has(oldIdx)) {
          newOrder.push(oldIdx);
          seen.add(oldIdx);
        }
      }
      try {
        await api(`/api/queues/${queueName}/reorder`, {
          method: "PUT",
          body: JSON.stringify({ order: newOrder }),
        });
        showToast("Queue reordered");
        await loadQueues();
      } catch (err) {
        showToast(err.message, "error");
        await loadQueues();
      }
    },
  });
}

async function loadQueues() {
  const data = await api("/api/queues");

  for (const [queueName, listId, countId, emptyId] of [
    ["main", "main-list", "main-count", "main-empty"],
    ["bonus", "bonus-list", "bonus-count", "bonus-empty"],
  ]) {
    const list = document.getElementById(listId);
    const items = data[queueName] || [];
    list.innerHTML = "";
    items.forEach((item, i) => list.appendChild(renderAlbumItem(item, i, queueName)));
    document.getElementById(countId).textContent = items.length;
    document.getElementById(emptyId).classList.toggle("hidden", items.length > 0);
    setupSortable(list, queueName);
  }

  const backlogList = document.getElementById("backlog-list");
  const backlog = data.backlog || [];
  backlogList.innerHTML = "";
  backlog.forEach((note, i) => backlogList.appendChild(renderBacklogItem(note, i)));
  document.getElementById("backlog-count").textContent = backlog.length;
  document.getElementById("backlog-empty").classList.toggle("hidden", backlog.length > 0);
}

function renderSearchResult(result) {
  const li = document.createElement("li");
  li.className = "search-result";

  let cover;
  if (result.image) {
    cover = document.createElement("img");
    cover.className = "album-cover";
    cover.src = result.image;
    cover.alt = "";
  } else {
    cover = document.createElement("div");
    cover.className = "album-cover placeholder";
    cover.textContent = "♪";
  }

  const info = document.createElement("div");
  info.className = "album-info";

  const title = document.createElement("div");
  title.className = "album-title";
  title.textContent = `${result.artist || "Unknown"} — ${result.title || "Unknown"}`;

  info.append(title);

  const addBtn = document.createElement("button");
  addBtn.className = "btn-primary";
  addBtn.textContent = "Add";
  addBtn.addEventListener("click", async () => {
    const queue = document.getElementById("add-queue").value;
    const userName = document.getElementById("suggester-name").value;
    addBtn.disabled = true;
    addBtn.textContent = "Adding…";
    try {
      await api(`/api/queues/${queue}/add`, {
        method: "POST",
        body: JSON.stringify({
          artist: result.artist,
          title: result.title,
          user_name: userName,
        }),
      });
      showToast(`Added to ${queue === "bonus" ? "bonus" : "normal"} queue`);
      await loadQueues();
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      addBtn.disabled = false;
      addBtn.textContent = "Add";
    }
  });

  li.append(cover, info, addBtn);
  return li;
}

async function searchAlbums(event) {
  event.preventDefault();
  const query = document.getElementById("search-query").value.trim();
  if (!query) return;

  searchBtn.disabled = true;
  searchBtn.textContent = "Searching…";
  searchStatus.textContent = "Searching Last.fm…";
  searchStatus.classList.remove("hidden", "error");
  searchResults.innerHTML = "";

  try {
    const data = await api(`/api/albums/search?q=${encodeURIComponent(query)}`);
    const results = data.results || [];
    if (!results.length) {
      searchStatus.textContent = "No albums found.";
      return;
    }
    searchStatus.textContent = `${results.length} result${results.length === 1 ? "" : "s"} — pick one to add.`;
    results.forEach((result) => searchResults.appendChild(renderSearchResult(result)));
  } catch (err) {
    searchStatus.textContent = err.message;
    searchStatus.classList.add("error");
  } finally {
    searchBtn.disabled = false;
    searchBtn.textContent = "Search";
    if (!searchStatus.classList.contains("error") && searchResults.children.length) {
      searchStatus.classList.remove("error");
    }
  }
}

loginBtn.addEventListener("click", tryLogin);
tokenInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") tryLogin();
});
refreshBtn.addEventListener("click", () => loadQueues().catch((err) => showToast(err.message, "error")));
logoutBtn.addEventListener("click", logout);
searchForm.addEventListener("submit", (e) => searchAlbums(e).catch((err) => showToast(err.message, "error")));

backlogForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = document.getElementById("backlog-input").value;
  const addedBy = document.getElementById("backlog-author").value;
  try {
    await api("/api/backlog", {
      method: "POST",
      body: JSON.stringify({ text, added_by: addedBy }),
    });
    document.getElementById("backlog-input").value = "";
    showToast("Note added");
    await loadQueues();
  } catch (err) {
    showToast(err.message, "error");
  }
});

if (token) {
  api("/api/queues")
    .then(() => {
      loginScreen.classList.add("hidden");
      app.classList.remove("hidden");
      return loadQueues();
    })
    .catch(() => {
      logout();
      loginScreen.classList.remove("hidden");
    });
} else {
  loginScreen.classList.remove("hidden");
}
