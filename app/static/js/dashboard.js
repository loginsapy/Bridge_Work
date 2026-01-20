// ============================================
// BridgeWork Dashboard JavaScript
// Interactive Charts and UI Components
// ============================================

document.addEventListener('DOMContentLoaded', function () {
  // Initialize all dashboard components
  initCharts();
  initSidebarToggle();
  initInteractiveElements();
});

// ============================================
// Chart Initialization
// ============================================

function initCharts() {
  initBudgetChart();
  initProjectStatusChart();
  initVelocityChart();
}

function initBudgetChart() {
  const budgetCtx = document.getElementById('budgetChart');
  if (!budgetCtx) return;

  const labels = JSON.parse(budgetCtx.dataset.labels || '[]');
  const usedData = JSON.parse(budgetCtx.dataset.used || '[]');
  const plannedData = JSON.parse(budgetCtx.dataset.planned || '[]');

  if (labels.length > 0) {
    new Chart(budgetCtx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Horas Invertidas',
            data: usedData,
            borderColor: 'var(--brand-accent)',
            backgroundColor: 'rgba(79, 93, 149, 0.1)',
            tension: 0.4,
            fill: true,
            pointRadius: 4,
            pointHoverRadius: 6,
            pointBackgroundColor: 'var(--brand-accent)',
            pointBorderColor: '#fff',
            pointBorderWidth: 2
          },
          {
            label: 'Horas Planificadas',
            data: plannedData,
            borderColor: 'var(--success)',
            backgroundColor: 'rgba(16, 185, 129, 0.05)',
            tension: 0.4,
            fill: true,
            pointRadius: 4,
            pointHoverRadius: 6,
            pointBackgroundColor: 'var(--success)',
            pointBorderColor: '#fff',
            pointBorderWidth: 2,
            borderDash: [5, 5]
          }
        ]
      },
      options: getCommonChartOptions('h')
    });
  }
}

function initProjectStatusChart() {
  const statusCtx = document.getElementById('projectStatusChart');
  if (!statusCtx) return;

  const statusData = JSON.parse(statusCtx.dataset.status || '{}');
  const labels = Object.keys(statusData);

  if (labels.length > 0) {
    const data = Object.values(statusData);
    // Colores hexadecimales para cada estado
    const statusColors = {
      'active': '#00c875',
      'ACTIVE': '#00c875',
      'planning': '#fdab3d',
      'PLANNING': '#fdab3d',
      'completed': '#0073ea',
      'COMPLETED': '#0073ea',
      'on_hold': '#787878',
      'ON_HOLD': '#787878',
      'cancelled': '#e2445c',
      'CANCELLED': '#e2445c',
      'archived': '#787878',
      'ARCHIVED': '#787878'
    };
    const backgroundColors = labels.map(label => statusColors[label] || '#787878');

    new Chart(statusCtx, {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: data,
          backgroundColor: backgroundColors,
          borderWidth: 0,
          hoverOffset: 10
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: getCommonTooltipOptions({
            callbacks: {
              label: function (context) {
                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                const percentage = ((context.parsed / total) * 100).toFixed(1);
                return `${context.label}: ${context.parsed} (${percentage}%)`;
              }
            }
          })
        },
        cutout: '70%'
      }
    });
  }
}

async function initVelocityChart() {
  const velocityCtx = document.getElementById('velocityChart');
  if (!velocityCtx) return;

  try {
    const response = await fetch('/api/kpi/velocity');
    if (!response.ok) throw new Error('Network response was not ok');
    
    const chartData = await response.json();

    new Chart(velocityCtx, {
      type: 'bar',
      data: {
        labels: chartData.labels,
        datasets: [{
          label: 'Horas Registradas',
          data: chartData.data,
          backgroundColor: '#0073ea',
          borderColor: '#0073ea',
          borderWidth: 1,
          borderRadius: 6,
          hoverBackgroundColor: '#a25ddc'
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#323338',
            titleFont: { size: 13, family: "'Inter', sans-serif" },
            bodyFont: { size: 12, family: "'Inter', sans-serif" },
            padding: 12,
            cornerRadius: 8,
            callbacks: {
              label: (context) => `Horas: ${context.parsed.y}h`
            }
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: { callback: (value) => `${value}h`, font: { size: 11 } },
            grid: { color: 'rgba(0, 0, 0, 0.05)', drawBorder: false }
          },
          x: {
            grid: { display: false },
            ticks: { font: { size: 11 } }
          }
        }
      }
    });
  } catch (error) {
    console.error("Error fetching velocity data:", error);
    velocityCtx.parentElement.innerHTML = '<div class="text-center text-muted py-4">No se pudieron cargar los datos del gráfico.</div>';
  }
}

// ============================================
// Chart Helpers
// ============================================

function getCommonChartOptions(unit = '', overrides = {}) {
  const commonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top',
        labels: { usePointStyle: true, padding: 15, font: { size: 12, family: "'Inter', sans-serif" } }
      },
      tooltip: getCommonTooltipOptions({
        callbacks: {
          label: (context) => `${context.dataset.label}: ${context.parsed.y}${unit}`
        }
      })
    },
    scales: {
      y: {
        beginAtZero: true,
        ticks: { callback: (value) => `${value}${unit}`, font: { size: 11 } },
        grid: { color: 'rgba(0, 0, 0, 0.05)', drawBorder: false }
      },
      x: {
        grid: { display: false },
        ticks: { font: { size: 11 } }
      }
    },
    interaction: {
      intersect: false,
      mode: 'index'
    }
  };
  
  // Simple deep merge for nested properties
  if (overrides.plugins && overrides.plugins.legend) {
    commonOptions.plugins.legend = { ...commonOptions.plugins.legend, ...overrides.plugins.legend };
    delete overrides.plugins.legend;
  }
  if (overrides.plugins) {
    commonOptions.plugins = { ...commonOptions.plugins, ...overrides.plugins };
  }
  
  return { ...commonOptions, ...overrides };
}

function getCommonTooltipOptions(overrides = {}) {
  const commonTooltip = {
    backgroundColor: 'rgba(0, 0, 0, 0.8)',
    padding: 12,
    titleFont: { size: 13, weight: '600' },
    bodyFont: { size: 12 },
    cornerRadius: 6,
    displayColors: true,
  };
  return { ...commonTooltip, ...overrides };
}


// ============================================
// Sidebar Toggle for Mobile
// ============================================

function initSidebarToggle() {
  const sidebarToggle = document.getElementById('sidebarToggle');
  const sidebar = document.getElementById('sidebar-wrapper');

  if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener('click', function () {
      sidebar.classList.toggle('show');
    });

    // Close sidebar when clicking outside on mobile
    document.addEventListener('click', function (event) {
      const isClickInsideSidebar = sidebar.contains(event.target);
      const isClickOnToggle = sidebarToggle.contains(event.target);

      if (!isClickInsideSidebar && !isClickOnToggle && sidebar.classList.contains('show')) {
        sidebar.classList.remove('show');
      }
    });
  }
}

// ============================================
// Interactive Elements
// ============================================

function initInteractiveElements() {
  // Animate stat cards on scroll
  const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
  };

  const observer = new IntersectionObserver(function (entries) {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('fade-in');
      }
    });
  }, observerOptions);

  document.querySelectorAll('.stat-card').forEach(card => {
    observer.observe(card);
  });

  // Add hover effect to team members
  document.querySelectorAll('.hover-shadow').forEach(element => {
    element.addEventListener('mouseenter', function () {
      this.style.boxShadow = '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)';
      this.style.transform = 'translateY(-2px)';
    });

    element.addEventListener('mouseleave', function () {
      this.style.boxShadow = 'none';
      this.style.transform = 'translateY(0)';
    });
  });

  // Time period selector for budget chart
  const periodButtons = document.querySelectorAll('.btn-group .btn');
  periodButtons.forEach(button => {
    button.addEventListener('click', function () {
      periodButtons.forEach(btn => btn.classList.remove('active'));
      this.classList.add('active');
      // Here you would typically reload chart data based on selected period
      console.log('Period changed to:', this.textContent);
    });
  });
}

// ============================================
// Utility Functions
// ============================================

// Format numbers with thousands separator
function formatNumber(num) {
  return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Calculate percentage
function calculatePercentage(value, total) {
  return ((value / total) * 100).toFixed(1);
}

// Show toast notification (for future use)
function showToast(message, type = 'info') {
  // Implementation for toast notifications
  console.log(`Toast [${type}]: ${message}`);
}

// ============================================
// Export functions for external use
// ============================================

window.BridgeWorkDashboard = {
  formatNumber,
  calculatePercentage,
  showToast
};