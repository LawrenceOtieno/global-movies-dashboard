import React, { useEffect, useState } from 'react';
import * as ChartJS from 'chart.js';
const { Chart, registerables } = ChartJS;
Chart.register(...registerables);

import ChartDownloader from './ChartDownloader';

const API_BASE_URL = import.meta.env.VITE_API_BASE || 'http://localhost:5000';
const FONT_STACK = "'Segoe UI', Inter, Arial, sans-serif";

const SECTION_ICONS = import.meta.glob('../assets/section-icons/*', { eager: true, import: 'default' });
function resolveSectionIcon(filename) {
  const entry = Object.entries(SECTION_ICONS).find(([path]) => path.endsWith(`/${filename}`));
  return entry ? entry[1] : null;
}

const TV_COMPANY_BIOS = {
  'BBC': { founded: '1922 (reconstituted as a public corporation under Royal Charter, 1927)', country: 'United Kingdom (London)', netWorth: '~£10B–£15B (~$13B–$20B) — publicly funded via the UK TV license fee, no stock market cap', ceo: 'Matt Brittin — Director-General (from May 18, 2026); Dr. Samir Shah, BBC Board Chairman', logoFile: 'bbc.png', logoDomain: 'bbc.com' },
  'Televisa': { founded: '1973 (merger of Telesistema Mexicano and Televisión Independiente de México)', country: 'Mexico (Mexico City)', netWorth: '~$1.25B market cap (Grupo Televisa); ~$5.83B book value', ceo: 'Alfonso de Angoitia Noriega & Bernardo Gómez Martínez — Co-CEOs, Grupo Televisa; Daniel Alegre — CEO, TelevisaUnivision', logoFile: 'televisa.png', logoDomain: 'televisaunivision.com' },
  'Warner Bros. Television': { founded: '1955 (Warner Bros. Television Division, launched March 21)', country: 'United States (Burbank, California)', netWorth: '~$72B–$82B enterprise valuation (Warner Bros. Studios & Streaming)', ceo: 'Channing Dungey — Chairman & CEO, Warner Bros. Television Group; reports to David Zaslav (President & CEO, WBD)', logoFile: 'warnerbrostv.png', logoDomain: 'warnerbros.com' },
  'Universal Television': { founded: '1943/2004 (originally Revue Studios; renamed Universal Television 1963; modern incarnation formed 2004 post NBC–Vivendi Universal merger)', country: 'United States (Universal City, California)', netWorth: '~$65B–$75B enterprise valuation (Universal Studio Group)', ceo: 'Erin Underhill — President, Universal Television; Pearlena Igbokwe — Chairman, Television Studios, NBC Entertainment & Peacock Scripted', logoFile: 'universaltv.png', logoDomain: 'nbcuniversal.com' },
  'Sony Pictures Television Studios': { founded: '2002/2017 (renamed from Columbia TriStar Television 2002; dedicated Studios arm founded July 25, 2017)', country: 'United States (Culver City, California; Sony Group HQ: Tokyo, Japan)', netWorth: '~$30B–$40B enterprise valuation (Sony Pictures Entertainment)', ceo: 'Katherine Pope — President, Sony Pictures Television Studios; reports to Ravi Ahuja (President & CEO, Sony Pictures Entertainment)', logoFile: 'sonytv.png', logoDomain: 'sonypictures.com' }
};

const FALLBACK_LOGO = 'data:image/svg+xml;utf8,' + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="#15616D"/><rect x="30" y="35" width="40" height="45" fill="#FF9F43"/><rect x="38" y="45" width="8" height="8" fill="#15616D"/><rect x="54" y="45" width="8" height="8" fill="#15616D"/><rect x="38" y="60" width="8" height="8" fill="#15616D"/><rect x="54" y="60" width="8" height="8" fill="#15616D"/></svg>'
);

const LOCAL_TV_LOGOS = import.meta.glob('../assets/tv-company-logos/*', { eager: true, import: 'default' });

function resolveTvLogo(bio) {
  if (!bio) return null;
  const localEntry = Object.entries(LOCAL_TV_LOGOS).find(([path]) => path.endsWith(`/${bio.logoFile}`));
  if (localEntry) return localEntry[1];
  return `https://logo.clearbit.com/${bio.logoDomain}?size=256`;
}

let cachedTvData = null;

export default function TvDashboard() {
  const [data, setData] = useState(cachedTvData);
  const [loadError, setLoadError] = useState(null);
  const [companyBarPositions, setCompanyBarPositions] = useState([10, 30, 50, 70, 90]);
  const [activeCompanyTooltip, setActiveCompanyTooltip] = useState(null);

  useEffect(() => {
    if (cachedTvData) return;
    Promise.all([
      fetch(`${API_BASE_URL}/api/tv/summary-stats`).then((r) => { if (!r.ok) throw new Error(`tv summary-stats failed (HTTP ${r.status})`); return r.json(); }),
      fetch(`${API_BASE_URL}/api/tv/genre-distribution`).then((r) => { if (!r.ok) throw new Error(`tv genre-distribution failed (HTTP ${r.status})`); return r.json(); }),
      fetch(`${API_BASE_URL}/api/tv/network-performance`).then((r) => { if (!r.ok) throw new Error(`tv network-performance failed (HTTP ${r.status})`); return r.json(); }),
      fetch(`${API_BASE_URL}/api/tv/production-companies-performance`).then((r) => { if (!r.ok) throw new Error(`tv production-companies-performance failed (HTTP ${r.status})`); return r.json(); }),
      fetch(`${API_BASE_URL}/api/tv/show-rankings`).then((r) => { if (!r.ok) throw new Error(`tv show-rankings failed (HTTP ${r.status})`); return r.json(); }),
    ])
      .then(([summary, genreDist, networkPerf, companyPerf, rankings]) => {
        const processed = {
          totalShows: summary.total_shows,
          avgRating: summary.average_rating,
          avgEpisodeRuntime: summary.average_episode_runtime_minutes,
          highlyRatedCount: summary.highly_rated_count,
          totalProductionCompanies: summary.total_production_companies,
          topGenreByCount: summary.top_genre_by_show_count ?? ['—', 0],
          genreStats: genreDist.genres.map((g) => [g.genre, g.count, g.percentage]),
          uncategorizedPct: genreDist.uncategorized_percentage,
          networkStats: networkPerf,
          companyStats: companyPerf,
          topShows: rankings.top,
          bottomShows: rankings.bottom,
        };
        cachedTvData = processed;
        setData(processed);
      })
      .catch((err) => setLoadError(`${err.message} — is the Flask backend running? (cd backend && python app.py)`));
  }, []);

  useEffect(() => {
    if (!data) return;

    const genrePct = Object.fromEntries(data.genreStats.map(([g, , pct]) => [g, pct]));
    const ctxGenre = document.getElementById('tvGenreChart').getContext('2d');
    const genreChartInstance = new Chart(ctxGenre, {
      type: 'doughnut',
      data: { labels: data.genreStats.map(([genre]) => genre), datasets: [{ data: data.genreStats.map(([, count]) => count), backgroundColor: ['#15616D', '#8AA79F', '#FF7D00', '#073B4C', '#208190', '#FF9F43', '#A3C1AD', '#5C8374'], borderWidth: 2, borderColor: '#ffffff' }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { font: { family: FONT_STACK, size: 11, weight: '600' }, boxWidth: 12, padding: 12, generateLabels: (chart) => chart.data.labels.map((label, i) => ({ text: `${label} (${genrePct[label]}%)`, fillStyle: chart.data.datasets[0].backgroundColor[i], strokeStyle: chart.data.datasets[0].backgroundColor[i], index: i })) } },
          tooltip: { callbacks: { label: (ctx) => `${ctx.label}: ${ctx.raw.toLocaleString()} shows (${genrePct[ctx.label]}%)` } }
        },
        cutout: '65%'
      }
    });

    const ctxNetwork = document.getElementById('tvNetworkChart').getContext('2d');
    const networkChartInstance = new Chart(ctxNetwork, {
      type: 'bar',
      data: { labels: data.networkStats.map((n) => n.network), datasets: [{ label: 'Average Rating', data: data.networkStats.map((n) => n.avg_rating), backgroundColor: '#FF7D00', borderRadius: 8, barThickness: 18 }] },
      options: {
        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => `${ctx.raw} avg rating (${data.networkStats[ctx.dataIndex].show_count} shows)` } } },
        scales: {
          x: { min: 0, max: 10, grid: { color: '#E7ECEF' }, ticks: { font: { family: FONT_STACK } }, title: { display: true, text: 'Average Rating (0–10)', font: { family: FONT_STACK, size: 10, weight: '600' }, color: '#8AA79F' } },
          y: { grid: { display: false }, ticks: { font: { family: FONT_STACK, weight: '600' } }, title: { display: true, text: 'Network', font: { family: FONT_STACK, size: 10, weight: '600' }, color: '#8AA79F' } }
        }
      }
    });

    const ctxCompany = document.getElementById('tvCompanyChart').getContext('2d');
    const companyChartInstance = new Chart(ctxCompany, {
      type: 'bar',
      data: { labels: data.companyStats.map((c) => c.production_company), datasets: [{ label: 'Average Rating', data: data.companyStats.map((c) => c.avg_rating), backgroundColor: '#15616D', borderRadius: 8, barThickness: 36 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => `${ctx.raw} avg rating (${data.companyStats[ctx.dataIndex].show_count} shows)` } } },
        scales: {
          x: { grid: { display: false }, ticks: { display: false } },
          y: { min: 0, max: 10, grid: { color: '#E7ECEF' }, ticks: { font: { family: FONT_STACK } }, title: { display: true, text: 'Average Rating (0–10)', font: { family: FONT_STACK, size: 10, weight: '600' }, color: '#8AA79F' } }
        }
      },
      plugins: [{
        id: 'syncTvCompanyLogoPositions',
        afterLayout: (chart) => { const meta = chart.getDatasetMeta(0); const width = chart.width || 1; const positions = meta.data.map((bar) => (bar.x / width) * 100); setCompanyBarPositions(positions); }
      }]
    });

    return () => { genreChartInstance.destroy(); networkChartInstance.destroy(); companyChartInstance.destroy(); };
  }, [data]);

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-4 pt-4">
        <h2 className="text-2xl font-extrabold text-[#073B4C] whitespace-nowrap flex items-center gap-2 shrink-0">
          {resolveSectionIcon('tv.png') ? (<span className="w-10 h-10 overflow-hidden shrink-0 flex items-center justify-center"><img src={resolveSectionIcon('tv.png')} alt="" className="h-full w-auto max-w-none" style={{ transform: 'scale(1.7)' }} /></span>) : (<span>📺</span>)}
          TV Shows
        </h2>
        <div className="h-px bg-gray-200 flex-1" />
      </div>

      {loadError && (<div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl p-4">Couldn't reach the TV endpoints at <code className="font-mono">{API_BASE_URL}/api/tv</code> — {loadError}</div>)}
      {!data && !loadError && (<div className="bg-white border border-gray-200 text-gray-500 text-sm rounded-xl p-4">Loading TV dataset…</div>)}

      {data && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="bg-white p-6 rounded-2xl shadow-md border-l-4 border-[#15616D] flex items-center justify-between">
              <div className="min-w-0 pr-2"><p className="text-xs font-bold uppercase tracking-wider text-gray-500">Total Shows Analyzed</p><h3 className="text-3xl font-extrabold text-[#15616D] mt-1">{data.totalShows.toLocaleString()}</h3><p className="text-xs text-emerald-600 font-semibold mt-1">{data.highlyRatedCount.toLocaleString()} rated 7.0+</p></div>
              <div className="bg-[#15616D]/10 p-4 rounded-xl text-[#15616D] shrink-0"><svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z"></path></svg></div>
            </div>
            <div className="bg-white p-6 rounded-2xl shadow-md border-l-4 border-[#8AA79F] flex items-center justify-between">
              <div className="min-w-0 pr-2"><p className="text-xs font-bold uppercase tracking-wider text-gray-500">Average Rating</p><h3 className="text-3xl font-extrabold text-[#15616D] mt-1">{data.avgRating.toFixed(2)} <span className="text-sm font-normal text-gray-500">/ 10</span></h3><p className="text-xs text-gray-500 font-medium mt-1">Across {data.totalShows.toLocaleString()} shows</p></div>
              <div className="bg-[#8AA79F]/20 p-4 rounded-xl text-[#15616D] shrink-0"><svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24"><path d="M12 .587l3.668 7.431 8.212 1.192-5.94 5.787 1.402 8.168-7.342-3.861-7.342 3.861 1.402-8.168-5.94-5.787 8.212-1.192z"/></svg></div>
            </div>
            <div className="bg-white p-6 rounded-2xl shadow-md border-l-4 border-[#FF7D00] flex items-center justify-between">
              <div className="min-w-0 pr-2"><p className="text-xs font-bold uppercase tracking-wider text-gray-500">Average Episode Runtime</p><h3 className="text-3xl font-extrabold text-[#15616D] mt-1">{data.avgEpisodeRuntime.toFixed(0)} <span className="text-sm font-normal text-gray-500">mins</span></h3><p className="text-xs text-gray-500 font-medium mt-1">Per episode</p></div>
              <div className="bg-[#FF7D00]/10 p-4 rounded-xl text-[#FF7D00] shrink-0"><svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg></div>
            </div>
            <div className="bg-white p-6 rounded-2xl shadow-md border-l-4 border-[#073B4C] flex items-center justify-between">
              <div className="min-w-0 pr-2"><p className="text-xs font-bold uppercase tracking-wider text-gray-500">Top Genre by Show Count</p><h3 className="text-2xl font-extrabold text-[#15616D] mt-1 truncate">{data.topGenreByCount[0]}</h3><p className="text-xs text-gray-500 font-medium mt-1">{data.topGenreByCount[1].toLocaleString()} shows</p></div>
              <div className="bg-[#073B4C]/10 p-4 rounded-xl text-[#073B4C] shrink-0"><svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M7 4v16M17 4v16M3 8h4m10 0h4M3 16h4m10 0h4M3 4h18v16H3V4z"></path></svg></div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 w-full">
            <div id="tv-genre-container" className="relative bg-white p-6 pb-12 rounded-2xl shadow-md w-full min-w-0 flex flex-col justify-between">
              <ChartDownloader containerId="tv-genre-container" filename="tv-genres.png" />
              <div className="flex items-center justify-between mb-4">
                <div className="min-w-0 pr-2"><h3 className="text-lg font-bold text-[#15616D] truncate">Top Show Genres Distribution</h3><p className="text-xs text-gray-500 truncate">Show count distribution across TV genre categories</p></div>
                <span className="bg-[#E7ECEF] text-[#15616D] text-xs font-semibold px-3 py-1 rounded-lg shrink-0">Top 8 Genres</span>
              </div>
              <div className="relative h-72 w-full flex items-center justify-center"><canvas id="tvGenreChart"></canvas></div>
              {data.uncategorizedPct > 0 && (<p className="text-[11px] text-gray-400 text-center mt-3">{data.uncategorizedPct}% of shows have no genre listed in the source data and aren't shown above.</p>)}
            </div>
            <div id="tv-network-container" className="relative bg-white p-6 pb-12 rounded-2xl shadow-md w-full min-w-0 flex flex-col justify-between">
              <ChartDownloader containerId="tv-network-container" filename="tv-networks.png" />
              <div className="flex items-center justify-between mb-4">
                <div className="min-w-0 pr-2"><h3 className="text-lg font-bold text-[#15616D] truncate">Top Networks & Ratings</h3><p className="text-xs text-gray-500 truncate">Catalog size vs. average rating per network</p></div>
                <span className="bg-[#E7ECEF] text-[#15616D] text-xs font-semibold px-3 py-1 rounded-lg shrink-0">By Network</span>
              </div>
              <div className="relative h-72 w-full flex items-center justify-center"><canvas id="tvNetworkChart"></canvas></div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 w-full">
            <div className="bg-white p-6 rounded-2xl shadow-md w-full min-w-0">
              <div className="flex items-center justify-between mb-4">
                <div className="min-w-0 pr-2"><h3 className="text-lg font-bold text-[#15616D] truncate">Top 10 Shows — Best Performers</h3><p className="text-xs text-gray-500 truncate">Ranked by weighted rating (accounts for vote count)</p></div>
                <span className="bg-emerald-50 text-emerald-700 text-xs font-semibold px-3 py-1 rounded-lg shrink-0">Top 10</span>
              </div>
              <ul className="space-y-2.5">
                {(data.topShows ?? []).map((s, idx) => (
                  <li key={`${s.name}-${s.year}-${idx}`} className="flex items-center gap-3">
                    <span className="w-6 h-6 rounded-full bg-[#15616D] text-white text-xs font-bold flex items-center justify-center shrink-0">{idx + 1}</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-2"><p className="text-sm font-semibold text-[#073B4C] truncate">{s.name} <span className="text-xs font-normal text-gray-400">({s.year ?? '—'})</span></p><span className="text-xs font-bold text-[#15616D] shrink-0">{s.seasons != null ? `${s.seasons} season${s.seasons === 1 ? '' : 's'}` : '—'}</span></div>
                      <div className="flex items-center gap-2 mt-1">
                        <div className="flex-1 bg-[#E7ECEF] rounded-full h-1.5 overflow-hidden"><div className="bg-gradient-to-r from-[#15616D] to-emerald-400 h-full rounded-full" style={{ width: `${(s.weighted_rating / 10) * 100}%` }}></div></div>
                        <span className="text-[11px] text-gray-500 shrink-0 flex items-center gap-0.5" title={`Raw rating: ${s.rating?.toFixed(2)} (${s.weighted_rating.toFixed(2)} weighted)`}><svg className="w-3 h-3 text-[#FF9F43]" fill="currentColor" viewBox="0 0 24 24"><path d="M12 .587l3.668 7.431 8.212 1.192-5.94 5.787 1.402 8.168-7.342-3.861-7.342 3.861 1.402-8.168-5.94-5.787 8.212-1.192z"/></svg>{s.weighted_rating.toFixed(2)}</span>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
            <div className="bg-white p-6 rounded-2xl shadow-md w-full min-w-0">
              <div className="flex items-center justify-between mb-4">
                <div className="min-w-0 pr-2"><h3 className="text-lg font-bold text-[#15616D] truncate">Bottom 10 Shows — Worst Performers</h3><p className="text-xs text-gray-500 truncate">Ranked by weighted rating (accounts for vote count)</p></div>
                <span className="bg-red-50 text-red-600 text-xs font-semibold px-3 py-1 rounded-lg shrink-0">Bottom 10</span>
              </div>
              <ul className="space-y-2.5">
                {(data.bottomShows ?? []).map((s, idx) => (
                  <li key={`${s.name}-${s.year}-${idx}`} className="flex items-center gap-3">
                    <span className="w-6 h-6 rounded-full bg-gray-400 text-white text-xs font-bold flex items-center justify-center shrink-0">{idx + 1}</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-2"><p className="text-sm font-semibold text-[#073B4C] truncate">{s.name} <span className="text-xs font-normal text-gray-400">({s.year ?? '—'})</span></p><span className="text-xs font-bold text-gray-500 shrink-0">{s.seasons != null ? `${s.seasons} season${s.seasons === 1 ? '' : 's'}` : '—'}</span></div>
                      <div className="flex items-center gap-2 mt-1">
                        <div className="flex-1 bg-[#E7ECEF] rounded-full h-1.5 overflow-hidden"><div className="bg-gradient-to-r from-red-400 to-[#FF7D00] h-full rounded-full" style={{ width: `${(s.weighted_rating / 10) * 100}%` }}></div></div>
                        <span className="text-[11px] text-gray-500 shrink-0 flex items-center gap-0.5" title={`Raw rating: ${s.rating?.toFixed(2)} (${s.weighted_rating.toFixed(2)} weighted)`}><svg className="w-3 h-3 text-[#FF9F43]" fill="currentColor" viewBox="0 0 24 24"><path d="M12 .587l3.668 7.431 8.212 1.192-5.94 5.787 1.402 8.168-7.342-3.861-7.342 3.861 1.402-8.168-5.94-5.787 8.212-1.192z"/></svg>{s.weighted_rating.toFixed(2)}</span>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div id="tv-company-container" className="relative bg-white p-6 pb-12 rounded-2xl shadow-md w-full min-w-0">
            <ChartDownloader containerId="tv-company-container" filename="tv-companies.png" />
            <div className="flex items-center justify-between mb-2">
              <div className="min-w-0 pr-2">
                <h3 className="text-lg font-bold text-[#15616D] truncate">Top Production Companies & Ratings</h3>
                {data.totalProductionCompanies > 0 && (<p className="text-xs text-gray-400 mt-0.5">Top 5 of {data.totalProductionCompanies.toLocaleString()} production companies in the dataset</p>)}
              </div>
              <span className="bg-[#E7ECEF] text-[#15616D] text-xs font-semibold px-3 py-1 rounded-lg shrink-0">By Company</span>
            </div>
            <div className="relative h-60 w-full flex items-center justify-center">
              <canvas id="tvCompanyChart"></canvas>
            </div>
            <div className="relative mt-4 pt-4 border-t border-gray-100 w-full" style={{ height: '100px' }}>
              {(data.companyStats ?? []).map((c, idx) => {
                const bio = TV_COMPANY_BIOS[c.production_company];
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
                    <div className="w-11 h-11 rounded-full p-0.5 bg-gradient-to-tr from-[#FF7D00] to-[#15616D] shadow-md group-hover:scale-110 transition duration-300 flex items-center justify-center overflow-hidden shrink-0 mx-auto">
                      <div className="w-full h-full rounded-full bg-white flex items-center justify-center p-1.5">
                        <img src={resolveTvLogo(bio) ?? FALLBACK_LOGO} alt={c.production_company} className="w-full h-full object-contain" onError={(e) => { e.currentTarget.onerror = null; e.currentTarget.src = FALLBACK_LOGO; }} />
                      </div>
                    </div>
                    <span className="text-[10px] font-bold text-[#073B4C] mt-1.5 block w-full truncate px-0.5">{c.production_company}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}