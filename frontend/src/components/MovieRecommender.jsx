import React, { useState } from 'react';

// Kept in its own component, isolated from Dashboard's state, on purpose:
// Dashboard also renders CultClassicsChart, which draws ~1500 scatter
// points. If the search box's state lived in Dashboard (as it originally
// did), every keystroke re-rendered the entire dashboard — including that
// chart — which is what made typing feel laggy. Isolating the input here
// means typing only re-renders this small component.

const API_BASE_URL = import.meta.env.VITE_API_BASE || 'http://localhost:5000';

export default function MovieRecommender() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [suggestions, setSuggestions] = useState([]);

  const runRecommend = async (titleOverride) => {
    const searchTitle = (titleOverride ?? query).trim();
    if (!searchTitle) return;
    setLoading(true);
    setError(null);
    setSuggestions([]);
    setResults(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/recommend?title=${encodeURIComponent(searchTitle)}&n=8`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setSuggestions(err.suggestions || []);
        throw new Error(err.error || `Recommendation failed (HTTP ${res.status})`);
      }
      const result = await res.json();
      setResults(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const pickSuggestion = (title) => {
    setQuery(title);
    runRecommend(title);
  };

  return (
    <section id="recommend-section" className="bg-white p-8 rounded-3xl shadow-md border border-gray-100">
      <div className="max-w-3xl mx-auto text-center mb-8">
        <span className="bg-[#FF7D00]/10 text-[#FF7D00] font-bold text-xs uppercase px-3 py-1 rounded-full tracking-wider">Content-Based Recommender</span>
        <h2 className="text-2xl sm:text-3xl font-extrabold text-[#15616D] mt-2">Find Movies Like This</h2>
        <p className="text-sm text-gray-500 mt-1">Type a movie title to get similar, well-rated recommendations.</p>
      </div>

      {/* FIX: flex-col on mobile, flex-row on tablet+ */}
      <div className="max-w-xl mx-auto flex flex-col sm:flex-row gap-3">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') runRecommend(); }}
          placeholder="e.g. Inception"
          className="w-full bg-white border border-gray-300 rounded-xl px-4 py-3 text-sm font-medium focus:ring-2 focus:ring-[#15616D] focus:outline-none"
        />
        <button
          onClick={() => runRecommend()}
          disabled={loading || !query.trim()}
          className="w-full sm:w-auto bg-[#15616D] hover:bg-teal-800 disabled:opacity-60 disabled:cursor-not-allowed text-white font-bold py-3 px-6 rounded-xl transition duration-200 shadow-md shrink-0"
        >
          {loading ? 'Searching…' : 'Recommend'}
        </button>
      </div>

      {error && (
        <div className="max-w-xl mx-auto mt-4 text-center">
          <p className="text-sm text-red-600">
            No movie found matching "{query}" in the dataset.
          </p>
          {suggestions.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2 justify-center">
              <span className="text-xs text-gray-400 self-center">Did you mean:</span>
              {suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => pickSuggestion(s)}
                  className="text-xs font-semibold text-[#15616D] bg-[#E7ECEF] hover:bg-[#15616D] hover:text-white transition px-3 py-1 rounded-full"
                >
                  {s}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {results && (
        <div className="max-w-3xl mx-auto mt-8">
          <p className="text-sm text-gray-500 mb-1 text-center">Because you searched for <span className="font-semibold text-[#073B4C]">{results.source_title}</span>:</p>
          {results.source === 'live_tmdb_lookup' && (
            <p className="text-xs text-[#FF7D00] text-center mb-3">
              This movie isn't in your indexed dataset — fetched live from TMDB for this search.
            </p>
          )}
          {results.source !== 'live_tmdb_lookup' && <div className="mb-3" />}

          {results.recommendations.length === 0 && (
            <p className="text-sm text-gray-500 text-center py-6">
              {results.accuracy_note || 'No close matches found.'}
            </p>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {results.recommendations.map((r, idx) => (
              <div
                key={`${r.title}-${r.year || idx}`}
                className="bg-[#E7ECEF]/60 border border-gray-200/60 rounded-xl p-4 flex items-center gap-3"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-baseline gap-1.5 min-w-0">
                    <button
                      onClick={() => runRecommend(r.title)}
                      title={r.title}
                      className="text-left text-sm font-semibold text-[#073B4C] hover:text-[#15616D] hover:underline transition truncate min-w-0"
                    >
                      {r.title}
                    </button>
                    {r.year && (
                      <span className="text-xs font-normal text-gray-400 shrink-0">({r.year})</span>
                    )}
                  </div>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {r.vote_count.toLocaleString()} votes · {Math.round(r.match)}% match
                  </p>
                </div>

                <span className="text-sm font-bold text-[#15616D] shrink-0 flex items-center gap-1">
                  <svg className="w-3.5 h-3.5 text-[#FF9F43]" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M12 .587l3.668 7.431 8.212 1.192-5.94 5.787 1.402 8.168-7.342-3.861-7.342 3.861 1.402-8.168-5.94-5.787 8.212-1.192z"/>
                  </svg>
                  {r.weighted_rating.toFixed(1)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}