// ExpenX Prototype Logic

// --- Configurations ---
const PRIMARY_COLOR = '#2dd4bf';
const ACCENT_RED = '#ff7b6b';
const CHART_BG_ALPHA = '20'; // Hex opacity

// --- Mock Data ---
const mockExpenses = [
    { date: '2025-12-09', desc: 'Starbucks Coffee', cat: 'Food', acc: 'Credit Card', amt: 350 },
    { date: '2025-12-08', desc: 'Uber Trip', cat: 'Transport', acc: 'UPI', amt: 420 },
    { date: '2025-12-07', desc: 'Netflix Subscription', cat: 'Entertainment', acc: 'Credit Card', amt: 649 },
    { date: '2025-12-05', desc: 'Grocery Run', cat: 'Groceries', acc: 'Cash', amt: 1200 },
    { date: '2025-12-01', desc: 'Rent Payment', cat: 'Rent', acc: 'Bank Transfer', amt: 25000 },
];

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    populateTable();
});

// --- Navigation ---
function switchTab(tabId, navElement) {
    // 1. Hide all sections
    document.querySelectorAll('[id^="section-"]').forEach(el => {
        el.classList.add('hidden');
    });

    // 2. Show target section
    const target = document.getElementById(`section-${tabId}`);
    if (target) {
        target.classList.remove('hidden');
    }

    // 3. Update Title
    const titles = {
        'dashboard': 'Dashboard',
        'add-expense': 'Add New Expense',
        'view-expenses': 'Expense History',
        'income': 'Income',
        'accounts': 'Accounts',
        'ledger': 'Ledger Management'
    };
    document.getElementById('page-title').innerText = titles[tabId] || 'ExpenX';

    // 4. Update Sidebar Active State (if clicked via sidebar)
    if (navElement) {
        document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
        navElement.classList.add('active');
    } else {
        // Handle programmatic switches (like from "New Entry" button)
        // This is a basic implementation; ideally we map tabId back to the nav item
    }
}

// --- Charts ---
function initCharts() {
    // 1. Spend Trend Chart (Line)
    const ctxSpend = document.getElementById('spendChart').getContext('2d');
    new Chart(ctxSpend, {
        type: 'line',
        data: {
            labels: ['1 Dec', '3 Dec', '5 Dec', '7 Dec', '9 Dec', '11 Dec', '13 Dec'],
            datasets: [{
                label: 'Daily Spend',
                data: [25000, 1500, 1200, 649, 770, 0, 0],
                borderColor: PRIMARY_COLOR,
                backgroundColor: PRIMARY_COLOR + CHART_BG_ALPHA,
                tension: 0.4,
                fill: true,
                pointBackgroundColor: '#0f1724',
                pointBorderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    grid: { color: '#334155', drawBorder: false },
                    ticks: { color: '#94a3b8' }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#94a3b8' }
                }
            }
        }
    });

    // 2. Category Donut Chart
    const ctxCat = document.getElementById('categoryChart').getContext('2d');
    new Chart(ctxCat, {
        type: 'doughnut',
        data: {
            labels: ['Rent', 'Food', 'Transport', 'Ent.', 'Others'],
            datasets: [{
                data: [55, 15, 10, 5, 15],
                backgroundColor: [
                    '#2dd4bf', // Primary
                    '#38bdf8', // Blue
                    '#fbbf24', // Amber
                    '#ff7b6b', // Red
                    '#94a3b8'  // Grey
                ],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'right', labels: { color: '#f8fafc' } }
            },
            cutout: '70%'
        }
    });
}

// --- Table Population ---
function populateTable() {
    const tbody = document.getElementById('expenseTableBody');
    tbody.innerHTML = '';

    mockExpenses.forEach(exp => {
        const row = `
            <tr>
                <td>${exp.date}</td>
                <td>${exp.desc}</td>
                <td><span class="badge badge-cat">${exp.cat}</span></td>
                <td>${exp.acc}</td>
                <td style="text-align:right; font-weight:600;">₹${exp.amt.toLocaleString()}</td>
            </tr>
        `;
        tbody.innerHTML += row;
    });
}

// --- Form Handling ---
function handleFormSubmit(e) {
    e.preventDefault();
    alert("This is a prototype! In the real app, this data would be sent to the Python backend.");
    // Visualize success
    e.target.reset();
}
