frappe.pages['al-buraq-dashboard'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Dashboard',
		single_column: true,
	});

	_ab_inject_css();

	page.main.html(
		'<div class="ab-dash"><div class="ab-loading"><div class="ab-spinner"></div><span>Loading dashboard…</span></div></div>'
	);

	frappe.call({
		method: 'al_buraq.api.dashboard.get_dashboard_data',
		callback: function (r) {
			if (r.message) {
				_ab_render(page, r.message);
			}
		},
		error: function () {
			page.main.html('<div class="ab-dash"><p style="color:#e94560;text-align:center;padding:60px">Failed to load dashboard.</p></div>');
		},
	});
};

// ─── Render ──────────────────────────────────────────────────────────────────
function _ab_render(page, d) {
	var html = '<div class="ab-dash">';

	// Header
	html += '<div class="ab-header">';
	html += '<div class="ab-header-left">';
	if (d.is_branch_user && !d.is_admin) {
		html += '<h2 class="ab-title">' + frappe.utils.escape_html(d.branch_name || 'Branch') +
			' <span class="ab-title-sub">Branch</span></h2>';
		html += '<span class="ab-subtitle">Sales Dashboard</span>';
	} else if (d.is_stock_user && !d.is_branch_user && !d.is_admin) {
		html += '<h2 class="ab-title">Warehouse <span class="ab-title-sub">Operations</span></h2>';
		html += '<span class="ab-subtitle">Stock Dashboard</span>';
	} else if (d.is_accounts && !d.is_admin) {
		html += '<h2 class="ab-title">Accounts <span class="ab-title-sub">Overview</span></h2>';
		html += '<span class="ab-subtitle">Finance Dashboard</span>';
	} else {
		html += '<h2 class="ab-title">Management <span class="ab-title-sub">Overview</span></h2>';
		html += '<span class="ab-subtitle">Admin Dashboard</span>';
	}
	html += '</div>';
	html += '<div class="ab-header-right"><span class="ab-date">' +
		frappe.datetime.str_to_user(frappe.datetime.get_today()) + '</span></div>';
	html += '</div>';

	// Sections
	if (d.is_branch_user || d.is_admin) html += _ab_sales_section(d);
	if (d.is_accounts || d.is_admin)    html += _ab_accounts_section(d);
	if (d.is_stock_user || d.is_admin)  html += _ab_stock_section(d);

	html += '</div>';
	page.main.html(html);

	// Animate cards
	setTimeout(function () {
		page.main.find('.ab-kpi,.ab-action,.ab-row-item').each(function (i) {
			var $el = $(this);
			setTimeout(function () { $el.addClass('ab-visible'); }, i * 40);
		});
	}, 50);

	// Card click
	page.main.find('.ab-action').on('click', function () {
		var action = $(this).data('action');
		var target = $(this).data('target');
		var filter = $(this).data('filter');
		if (action === 'new') {
			frappe.new_doc(target);
		} else if (action === 'list') {
			if (filter) {
				var obj = {};
				filter.split('&').forEach(function (p) {
					var kv = p.split('=');
					if (kv.length === 2) obj[kv[0]] = kv[1];
				});
				frappe.set_route('List', target, obj);
			} else {
				frappe.set_route('List', target);
			}
		} else if (action === 'report') {
			frappe.set_route('query-report', target);
		}
	});

	// MR link
	page.main.find('.ab-mr-link').on('click', function () {
		frappe.set_route('Form', 'Material Request', $(this).data('name'));
	});
}

// ─── Sales Section ───────────────────────────────────────────────────────────
function _ab_sales_section(d) {
	var c = d.currency || 'SAR';
	var html = '';

	html += '<div class="ab-kpi-row">';
	html += _kpi(_fmt_currency(d.daily_sales, c), 'Daily Sales', 'today', '📊');
	html += _kpi(_fmt_currency(d.monthly_sales, c), 'Monthly Sales', 'month', '📈');
	html += _kpi(_fmt_num(d.mtd_invoices), 'MTD Invoices', 'invoices', '🧾');
	html += _kpi(_fmt_currency(d.credits_outstanding, c), 'Outstanding', 'outstanding', '💰');
	html += _kpi(_fmt_currency(d.daily_returns, c), 'Today Returns', 'returns', '↩️');
	html += '</div>';

	html += '<h3 class="ab-section-title">Quick Actions</h3>';
	html += '<div class="ab-action-grid">';
	html += _action('receipt',       'Sales Invoice',   'Create invoice',      'new',    'Sales Invoice');
	html += _action('document',      'Quotation',       'View quotations',     'list',   'Quotation');
	html += _action('send',          'Delivery Note',   'View deliveries',     'list',   'Delivery Note');
	html += _action('people',        'Customer',        'Manage customers',    'list',   'Customer');
	html += _action('credit-card',   'Payment Entry',   'Record payments',     'list',   'Payment Entry');
	html += _action('package',       'Purchase Receipt','View receipts',       'list',   'Purchase Receipt');
	html += _action('file-text',     'Purchase Invoice','View invoices',       'list',   'Purchase Invoice');
	html += _action('truck',         'Material Request','Request materials',   'list',   'Material Request');
	html += _action('corner-down-left', 'Sales Return', 'Process returns',     'list',   'Sales Invoice', 'is_return=1');
	html += '</div>';

	html += '<h3 class="ab-section-title">Reports</h3>';
	html += '<div class="ab-action-grid">';
	html += _action('layers',    'Stock Balance',      'Current stock',        'report', 'Stock Balance');
	html += _action('book-open', 'Stock Ledger',       'Stock transactions',   'report', 'Stock Ledger');
	html += _action('user',      'General Ledger',     'Account statements',   'report', 'General Ledger');
	html += _action('dollar-sign','Accounts Receivable','Outstanding AR',      'report', 'Accounts Receivable');
	html += _action('list',      'Item',               'Browse items',         'list',   'Item');
	html += _action('tag',       'Item Price',         'View price lists',     'list',   'Item Price');
	html += '</div>';

	return html;
}

// ─── Accounts Section ────────────────────────────────────────────────────────
function _ab_accounts_section(d) {
	var c = d.currency || 'SAR';
	var html = '<div class="ab-divider"></div>';
	html += '<h3 class="ab-section-title">Finance Overview</h3>';

	html += '<div class="ab-kpi-row">';
	html += _kpi(_fmt_currency(d.monthly_purchase, c), 'Monthly Purchase', 'month', '🛒');
	html += _kpi(_fmt_currency(d.payables_outstanding, c), 'Payables', 'outstanding', '📋');
	html += '</div>';

	html += '<div class="ab-action-grid">';
	html += _action('dollar-sign', 'Accounts Receivable', 'AR report',         'report', 'Accounts Receivable');
	html += _action('dollar-sign', 'Accounts Payable',    'AP report',         'report', 'Accounts Payable');
	html += _action('book-open',   'General Ledger',       'GL entries',        'report', 'General Ledger');
	html += _action('file-text',   'Purchase Invoice',     'View PIs',          'list',   'Purchase Invoice');
	html += _action('credit-card', 'Payment Entry',        'Payments',          'list',   'Payment Entry');
	html += _action('user',        'Supplier',             'Manage suppliers',  'list',   'Supplier');
	html += '</div>';

	return html;
}

// ─── Stock Section ───────────────────────────────────────────────────────────
function _ab_stock_section(d) {
	var html = '<div class="ab-divider"></div>';
	html += '<h3 class="ab-section-title">Stock Operations</h3>';

	html += '<div class="ab-kpi-row">';
	html += _kpi(_fmt_num(d.total_items || 0), 'Total Items', 'invoices', '🏷️');
	html += _kpi(_fmt_num(d.pending_mrs || 0), 'Pending MRs', 'pending', '📋');
	html += '</div>';

	html += '<div class="ab-action-grid">';
	html += _action('truck',    'Material Request',  'Create MR',         'new',    'Material Request');
	html += _action('list',     'Material Requests', 'View all MRs',      'list',   'Material Request');
	html += _action('send',     'Delivery Note',     'New delivery',      'new',    'Delivery Note');
	html += _action('package',  'Purchase Receipt',  'Receive goods',     'list',   'Purchase Receipt');
	html += _action('list',     'Item',              'Manage items',      'list',   'Item');
	html += _action('layers',   'Stock Balance',     'Current stock',     'report', 'Stock Balance');
	html += _action('book-open','Stock Ledger',      'Stock transactions','report', 'Stock Ledger');
	html += _action('tag',      'Item Group',        'Browse groups',     'list',   'Item Group');
	html += '</div>';

	// Pending MR list
	if (d.pending_mr_list && d.pending_mr_list.length) {
		html += '<h3 class="ab-section-title">Pending Material Requests</h3>';
		html += '<div class="ab-list-card"><div class="ab-list-header">';
		html += '<span class="ab-list-icon">📋</span> Material Requests</div>';
		html += '<div class="ab-list-body">';
		d.pending_mr_list.forEach(function (mr) {
			html += '<div class="ab-row-item">';
			html += '<div class="ab-row-info">';
			html += '<a class="ab-mr-link" data-name="' + frappe.utils.escape_html(mr.name) + '">' +
				frappe.utils.escape_html(mr.name) + '</a>';
			html += '<div class="ab-row-route">';
			html += '<span class="ab-wh-from">' + frappe.utils.escape_html(mr.set_from_warehouse || 'Any') + '</span>';
			html += '<span class="ab-route-arrow">→</span>';
			html += '<span class="ab-wh-to">' + frappe.utils.escape_html(mr.set_warehouse || 'Any') + '</span>';
			html += '</div></div>';
			html += '<div class="ab-row-meta">';
			html += '<div class="ab-row-date">' + frappe.datetime.str_to_user(mr.transaction_date) + '</div>';
			html += '<div class="ab-row-status">' + frappe.utils.escape_html(mr.status) + '</div>';
			html += '</div></div>';
		});
		html += '</div></div>';
	}

	return html;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────
function _kpi(value, label, type, emoji) {
	return '<div class="ab-kpi ab-kpi-' + type + '">' +
		'<div class="ab-kpi-top"><span class="ab-kpi-emoji">' + emoji + '</span>' +
		'<span class="ab-kpi-label">' + frappe.utils.escape_html(label) + '</span></div>' +
		'<div class="ab-kpi-value">' + value + '</div></div>';
}

var _ICONS = {
	'receipt':        '<path d="M14 2H6a2 2 0 0 0-2 2v16l4-2 4 2 4-2 4 2V4a2 2 0 0 0-2-2z"/>',
	'document':       '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
	'people':         '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
	'credit-card':    '<rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/>',
	'package':        '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>',
	'file-text':      '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
	'truck':          '<rect x="1" y="3" width="15" height="13"/><polygon points="16 8 20 8 23 11 23 16 16 16 16 8"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/>',
	'send':           '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>',
	'corner-down-left':'<polyline points="9 10 4 15 9 20"/><path d="M20 4v7a4 4 0 0 1-4 4H4"/>',
	'layers':         '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
	'book-open':      '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
	'dollar-sign':    '<line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
	'user':           '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
	'list':           '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/>',
	'tag':            '<path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/>',
};

function _icon(name) {
	return '<svg class="ab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' +
		(_ICONS[name] || '') + '</svg>';
}

function _action(icon, title, desc, action, target, filter) {
	var attrs = 'data-action="' + action + '" data-target="' + frappe.utils.escape_html(target) + '"';
	if (filter) attrs += ' data-filter="' + frappe.utils.escape_html(filter) + '"';
	return '<div class="ab-action" ' + attrs + '>' +
		'<div class="ab-action-icon">' + _icon(icon) + '</div>' +
		'<div class="ab-action-text">' +
		'<div class="ab-action-title">' + frappe.utils.escape_html(title) + '</div>' +
		'<div class="ab-action-desc">' + frappe.utils.escape_html(desc) + '</div>' +
		'</div></div>';
}

function _fmt_currency(v, currency) {
	if (!v && v !== 0) return '0';
	var n = parseFloat(v);
	if (isNaN(n)) return '0';
	if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
	if (n >= 1000)    return (n / 1000).toFixed(n >= 100000 ? 0 : 1) + 'K';
	return n.toLocaleString(undefined, {maximumFractionDigits: 0});
}

function _fmt_num(v) {
	if (!v && v !== 0) return '0';
	var n = parseInt(v);
	if (isNaN(n)) return '0';
	if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
	if (n >= 1000)    return (n / 1000).toFixed(1) + 'K';
	return n.toLocaleString();
}

// ─── CSS ─────────────────────────────────────────────────────────────────────
function _ab_inject_css() {
	if (document.getElementById('ab-dash-style')) return;
	var s = document.createElement('style');
	s.id = 'ab-dash-style';
	s.textContent = `
	.ab-dash { padding:24px 28px; max-width:1260px; margin:0 auto; }
	.ab-loading { display:flex;align-items:center;justify-content:center;gap:12px;padding:80px 20px;color:#8492a6;font-size:14px; }
	.ab-spinner { width:20px;height:20px;border:2px solid #e0e6ed;border-top-color:#e94560;border-radius:50%;animation:ab-spin .6s linear infinite; }
	@keyframes ab-spin { to { transform:rotate(360deg); } }

	.ab-header { display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:28px;padding-bottom:20px;border-bottom:1px solid #e8ecf1; }
	.ab-title { font-size:26px;font-weight:800;color:#1a1a2e;margin:0;letter-spacing:-.5px; }
	.ab-title-sub { font-weight:400;color:#8492a6; }
	.ab-subtitle { font-size:13px;color:#8492a6;margin-top:4px;display:block; }
	.ab-date { font-size:13px;color:#8492a6;background:#f4f6f9;padding:6px 14px;border-radius:20px;font-weight:500; }
	.ab-divider { height:1px;background:#e8ecf1;margin:36px 0 12px;border:none; }

	.ab-kpi-row { display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:32px; }
	.ab-kpi { background:#fff;border-radius:14px;padding:20px 18px;border:1px solid #e8ecf1;position:relative;overflow:hidden;opacity:0;transform:translateY(12px);transition:opacity .35s,transform .35s,box-shadow .2s; }
	.ab-kpi.ab-visible { opacity:1;transform:translateY(0); }
	.ab-kpi::before { content:'';position:absolute;top:0;left:0;right:0;height:3px; }
	.ab-kpi-today::before,.ab-kpi-returns::before { background:#10b981; }
	.ab-kpi-month::before { background:#3b82f6; }
	.ab-kpi-invoices::before { background:#6366f1; }
	.ab-kpi-pending::before { background:#f59e0b; }
	.ab-kpi-outstanding::before { background:#ef4444; }
	.ab-kpi-top { display:flex;align-items:center;gap:6px;margin-bottom:10px; }
	.ab-kpi-emoji { font-size:16px;line-height:1; }
	.ab-kpi-label { font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:#8492a6; }
	.ab-kpi-value { font-size:32px;font-weight:800;line-height:1;color:#1a1a2e;letter-spacing:-1px; }
	.ab-kpi-today .ab-kpi-value,.ab-kpi-returns .ab-kpi-value { color:#059669; }
	.ab-kpi-month .ab-kpi-value { color:#2563eb; }
	.ab-kpi-invoices .ab-kpi-value { color:#4f46e5; }
	.ab-kpi-pending .ab-kpi-value { color:#d97706; }
	.ab-kpi-outstanding .ab-kpi-value { color:#dc2626; }

	.ab-section-title { font-size:15px;font-weight:700;margin:28px 0 14px;color:#1a1a2e;text-transform:uppercase;letter-spacing:.5px; }

	.ab-action-grid { display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px; }
	.ab-action { display:flex;align-items:center;gap:14px;background:#fff;border-radius:12px;padding:16px 18px;border:1px solid #e8ecf1;cursor:pointer;transition:all .2s;opacity:0;transform:translateY(8px); }
	.ab-action.ab-visible { opacity:1;transform:translateY(0); }
	.ab-action:hover { border-color:#e94560;box-shadow:0 4px 14px rgba(233,69,96,.08);transform:translateY(-2px); }
	.ab-action-icon { flex-shrink:0;width:38px;height:38px;display:flex;align-items:center;justify-content:center;border-radius:10px;background:#f4f6f9;color:#5a6c7d;transition:all .2s; }
	.ab-action:hover .ab-action-icon { background:#fef2f2;color:#e94560; }
	.ab-icon { width:18px;height:18px; }
	.ab-action-title { font-size:13px;font-weight:600;color:#1a1a2e;line-height:1.3; }
	.ab-action-desc { font-size:11px;color:#8492a6;margin-top:2px; }

	.ab-list-card { background:#fff;border-radius:14px;border:1px solid #e8ecf1;overflow:hidden; }
	.ab-list-header { font-size:13px;font-weight:700;color:#1a1a2e;padding:10px 16px;background:#f8f9fb;border-bottom:1px solid #e8ecf1;display:flex;align-items:center;gap:6px; }
	.ab-list-icon { font-size:15px; }
	.ab-list-body { max-height:400px;overflow-y:auto; }
	.ab-row-item { display:flex;justify-content:space-between;align-items:center;padding:14px 20px;border-bottom:1px solid #f0f3f7;opacity:0;transform:translateX(-8px);transition:opacity .3s,transform .3s,background .15s; }
	.ab-row-item.ab-visible { opacity:1;transform:translateX(0); }
	.ab-row-item:last-child { border-bottom:0; }
	.ab-row-item:hover { background:#fafbfd; }
	.ab-mr-link { cursor:pointer;color:#2563eb;font-weight:700;font-size:13px;text-decoration:none; }
	.ab-mr-link:hover { color:#e94560;text-decoration:underline; }
	.ab-row-route { font-size:12px;color:#8492a6;margin-top:4px;display:flex;align-items:center;gap:6px; }
	.ab-route-arrow { color:#c0c9d4;font-weight:700; }
	.ab-row-meta { text-align:right;flex-shrink:0; }
	.ab-row-date { font-size:12px;color:#8492a6; }
	.ab-row-status { font-size:11px;color:#d97706;font-weight:600;margin-top:3px;text-transform:uppercase;letter-spacing:.5px; }

	@media(max-width:1100px) { .ab-kpi-row { grid-template-columns:repeat(3,1fr); } }
	@media(max-width:768px) {
		.ab-dash { padding:16px; }
		.ab-kpi-row { grid-template-columns:repeat(2,1fr);gap:10px; }
		.ab-kpi-value { font-size:26px; }
		.ab-action-grid { grid-template-columns:repeat(2,1fr);gap:8px; }
		.ab-header { flex-direction:column;align-items:flex-start;gap:10px; }
	}
	`;
	document.head.appendChild(s);
}
