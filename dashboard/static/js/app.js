function dashboard() {
    return {
        // State
        tab: 'overview',
        sourceFilter: 'all',
        searchQuery: '',
        posts: [],
        trends: [],
        stats: { total_posts: 0, posts_today: 0, avg_engagement: 0, per_source: {} },
        sourceStats: [],
        runs: [],
        activityData: [],
        sseConnected: false,
        loading: true,
        lastUpdate: null,

        // Lifecycle
        async init() {
            await this.fetchAll();
            this.connectSSE();
            // Auto-refresh every 30 seconds
            setInterval(() => this.fetchAll(), 30000);
        },

        // Data fetching
        async fetchAll() {
            this.loading = true;
            await Promise.all([
                this.fetchPosts(),
                this.fetchStats(),
                this.fetchTrends(),
                this.fetchSourceStats(),
                this.fetchRuns(),
                this.fetchActivity(),
            ]);
            this.loading = false;
            this.lastUpdate = new Date().toLocaleTimeString();
        },

        async fetchPosts() {
            const params = new URLSearchParams({ limit: '50', order: 'desc', sort: 'engagement_score' });
            if (this.sourceFilter !== 'all') params.set('source', this.sourceFilter);
            if (this.searchQuery) params.set('search', this.searchQuery);
            try {
                const res = await fetch(`/api/posts?${params}`);
                this.posts = await res.json();
            } catch (e) { console.error('Failed to fetch posts:', e); }
        },

        async fetchStats() {
            try {
                const res = await fetch('/api/posts/stats');
                this.stats = await res.json();
            } catch (e) { console.error('Failed to fetch stats:', e); }
        },

        async fetchTrends() {
            try {
                const params = new URLSearchParams({ limit: '15' });
                if (this.sourceFilter !== 'all') params.set('source', this.sourceFilter);
                const res = await fetch(`/api/trends?${params}`);
                this.trends = await res.json();
            } catch (e) { console.error('Failed to fetch trends:', e); }
        },

        async fetchSourceStats() {
            try {
                const res = await fetch('/api/sources/stats');
                this.sourceStats = await res.json();
            } catch (e) { console.error('Failed to fetch source stats:', e); }
        },

        async fetchRuns() {
            try {
                const res = await fetch('/api/sources/runs?limit=10');
                this.runs = await res.json();
            } catch (e) { console.error('Failed to fetch runs:', e); }
        },

        async fetchActivity() {
            try {
                const res = await fetch('/api/posts/activity?hours=24');
                this.activityData = await res.json();
                this.$nextTick(() => this.renderChart());
            } catch (e) { console.error('Failed to fetch activity:', e); }
        },

        // SSE
        connectSSE() {
            const es = new EventSource('/api/events');
            es.onopen = () => { this.sseConnected = true; };
            es.onmessage = (e) => {
                if (!e.data) return;
                try {
                    const data = JSON.parse(e.data);
                    if (data.event === 'scrape_complete') {
                        this.fetchAll();
                    }
                } catch {}
            };
            es.onerror = () => {
                this.sseConnected = false;
                setTimeout(() => this.connectSSE(), 5000);
            };
        },

        // Chart rendering
        renderChart() {
            const canvas = document.getElementById('activityChart');
            if (!canvas) return;

            // Destroy previous chart instance
            if (window._activityChart) {
                window._activityChart.destroy();
            }

            // Group data by source
            const sources = {};
            const colors = { reddit: '#ff4500', twitter: '#1d9bf0', news: '#22c55e' };
            for (const row of this.activityData) {
                if (!sources[row.source]) sources[row.source] = {};
                sources[row.source][row.hour] = row.count;
            }

            // Collect all unique hours and sort
            const allHours = [...new Set(this.activityData.map(r => r.hour))].sort();
            const labels = allHours.map(h => {
                const d = new Date(h + 'Z');
                return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            });

            const datasets = Object.entries(sources).map(([src, hourMap]) => ({
                label: src.charAt(0).toUpperCase() + src.slice(1),
                data: allHours.map(h => hourMap[h] || 0),
                borderColor: colors[src] || '#8b5cf6',
                backgroundColor: (colors[src] || '#8b5cf6') + '20',
                fill: true,
                tension: 0.35,
                pointRadius: 0,
                borderWidth: 2,
            }));

            window._activityChart = new Chart(canvas, {
                type: 'line',
                data: { labels, datasets },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: {
                            labels: { color: '#94a3b8', usePointStyle: true, pointStyle: 'circle' }
                        },
                        tooltip: { backgroundColor: '#1f2937', titleColor: '#f1f5f9', bodyColor: '#94a3b8' }
                    },
                    scales: {
                        x: {
                            grid: { color: '#1f293750' },
                            ticks: { color: '#64748b', maxTicksLimit: 12 }
                        },
                        y: {
                            grid: { color: '#1f293750' },
                            ticks: { color: '#64748b' },
                            beginAtZero: true,
                        }
                    }
                }
            });
        },

        // Manual scrape trigger
        async triggerScrape(source) {
            try {
                const res = await fetch(`/api/scraper/run/${source}`, { method: 'POST' });
                const data = await res.json();
                await this.fetchAll();
            } catch (e) { console.error('Failed to trigger scrape:', e); }
        },

        // Helpers
        timeAgo(isoStr) {
            if (!isoStr) return 'N/A';
            const diff = Date.now() - new Date(isoStr).getTime();
            const mins = Math.floor(diff / 60000);
            if (mins < 1) return 'just now';
            if (mins < 60) return `${mins}m ago`;
            const hrs = Math.floor(mins / 60);
            if (hrs < 24) return `${hrs}h ago`;
            return `${Math.floor(hrs / 24)}d ago`;
        },

        formatNumber(n) {
            if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
            if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
            return String(n);
        },

        sourceColor(src) {
            return { twitter: '#1d9bf0', reddit: '#ff4500', news: '#22c55e' }[src] || '#8b5cf6';
        },

        activeSources() {
            return Object.keys(this.stats.per_source || {}).length;
        },
    };
}
