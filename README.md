# iTalk Lead Manager

A lead generation capture and analytics platform for managing appointments booked by iTalk, your outsourced appointment setting firm.

## Features

- **Lead Entry**: Add new leads with company, contact, address, and appointment details
- **Approval Workflow**: Review queue to approve or deny leads with denial reasons
- **Analytics Dashboard**: Conversion funnels, volume trends, city breakdowns, win/loss rates, and revenue tracking
- **Search & Filter**: Find leads by status, region, or keyword

## Quick Start

```bash
pip install -r requirements.txt
python import_data.py
python app.py
# Open http://localhost:5000
```

## Project Structure

```
italk-lead-manager/
├── app.py              # Flask backend (API + server)
├── import_data.py      # Excel data import script
├── requirements.txt    # Python dependencies
├── leads.db            # SQLite database (auto-created)
├── templates/
│   └── index.html      # React frontend (single-page app)
└── README.md
```
