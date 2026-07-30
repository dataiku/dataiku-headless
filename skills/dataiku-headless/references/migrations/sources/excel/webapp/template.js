(function () {
  var PALETTE = ["hsl(234,50%,35%)","hsl(172,46%,48%)","hsl(22,84%,60%)","hsl(221,47%,31%)",
                 "hsl(280,45%,55%)","hsl(48,80%,55%)","hsl(0,72%,58%)","hsl(200,55%,52%)","hsl(240,4%,58%)"];
  var GRID = "hsl(240,6%,90%)";
  var HAS_CHARTJS = (typeof Chart !== "undefined");
  if (HAS_CHARTJS) {
    Chart.defaults.font.family = "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
    Chart.defaults.font.size = 11;
    Chart.defaults.color = "hsl(240,3.8%,46.1%)";
  }

  var D = null, CHARTS_DRAWN = false, CHART_OBJS = [];

  function esc(s){
    return String(s == null ? "" : s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  }
  function money(v){
    if (v === null || v === undefined || isNaN(v)) return "–";
    var cur = D ? D.currency : "";
    var a = Math.abs(v), s = (v < 0 ? "-" : "") + cur;
    return s + a.toLocaleString(D ? D.locale : undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
  }
  function fmt(v, kind){
    if (v === null || v === undefined) return "–";
    if (kind === "text") return String(v);
    if (kind === "date") return String(v).substring(0, 10);
    if (typeof v !== "number") return String(v);
    var loc = D ? D.locale : undefined;
    if (kind === "money") return money(v);
    if (kind === "number2") return v.toLocaleString(loc, {minimumFractionDigits:2, maximumFractionDigits:2});
    if (kind === "percent") return (v*100).toLocaleString(loc, {maximumFractionDigits:1}) + "%";
    if (kind === "number") return Math.round(v).toLocaleString(loc);
    return v.toLocaleString(loc, {maximumFractionDigits:2});
  }
  function backendUrl(p){ try { return getWebAppBackendUrl(p); } catch(e){ return p; } }

  fetch(backendUrl("/api/overview"))
    .then(function(r){ if(!r.ok) throw new Error("HTTP "+r.status); return r.json(); })
    .then(render)
    .catch(function(e){
      var el = document.getElementById("mig-error");
      el.style.display = "block";
      el.textContent = "Could not load data: " + e.message + ". Build the output datasets and restart the web-app backend.";
    });

  function render(d){
    D = d;
    document.getElementById("mig-title").textContent = d.title || "Overview";
    document.getElementById("mig-subtitle").textContent = d.subtitle || "";
    document.title = d.title || "Overview";

    document.getElementById("mig-badges").innerHTML = (d.badges || []).map(function(b){
      return '<div class="mig-badge"><span class="b-label">'+esc(b.label)+'</span><span class="b-val">'+esc(b.value || "–")+'</span></div>';
    }).join("");

    document.getElementById("mig-kpis").innerHTML = (d.kpis || []).map(function(k){
      return '<div class="mig-kpi'+(k.accent?" accent":"")+'"><div class="k-label">'+esc(k.label)+
             '</div><div class="k-val">'+esc(fmt(k.value, k.format))+'</div><div class="k-sub">'+esc(k.sub)+'</div></div>';
    }).join("");

    var names = (d.sheets || []).map(function(s){ return s.label; });
    document.getElementById("mig-foot").textContent =
      "Generated from the validated Dataiku flow. Views: " + names.join(" · ");

    buildViews();
    buildTabs();
    var first = document.querySelector(".mig-tab");
    if (first) first.click();
  }

  /* ---------- tabs & views ---------- */
  function hasCharts(){ return HAS_CHARTJS && D.charts && D.charts.length > 0; }

  function buildTabs(){
    var tabs = (D.sheets || []).map(function(s){
      return '<button class="mig-tab" data-view="'+s.id+'">'+esc(s.label)+'</button>';
    });
    if (hasCharts()) tabs.push('<button class="mig-tab" data-view="charts">Charts</button>');
    var nav = document.getElementById("mig-tabs");
    nav.innerHTML = tabs.join("");
    nav.querySelectorAll(".mig-tab").forEach(function(t){
      t.addEventListener("click", function(){
        nav.querySelectorAll(".mig-tab").forEach(function(x){ x.classList.remove("is-active"); });
        t.classList.add("is-active");
        var view = t.getAttribute("data-view");
        document.querySelectorAll(".mig-view").forEach(function(v){
          v.style.display = (v.id === "view-" + view) ? "" : "none";
        });
        if (view === "charts"){
          if (!CHARTS_DRAWN){ drawCharts(); CHARTS_DRAWN = true; }
          else { CHART_OBJS.forEach(function(c){ try{c.resize();}catch(e){} }); }
        }
      });
    });
  }

  function buildViews(){
    var html = (D.sheets || []).map(sheetView).join("");
    if (hasCharts()) html += chartsView();
    document.getElementById("mig-views").innerHTML = html;
    (D.sheets || []).forEach(function(s){
      var btn = document.getElementById("dl-" + s.id);
      if (btn) btn.addEventListener("click", function(){ downloadXLSX(s); });
    });
  }

  /* ---------- sheet (table) views ---------- */
  function colKinds(s){
    return s.columns.map(function(c, ci){
      if (s.formats && s.formats[c]) return s.formats[c];
      var isNum = s.rows.some(function(r){ return typeof r[ci] === "number"; });
      return isNum ? "auto" : "text";
    });
  }

  function sheetView(s){
    var h = '<section class="mig-view" id="view-'+s.id+'" style="display:none">' +
            '<div class="mig-card mig-wide"><div class="mig-card-head"><div><h2>'+esc(s.label)+'</h2>' +
            '<p class="mig-cardsub">'+esc(s.description)+'</p></div>';
    if (!s.error) h += '<div class="mig-controls"><button class="mig-dl" id="dl-'+s.id+'">Export to Excel</button></div>';
    h += '</div>';
    if (s.error){
      h += '<div class="mig-sheet-error">This view could not be loaded: '+esc(s.error)+'</div>';
    } else {
      var kinds = colKinds(s);
      h += '<div class="mig-tablewrap"><table class="mig-tbl"><thead><tr>' +
           s.columns.map(function(c, ci){
             return '<th class="'+(kinds[ci]==="text"?"is-text":"")+'">'+esc(c)+'</th>';
           }).join("") + '</tr></thead><tbody>';
      s.rows.forEach(function(r){
        h += '<tr>' + r.map(function(v, ci){
          return '<td class="'+(kinds[ci]==="text"?"is-text":"")+'">'+esc(fmt(v, kinds[ci]))+'</td>';
        }).join("") + '</tr>';
      });
      if (s.total_row){
        h += '<tr class="row-total">' + s.columns.map(function(c, ci){
          if (ci === 0) return '<td class="is-text">Total</td>';
          var sum = 0, seen = false;
          s.rows.forEach(function(r){ if (typeof r[ci] === "number"){ sum += r[ci]; seen = true; } });
          return '<td class="'+(kinds[ci]==="text"?"is-text":"")+'">'+(seen ? esc(fmt(sum, kinds[ci])) : "")+'</td>';
        }).join("") + '</tr>';
      }
      h += '</tbody></table></div>';
      if (s.truncated) h += '<p class="mig-trunc">Showing the first '+s.rows.length.toLocaleString()+
                            ' of '+s.row_count.toLocaleString()+' rows. The full dataset lives in the Flow.</p>';
    }
    h += '</div></section>';
    return h;
  }

  function downloadXLSX(s){
    var rows = [ s.columns.slice() ];
    s.rows.forEach(function(r){ rows.push(r.slice()); });
    fetch(backendUrl("/api/export_xlsx"), {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ sheet: s.label.substring(0,31), rows: rows })
    })
    .then(function(r){ if(!r.ok) throw new Error("HTTP "+r.status); return r.blob(); })
    .then(function(blob){
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = s.label.replace(/[^A-Za-z0-9_-]+/g, "_").toLowerCase() + ".xlsx";
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(a.href);
    })
    .catch(function(e){
      var el = document.getElementById("mig-error");
      el.style.display = "block"; el.textContent = "Excel export failed: " + e.message;
    });
  }

  /* ---------- charts (drawn lazily when the Charts tab opens) ---------- */
  function chartsView(){
    var wides = [], smalls = [];
    D.charts.forEach(function(c, i){
      var card = '<div class="mig-card'+(c.wide?" mig-wide":"")+'"><div class="mig-card-head"><div><h2>'+esc(c.title)+'</h2>' +
                 '<p class="mig-cardsub">'+esc(c.subtitle)+'</p></div></div>' +
                 (c.error ? '<div class="mig-sheet-error">'+esc(c.error)+'</div>'
                          : '<div class="mig-chart"><canvas id="chart-'+i+'"></canvas></div>') +
                 '</div>';
      (c.wide ? wides : smalls).push(card);
    });
    var h = '<section class="mig-view" id="view-charts" style="display:none">';
    h += wides.join("");
    if (smalls.length === 1) h += smalls[0];
    else if (smalls.length) h += '<div class="mig-grid2">' + smalls.join("") + '</div>';
    h += '</section>';
    return h;
  }

  function drawCharts(){
    D.charts.forEach(function(c, i){
      if (c.error) return;
      var el = document.getElementById("chart-" + i);
      if (el) CHART_OBJS.push(drawChart(el, c));
    });
  }

  function drawChart(el, c){
    var horizontal = (c.type === "horizontal_bar");
    var stacked = (c.type === "stacked_bar");
    var line = (c.type === "line");
    var single = (c.series.length === 1);
    var datasets = c.series.map(function(s, i){
      var color = PALETTE[i % PALETTE.length];
      return line
        ? { label:s.label, data:s.data, borderColor:color, borderWidth:2, pointRadius:0, tension:.25,
            fill:single, backgroundColor:"rgba(45,63,168,.08)", spanGaps:true }
        : { label:s.label, data:s.data, backgroundColor:color, borderWidth:0, stack: stacked ? "s" : undefined };
    });
    function vfmt(v){ return fmt(v, c.format); }
    var valScale = { grid:{color:GRID}, stacked:stacked, ticks:{ callback:function(v){ return vfmt(v); } } };
    var catScale = { grid:{display:false}, stacked:stacked, ticks:{ maxTicksLimit:14, autoSkip:true } };
    return new Chart(el, {
      type: line ? "line" : "bar",
      data: { labels:c.labels, datasets:datasets },
      options: {
        responsive:true, maintainAspectRatio:false,
        indexAxis: horizontal ? "y" : "x",
        interaction:{mode:"index",intersect:false},
        plugins:{
          legend:{ display:!single, position:"bottom", labels:{ boxWidth:10, font:{size:10}, padding:8 } },
          tooltip:{ callbacks:{ label:function(ctx){
            var n = ctx.dataset.label && !single ? ctx.dataset.label+": " : "";
            return n + vfmt(horizontal ? ctx.parsed.x : ctx.parsed.y);
          } } }
        },
        scales: horizontal ? { x:valScale, y:{ grid:{display:false}, ticks:{font:{size:10}} } }
                           : { x:catScale, y:valScale }
      }
    });
  }
})();
