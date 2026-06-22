/* TRIDENT backend bridge — injected by server.py at serve time.
 * Makes "run a prompt" fetch real backend results automatically:
 * it wraps the UI's launch/recon hooks so that submitting a prompt POSTs to
 * /api/run, then renders the returned trace.jsonl via the existing instant path
 * (window.TRIDENT_launch/recon with instant=true). index.html stays untouched. */
(function () {
  "use strict";
  if (!/^https?:$/.test(location.protocol)) return; // only when served by the bridge

  var origLaunch = window.TRIDENT_launch;
  var origRecon = window.TRIDENT_recon;

  function looksLikeTrace(s) { return typeof s === "string" && s.indexOf('"kind"') >= 0; }

  // --- minimal loading overlay -------------------------------------------
  var ov;
  function overlay(on, msg) {
    if (on) {
      if (!ov) {
        ov = document.createElement("div");
        ov.id = "tridentBridgeOverlay";
        ov.style.cssText = "position:fixed;inset:0;z-index:2147483647;display:flex;" +
          "align-items:center;justify-content:center;flex-direction:column;gap:18px;" +
          "background:rgba(8,8,11,.82);backdrop-filter:blur(3px);color:#fff;" +
          "font:600 15px ui-sans-serif,system-ui,sans-serif;text-align:center";
        ov.innerHTML = '<div style="width:46px;height:46px;border:3px solid rgba(225,29,42,.25);' +
          'border-top-color:#e11d2a;border-radius:50%;animation:tbspin 1s linear infinite"></div>' +
          '<div id="tridentBridgeMsg"></div>' +
          '<style>@keyframes tbspin{to{transform:rotate(360deg)}}</style>';
        document.body.appendChild(ov);
      }
      ov.querySelector("#tridentBridgeMsg").textContent = msg || "Running campaign…";
      ov.style.display = "flex";
    } else if (ov) {
      ov.style.display = "none";
    }
  }

  function runBackend(prompt, mode) {
    return fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: prompt || "", mode: mode })
    }).then(function (res) {
      return res.json().catch(function () { return { ok: false, error: "bad response" }; })
        .then(function (data) {
          if (!res.ok || !data.ok) {
            throw new Error((data && (data.error || data.detail)) || ("HTTP " + res.status));
          }
          return data.trace;
        });
    });
  }

  if (typeof origLaunch === "function") {
    window.TRIDENT_launch = function (prompt, trace, instant, pkgTechs) {
      // an explicit real trace (e.g. internal replay) bypasses the backend call
      if (looksLikeTrace(trace)) return origLaunch(prompt, trace, instant, pkgTechs);
      overlay(true, "Running attack campaign…");
      runBackend(prompt, "attack").then(function (t) {
        overlay(false);
        origLaunch(prompt || "", t, true, pkgTechs);
      }).catch(function (e) {
        overlay(false);
        alert("Backend run failed:\n" + e.message);
      });
    };
  }

  if (typeof origRecon === "function") {
    window.TRIDENT_recon = function (prompt, trace, instant, launched) {
      if (looksLikeTrace(trace)) return origRecon(prompt, trace, instant, launched);
      overlay(true, "Running recon…");
      runBackend(prompt, "recon").then(function (t) {
        overlay(false);
        origRecon(prompt || "", t, true, launched);
      }).catch(function (e) {
        overlay(false);
        alert("Backend run failed:\n" + e.message);
      });
    };
  }

  console.log("[trident] backend bridge active — prompts now hit /api/run");
})();
