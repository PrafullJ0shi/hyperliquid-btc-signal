/**
 * Fig. 1 — wireframe inclination sphere.
 * The accent great-circle tilts with P(long). Canvas 2D only.
 */
(function (global) {
  "use strict";

  var INK = "#141414";
  var HAIR = "#B7B3A9";
  var ACCENT = "#8C1D12";

  function createInclination(canvas) {
    var pLong = null;
    var running = true;
    var start = performance.now();
    var raf = 0;
    var reduced =
      typeof window !== "undefined" &&
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function resize() {
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      var rect = canvas.getBoundingClientRect();
      var w = Math.max(200, Math.floor(rect.width));
      var h = w;
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      canvas.style.width = w + "px";
      canvas.style.height = h + "px";
    }

    function project(x, y, z, cx, cy, r, fl) {
      var s = r * fl / (fl + z);
      return { x: cx + x * s, y: cy - y * s, z: z };
    }

    function yawPoint(p, psi) {
      var c = Math.cos(psi);
      var s = Math.sin(psi);
      return { x: p.x * c - p.z * s, y: p.y, z: p.x * s + p.z * c };
    }

    function drawRing(ctx, pts, color, width, cx, cy, r, fl) {
      var projected = pts.map(function (p) {
        return project(p.x, p.y, p.z, cx, cy, r, fl);
      });
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      function stroke(filterZ, col, w) {
        ctx.beginPath();
        ctx.strokeStyle = col;
        ctx.lineWidth = w;
        var pen = false;
        for (var i = 0; i <= projected.length; i++) {
          var q = projected[i % projected.length];
          var ok = filterZ(q.z);
          if (ok) {
            if (!pen) {
              ctx.moveTo(q.x, q.y);
              pen = true;
            } else {
              ctx.lineTo(q.x, q.y);
            }
          } else {
            pen = false;
          }
        }
        ctx.stroke();
      }
      stroke(function (z) { return z < 0.02; }, HAIR, Math.max(0.6, width * 0.7));
      stroke(function (z) { return z >= -0.02; }, color, width);
    }

    function circle(n, map) {
      var pts = [];
      for (var i = 0; i <= n; i++) {
        var t = (i / n) * Math.PI * 2;
        pts.push(map(t));
      }
      return pts;
    }

    function draw(now) {
      var ctx = canvas.getContext("2d");
      if (!ctx) return;
      var w = canvas.width;
      var h = canvas.height;
      var cssW = parseFloat(canvas.style.width) || w;
      var dpr = w / cssW;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, w, h);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      var W = w / dpr;
      var H = h / dpr;
      var cx = W * 0.48;
      var cy = H * 0.50;
      var r = Math.min(W, H) * 0.38;
      var fl = 3.15;
      var elapsed = (now - start) / 1000;
      var psi = reduced ? 0.35 : 0.35 + elapsed * 0.08;
      var p = pLong == null ? 0.5 : pLong;
      var alpha = (2 * p - 1) * (Math.PI / 2);

      ctx.beginPath();
      ctx.strokeStyle = INK;
      ctx.lineWidth = 1.1;
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.stroke();

      var meridians = 12;
      var parallels = 6;
      var i, pts, th, ph;
      for (i = 1; i < parallels; i++) {
        th = (i / parallels) * Math.PI;
        pts = circle(96, function (t) {
          var x = Math.sin(th) * Math.cos(t);
          var y = Math.cos(th);
          var z = Math.sin(th) * Math.sin(t);
          return yawPoint({ x: x, y: y, z: z }, psi);
        });
        drawRing(ctx, pts, INK, 0.7, cx, cy, r, fl);
      }
      for (i = 0; i < meridians; i++) {
        ph = (i / meridians) * Math.PI;
        pts = circle(96, function (t) {
          var x = Math.sin(t) * Math.cos(ph);
          var y = Math.cos(t);
          var z = Math.sin(t) * Math.sin(ph);
          return yawPoint({ x: x, y: y, z: z }, psi);
        });
        drawRing(ctx, pts, INK, 0.7, cx, cy, r, fl);
      }

      pts = circle(128, function (t) {
        return yawPoint({ x: Math.cos(t), y: 0, z: Math.sin(t) }, psi);
      });
      drawRing(ctx, pts, INK, 1.15, cx, cy, r, fl);

      pts = circle(160, function (t) {
        var x = Math.cos(t);
        var y = -Math.sin(t) * Math.sin(alpha);
        var z = Math.sin(t) * Math.cos(alpha);
        return yawPoint({ x: x, y: y, z: z }, psi);
      });
      drawRing(ctx, pts, ACCENT, 1.8, cx, cy, r, fl);

      function pole(y, label, dy) {
        var p3 = yawPoint({ x: 0, y: y, z: 0 }, psi);
        var q = project(p3.x, p3.y, p3.z, cx, cy, r, fl);
        ctx.fillStyle = INK;
        ctx.beginPath();
        ctx.arc(q.x, q.y, 2.0, 0, Math.PI * 2);
        ctx.fill();
        ctx.font = "11px 'IBM Plex Sans', sans-serif";
        ctx.fillStyle = INK;
        ctx.textAlign = "center";
        ctx.fillText(label, q.x, q.y + dy);
      }
      pole(1, "LONG", -8);
      pole(-1, "SHORT", 16);

      var sx = W * 0.90;
      var y0 = cy + r;
      var y1 = cy - r;
      ctx.strokeStyle = INK;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(sx, y0);
      ctx.lineTo(sx, y1);
      ctx.stroke();
      var ticks = [
        { v: 0, label: "0.00" },
        { v: 0.4, label: "0.40" },
        { v: 0.5, label: "0.50" },
        { v: 0.6, label: "0.60" },
        { v: 1, label: "1.00" }
      ];
      ctx.font = "10px 'IBM Plex Mono', monospace";
      ctx.textAlign = "left";
      ctx.fillStyle = INK;
      ticks.forEach(function (tick) {
        var y = y0 + (y1 - y0) * tick.v;
        ctx.beginPath();
        ctx.moveTo(sx - 4, y);
        ctx.lineTo(sx + 4, y);
        ctx.stroke();
        ctx.fillText(tick.label, sx + 7, y + 3);
      });
      if (pLong != null) {
        var yn = y0 + (y1 - y0) * p;
        ctx.fillStyle = ACCENT;
        ctx.beginPath();
        ctx.moveTo(sx - 11, yn);
        ctx.lineTo(sx - 4, yn - 4);
        ctx.lineTo(sx - 4, yn + 4);
        ctx.closePath();
        ctx.fill();
      }
    }

    function loop(now) {
      if (!running) return;
      draw(now);
      if (!reduced) raf = requestAnimationFrame(loop);
    }

    function setReading(value) {
      pLong = value;
      if (typeof value === "number") {
        canvas.setAttribute(
          "aria-label",
          "Fig. 1. Consensus inclination sphere. Weighted P of long is " +
            value.toFixed(3) +
            "."
        );
      }
      if (reduced) draw(performance.now());
    }

    function destroy() {
      running = false;
      if (raf) cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
    }

    function onResize() {
      resize();
      if (reduced) draw(performance.now());
    }

    resize();
    window.addEventListener("resize", onResize);
    if (reduced) draw(performance.now());
    else raf = requestAnimationFrame(loop);

    return { setReading: setReading, destroy: destroy, resize: onResize };
  }

  global.createInclination = createInclination;
})(typeof window !== "undefined" ? window : this);
