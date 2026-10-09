/**
 * TvCultClassicsChart.jsx
 *
 * Mirrors CultClassicsChart.jsx exactly — theme-tiered coloring, custom
 * legend, click-to-recommend — for TV shows instead of movies. Hits
 * /api/tv/cult-classics and /api/tv/recommend; the TV dataset's title field
 * is `name`, not `title`.
 */

import { useEffect, useState, memo } from "react";
import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Label,
} from "recharts";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:5000";
const AXIS_COLOR = "#6b7280";

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
      <strong>{p.name} {p.year && `(${p.year})`}</strong>
      <div>Popularity: {ordinal(p.popularity_percentile)} percentile</div>
      <div>Rating: {ordinal(p.rating_percentile)} percentile</div>
      {p.weighted_rating && <div>Weighted rating: {p.weighted_rating}</div>}
      <div style={{ marginTop: 4, color: "#8AA79F" }}>Click for details & similar shows</div>
    </div>
  );
}

// Module-level cache, outside the component — same rationale as
// CultClassicsChart.jsx's cultClassicsCache: survives remounts when
// navigating away from the Overview page and back.
const tvCultClassicsCache = {};

function TvCultClassicsChart({ limit = 15 }) {
  const [data, setData] = useState(tvCultClassicsCache[limit]?.data ?? null);
  const [error, setError] = useState(null);
  const [plotted, setPlotted] = useState(tvCultClassicsCache[limit]?.plotted ?? []);

  const [selected, setSelected] = useState(null);
  const [recLoading, setRecLoading] = useState(false);
  const [recResults, setRecResults] = useState(null);
  const [recError, setRecError] = useState(null);

  useEffect(() => {
    if (tvCultClassicsCache[limit]) return; // already have it from a previous visit
    fetch(`${API_BASE}/api/tv/cult-classics?limit=${limit}&sample_size=500`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((result) => {
        setData(result);
        const byName = new Map();
        [...(result.all_points || []), ...(result.hidden_gems || []), ...(result.overrated || [])]
          .forEach((p) => byName.set(p.name, p));
        const plottedResult = Array.from(byName.values()).map((p) => {
          const tension = (p.rating_percentile ?? 0) - (p.popularity_percentile ?? 0);
          return { ...p, tension, tier: tierFor(tension) };
        });
        setPlotted(plottedResult);
        tvCultClassicsCache[limit] = { data: result, plotted: plottedResult };
      })
      .catch((e) => setError(e.message));
  }, [limit]);

  const runRecommendFor = async (name) => {
    setRecLoading(true);
    setRecError(null);
    setRecResults(null);
    try {
      const res = await fetch(`${API_BASE}/api/tv/recommend?title=${encodeURIComponent(name)}&n=5`);
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
    runRecommendFor(point.name);
  };

  if (error) {
    return (
      <div className="text-sm text-red-600 text-center py-12">
        Couldn't load TV cult classics data: {error} — is the Flask backend running?
      </div>
    );
  }
  if (!data) {
    return <div className="text-sm text-gray-400 text-center py-12">Loading...</div>;
  }
  if (plotted.length === 0) {
    return (
      <div className="text-sm text-gray-400 text-center py-12">
        No TV cult-classics data yet — run <code className="font-mono">train_tv_model.py</code> against
        the full dataset, then restart the Flask server.
      </div>
    );
  }

  return (
    <div className="tv-cult-classics-chart">
      <h3 className="text-lg font-bold text-[#15616D]">Hidden Gems vs. Overrated — TV Shows</h3>
      <p className="text-sm text-gray-600 mb-4 max-w-3xl leading-relaxed">
        Television runs on a different kind of word of mouth than movies do. A show can land on a streaming
        service with almost no fanfare, picked up by a few strangers on a slow weekend, and still end up with
        a following so devoted they'll corner you at a party to make you promise you'll watch it. Meanwhile
        the show everyone was supposed to be talking about, the one with its name on every bus stop for a
        month, quietly loses its audience a few episodes in. Every dot below marks one of those stories: how
        much attention a show pulled in, set against how much the people who stuck around actually rated it.
        Most shows deliver roughly what their buzz promised. The far more interesting ones are the outliers,
        the slow-burn favorite nobody saw coming and the heavily hyped premiere that didn't hold up. See the
        legend below for what each color means.{' '}
        <em>Click any dot for its details and similar recommendations.</em>{' '}
        <em>For peak performance, the plot represents a sample of 500 TV shows; the recommenders below, however, work with the entire dataset plus TMDB Live lookup.</em>
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
                stroke={selected?.name === props.payload.name ? "#073B4C" : "none"}
                strokeWidth={selected?.name === props.payload.name ? 2 : 0}
              />
            )}
          />
        </ScatterChart>
      </ResponsiveContainer>

      <div className="flex flex-wrap gap-x-5 gap-y-2 mt-2 px-2">
        {TIERS.map((t) => (
          <div key={t.label} className="flex items-center gap-1.5" title={t.desc}>
            <span className="w-3 h-3 rounded-full inline-block shrink-0" style={{ backgroundColor: t.color }}></span>
            <span className="text-xs text-gray-600">{t.label}</span>
          </div>
        ))}
      </div>

      {selected && (
        <div className="mt-5 bg-[#E7ECEF]/60 border border-gray-200/60 rounded-2xl p-5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-xs font-bold uppercase tracking-wider" style={{ color: selected.tier.color }}>{selected.tier.label}</p>
              <h4 className="text-lg font-bold text-[#073B4C]">
                {selected.name} {selected.year && <span className="text-sm font-normal text-gray-400">({selected.year})</span>}
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
            <p className="text-xs font-bold uppercase tracking-wider text-[#15616D] mb-2">Similar shows</p>
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
                    key={`${r.name}-${r.year || idx}`}
                    className="bg-white border border-gray-200/60 rounded-xl p-3 flex items-center gap-3"
                  >
                    {/* Left column: takes remaining width, truncates the
                        name, keeps the year visible as a shrink-0 sibling. */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-baseline gap-1.5 min-w-0">
                        <button
                          onClick={() => runRecommendFor(r.name)}
                          title={r.name}
                          className="text-left text-sm font-semibold text-[#073B4C] hover:text-[#15616D] hover:underline transition truncate min-w-0"
                        >
                          {r.name}
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

export default memo(TvCultClassicsChart);