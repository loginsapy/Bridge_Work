document.addEventListener('DOMContentLoaded', function () {
  // Speed chart
  const ctx = document.getElementById('speedChartMock')?.getContext('2d');
  if (ctx){
    new Chart(ctx, {
      type: 'line',
      data: {
        labels: ['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'],
        datasets: [{
          label: 'Horas completadas',
          data: [24, 28, 30, 20, 36, 18, 28],
          borderColor: getComputedStyle(document.documentElement).getPropertyValue('--brand').trim() || '#0d6efd',
          backgroundColor: 'rgba(0,0,0,0.04)',
          tension: 0.25,
          fill: true,
        }]
      },
      options: { responsive:true, maintainAspectRatio:false, plugins:{ legend:{ display:false } } }
    });
  }
});