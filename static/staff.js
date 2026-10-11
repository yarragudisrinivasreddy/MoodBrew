const NAMES = { spark: "Spark", zen: "Zen", cozy: "Cozy", chaos: "Chaos" };
const $ = (s) => document.querySelector(s);

async function refresh() {
  try {
    const r = await (await fetch("/api/room")).json();
    $("#guests").textContent = r.guests_last_hour
      ? `${r.guests_last_hour} guest${r.guests_last_hour === 1 ? "" : "s"} played in the last hour`
      : "No games played in the last hour";
    const list = $("#mix");
    list.replaceChildren();
    for (const [key, pct] of Object.entries(r.mix)) {
      const li = document.createElement("li");
      li.className = "v-" + key;
      const name = document.createElement("span");
      name.textContent = NAMES[key];
      const bar = document.createElement("div");
      bar.className = "bar";
      const fill = document.createElement("span");
      fill.style.width = `${pct}%`;
      bar.append(fill);
      const num = document.createElement("span");
      num.className = "pct";
      num.textContent = `${pct}%`;
      li.append(name, bar, num);
      list.append(li);
    }
    $("#tip").textContent = r.tip;
    $("#wait").textContent = `${r.wait_minutes} min`;
    $("#wait-status").textContent = `The bar is ${r.status}.`;
    $("#updated").textContent = `Updated ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
  } catch {
    $("#updated").textContent = "Offline, retrying";
  }
}

refresh();
setInterval(refresh, 10000);
