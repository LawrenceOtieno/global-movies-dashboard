import React, { useEffect } from 'react';
import { Chart, registerables } from 'chart.js';
Chart.register(...registerables);

export default function Dashboard() {
  useEffect(() => {
    // 1. Genre Distribution Chart (Doughnut)
    const ctxGenre = document.getElementById('genreChart').getContext('2d');
    const genreChartInstance = new Chart(ctxGenre, {
      type: 'doughnut',
      data: {
        labels: ['Action', 'Drama', 'Comedy', 'Sci-Fi', 'Thriller', 'Romance', 'Animation'],
        datasets: [{
          data: [28450, 24100, 18900, 12300, 10500, 6800, 3800],
          backgroundColor: [
            '#15616D',
            '#8AA79F',
            '#FF7D00',
            '#073B4C',
            '#208190',
            '#FF9F43',
            '#A3C1AD'
          ],
          borderWidth: 2,
          borderColor: '#ffffff'
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              font: { family: 'Inter', size: 11, weight: '600' },
              boxWidth: 12,
              padding: 15
            }
          }
        },
        cutout: '65%'
      }
    });

    // 2. Streaming Platforms Comparison (Horizontal Bar Chart)
    const ctxPlatform = document.getElementById('platformChart').getContext('2d');
    const platformChartInstance = new Chart(ctxPlatform, {
      type: 'bar',
      data: {
        labels: ['Apple TV+', 'Netflix', 'Disney+', 'Prime Video', 'MGM+'],
        datasets: [{
          label: 'Average IMDb Rating',
          data: [7.1, 6.8, 6.9, 6.5, 6.6],
          backgroundColor: '#FF7D00',
          borderRadius: 8,
          barThickness: 20
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false }
        },
        scales: {
          x: {
            min: 5.0,
            max: 8.0,
            grid: { color: '#E7ECEF' }
          },
          y: {
            grid: { display: false },
            ticks: { font: { family: 'Inter', weight: '600' } }
          }
        }
      }
    });

    // 3. Top Directors by Total Revenue (Bar Chart)
    const ctxDirector = document.getElementById('directorChart').getContext('2d');
    const directorChartInstance = new Chart(ctxDirector, {
      type: 'bar',
      data: {
        labels: ['James Cameron', 'Christopher Nolan', 'Patty Jenkins', 'Bong Joon-ho', 'Martin Scorsese'],
        datasets: [{
          label: 'Box Office Revenue ($B)',
          data: [24.8, 18.5, 14.2, 9.6, 8.9],
          backgroundColor: '#15616D',
          borderRadius: 8,
          barThickness: 32
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { font: { family: 'Inter', weight: '600', size: 11 } }
          },
          y: {
            grid: { color: '#E7ECEF' },
            ticks: {
              callback: function(value) { return '$' + value + 'B'; },
              font: { family: 'Inter' }
            }
          }
        }
      }
    });

    // Cleanup chart instances on unmount
    return () => {
      genreChartInstance.destroy();
      platformChartInstance.destroy();
      directorChartInstance.destroy();
    };
  }, []);

  // Live ML Prediction Function
  const runPrediction = () => {
    const genre = document.getElementById('pred-genre').value;
    const budget = parseFloat(document.getElementById('pred-budget').value) || 100;
    const runtime = parseFloat(document.getElementById('pred-runtime').value) || 120;
    const platform = document.getElementById('pred-platform').value;
    const director = document.getElementById('pred-director').value;

    let multiplier = 2.2;
    if (genre === 'Action' || genre === 'Sci-Fi') multiplier = 3.4;
    if (genre === 'Animation') multiplier = 2.8;
    if (director === 'A-List') multiplier *= 1.35;
    if (director === 'Rising') multiplier *= 0.85;

    const predictedRevenue = budget * multiplier;
    
    let baseRating = 6.5;
    if (platform === 'Apple TV+') baseRating = 7.1;
    else if (platform === 'Disney+') baseRating = 6.9;
    else if (platform === 'Netflix') baseRating = 6.8;
    else if (platform === 'MGM+') baseRating = 6.6;

    if (director === 'A-List') baseRating += 0.5;
    if (runtime > 110 && runtime < 150) baseRating += 0.3;
    const predictedRating = Math.min(Math.max(baseRating, 5.0), 9.2).toFixed(1);

    let tierText = 'Moderate Hit';
    let tierClass = 'bg-amber-500';
    let roiPercent = Math.min((predictedRevenue / budget) * 25, 100);

    if (predictedRevenue > 500) {
      tierText = 'Global Blockbuster';
      tierClass = 'bg-emerald-500';
    } else if (predictedRevenue > 250) {
      tierText = 'Box Office Hit';
      tierClass = 'bg-[#15616D]';
    } else if (predictedRevenue < 100) {
      tierText = 'Niche / Indie Release';
      tierClass = 'bg-gray-500';
    }

    document.getElementById('prediction-initial').classList.add('hidden');
    document.getElementById('prediction-output').classList.remove('hidden');

    document.getElementById('res-revenue').innerText = `$${predictedRevenue.toFixed(1)} M`;
    document.getElementById('res-rating').innerText = `${predictedRating} / 10`;
    
    const tierEl = document.getElementById('res-tier');
    tierEl.innerText = tierText;
    tierEl.className = `inline-block mt-1 px-3 py-1 rounded-full text-xs font-bold text-white ${tierClass}`;

    document.getElementById('res-confidence').innerText = `${(88 + Math.random() * 8).toFixed(1)}%`;
    document.getElementById('res-roi-text').innerText = `${(predictedRevenue / budget).toFixed(1)}x ROI`;
    document.getElementById('res-roi-bar').style.width = `${roiPercent}%`;
  };

  return (
    <div className="bg-[#E7ECEF] min-h-screen text-[#073B4C] antialiased font-sans">
      
      {/* Header */}
      <header className="bg-[#15616D] text-white shadow-lg sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex flex-col sm:flex-row justify-between items-center">
          <div className="flex items-center space-x-3">
            <div className="bg-[#FF7D00] text-white p-2.5 rounded-xl shadow-md flex items-center justify-center shrink-0">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4"></path></svg>
            </div>
            <div>
              <h1 className="text-2xl font-extrabold tracking-tight">CineMetrics Pro</h1>
              <p className="text-xs text-[#8AA79F] font-medium">Global Movie Intelligence & ML Box Office Predictor</p>
            </div>
          </div>
          <div className="mt-3 sm:mt-0 flex items-center space-x-4">
            <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-[#8AA79F]/30 text-white border border-[#8AA79F]/50">
              <span className="w-2 h-2 mr-2 bg-emerald-400 rounded-full animate-pulse shrink-0"></span>
              Dataset: 104,850 Movies (1950–2026)
            </span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        
        {/* KPI Metrics Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          <div className="bg-white p-6 rounded-2xl shadow-md border-l-4 border-[#15616D] flex items-center justify-between">
            <div className="min-w-0 pr-2">
              <p className="text-xs font-bold uppercase tracking-wider text-gray-500">Total Movies Analyzed</p>
              <h3 className="text-3xl font-extrabold text-[#15616D] mt-1">104,850</h3>
              <p className="text-xs text-emerald-600 font-semibold mt-1 flex items-center gap-1">
                <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"></path></svg>
                +12.4% vs last decade
              </p>
            </div>
            <div className="bg-[#15616D]/10 p-4 rounded-xl text-[#15616D] shrink-0">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z"></path></svg>
            </div>
          </div>

          <div className="bg-white p-6 rounded-2xl shadow-md border-l-4 border-[#8AA79F] flex items-center justify-between">
            <div className="min-w-0 pr-2">
              <p className="text-xs font-bold uppercase tracking-wider text-gray-500">Average IMDb Rating</p>
              <h3 className="text-3xl font-extrabold text-[#15616D] mt-1">6.85 <span className="text-sm font-normal text-gray-500">/ 10</span></h3>
              <p className="text-xs text-gray-500 font-medium mt-1">Across 100k+ global titles</p>
            </div>
            <div className="bg-[#8AA79F]/20 p-4 rounded-xl text-[#15616D] shrink-0">
              <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24"><path d="M12 .587l3.668 7.431 8.212 1.192-5.94 5.787 1.402 8.168-7.342-3.861-7.342 3.861 1.402-8.168-5.94-5.787 8.212-1.192z"/></svg>
            </div>
          </div>

          <div className="bg-white p-6 rounded-2xl shadow-md border-l-4 border-[#FF7D00] flex items-center justify-between">
            <div className="min-w-0 pr-2">
              <p className="text-xs font-bold uppercase tracking-wider text-gray-500">Total Box Office Revenue</p>
              <h3 className="text-3xl font-extrabold text-[#15616D] mt-1">$482.5B</h3>
              <p className="text-xs text-emerald-600 font-semibold mt-1">Global theatrical gross</p>
            </div>
            <div className="bg-[#FF7D00]/10 p-4 rounded-xl text-[#FF7D00] shrink-0">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
            </div>
          </div>

          <div className="bg-white p-6 rounded-2xl shadow-md border-l-4 border-[#073B4C] flex items-center justify-between">
            <div className="min-w-0 pr-2">
              <p className="text-xs font-bold uppercase tracking-wider text-gray-500">Average Runtime</p>
              <h3 className="text-3xl font-extrabold text-[#15616D] mt-1">112.4 <span className="text-sm font-normal text-gray-500">mins</span></h3>
              <p className="text-xs text-gray-500 font-medium mt-1">Standard feature length</p>
            </div>
            <div className="bg-[#073B4C]/10 p-4 rounded-xl text-[#073B4C] shrink-0">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
            </div>
          </div>
        </div>

        {/* Charts Row 1 (Side-by-Side Grid) */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 w-full">
          <div className="bg-white p-6 rounded-2xl shadow-md w-full min-w-0 flex flex-col justify-between">
            <div className="flex items-center justify-between mb-4">
              <div className="min-w-0 pr-2">
                <h2 className="text-lg font-bold text-[#15616D] truncate">Top Movie Genres Distribution</h2>
                <p className="text-xs text-gray-500 truncate">Movie count distribution across primary cinematic genres</p>
              </div>
              <span className="bg-[#E7ECEF] text-[#15616D] text-xs font-semibold px-3 py-1 rounded-lg shrink-0">Top 7 Genres</span>
            </div>
            <div className="relative h-72 w-full flex items-center justify-center">
              <canvas id="genreChart"></canvas>
            </div>
          </div>

          <div className="bg-white p-6 rounded-2xl shadow-md w-full min-w-0 flex flex-col justify-between">
            <div className="flex items-center justify-between mb-4">
              <div className="min-w-0 pr-2">
                <h2 className="text-lg font-bold text-[#15616D] truncate">Top Streaming Platforms & Ratings</h2>
                <p className="text-xs text-gray-500 truncate">Catalog size vs. average IMDb rating per platform</p>
              </div>
              <span className="bg-[#E7ECEF] text-[#15616D] text-xs font-semibold px-3 py-1 rounded-lg shrink-0">Catalog & Ratings</span>
            </div>
            <div className="relative h-72 w-full flex items-center justify-center">
              <canvas id="platformChart"></canvas>
            </div>
          </div>
        </div>

        {/* Charts Row 2 & Insights (Side-by-Side Grid) */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 w-full">
          <div className="bg-white p-6 rounded-2xl shadow-md lg:col-span-2 w-full min-w-0 flex flex-col justify-between">
            <div className="flex items-center justify-between mb-4">
              <div className="min-w-0 pr-2">
                <h2 className="text-lg font-bold text-[#15616D] truncate">Top Directors by Total Box Office Revenue</h2>
                <p className="text-xs text-gray-500 truncate">Cumulative global box office earnings in Billions ($B)</p>
              </div>
              <span className="bg-[#E7ECEF] text-[#15616D] text-xs font-semibold px-3 py-1 rounded-lg shrink-0">Box Office Leaders</span>
            </div>
            <div className="relative h-72 w-full flex items-center justify-center">
              <canvas id="directorChart"></canvas>
            </div>
          </div>

          <div className="bg-gradient-to-br from-[#15616D] to-[#073B4C] text-white p-6 rounded-2xl shadow-md lg:col-span-1 w-full min-w-0 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-bold flex items-center gap-2">
                  <svg className="w-5 h-5 text-[#FF7D00] shrink-0" fill="currentColor" viewBox="0 0 24 24"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
                  <span>ML Insights</span>
                </h2>
                <span className="bg-[#FF7D00] text-white text-xs font-bold px-2.5 py-0.5 rounded-full shrink-0">Active Model</span>
              </div>
              <p className="text-sm text-gray-200 mb-4">Our Random Forest Regression model analyzes budget, runtime, genre, and streaming distribution with an <span className="text-[#FF7D00] font-bold">R² score of 0.84</span>.</p>
              
              <div className="space-y-3 pt-2">
                <div className="bg-white/15 p-3 rounded-xl backdrop-blur-sm border border-white/10">
                  <p className="text-xs text-[#8AA79F]">Highest Grossing Genre</p>
                  <p className="text-base font-bold text-white">Action & Sci-Fi ($142.8B)</p>
                </div>
                <div className="bg-white/15 p-3 rounded-xl backdrop-blur-sm border border-white/10">
                  <p className="text-xs text-[#8AA79F]">Top Rated Platform</p>
                  <p className="text-base font-bold text-white">Apple TV+ (7.1 Avg IMDb)</p>
                </div>
                <div className="bg-white/15 p-3 rounded-xl backdrop-blur-sm border border-white/10">
                  <p className="text-xs text-[#8AA79F]">Optimal Runtime for Hits</p>
                  <p className="text-base font-bold text-white">118 - 135 Minutes</p>
                </div>
              </div>
            </div>
            <div className="mt-6 pt-4 border-t border-white/10 text-center">
              <a href="#prediction-section" className="inline-block bg-[#FF7D00] hover:bg-orange-600 text-white font-semibold text-sm px-6 py-2.5 rounded-xl transition duration-200 shadow-md">
                Try Live Predictor ↓
              </a>
            </div>
          </div>
        </div>

        {/* Interactive ML Prediction Section */}
        <section id="prediction-section" className="bg-white p-8 rounded-3xl shadow-md border border-gray-100">
          <div className="max-w-3xl mx-auto text-center mb-8">
            <span className="bg-[#FF7D00]/10 text-[#FF7D00] font-bold text-xs uppercase px-3 py-1 rounded-full tracking-wider">Interactive ML Engine</span>
            <h2 className="text-2xl sm:text-3xl font-extrabold text-[#15616D] mt-2">Run Live Movie Success Prediction</h2>
            <p className="text-sm text-gray-500 mt-1">Configure movie features below to instantly simulate box office revenue and critical success score using our trained model.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-stretch w-full">
            <div className="space-y-4 bg-[#E7ECEF]/50 p-6 rounded-2xl border border-gray-200/60 w-full min-w-0 flex flex-col justify-between">
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-bold uppercase text-gray-600 mb-1">Primary Genre</label>
                  <select id="pred-genre" className="w-full bg-white border border-gray-300 rounded-xl px-4 py-2.5 text-sm font-medium focus:ring-2 focus:ring-[#15616D] focus:outline-none">
                    <option value="Action">Action</option>
                    <option value="Sci-Fi">Sci-Fi</option>
                    <option value="Drama">Drama</option>
                    <option value="Comedy">Comedy</option>
                    <option value="Thriller">Thriller</option>
                    <option value="Animation">Animation</option>
                    <option value="Romance">Romance</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-bold uppercase text-gray-600 mb-1">Production Budget ($ Millions)</label>
                  <input type="number" id="pred-budget" defaultValue="120" min="1" max="400" className="w-full bg-white border border-gray-300 rounded-xl px-4 py-2.5 text-sm font-medium focus:ring-2 focus:ring-[#15616D] focus:outline-none" />
                </div>

                <div>
                  <label className="block text-xs font-bold uppercase text-gray-600 mb-1">Runtime (Minutes)</label>
                  <input type="number" id="pred-runtime" defaultValue="125" min="60" max="240" className="w-full bg-white border border-gray-300 rounded-xl px-4 py-2.5 text-sm font-medium focus:ring-2 focus:ring-[#15616D] focus:outline-none" />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-bold uppercase text-gray-600 mb-1">Streaming Platform</label>
                    <select id="pred-platform" className="w-full bg-white border border-gray-300 rounded-xl px-4 py-2.5 text-sm font-medium focus:ring-2 focus:ring-[#15616D] focus:outline-none">
                      <option value="Apple TV+">Apple TV+</option>
                      <option value="Netflix">Netflix</option>
                      <option value="Disney+">Disney+</option>
                      <option value="Prime Video">Prime Video</option>
                      <option value="MGM+">MGM+</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-bold uppercase text-gray-600 mb-1">Director Tier</label>
                    <select id="pred-director" className="w-full bg-white border border-gray-300 rounded-xl px-4 py-2.5 text-sm font-medium focus:ring-2 focus:ring-[#15616D] focus:outline-none">
                      <option value="A-List">A-List (Cameron, Nolan, etc.)</option>
                      <option value="Established">Established Director</option>
                      <option value="Rising">Rising Star / Indie</option>
                    </select>
                  </div>
                </div>
              </div>

              <button onClick={runPrediction} className="w-full bg-[#15616D] hover:bg-teal-800 text-white font-bold py-3 px-6 rounded-xl transition duration-200 shadow-lg flex items-center justify-center space-x-2 mt-6">
                <svg className="w-5 h-5 text-[#FF7D00] shrink-0" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86 1.517l-.318.318a6 6 0 01-3.86 1.517H6.5a2 2 0 01-2-2v-1.5a2 2 0 01.547-1.022l4.773-4.773a2 2 0 00.547-1.022V6.5a2 2 0 012-2h1.5a2 2 0 012 2v1.5a2 2 0 00.547 1.022l1.022 1.022a2 2 0 001.022.547l2.387.477a2 2 0 011.666 1.666l.477 2.387a2 2 0 01-.547 1.022z"></path></svg>
                <span>Run ML Prediction</span>
              </button>
            </div>

            {/* Prediction Output Results */}
            <div id="prediction-results" className="bg-gradient-to-br from-[#15616D] to-[#073B4C] text-white p-8 rounded-2xl shadow-md flex flex-col justify-between w-full min-w-0 min-h-[380px]">
              <div id="prediction-initial" className="text-center my-auto py-12">
                <div className="bg-white/15 w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4 text-[#FF7D00] shrink-0">
                  <svg className="w-8 h-8" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z"></path></svg>
                </div>
                <h3 className="text-lg font-bold">Ready for Simulation</h3>
                <p className="text-sm text-[#8AA79F] mt-1">Adjust parameters on the left and click 'Run ML Prediction' to generate theatrical forecasts.</p>
              </div>

              <div id="prediction-output" className="hidden space-y-6">
                <div className="flex items-center justify-between border-b border-white/10 pb-4">
                  <div>
                    <span className="text-xs uppercase tracking-wider text-[#8AA79F] font-semibold">Predicted Box Office</span>
                    <h3 id="res-revenue" className="text-4xl font-extrabold text-[#FF7D00] mt-1">$0.0 M</h3>
                  </div>
                  <div className="text-right">
                    <span className="text-xs uppercase tracking-wider text-[#8AA79F] font-semibold">Success Tier</span>
                    <div id="res-tier" className="inline-block mt-1 px-3 py-1 rounded-full text-xs font-bold bg-emerald-500 text-white">Blockbuster</div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-white/15 p-4 rounded-xl backdrop-blur-sm min-w-0">
                    <span className="text-xs text-[#8AA79F]">Predicted IMDb Rating</span>
                    <h4 id="res-rating" className="text-2xl font-bold text-white mt-1">7.4 / 10</h4>
                  </div>
                  <div className="bg-white/15 p-4 rounded-xl backdrop-blur-sm min-w-0">
                    <span className="text-xs text-[#8AA79F]">Model Confidence</span>
                    <h4 id="res-confidence" className="text-2xl font-bold text-white mt-1">91.4%</h4>
                  </div>
                </div>

                <div className="bg-white/15 p-4 rounded-xl backdrop-blur-sm">
                  <div className="flex justify-between text-xs font-semibold mb-1">
                    <span className="text-[#8AA79F]">Profitability Index</span>
                    <span id="res-roi-text" className="text-white">3.4x ROI</span>
                  </div>
                  <div className="w-full bg-white/20 rounded-full h-2 overflow-hidden">
                    <div id="res-roi-bar" className="bg-[#FF7D00] h-full rounded-full transition-all duration-500" style={{ width: '75%' }}></div>
                  </div>
                </div>
              </div>

              <div className="pt-4 border-t border-white/10 text-xs text-[#8AA79F] text-center">
                CineMetrics Machine Learning Engine v2.4 • Powered by Random Forest & Regression
              </div>
            </div>
          </div>
        </section>

      </main>

      {/* Footer */}
      <footer className="bg-[#073B4C] text-white mt-16 py-8 border-t border-white/10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row justify-between items-center text-xs text-[#8AA79F]">
          <p>&copy; 2026 CineMetrics Pro Analytics Dashboard. All rights reserved.</p>
          <div className="flex space-x-6 mt-4 sm:mt-0">
            <span className="hover:text-white cursor-pointer">Privacy Policy</span>
            <span className="hover:text-white cursor-pointer">Terms of Service</span>
            <span className="hover:text-white cursor-pointer">API Documentation</span>
          </div>
        </div>
      </footer>

    </div>
  );
}