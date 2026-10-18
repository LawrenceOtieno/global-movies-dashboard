import React from 'react';
import { Chart } from 'chart.js'; // Import Chart directly

export default function ChartDownloader({ containerId, filename = 'chart.png' }) {
  const handleDownload = () => {
    const container = document.getElementById(containerId);
    if (!container) return;

    const canvas = container.querySelector('canvas');
    if (!canvas) return;

    // Get the Chart.js instance directly from the imported module
    const chartInstance = Chart.getChart(canvas);
    if (!chartInstance) {
      console.warn("Could not find Chart instance for this canvas.");
      return;
    }

    // 1. Save original size
    const originalWidth = canvas.style.width;
    const originalHeight = canvas.style.height;
    const originalAspectRatio = chartInstance.options.maintainAspectRatio;

    // 2. Resize to a high-resolution export size (1600px wide)
    chartInstance.options.maintainAspectRatio = false;
    canvas.style.width = '1600px';
    canvas.style.height = '900px';
    
    // 3. Tell Chart.js to redraw at the new size
    chartInstance.resize();
    chartInstance.update('none'); 

    // 4. Wait a tiny fraction of a second for the browser to paint
    setTimeout(() => {
      const tempCanvas = document.createElement('canvas');
      tempCanvas.width = canvas.width;
      tempCanvas.height = canvas.height;
      const ctx = tempCanvas.getContext('2d');
      
      // Add white background
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, tempCanvas.width, tempCanvas.height);
      ctx.drawImage(canvas, 0, 0);

      // Trigger download
      const dataUrl = tempCanvas.toDataURL('image/png', 1.0);
      const link = document.createElement('a');
      link.href = dataUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      // 5. Restore the chart back to its original responsive size
      chartInstance.options.maintainAspectRatio = originalAspectRatio;
      canvas.style.width = originalWidth;
      canvas.style.height = originalHeight;
      chartInstance.resize();
      chartInstance.update('none');
    }, 50); 
  };

  return (
    <button
      onClick={handleDownload}
      className="absolute bottom-2 right-2 bg-gray-100 hover:bg-gray-200 text-gray-600 p-1.5 rounded-lg shadow-sm transition-colors z-10"
      title="Download high-res PNG"
    >
      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="7 10 12 15 17 10" />
        <line x1="12" y1="15" x2="12" y2="3" />
      </svg>
    </button>
  );
}