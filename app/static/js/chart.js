export class ChartManager {
    constructor(canvasId) {
        const ctx = document.getElementById(canvasId).getContext('2d');
        Chart.defaults.color = '#94a3b8';
        Chart.defaults.font.family = 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas';

        this.chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: ' CPU Usage',
                    data: [],
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    borderWidth: 2,
                    pointRadius: 0,
                    pointHoverRadius: 6,
                    pointBackgroundColor: '#fff',
                    pointBorderColor: '#3b82f6',
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        backgroundColor: 'rgba(15, 23, 42, 0.9)',
                        titleColor: '#fff',
                        bodyColor: '#cbd5e1',
                        borderColor: '#334155',
                        borderWidth: 1,
                        padding: 10,
                        displayColors: false
                    }
                },
                scales: {
                    x: { grid: { color: '#334155', drawBorder: false }, ticks: { maxTicksLimit: 8 } },
                    y: {
                        beginAtZero: true,
                        grid: { color: '#334155', drawBorder: false },
                        suggestedMax: 0.05,
                        ticks: { callback: function(value) { return value.toFixed(3) + ' c'; } }
                    }
                },
                interaction: { mode: 'nearest', axis: 'x', intersect: false }
            }
        });
    }

    updateData(labels, dataPoints) {
        this.chart.data.labels = labels;
        this.chart.data.datasets[0].data = dataPoints;
        this.chart.update();
    }

    clear() {
        this.chart.data.labels = [];
        this.chart.data.datasets[0].data = [];
        this.chart.update();
    }

    isEmpty() {
        return this.chart.data.labels.length === 0;
    }
}
