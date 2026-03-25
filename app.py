"""
iTalk Lead Manager - Lead Generation Capture & Analytics Application
Flask backend with SQLite database, REST API, and email notifications.
"""

import os
import json
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory, g

app = Flask(__name__)
# SQLite needs a writable directory for WAL mode; use env var or same directory as app
app.config['DATABASE'] = os.environ.get('DB_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'leads.db'))


# =============================================================================
# Database helpers
# =============================================================================
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(app.config['DATABASE'])
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            company TEXT NOT NULL,
            address TEXT,
            contact TEXT,
            email TEXT,
            phone TEXT,
            city TEXT,
            region TEXT,
            sys4 TEXT,
            appointment_completed INTEGER DEFAULT 0,
            proposal INTEGER DEFAULT 0,
            revenue_sold REAL DEFAULT 0,
            revenue_monthly REAL DEFAULT 0,
            won INTEGER DEFAULT 0,
            lost INTEGER DEFAULT 0,
            notes TEXT,
            status TEXT DEFAULT 'pending',
            reviewed_by TEXT,
            reviewed_at TEXT,
            denial_reason TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER,
            action TEXT NOT NULL,
            details TEXT,
            performed_by TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (lead_id) REFERENCES leads(id)
        );

        CREATE TABLE IF NOT EXISTS notification_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            region TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL
        );
    ''')
    db.commit()
    db.close()


# =============================================================================
# API Routes
# =============================================================================

@app.route('/')
def index():
    return send_from_directory(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'), 'index.html')


# --- Leads CRUD ---

@app.route('/api/leads', methods=['GET'])
def get_leads():
    db = get_db()
    status = request.args.get('status', None)
    region = request.args.get('region', None)
    search = request.args.get('search', None)
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))

    query = 'SELECT * FROM leads WHERE 1=1'
    params = []

    if status:
        query += ' AND status = ?'
        params.append(status)
    if region:
        query += ' AND (region = ? OR city = ?)'
        params.extend([region, region])
    if search:
        query += ' AND (company LIKE ? OR contact LIKE ? OR notes LIKE ?)'
        params.extend([f'%{search}%'] * 3)

    # Get total count
    count_query = query.replace('SELECT *', 'SELECT COUNT(*)')
    total = db.execute(count_query, params).fetchone()[0]

    query += ' ORDER BY date DESC, created_at DESC LIMIT ? OFFSET ?'
    params.extend([per_page, (page - 1) * per_page])

    rows = db.execute(query, params).fetchall()
    leads = [dict(row) for row in rows]

    return jsonify({
        'leads': leads,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page
    })


@app.route('/api/leads', methods=['POST'])
def create_lead():
    data = request.json
    db = get_db()

    # Determine region from city
    city = data.get('city', '')
    region = data.get('region', '')
    if not region:
        city_lower = city.lower() if city else ''
        if 'columbus' in city_lower or 'gahanna' in city_lower or 'westerville' in city_lower:
            region = 'Columbus'
        elif 'cincinnati' in city_lower or 'norwood' in city_lower:
            region = 'Cincinnati'
        else:
            region = 'Other'

    cursor = db.execute('''
        INSERT INTO leads (date, company, address, contact, email, phone, city, region,
                          sys4, notes, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
    ''', (
        data.get('date', datetime.now().strftime('%Y-%m-%d')),
        data.get('company', ''),
        data.get('address', ''),
        data.get('contact', ''),
        data.get('email', ''),
        data.get('phone', ''),
        city,
        region,
        data.get('sys4', ''),
        data.get('notes', '')
    ))
    db.commit()
    lead_id = cursor.lastrowid

    # Log activity
    db.execute('INSERT INTO activity_log (lead_id, action, details) VALUES (?, ?, ?)',
               (lead_id, 'created', f"Lead created for {data.get('company', '')}"))
    db.commit()

    return jsonify({'id': lead_id, 'message': 'Lead created successfully'}), 201


@app.route('/api/leads/<int:lead_id>', methods=['GET'])
def get_lead(lead_id):
    db = get_db()
    row = db.execute('SELECT * FROM leads WHERE id = ?', (lead_id,)).fetchone()
    if not row:
        return jsonify({'error': 'Lead not found'}), 404
    return jsonify(dict(row))


@app.route('/api/leads/<int:lead_id>', methods=['PUT'])
def update_lead(lead_id):
    data = request.json
    db = get_db()

    # Build dynamic update
    fields = []
    params = []
    allowed = ['date', 'company', 'address', 'contact', 'email', 'phone', 'city',
               'region', 'sys4', 'appointment_completed', 'proposal', 'revenue_sold',
               'revenue_monthly', 'won', 'lost', 'notes', 'status', 'reviewed_by',
               'reviewed_at', 'denial_reason']

    for field in allowed:
        if field in data:
            fields.append(f'{field} = ?')
            params.append(data[field])

    if not fields:
        return jsonify({'error': 'No fields to update'}), 400

    fields.append("updated_at = datetime('now')")
    params.append(lead_id)

    db.execute(f"UPDATE leads SET {', '.join(fields)} WHERE id = ?", params)
    db.commit()

    return jsonify({'message': 'Lead updated successfully'})


@app.route('/api/leads/<int:lead_id>/approve', methods=['POST'])
def approve_lead(lead_id):
    data = request.json or {}
    db = get_db()

    db.execute('''UPDATE leads SET status = 'approved', reviewed_by = ?,
                  reviewed_at = datetime('now'), updated_at = datetime('now')
                  WHERE id = ?''',
               (data.get('reviewed_by', 'Admin'), lead_id))
    db.execute('INSERT INTO activity_log (lead_id, action, details, performed_by) VALUES (?, ?, ?, ?)',
               (lead_id, 'approved', 'Lead approved', data.get('reviewed_by', 'Admin')))
    db.commit()

    return jsonify({'message': 'Lead approved'})


@app.route('/api/leads/<int:lead_id>/deny', methods=['POST'])
def deny_lead(lead_id):
    data = request.json or {}
    db = get_db()

    db.execute('''UPDATE leads SET status = 'denied', reviewed_by = ?,
                  reviewed_at = datetime('now'), denial_reason = ?,
                  updated_at = datetime('now') WHERE id = ?''',
               (data.get('reviewed_by', 'Admin'), data.get('reason', ''), lead_id))
    db.execute('INSERT INTO activity_log (lead_id, action, details, performed_by) VALUES (?, ?, ?, ?)',
               (lead_id, 'denied', data.get('reason', 'No reason given'), data.get('reviewed_by', 'Admin')))
    db.commit()

    return jsonify({'message': 'Lead denied'})


# --- Analytics ---

@app.route('/api/analytics/summary', methods=['GET'])
def analytics_summary():
    db = get_db()
    period = request.args.get('period', 'all')

    date_filter = ''
    if period == '30d':
        date_filter = f"AND date >= date('now', '-30 days')"
    elif period == '90d':
        date_filter = f"AND date >= date('now', '-90 days')"
    elif period == '6m':
        date_filter = f"AND date >= date('now', '-6 months')"
    elif period == '1y':
        date_filter = f"AND date >= date('now', '-1 year')"

    stats = {}

    # Total leads
    row = db.execute(f"SELECT COUNT(*) as total FROM leads WHERE 1=1 {date_filter}").fetchone()
    stats['total_leads'] = row['total']

    # By status
    rows = db.execute(f"SELECT status, COUNT(*) as count FROM leads WHERE 1=1 {date_filter} GROUP BY status").fetchall()
    stats['by_status'] = {r['status']: r['count'] for r in rows}

    # Approval rate
    reviewed = stats['by_status'].get('approved', 0) + stats['by_status'].get('denied', 0)
    stats['approval_rate'] = round(stats['by_status'].get('approved', 0) / reviewed * 100, 1) if reviewed > 0 else 0

    # By region
    rows = db.execute(f"SELECT region, COUNT(*) as count FROM leads WHERE 1=1 {date_filter} GROUP BY region").fetchall()
    stats['by_region'] = {r['region'] or 'Unknown': r['count'] for r in rows}

    # Appointments completed
    row = db.execute(f"SELECT COUNT(*) as total FROM leads WHERE appointment_completed = 1 {date_filter}").fetchone()
    stats['appointments_completed'] = row['total']

    # Proposals sent
    row = db.execute(f"SELECT COUNT(*) as total FROM leads WHERE proposal = 1 {date_filter}").fetchone()
    stats['proposals_sent'] = row['total']

    # Won/Lost
    row = db.execute(f"SELECT COALESCE(SUM(won), 0) as won, COALESCE(SUM(lost), 0) as lost FROM leads WHERE 1=1 {date_filter}").fetchone()
    stats['won'] = row['won']
    stats['lost'] = row['lost']
    stats['win_rate'] = round(row['won'] / (row['won'] + row['lost']) * 100, 1) if (row['won'] + row['lost']) > 0 else 0

    # Revenue
    row = db.execute(f"SELECT COALESCE(SUM(revenue_sold), 0) as total_sold, COALESCE(SUM(revenue_monthly), 0) as total_monthly FROM leads WHERE 1=1 {date_filter}").fetchone()
    stats['revenue_sold'] = row['total_sold']
    stats['revenue_monthly'] = row['total_monthly']

    # Conversion funnel
    stats['funnel'] = {
        'leads': stats['total_leads'],
        'appointments': stats['appointments_completed'],
        'proposals': stats['proposals_sent'],
        'won': stats['won']
    }

    return jsonify(stats)


@app.route('/api/analytics/timeline', methods=['GET'])
def analytics_timeline():
    db = get_db()
    granularity = request.args.get('granularity', 'month')

    if granularity == 'week':
        date_fmt = "strftime('%Y-W%W', date)"
    elif granularity == 'month':
        date_fmt = "strftime('%Y-%m', date)"
    else:
        date_fmt = "strftime('%Y', date)"

    rows = db.execute(f'''
        SELECT {date_fmt} as period,
               COUNT(*) as leads,
               SUM(CASE WHEN appointment_completed = 1 THEN 1 ELSE 0 END) as appointments,
               SUM(CASE WHEN proposal = 1 THEN 1 ELSE 0 END) as proposals,
               SUM(CASE WHEN won = 1 THEN 1 ELSE 0 END) as won,
               SUM(CASE WHEN lost = 1 THEN 1 ELSE 0 END) as lost,
               SUM(COALESCE(revenue_sold, 0)) as revenue_sold,
               SUM(COALESCE(revenue_monthly, 0)) as revenue_monthly
        FROM leads WHERE date IS NOT NULL
        GROUP BY period ORDER BY period
    ''').fetchall()

    return jsonify([dict(r) for r in rows])


@app.route('/api/analytics/by_city', methods=['GET'])
def analytics_by_city():
    db = get_db()
    rows = db.execute('''
        SELECT city, COUNT(*) as leads,
               SUM(CASE WHEN appointment_completed = 1 THEN 1 ELSE 0 END) as appointments,
               SUM(CASE WHEN proposal = 1 THEN 1 ELSE 0 END) as proposals,
               SUM(CASE WHEN won = 1 THEN 1 ELSE 0 END) as won,
               SUM(CASE WHEN lost = 1 THEN 1 ELSE 0 END) as lost,
               SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved,
               SUM(CASE WHEN status = 'denied' THEN 1 ELSE 0 END) as denied
        FROM leads GROUP BY city ORDER BY leads DESC
    ''').fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/analytics/denial_reasons', methods=['GET'])
def denial_reasons():
    db = get_db()
    rows = db.execute('''
        SELECT denial_reason, COUNT(*) as count
        FROM leads WHERE status = 'denied' AND denial_reason IS NOT NULL AND denial_reason != ''
        GROUP BY denial_reason ORDER BY count DESC LIMIT 20
    ''').fetchall()
    return jsonify([dict(r) for r in rows])


# --- Activity Log ---

@app.route('/api/activity', methods=['GET'])
def get_activity():
    db = get_db()
    limit = int(request.args.get('limit', 50))
    rows = db.execute('''
        SELECT a.*, l.company FROM activity_log a
        LEFT JOIN leads l ON a.lead_id = l.id
        ORDER BY a.created_at DESC LIMIT ?
    ''', (limit,)).fetchall()
    return jsonify([dict(r) for r in rows])


# =============================================================================
# Initialize and run
# =============================================================================
with app.app_context():
    init_db()


if __name__ == '__main__':
    print("\n" + "="*60)
    print("  iTalk Lead Manager")
    print("  Open http://localhost:5000 in your browser")
    print("="*60 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
