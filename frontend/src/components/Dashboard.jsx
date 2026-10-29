import React, { useEffect, useRef, useState } from 'react';
import * as ChartJS from 'chart.js';
const { Chart, registerables } = ChartJS;
Chart.register(...registerables);

import CultClassicsChart from './CultClassicsChart';
import TvCultClassicsChart from './TvCultClassicsChart';
import TvDashboard from './TvDashboard';
import MovieRecommender from './MovieRecommender';
import TvRecommender from './TvRecommender';
import ChartDownloader from './ChartDownloader';

import logoThumbnail from '../assets/logo.png';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

const SECTION_ICONS = import.meta.glob('../assets/section-icons/*', { eager: true, import: 'default' });
function resolveSectionIcon(filename) {
  const entry = Object.entries(SECTION_ICONS).find(([path]) => path.endsWith(`/${filename}`));
  return entry ? entry[1] : null;
}

const FONT_STACK = "'Segoe UI', Inter, Arial, sans-serif";

const COMPANY_BIOS = {
  'Walt Disney Pictures': { founded: 1923, country: 'United States', netWorth: '~$170B market cap (The Walt Disney Company)', ceo: "Josh D'Amaro — CEO, The Walt Disney Company", logoFile: 'disney.png', logoDomain: 'disney.com' },
  'Paramount': { founded: 1912, country: 'United States', netWorth: '~$10B market cap (Paramount Skydance)', ceo: 'David Ellison — Chairman & CEO, Paramount Skydance', logoFile: 'paramount.png', logoDomain: 'paramount.com' },
  'Universal Pictures': { founded: 1912, country: 'United States', netWorth: '~$100B market cap (Comcast, parent company)', ceo: 'Donna Langley — Chairman, Universal Pictures', logoFile: 'universal.png', logoDomain: 'universalpictures.com' },
  'Marvel Studios': { founded: 1993, country: 'United States', netWorth: '~$170B market cap (The Walt Disney Company, parent)', ceo: 'Kevin Feige — President, Marvel Studios', logoFile: 'marvel.png', logoDomain: 'marvel.com' },
  'Columbia Pictures': { founded: 1924, country: 'United States (Sony Group HQ: Tokyo, Japan)', netWorth: '~$140B market cap (Sony Group, parent company)', ceo: 'Tom Rothman — Chairman & CEO, Sony Pictures Motion Picture Group', logoFile: 'columbia.png', logoDomain: 'sonypictures.com' },
  'Warner Bros. Pictures': { founded: 1923, country: 'United States', netWorth: '~$67B market cap (Warner Bros. Discovery, parent)', ceo: 'Mike De Luca & Pam Abdy — Co-CEOs, Warner Bros. Motion Picture Group', logoFile: 'warnerbros.png', logoDomain: 'warnerbros.com' }
};

const LOCAL_LOGOS = import.meta.glob('../assets/company-logos/*', { eager: true, import: 'default' });

function resolveLogo(bio) {
  if (!bio) return null;
  const localEntry = Object.entries(LOCAL_LOGOS).find(([path]) => path.endsWith(`/${bio.logoFile}`));
  if (localEntry) return localEntry[1];
  return `https://logo.clearbit.com/${bio.logoDomain}?size=256`;
}

const FALLBACK_LOGO = 'data:image/svg+xml;utf8,' + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="#15616D"/><rect x="30" y="35" width="40" height="45" fill="#FF9F43"/><rect x="38" y="45" width="8" height="8" fill="#15616D"/><rect x="54" y="45" width="8" height="8" fill="#15616D"/><rect x="38" y="60" width="8" height="8" fill="#15616D"/><rect x="54" y="60" width="8" height="8" fill="#15616D"/></svg>'
);

function formatCurrency(dollars) {
  if (!dollars || Number.isNaN(dollars)) return '$0';
  if (dollars >= 1e12) return `$${(dollars / 1e12).toFixed(2)}T`;
  if (dollars >= 1e9) return `$${(dollars / 1e9).toFixed(2)}B`;
  if (dollars >= 1e6) return `$${(dollars / 1e6).toFixed(1)}M`;
  if (dollars >= 1e3) return `$${(dollars / 1e3).toFixed(1)}K`;
  return `$${dollars.toFixed(0)}`;
}

export default function Dashboard() {
  const [currentPage, setCurrentPage] = useState('overview');
  const [data, setData] = useState(null);
  const [modelMeta, setModelMeta] = useState(null);
  const [loadError, setLoadError] = useState(null);

  const genreCanvasRef = useRef(null);
  const countryCanvasRef = useRef(null);
  const companyCanvasRef = useRef(null);

  const [companyBarPositions, setCompanyBarPositions] = useState([10, 30, 50, 70, 90]);
  const [activeCompanyTooltip, setActiveCompanyTooltip] = useState(null);

  // --- Swipe Navigation Logic ---
  const touchStartX = useRef(null);
  const touchEndX = useRef(null);

  const handlePointerDown = (e) => {
    if (e.isPrimary) {
      touchStartX.current = e.clientX;
    }
  };

  const handlePointerUp = (e) => {
    if (!e.isPrimary || touchStartX.current === null) return;
    
    touchEndX.current = e.clientX;
    const distance = touchStartX.current - touchEndX.current;

    // 50px swipe threshold
    if (distance > 50) {
      // Swiped Left -> Go to Full Analytics
      if (currentPage === 'overview') setCurrentPage('analytics');
    } else if (distance < -50) {
      // Swiped Right -> Go to Overview
      if (currentPage === 'analytics') setCurrentPage('overview');
    }
    
    touchStartX.current = null;
    touchEndX.current = null;
  };

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE_URL}/api/summary-stats`).then((r) => { if (!r.ok) throw new Error(`summary-stats failed (HTTP ${r.status})`); return r.json(); }),
      fetch(`${API_BASE_URL}/api/genre-distribution`).then((r) => { if (!r.ok) throw new Error(`genre-distribution failed (HTTP ${r.status})`); return r.json(); }),
      fetch(`${API_BASE_URL}/api/production-countries-performance`).then((r) => { if (!r.ok) throw new Error(`production-countries-performance failed (HTTP ${r.status})`); return r.json(); }),
      fetch(`${API_BASE_URL}/api/production-companies-performance`).then((r) => { if (!r.ok) throw new Error(`production-companies-performance failed (HTTP ${r.status})`); return r.json(); }),
      fetch(`${API_BASE_URL}/api/movie-rankings`).then((r) => { if (!r.ok) throw new Error(`movie-rankings failed (HTTP ${r.status})`); return r.json(); }),
      fetch(`${API_BASE_URL}/api/model-metadata`).then((r) => { if (!r.ok) throw new Error(`model-metadata failed (HTTP ${r.status})`); return r.json(); })
    ])
      .then(([summary, genreDist, countryPerf, companyPerf, rankings, meta]) => {
        setData({
          totalMovies: summary.total_movies,
          totalProductionCompanies: summary.total_production_companies,
          avgRating: summary.average_rating,
          totalRevenue: summary.total_revenue,
          avgRuntime: summary.average_runtime_minutes,
          highlyRatedCount: summary.highly_rated_count,
          topGenreByRevenue: summary.top_genre_by_revenue ?? ['—', 0],
          genreStats: genreDist.genres.map((g) => [g.genre, g.count, g.percentage]),
          uncategorizedPct: genreDist.uncategorized_percentage,
          countryStats: countryPerf,
          companyStats: companyPerf,
          topMovies: rankings.top,
          bottomMovies: rankings.bottom
        });
        setModelMeta(meta);
      })
      .catch((err) => setLoadError(`${err.message} — is the Flask backend running? (cd backend && python app.py)`));
  }, []);

  useEffect(() => {
    if (!data || currentPage !== 'analytics') return;

    const genreCanvas = genreCanvasRef.current;
    const countryCanvas = countryCanvasRef.current;
    const companyCanvas = companyCanvasRef.current;
    if (!genreCanvas || !countryCanvas || !companyCanvas) return;

    const genrePct = Object.fromEntries(data.genreStats.map(([g, , pct]) => [g, pct]));
    const genreChartInstance = new Chart(genreCanvas.getContext('2d'), {
      type: 'doughnut',
      data: {
        labels: data.genreStats.map(([genre]) => genre),
        datasets: [{ data: data.genreStats.map(([, count]) => count), backgroundColor: ['#15616D', '#8AA79F', '#FF7D00', '#073B4C', '#208190', '#FF9F43', '#A3C1AD', '#5C8374'], borderWidth: 2, borderColor: '#ffffff' }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { font: { family: FONT_STACK, size: 11, weight: '600' }, boxWidth: 12, padding: 12, generateLabels: (chart) => chart.data.labels.map((label, i) => ({ text: `${label} (${genrePct[label]}%)`, fillStyle: chart.data.datasets[0].backgroundColor[i], strokeStyle: chart.data.datasets[0].backgroundColor[i], index: i })) } },
          tooltip: { callbacks: { label: (ctx) => `${ctx.label}: ${ctx.raw.toLocaleString()} movies (${genrePct[ctx.label]}%)` } }
        },
        cutout: '65%'
      }
    });

    const countryChartInstance = new Chart(countryCanvas.getContext('2d'), {
      type: 'bar',
      data: { labels: data.countryStats.map((c) => c.production_country), datasets: [{ label: 'Average Rating', data: data.countryStats.map((c) => c.avg_rating), backgroundColor: '#FF7D00', borderRadius: 8, barThickness: 18 }] },
      options: {
        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { min: 0, max: 10, grid: { color: '#E7ECEF' }, ticks: { font: { family: FONT_STACK } }, title: { display: true, text: 'Average Rating (0–10)', font: { family: FONT_STACK, size: 10, weight: '600' }, color: '#8AA79F' } },
          y: { grid: { display: false }, ticks: { font: { family: FONT_STACK, weight: '600' } }, title: { display: true, text: 'Country', font: { family: FONT_STACK, size: 10, weight: '600' }, color: '#8AA79F' } }
        }
      }
    });

    const companyPct = Object.fromEntries(data.companyStats.map((c) => [c.production_company, c.percentage_of_total]));
    const companyChartInstance = new Chart(companyCanvas.getContext('2d'), {
      type: 'bar',
      data: { labels: data.companyStats.map((c) => c.production_company), datasets: [{ label: 'Total Revenue ($B)', data: data.companyStats.map((c) => Number((c.total_revenue / 1e9).toFixed(2))), backgroundColor: '#15616D', borderRadius: 8, barThickness: 32 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (ctx) => `$${ctx.raw}B (${companyPct[data.companyStats[ctx.dataIndex].production_company]}% of total revenue)` } }
        },
        scales: { x: { grid: { display: false }, ticks: { display: false } }, y: { grid: { color: '#E7ECEF' }, ticks: { callback: (v) => '$' + v + 'B', font: { family: FONT_STACK } } } }
      },
      plugins: [{
        id: 'syncCompanyLogoPositions',
        afterLayout: (chart) => { const meta = chart.getDatasetMeta(0); const width = chart.width || 1; const positions = meta.data.map((bar) => (bar.x / width) * 100); setCompanyBarPositions(positions); }
      }]
    });

    return () => { genreChartInstance.destroy(); countryChartInstance.destroy(); companyChartInstance.destroy(); };
  }, [data, currentPage]);

  return (
    <div className="bg-[#E7ECEF] min-h-screen text-[#073B4C] antialiased" style={{ fontFamily: FONT_STACK }}>
      <header className="bg-[#15616D] text-white shadow-lg sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex flex-col sm:flex-row justify-between items-center">
          <div className="flex items-center space-x-3">
            <div className="h-12 rounded-xl overflow-hidden shadow-md flex items-center justify-center border-2 border-white/30 shrink-0">
              <img src={logoThumbnail} alt="CineMetrics" className="h-full w-auto object-contain block" />
            </div>
            <div>
              <h1 className="text-2xl font-extrabold tracking-tight">CineMetrics</h1>
              <p className="text-xs text-[#8AA79F] font-medium">Gems vs. Overrated: Global Movie Intelligence & Recommendation Engine</p>
            </div>
          </div>
          <div className="mt-3 sm:mt-0 flex items-center space-x-4">
            <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-[#8AA79F]/30 text-white border border-[#8AA79F]/50">
              <span className={`w-2 h-2 mr-2 rounded-full shrink-0 ${data ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400 animate-pulse'}`}></span>
              {data ? `Dataset: ${data.totalMovies.toLocaleString()} Movies (TMDB)` : loadError ? 'Dataset failed to load' : 'Loading dataset…'}
            </span>
          </div>
        </div>
      </header>

      <div className="bg-white border-b border-gray-200 sticky top-[72px] sm:top-[76px] z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex gap-1">
          <button onClick={() => setCurrentPage('overview')} className={`px-4 py-3 text-sm font-semibold border-b-2 transition ${currentPage === 'overview' ? 'border-[#FF7D00] text-[#15616D]' : 'border-transparent text-gray-400 hover:text-gray-600'}`}>Overview</button>
          <button onClick={() => setCurrentPage('analytics')} className={`px-4 py-3 text-sm font-semibold border-b-2 transition ${currentPage === 'analytics' ? 'border-[#FF7D00] text-[#15616D]' : 'border-transparent text-gray-400 hover:text-gray-600'}`}>Full Analytics</button>
        </div>
        {/* Swipe Hint for Mobile */}
        <div className="text-center pb-2 text-[10px] text-gray-400 font-medium sm:hidden">
          Swipe left or right to change views
        </div>
      </div>

      {loadError && (<div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-6"><div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl p-4">Couldn't reach the backend at <code className="font-mono">{API_BASE_URL}</code> — {loadError}</div></div>)}
      {!data && !loadError && (<div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-6"><div className="bg-white border border-gray-200 text-gray-500 text-sm rounded-xl p-4">Loading your dataset…</div></div>)}

      <main 
        className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8"
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
        style={{ touchAction: 'pan-y' }}
      >
      {currentPage === 'overview' && (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 w-full items-start">
            <div className="bg-white p-6 rounded-2xl shadow-md w-full min-w-0"><CultClassicsChart limit={15} /></div>
            <div className="bg-white p-6 rounded-2xl shadow-md w-full min-w-0"><TvCultClassicsChart limit={15} /></div>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 w-full items-start">
            <MovieRecommender />
            <TvRecommender />
          </div>
        </>
      )}

      {currentPage === 'analytics' && (
        <>
        <div className="flex items-center gap-4">
          <h2 className="text-2xl font-extrabold text-[#073B4C] whitespace-nowrap flex items-center gap-2 shrink-0">
            {resolveSectionIcon('movies.png') ? (<span className="w-10 h-10 overflow-hidden shrink-0 flex items-center justify-center"><img src={resolveSectionIcon('movies.png')} alt="" className="h-full w-auto max-w-none" style={{ transform: 'scale(1.7)' }} /></span>) : (<span>🎬</span>)}
            Movies
          </h2>
          <div className="h-px bg-gray-200 flex-1" />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          <div className="bg-white p-5 rounded-2xl shadow-md border-l-4 border-[#15616D] flex flex-col min-w-0">
            <div className="flex items-start justify-between gap-2"><p className="text-xs font-bold uppercase tracking-wider text-gray-500 min-w-0">Total Movies Analyzed</p><div className="bg-[#15616D]/10 p-2 rounded-lg text-[#15616D] shrink-0"><svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z"></path></svg></div></div>
            <h3 className="text-2xl font-extrabold text-[#15616D] mt-3 truncate">{data ? data.totalMovies.toLocaleString() : '—'}</h3>
            <p className="text-xs text-emerald-600 font-semibold mt-1">{data ? `${data.highlyRatedCount.toLocaleString()} rated 7.0+` : '—'}</p>
          </div>
          <div className="bg-white p-5 rounded-2xl shadow-md border-l-4 border-[#8AA79F] flex flex-col min-w-0">
            <div className="flex items-start justify-between gap-2"><p className="text-xs font-bold uppercase tracking-wider text-gray-500 min-w-0">Average Rating</p><div className="bg-[#8AA79F]/20 p-2 rounded-lg text-[#15616D] shrink-0"><svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 .587l3.668 7.431 8.212 1.192-5.94 5.787 1.402 8.168-7.342-3.861-7.342 3.861 1.402-8.168-5.94-5.787 8.212-1.192z"/></svg></div></div>
            <h3 className="text-2xl font-extrabold text-[#15616D] mt-3 truncate">{data ? data.avgRating.toFixed(2) : '—'} <span className="text-sm font-normal text-gray-500">/ 10</span></h3>
            <p className="text-xs text-gray-500 font-medium mt-1">Across all titles</p>
          </div>
          <div className="bg-white p-5 rounded-2xl shadow-md border-l-4 border-[#FF7D00] flex flex-col min-w-0">
            <div className="flex items-start justify-between gap-2"><p className="text-xs font-bold uppercase tracking-wider text-gray-500 min-w-0">Total Box Office Revenue</p><div className="bg-[#FF7D00]/10 p-2 rounded-lg text-[#FF7D00] shrink-0"><svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg></div></div>
            <h3 className="text-2xl font-extrabold text-[#15616D] mt-3 truncate">{data ? formatCurrency(data.totalRevenue) : '—'}</h3>
            <p className="text-xs text-emerald-600 font-semibold mt-1">Worldwide gross</p>
          </div>
          <div className="bg-white p-5 rounded-2xl shadow-md border-l-4 border-[#073B4C] flex flex-col min-w-0">
            <div className="flex items-start justify-between gap-2"><p className="text-xs font-bold uppercase tracking-wider text-gray-500 min-w-0">Average Runtime</p><div className="bg-[#073B4C]/10 p-2 rounded-lg text-[#073B4C] shrink-0"><svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg></div></div>
            <h3 className="text-2xl font-extrabold text-[#15616D] mt-3 truncate">{data ? data.avgRuntime.toFixed(1) : '—'} <span className="text-sm font-normal text-gray-500">mins</span></h3>
            <p className="text-xs text-gray-500 font-medium mt-1">Avg. feature length</p>
          </div>
          <div className="bg-white p-5 rounded-2xl shadow-md border-l-4 border-[#FF9F43] flex flex-col min-w-0">
            <div className="flex items-start justify-between gap-2"><p className="text-xs font-bold uppercase tracking-wider text-gray-500 min-w-0">Highest Grossing Genre</p><div className="bg-[#FF9F43]/10 p-2 rounded-lg text-[#FF9F43] shrink-0"><svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg></div></div>
            <h3 className="text-2xl font-extrabold text-[#15616D] mt-3 truncate">{data ? data.topGenreByRevenue[0] : '—'}</h3>
            <p className="text-xs text-emerald-600 font-semibold mt-1">{data ? `${formatCurrency(data.topGenreByRevenue[1])} revenue` : '—'}</p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 w-full">
          <div id="movie-genre-container" className="relative bg-white p-6 pb-12 rounded-2xl shadow-md w-full min-w-0 flex flex-col justify-between">
            <ChartDownloader containerId="movie-genre-container" filename="movie-genres.png" />
            <div className="flex items-center justify-between mb-4">
              <div className="min-w-0 pr-2">
                <h2 className="text-lg font-bold text-[#15616D] truncate">Top Movie Genres Distribution</h2>
                <p className="text-xs text-gray-500 truncate">Movie count distribution across primary cinematic genres</p>
              </div>
              <span className="bg-[#E7ECEF] text-[#15616D] text-xs font-semibold px-3 py-1 rounded-lg shrink-0">Top 8 Genres</span>
            </div>
            <div className="relative h-72 w-full flex items-center justify-center">
              <canvas ref={genreCanvasRef} id="genreChart"></canvas>
            </div>
            {data && data.uncategorizedPct > 0 && (<p className="text-[11px] text-gray-400 text-center mt-3">{data.uncategorizedPct}% of movies have no genre listed in the source data and aren't shown above.</p>)}
          </div>

          <div id="movie-country-container" className="relative bg-white p-6 pb-12 rounded-2xl shadow-md w-full min-w-0 flex flex-col justify-between">
            <ChartDownloader containerId="movie-country-container" filename="movie-countries.png" />
            <div className="flex items-center justify-between mb-4">
              <div className="min-w-0 pr-2">
                <h2 className="text-lg font-bold text-[#15616D] truncate">Top Production Countries & Ratings</h2>
                <p className="text-xs text-gray-500 truncate">Catalog size vs. average rating per country</p>
              </div>
              <span className="bg-[#E7ECEF] text-[#15616D] text-xs font-semibold px-3 py-1 rounded-lg shrink-0">By Country</span>
            </div>
            <div className="relative h-72 w-full flex items-center justify-center">
              <canvas ref={countryCanvasRef} id="countryChart"></canvas>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 w-full">
          <div className="bg-white p-6 rounded-2xl shadow-md w-full min-w-0">
            <div className="flex items-center justify-between mb-4">
              <div className="min-w-0 pr-2"><h2 className="text-lg font-bold text-[#15616D] truncate">Top 10 Movies — Best Performers</h2><p className="text-xs text-gray-500 truncate">Ranked by weighted rating (accounts for vote count)</p></div>
              <span className="bg-emerald-50 text-emerald-700 text-xs font-semibold px-3 py-1 rounded-lg shrink-0">Top 10</span>
            </div>
            <ul className="space-y-2.5">
              {(data?.topMovies ?? []).map((m, idx) => (
                <li key={`${m.title}-${m.year}-${idx}`} className="flex items-center gap-3">
                  <span className="w-6 h-6 rounded-full bg-[#15616D] text-white text-xs font-bold flex items-center justify-center shrink-0">{idx + 1}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-2"><p className="text-sm font-semibold text-[#073B4C] truncate">{m.title} <span className="text-xs font-normal text-gray-400">({m.year ?? '—'})</span></p><span className="text-xs font-bold text-[#15616D] shrink-0">{formatCurrency(m.revenue)}</span></div>
                    <div className="flex items-center gap-2 mt-1">
                      <div className="flex-1 bg-[#E7ECEF] rounded-full h-1.5 overflow-hidden"><div className="bg-gradient-to-r from-[#15616D] to-emerald-400 h-full rounded-full" style={{ width: `${(m.weighted_rating / 10) * 100}%` }}></div></div>
                      <span className="text-[11px] text-gray-500 shrink-0 flex items-center gap-0.5"><svg className="w-3 h-3 text-[#FF9F43]" fill="currentColor" viewBox="0 0 24 24"><path d="M12 .587l3.668 7.431 8.212 1.192-5.94 5.787 1.402 8.168-7.342-3.861-7.342 3.861 1.402-8.168-5.94-5.787 8.212-1.192z"/></svg>{m.weighted_rating.toFixed(1)}</span>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>
          <div className="bg-white p-6 rounded-2xl shadow-md w-full min-w-0">
            <div className="flex items-center justify-between mb-4">
              <div className="min-w-0 pr-2"><h2 className="text-lg font-bold text-[#15616D] truncate">Bottom 10 Movies — Worst Performers</h2><p className="text-xs text-gray-500 truncate">Ranked by weighted rating (accounts for vote count)</p></div>
              <span className="bg-red-50 text-red-600 text-xs font-semibold px-3 py-1 rounded-lg shrink-0">Bottom 10</span>
            </div>
            <ul className="space-y-2.5">
              {(data?.bottomMovies ?? []).map((m, idx) => (
                <li key={`${m.title}-${m.year}-${idx}`} className="flex items-center gap-3">
                  <span className="w-6 h-6 rounded-full bg-gray-400 text-white text-xs font-bold flex items-center justify-center shrink-0">{idx + 1}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-2"><p className="text-sm font-semibold text-[#073B4C] truncate">{m.title} <span className="text-xs font-normal text-gray-400">({m.year ?? '—'})</span></p><span className="text-xs font-bold text-gray-500 shrink-0">{formatCurrency(m.revenue)}</span></div>
                    <div className="flex items-center gap-2 mt-1">
                      <div className="flex-1 bg-[#E7ECEF] rounded-full h-1.5 overflow-hidden"><div className="bg-gradient-to-r from-red-400 to-[#FF7D00] h-full rounded-full" style={{ width: `${(m.weighted_rating / 10) * 100}%` }}></div></div>
                      <span className="text-[11px] text-gray-500 shrink-0 flex items-center gap-0.5"><svg className="w-3 h-3 text-[#FF9F43]" fill="currentColor" viewBox="0 0 24 24"><path d="M12 .587l3.668 7.431 8.212 1.192-5.94 5.787 1.402 8.168-7.342-3.861-7.342 3.861 1.402-8.168-5.94-5.787 8.212-1.192z"/></svg>{m.weighted_rating.toFixed(1)}</span>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-8 w-full">
          <div id="movie-company-container" className="relative bg-white p-6 pb-12 rounded-2xl shadow-md w-full min-w-0 flex flex-col justify-between">
            <ChartDownloader containerId="movie-company-container" filename="movie-companies.png" />
            <div className="flex items-center justify-between mb-2">
              <div className="min-w-0 pr-2">
                <h2 className="text-lg font-bold text-[#15616D] truncate">Top Production Companies by Total Revenue</h2>
                {data?.totalProductionCompanies > 0 && (<p className="text-xs text-gray-400 mt-0.5">Top 5 of {data.totalProductionCompanies.toLocaleString()} production companies in the dataset</p>)}
              </div>
              <span className="bg-[#E7ECEF] text-[#15616D] text-xs font-semibold px-3 py-1 rounded-lg shrink-0">Revenue Leaders</span>
            </div>
            <div className="relative h-60 w-full flex items-center justify-center">
              <canvas ref={companyCanvasRef} id="companyChart"></canvas>
            </div>
            <div className="relative mt-4 pt-4 border-t border-gray-100 w-full" style={{ height: '100px' }}>
              {(data?.companyStats ?? []).map((c, idx) => {
                const bio = COMPANY_BIOS[c.production_company];
                return (
                  <div key={c.production_company} className="absolute flex flex-col items-center justify-start cursor-pointer text-center group" style={{ left: `${companyBarPositions[idx]}%`, top: '16px', transform: 'translateX(-50%)', width: '84px' }} onMouseEnter={() => setActiveCompanyTooltip(idx)} onMouseLeave={() => setActiveCompanyTooltip(null)}>
                    {activeCompanyTooltip === idx && (
                      <div className="absolute bottom-16 z-30 bg-[#073B4C] text-white text-xs rounded-xl p-3 shadow-2xl w-56 border border-white/10 pointer-events-none">
                        <p className="font-bold text-[#FF7D00] text-sm">{c.production_company}</p>
                        <div className="mt-1 space-y-0.5 text-gray-200 text-left">
                          <p><span className="text-[#8AA79F]">Founded:</span> {bio?.founded ?? '—'}</p>
                          <p><span className="text-[#8AA79F]">Country:</span> {bio?.country ?? 'Unknown'}</p>
                          <p><span className="text-[#8AA79F]">Net worth:</span> {bio?.netWorth ?? '—'}</p>
                          <p><span className="text-[#8AA79F]">Leadership:</span> {bio?.ceo ?? '—'}</p>
                        </div>
                        <div className="absolute -bottom-1.5 left-1/2 transform -translate-x-1/2 w-3 h-3 bg-[#073B4C] rotate-45 border-r border-b border-white/10"></div>
                      </div>
                    )}
                    <div className="w-14 h-14 rounded-full p-0.5 bg-gradient-to-tr from-[#FF7D00] to-[#15616D] shadow-md group-hover:scale-110 transition duration-300 flex items-center justify-center overflow-hidden shrink-0 mx-auto">
                      <div className="w-full h-full rounded-full bg-white flex items-center justify-center p-1.5">
                        <img src={resolveLogo(bio) ?? FALLBACK_LOGO} alt={c.production_company} className="w-full h-full object-contain" onError={(e) => { e.currentTarget.onerror = null; e.currentTarget.src = FALLBACK_LOGO; }} />
                      </div>
                    </div>
                    <span className="text-[10px] font-bold text-[#073B4C] mt-1.5 block w-full truncate px-0.5">{c.production_company}</span>
                    <span className="text-[9px] text-gray-400 block w-full truncate px-0.5">{c.percentage_of_total}%</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        <TvDashboard />
        </>
      )}
      </main>

      <footer className="bg-[#073B4C] text-white mt-16 py-8 border-t border-white/10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row justify-between items-center text-xs text-[#8AA79F]">
          <p>&copy; 2026 CineMetrics Analytics Dashboard. All rights reserved.</p>
          <div className="flex space-x-6 mt-4 sm:mt-0">
            <a href="/privacy.html" target="_blank" rel="noopener" className="hover:text-white cursor-pointer">Privacy Policy</a>
            <a href="/terms.html" target="_blank" rel="noopener" className="hover:text-white cursor-pointer">Terms of Service</a>
            <a href="/api-docs.html" target="_blank" rel="noopener" className="hover:text-white cursor-pointer">API Documentation</a>
          </div>
        </div>
      </footer>
    </div>
  );
}