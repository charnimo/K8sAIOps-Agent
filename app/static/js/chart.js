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
                        displayColors: false,
                        callbacks: {
                            label: function(context) {
                                let value = context.raw;
                                const metricType = context.chart.options.scales.y.metricFormat || 'cpu';
                                if (metricType === 'memory' || metricType.startsWith('network')) {
                                    if (value >= 1073741824) return (value / 1073741824).toFixed(2) + ' GB';
                                    if (value >= 1048576) return (value / 1048576).toFixed(2) + ' MB';
                                    if (value >= 1024) return (value / 1024).toFixed(2) + ' KB';
                                    const suffix = metricType.startsWith('network') ? ' B/s' : ' B';
                                    return (value % 1 === 0 ? value : value.toFixed(2)) + suffix;
                                }
                                return value.toFixed(5) + ' c';
                            }
                        }
                    }
                },
                scales: {
                    x: { grid: { color: '#334155', drawBorder: false }, ticks: { maxTicksLimit: 8 } },
                    y: {
                        beginAtZero: true,
                        grid: { color: '#334155', drawBorder: false },
                        suggestedMax: 0.05,
                        title: { display: true, text: 'vCores', color: '#94a3b8' },
                        ticks: { 
                            callback: function(value) {
                                // Default cpu parsing
                                const metricType = this.chart.options.scales.y.metricFormat || 'cpu';
                                if (metricType === 'memory' || metricType.startsWith('network')) {
                                    if (value >= 1073741824) return (value / 1073741824).toFixed(2) + ' GB';
                                    if (value >= 1048576) return (value / 1048576).toFixed(2) + ' MB';
                                    if (value >= 1024) return (value / 1024).toFixed(2) + ' KB';
                                    const suffix = metricType.startsWith('network') ? ' B/s' : ' B';
                                    return (value % 1 === 0 ? value : value.toFixed(2)) + suffix;
                                }
                                return value.toFixed(3) + ' c'; 
                            }
                        }
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

    setMetricType(metricType, metricLabel) {
        this.chart.options.scales.y.metricFormat = metricType;
        this.chart.options.scales.y.title.text = metricLabel;
        this.chart.data.datasets[0].label = ` ${metricLabel}`;
        
        if (metricType === 'cpu') {
            this.chart.options.scales.y.suggestedMax = 0.05;
        } else {
            delete this.chart.options.scales.y.suggestedMax;
        }
        this.chart.update();
    }
}
