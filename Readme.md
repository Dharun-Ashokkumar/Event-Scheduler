# Event Scheduling & Resource Allocation System

A small Flask + MySQL web application to schedule events (workshops, seminars, classes) and allocate shared resources (rooms, instructors, equipment). The system prevents double-booking of resources, detects time conflicts, and provides a resource utilisation report.

## Features

- Add / Edit / View **Events**
- Add / Edit / View **Resources**
- Allocate multiple resources to a single event
- **Conflict detection**:
  - No resource is double-booked
  - Time overlaps correctly handled
  - Edge cases: `start >= end`, nested intervals, partial overlaps
- **Resource Utilisation Report**:
  - User selects a date-time range
  - For each resource:
    - Total hours utilised in that range
    - List of upcoming bookings
- Global **Conflict Detection View** showing all current overlaps between events and resources

## Tech Stack

- Python 3.x
- Flask
- Flask-SQLAlchemy
- MySQL (with PyMySQL driver)
- HTML + Bootstrap 5

## Setup Instructions

### 1. Clone the repository

```bash
git clone https://github.com/your-username/event-scheduler.git
cd event-scheduler


VIDEO PRESENTATION:
https://drive.google.com/file/d/1uwAS9q52ul8L0-Xk_oRarL4Dss29lfbX/view?usp=drive_link