"""
Import existing iTalk leads from the Excel spreadsheet into the SQLite database.
Run this once after setting up the app: python import_data.py
"""

import os
import sqlite3
from datetime import datetime
import openpyxl

EXCEL_FILE = os.environ.get('ITALK_EXCEL', 'ITALK_Lead_Overview.xlsx')
DB_FILE = os.environ.get('DB_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'leads.db'))


def determine_region(city):
    if not city:
        return 'Other'
    city_lower = city.lower().strip()
    columbus_areas = ['columbus', 'gahanna', 'westerville', 'new albany', 'dublin',
                      'hilliard', 'grove city', 'reynoldsburg', 'lancaster', 'pickerington',
                      'powell', 'worthington', 'upper arlington', 'grandview']
    cincinnati_areas = ['cincinnati', 'norwood', 'mason', 'west chester', 'fairfield',
                        'hamilton', 'middletown', 'loveland', 'milford', 'blue ash',
                        'sharonville', 'kenwood', 'hyde park']
    for area in columbus_areas:
        if area in city_lower:
            return 'Columbus'
    for area in cincinnati_areas:
        if area in city_lower:
            return 'Cincinnati'
    return 'Other'


def import_leads():
    if not os.path.exists(EXCEL_FILE):
        # Try looking in uploads folder
        alt_path = os.path.join(os.path.dirname(__file__), '..', '..', 'uploads', 'ITALK Lead Overview.xlsx')
        if os.path.exists(alt_path):
            excel_file = alt_path
        else:
            print(f"Excel file not found: {EXCEL_FILE}")
            print("Set ITALK_EXCEL environment variable to the path of your spreadsheet.")
            return
    else:
        excel_file = EXCEL_FILE

    wb = openpyxl.load_workbook(excel_file, data_only=True)
    ws = wb['Sheet1']

    # Initialize database
    db = sqlite3.connect(DB_FILE)
    db.execute("PRAGMA journal_mode=WAL")

    # Create tables if they don't exist
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

    imported = 0
    skipped = 0

    for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        # Columns: Date, Company, Address, Contact, Email, Phone, City, Sys4,
        #          Appointment Completed, Proposal, RS$, RM$, Won, Lost, Notes
        date_val, company, address, contact, email, phone, city, sys4, \
            appt_completed, proposal, rev_sold, rev_monthly, won, lost, notes = (
                list(row) + [None] * 15)[:15]

        if not company:
            skipped += 1
            continue

        # Format date
        if isinstance(date_val, datetime):
            date_str = date_val.strftime('%Y-%m-%d')
        elif date_val:
            date_str = str(date_val)
        else:
            date_str = None

        # Determine region
        region = determine_region(city)

        # Parse boolean/numeric fields
        appt = 1 if appt_completed and str(appt_completed).strip().lower() in ('yes', 'y', '1', 'true', 'x', 'â') else 0
        prop = 1 if proposal and str(proposal).strip().lower() in ('yes', 'y', '1', 'true', 'x', 'â') else 0
        w = 1 if won and str(won).strip().lower() in ('yes', 'y', '1', 'true', 'x', 'â') else 0
        l = 1 if lost and str(lost).strip().lower() in ('yes', 'y', '1', 'true', 'x', 'â') else 0

        # Parse revenue
        rs = 0
        rm = 0
        try:
            if rev_sold:
                rs = float(str(rev_sold).replace('$', '').replace(',', ''))
        except:
            pass
        try:
            if rev_monthly:
                rm = float(str(rev_monthly).replace('$', '').replace(',', ''))
        except:
            pass

        db.execute('''
            INSERT INTO leads (date, company, address, contact, email, phone, city, region,
                              sys4, appointment_completed, proposal, revenue_sold,
                              revenue_monthly, won, lost, notes, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        ''', (date_str, str(company).strip(), str(address or '').strip(),
              str(contact or '').strip(), str(email or '').strip(),
              str(phone or '').strip(), str(city or '').strip(), region,
              str(sys4 or '').strip(), appt, prop, rs, rm, w, l,
              str(notes or '').strip()))

        imported += 1

    db.commit()

    # Add import activity log
    db.execute('''INSERT INTO activity_log (action, details)
                  VALUES (?, ?)''',
               ('import', f'Imported {imported} leads from Excel spreadsheet'))
    db.commit()
    db.close()

    print(f"\nImport complete!")
    print(f"  Imported: {imported} leads")
    print(f"  Skipped:  {skipped} empty rows")
    print(f"  Database: {DB_FILE}")


if __name__ == '__main__':
    import_leads()
