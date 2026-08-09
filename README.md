# Community Riggers

Community Riggers is a web application for tracking the availability of IATSE stage riggers working in the San Francisco Bay Area. 

## The Problem

Stage riggers in the Bay Area often work across multiple IATSE locals. The systems used to book technicians, such as CallSteward and Local 16's internal system, sometimes leave gaps in availability tracking. During busy periods, it becomes difficult for call stewards and business agents to know where people are on a given day. Calls get cancelled, added, people get injured, call out sick, or find replacements. Keeping availability updated across multiple systems is a burden on workers who are already putting in long, non-standard hours. It is sometimes hard enough to get employees to update their availability with one local, let alone many.

## The Solution

Community Riggers provides a voluntary, opt-in availability system where riggers can self-report their availability for the next 5 days. The most common use case would be for call stewards to be able to fill a last-minute call or respond to a drastic change in a labor order.  The system is designed to be frictionless. Riggers receive a personal bookmarked link and can toggle their availability with a single tap. There is no login process required. Call stewards and business agents log in via a secure admin interface to see who is available and contact them directly.

## Features

- Rigger self-registration with admin approval queue
- Token-based personal availability links with no login required for riggers
- 5-day availability toggle
- Admin availability view with date filtering and last-updated timestamps
- Full rigger directory with one-tap call and text contact links
- Rigger self-service profile editing
- Phone number normalization and formatting
- Bootstrap dark theme responsive design, mobile first

## Proposed/Upcoming Features

- Twilio text messaging integration

## Tech Stack

- **Backend:** Python, Flask
- **Database:** SQLite
- **Authentication:** Auth0 (admin only, via OIDC/OAuth2 using Authlib)
- **Frontend:** Jinja2 templating, Bootstrap 5
- **Hosting:** PythonAnywhere
- **DNS/CDN:** Cloudflare

## Setup

### Prerequisites

- Python 3.13+
- An Auth0 account with a Regular Web Application configured

### Installation

```bash
git clone https://github.com/dkmkelley/community-riggers.git
cd community-riggers
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Configuration

Copy `.env.example` to `.env` and fill in your Auth0 credentials:

```bash
cp .env.example .env
```

### Database Initialization

```bash
python database.py
```

### Running Locally

```bash
python app.py
```

The app will be available at `http://localhost:5000`.

## Live Demo

[communityriggers.org](https://communityriggers.org)