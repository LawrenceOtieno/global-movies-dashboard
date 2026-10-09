/**
 * CultClassicsChart.jsx
 *
 * Popularity (x) vs. rating (y) quadrant scatter, both as dataset percentiles.
 * Top-left = hidden gems (highly rated, stayed obscure).
 * Bottom-right = overrated (hyped, underwhelmed).
 *
 * Requires recharts: npm install recharts
 *
 * Every point is colored by a continuous "tension" tier (rating percentile
 * minus popularity percentile) using the dashboard's own palette — not a
 * green/red highlight layer — with a custom legend explaining each tier.
 * Deliberately no on-chart arrows or text labels (per design direction —
 * they clutter at this point density); the legend carries that explanation
 * instead.
 *
 * Clicking any point selects it and shows its details plus a live inline
 * "movies like this" lookup, reusing /api/recommend directly (not the
 * separate MovieRecommender component — kept as its own isolated fetch so
 * clicking a dot never touches that component's state or vice versa).
 *
 * Axis/tick colors are set explicitly (rather than left to Recharts'
 * defaults) because this component is embedded in a host page with its own
 * global Tailwind styles — an inherited `color` or `fill` from the host page
 * can silently make default SVG tick text invisible even though the chart
 * itself mounted correctly.
 */

import { useEffect, useState, memo } from "react";
import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Label,
} from "recharts";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:5000";
const AXIS_COLOR = "#6b7280";

// Dashboard's own palette, used for every tier below — no green/red.
const TIERS = [
  { min: 40, max: 101, label: "Top-Tier Gem", color: "#073B4C", desc: "Rated far above its popularity, a standout the crowd missed" },
  { min: 20, max: 40, label: "Strong Gem", color: "#15616D", desc: "Clearly rated above what its popularity would predict" },
  { min: 8, max: 20, label: "Rising Gem", color: "#8AA79F", desc: "A little more loved than its popularity suggests" },
  { min: -8, max: 8, label: "Expected", color: "#B9C2C5", desc: "Rating and popularity roughly line up" },
  { min: -20, max: -8, label: "Mildly Overrated", color: "#FFB366", desc: "A little more hyped than the rating backs up" },
  { min: -40, max: -20, label: "Overrated", color: "#FF7D00", desc: "Clearly more popular than its rating justifies" },
  { min: -101, max: -40, label: "Heavily Overrated", color: "#B8440A", desc: "Huge popularity, rating far behind it" },
];

function tierFor(tension) {
  return TIERS.find((t) => tension >= t.min && tension < t.max) || TIERS[3];
}

// Correct ordinal suffix for any integer — 1st, 2nd, 3rd, 4th ... 11th, 12th,
// 13th (the "teens" are all "th", not "1th/2th/3th") ... 21st, 22nd, 23rd, 24th ...
function ordinal(n) {
  const rounded = Math.round(n);
  const remainder100 = rounded % 100;
  if (remainder100 >= 11 && remainder100 <= 13) return `${rounded}th`;
  switch (rounded % 10) {
    case 1: return `${rounded}st`;
    case 2: return `${rounded}nd`;
    case 3: return `${rounded}rd`;
    default: return `${rounded}th`;
  }
}

function CustomTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const p = payload[0].payload;
  return (
    <div style={{
      background: "#073B4C", border: "1px solid #15616D", borderRadius: 8,
      padding: "8px 12px", color: "#fff", fontSize: 13,
    }}>
      <strong>{p.title} {p.year && `(${p.year})`}</strong>
      <div>Popularity: {ordinal(p.popularity_percentile)} percentile</div>
      <div>Rating: {ordinal(p.rating_percentile)} percentile</div>
      {p.weighted_rating && <div>Weighted rating: {p.weighted_rating}</div>}
      <div style={{ marginTop: 4, color: "#8AA79F" }}>Click for details & similar movies</div>
    </div>
  );
}

// Module-level cache, outside the component — survives CultClassicsChart
// being unmounted/remounted every time you navigate away from the Overview
// page and back. Without this, switching to Analytics and back re-fetched
// the full sample and rebuilt the scatter from scratch every time. This data
// doesn't change during a server session, so caching by `limit` (the only
// prop that affects the request) is safe and correct.
const cultClassicsCache = {};

function CultClassicsChart({ limit = 15 }) {
  const [data, setData] = useState(cultClassicsCache[limit]?.data ?? null);
  const [error, setError] = useState(null);
  const [plotted, setPlotted] = useState(cultClassicsCache[limit]?.plotted ?? []);

  const [selected, setSelected] = useState(null);
  const [recLoading, setRecLoading] = useState(false);
  const [recResults, setRecResults] = useState(null);
  const [recError, setRecError] = useState(null);

  useEffect(() => {
    if (cultClassicsCache[limit]) return; // already have it from a previous visit
    fetch(`${API_BASE}/api/cult-classics?limit=${limit}&sample_size=500`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((result) => {
        setData(result);
        // Merge the background sample with the guaranteed hidden-gem/
        // overrated extremes (deduped by title) so the most interesting
        // points are always represented, then tier-color every one of
        // them under a single unified scheme.
        const byTitle = new Map();
        [...(result.all_points || []), ...(result.hidden_gems || []), ...(result.overrated || [])]
          .forEach((p) => byTitle.set(p.title, p));
        const plottedResult = Array.from(byTitle.values()).map((p) => {
          const tension = (p.rating_percentile ?? 0) - (p.popularity_percentile ?? 0);
          return { ...p, tension, tier: tierFor(tension) };
        });
        setPlotted(plottedResult);
        cultClassicsCache[limit] = { data: result, plotted: plottedResult };
      })
      .catch((e) => setError(e.message));
  }, [limit]);

  const runRecommendFor = async (title) => {
    setRecLoading(true);
    setRecError(null);
    setRecResults(null);
    try {
      const res = await fetch(`${API_BASE}/api/recommend?title=${encodeURIComponent(title)}&n=5`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `Recommendation failed (HTTP ${res.status})`);
      }
      setRecResults(await res.json());
    } catch (e) {
      setRecError(e.message);
    } finally {
      setRecLoading(false);
    }
  };

  const handleDotClick = (point) => {
    setSelected(point);
    runRecommendFor(point.title);
  };

  if (error) {
    return (
      <div className="text-sm text-red-600 text-center py-12">
        Couldn't load cult classics data: {error} — is the Flask backend running?
      </div>
    );
  }
  if (!data) {
    return <div className="text-sm text-gray-400 text-center py-12">Loading...</div>;
  }
  if (plotted.length === 0) {
    return (
      <div className="text-sm text-gray-400 text-center py-12">
        No cult-classics data yet — run <code className="font-mono">train_model.py</code> against
        the full dataset, then restart the Flask server.
      </div>
    );
  }

  return (
    <div className="cult-classics-chart">
      <h3 className="text-lg font-bold text-[#15616D]">Hidden Gems vs. Overrated — Movies</h3>
      <p className="text-sm text-gray-600 mb-4 max-w-3xl leading-relaxed">
        Somewhere in this dataset sits a quiet little film that almost nobody bought a ticket for, and the
        handful of people who found it anyway still won't stop talking about it. Somewhere else sits a
        blockbuster that filled every billboard in town, then left the people who actually sat down to watch
        it a little underwhelmed. Every dot below is a movie caught at that exact moment of truth: how loudly
        the world talked about it, placed against how much the people who watched it genuinely loved it. Most
        movies play it straight, landing close to the dashed line, where hype and heart roughly agree. The
        ones worth noticing are the dots that drift away from it, in either direction. The color of each dot
        tells you which way it drifted and by how much, fully explained in the legend below.{' '}
        <em>Click any dot for its details and similar recommendations.</em>{' '}
        <em>For peak performance, the plot represents a sample of 500 movies; the recommenders below, however, work with the entire dataset plus TMDB Live lookup.</em>
      </p>
      <ResponsiveContainer width="100%" height={480}>
        <ScatterChart margin={{ top: 10, right: 30, bottom: 30, left: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E7ECEF" />
          <XAxis
            type="number" dataKey="popularity_percentile" domain={[0, 100]}
            tick={{ fontSize: 12, fill: AXIS_COLOR }}
            axisLine={{ stroke: AXIS_COLOR }}
            tickLine={{ stroke: AXIS_COLOR }}
          >
            <Label value="Popularity percentile →" position="bottom" offset={0} fill={AXIS_COLOR} fontSize={12} />
          </XAxis>
          <YAxis
            type="number" dataKey="rating_percentile" domain={[0, 100]}
            tick={{ fontSize: 12, fill: AXIS_COLOR }}
            axisLine={{ stroke: AXIS_COLOR }}
            tickLine={{ stroke: AXIS_COLOR }}
          >
            <Label value="Rating percentile →" angle={-90} position="left" fill={AXIS_COLOR} fontSize={12} />
          </YAxis>
          <ZAxis range={[36, 36]} />
          <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 100, y: 100 }]} stroke="#9ca3af" strokeDasharray="4 4" />
          <Tooltip content={<CustomTooltip />} cursor={{ strokeDasharray: "3 3" }} />

          <Scatter
            data={plotted}
            onClick={(point) => handleDotClick(point)}
            cursor="pointer"
            isAnimationActive={false}
            shape={(props) => (
              <circle
                cx={props.cx} cy={props.cy} r={5}
                fill={props.payload.tier.color}
                fillOpacity={0.75}
                stroke={selected?.title === props.payload.title ? "#073B4C" : "none"}
                strokeWidth={selected?.title === props.payload.title ? 2 : 0}
              />
            )}
          />
        </ScatterChart>
      </ResponsiveContainer>

      {/* Custom legend — replaces on-chart arrows/text, which clutter at this point density */}
      <div className="flex flex-wrap gap-x-5 gap-y-2 mt-2 px-2">
        {TIERS.map((t) => (
          <div key={t.label} className="flex items-center gap-1.5" title={t.desc}>
            <span className="w-3 h-3 rounded-full inline-block shrink-0" style={{ backgroundColor: t.color }}></span>
            <span className="text-xs text-gray-600">{t.label}</span>
          </div>
        ))}
      </div>

      {/* Selected-point detail panel + inline recommendations */}
      {selected && (
        <div className="mt-5 bg-[#E7ECEF]/60 border border-gray-200/60 rounded-2xl p-5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-xs font-bold uppercase tracking-wider" style={{ color: selected.tier.color }}>{selected.tier.label}</p>
              <h4 className="text-lg font-bold text-[#073B4C]">
                {selected.title} {selected.year && <span className="text-sm font-normal text-gray-400">({selected.year})</span>}
              </h4>
              <p className="text-xs text-gray-500 mt-1">
                Rating: {selected.weighted_rating?.toFixed(1)} · {ordinal(selected.rating_percentile)} percentile for rating,{' '}
                {ordinal(selected.popularity_percentile)} for popularity
                {selected.vote_count != null && ` · ${selected.vote_count.toLocaleString()} votes`}
              </p>
            </div>
            <button onClick={() => { setSelected(null); setRecResults(null); }} className="text-gray-400 hover:text-gray-600 text-sm shrink-0">✕</button>
          </div>

          <div className="mt-4">
            <p className="text-xs font-bold uppercase tracking-wider text-[#15616D] mb-2">Similar movies</p>
            {recLoading && <p className="text-sm text-gray-400">Loading…</p>}
            {recError && <p className="text-sm text-red-600">{recError}</p>}
            {recResults && recResults.recommendations.length === 0 && (
              <p className="text-sm text-gray-500">
                {recResults.accuracy_note || 'No close matches found.'}
              </p>
            )}
            {recResults && recResults.recommendations.length > 0 && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {recResults.recommendations.map((r, idx) => (
                  <div
                    key={`${r.title}-${r.year || idx}`}
                    className="bg-white border border-gray-200/60 rounded-xl p-3 flex items-center gap-3"
                  >
                    {/* Left column: takes remaining width, truncates the
                        title, keeps the year visible as a shrink-0 sibling. */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-baseline gap-1.5 min-w-0">
                        <button
                          onClick={() => runRecommendFor(r.title)}
                          title={r.title}
                          className="text-left text-sm font-semibold text-[#073B4C] hover:text-[#15616D] hover:underline transition truncate min-w-0"
                        >
                          {r.title}
                        </button>
                        {r.year && (
                          <span className="text-xs font-normal text-gray-400 shrink-0">({r.year})</span>
                        )}
                      </div>
                      <p className="text-xs text-gray-500 mt-0.5">{Math.round(r.match)}% match</p>
                    </div>

                    {/* Right column: fixed-width rating badge, never shrinks,
                        never gets overlapped. */}
                    <span className="text-sm font-bold text-[#15616D] shrink-0 flex items-center gap-1">
                      <svg className="w-3.5 h-3.5 text-[#FF9F43]" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M12 .587l3.668 7.431 8.212 1.192-5.94 5.787 1.402 8.168-7.342-3.861-7.342 3.861 1.402-8.168-5.94-5.787 8.212-1.192z"/>
                      </svg>
                      {r.weighted_rating.toFixed(1)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default memo(CultClassicsChart);