from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-me'  # change in production

# ------------------ MySQL DATABASE CONFIG ------------------
# Make sure this DB exists: CREATE DATABASE event_scheduler;
# Edit username, password, host, and db name as needed.
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:dharun%402004@127.0.0.1:3307/event_scheduler'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# ------------------ MODELS ------------------

class Event(db.Model):
    __tablename__ = 'events'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    description = db.Column(db.Text)

    allocations = db.relationship(
        'EventResourceAllocation',
        back_populates='event',
        cascade='all, delete-orphan'
    )


class Resource(db.Model):
    __tablename__ = 'resources'
    id = db.Column(db.Integer, primary_key=True)
    resource_name = db.Column(db.String(200), nullable=False)
    resource_type = db.Column(db.String(50), nullable=False)  # room, instructor, equipment, etc.

    allocations = db.relationship(
        'EventResourceAllocation',
        back_populates='resource',
        cascade='all, delete-orphan'
    )


class EventResourceAllocation(db.Model):
    __tablename__ = 'event_resource_allocations'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    resource_id = db.Column(db.Integer, db.ForeignKey('resources.id'), nullable=False)

    event = db.relationship('Event', back_populates='allocations')
    resource = db.relationship('Resource', back_populates='allocations')

    __table_args__ = (
        db.UniqueConstraint('event_id', 'resource_id', name='uq_event_resource'),
    )


with app.app_context():
    db.create_all()


# ------------------ HELPERS ------------------

def parse_datetime(value: str) -> datetime:
    """
    Parse datetime from <input type="datetime-local"> format: YYYY-MM-DDTHH:MM
    """
    return datetime.strptime(value, "%Y-%m-%dT%H:%M")


def interval_overlap_hours(start, end, range_start, range_end) -> float:
    """
    Compute overlap in hours between [start, end) and [range_start, range_end)
    """
    latest_start = max(start, range_start)
    earliest_end = min(end, range_end)
    if latest_start >= earliest_end:
        return 0.0
    return (earliest_end - latest_start).total_seconds() / 3600.0


def find_conflicts(start_time, end_time, resource_ids, current_event_id=None):
    """
    Returns a list of dicts: { 'conflicting_event': Event, 'resource': Resource }
    Detects any event using the same resource with overlapping time:
      existing.start < new.end AND existing.end > new.start
    """
    conflicts = []

    for rid in resource_ids:
        q = (
            db.session.query(Event)
            .join(EventResourceAllocation)
            .filter(EventResourceAllocation.resource_id == rid)
        )

        if current_event_id is not None:
            q = q.filter(Event.id != current_event_id)

        overlapping_events = q.filter(
            Event.start_time < end_time,
            Event.end_time > start_time
        ).all()

        resource = Resource.query.get(rid)
        for ev in overlapping_events:
            conflicts.append({
                'conflicting_event': ev,
                'resource': resource
            })

    return conflicts


def find_all_conflicts():
    """
    For the /conflicts view: scan all resources and find pairwise overlapping events.
    Returns list of dicts:
      { 'resource': Resource, 'event_a': Event, 'event_b': Event }
    """
    results = []
    resources = Resource.query.all()
    for r in resources:
        events = sorted(
            [alloc.event for alloc in r.allocations],
            key=lambda e: e.start_time
        )
        n = len(events)
        for i in range(n):
            for j in range(i + 1, n):
                e1, e2 = events[i], events[j]
                if e1.start_time < e2.end_time and e2.start_time < e1.end_time:
                    results.append({
                        'resource': r,
                        'event_a': e1,
                        'event_b': e2
                    })
    return results


# ------------------ ROUTES: HOME ------------------

@app.route('/')
def index():
    return redirect(url_for('list_events'))


# ------------------ ROUTES: EVENTS ------------------

@app.route('/events')
def list_events():
    events = Event.query.order_by(Event.start_time).all()
    return render_template('events.html', events=events)


@app.route('/events/new', methods=['GET', 'POST'])
def create_event():
    resources = Resource.query.all()
    selected_ids = []

    if request.method == 'POST':
        title = request.form['title'].strip()
        description = request.form.get('description') or ""
        start_raw = request.form['start_time']
        end_raw = request.form['end_time']

        try:
            start_time = parse_datetime(start_raw)
            end_time = parse_datetime(end_raw)
        except ValueError:
            flash("Invalid date/time format.", "danger")
            dummy = type('DummyEvent', (), {})()
            dummy.title = title
            dummy.description = description
            dummy.start_time = datetime.now()
            dummy.end_time = datetime.now()
            return render_template(
                'event_form.html',
                event=dummy,
                resources=resources,
                selected_ids=[],
                conflicts=[]
            )

        if start_time >= end_time:
            flash("Start time must be earlier than end time (start != end).", "danger")
            dummy = type('DummyEvent', (), {})()
            dummy.title = title
            dummy.description = description
            dummy.start_time = start_time
            dummy.end_time = end_time
            selected_ids = [int(r) for r in request.form.getlist('resources')]
            return render_template(
                'event_form.html',
                event=dummy,
                resources=resources,
                selected_ids=selected_ids,
                conflicts=[]
            )

        selected_ids = [int(r) for r in request.form.getlist('resources')]

        conflicts = find_conflicts(start_time, end_time, selected_ids, current_event_id=None)
        if conflicts:
            flash("Resource conflict detected. Please resolve the conflicts below.", "danger")
            dummy = type('DummyEvent', (), {})()
            dummy.title = title
            dummy.description = description
            dummy.start_time = start_time
            dummy.end_time = end_time
            return render_template(
                'event_form.html',
                event=dummy,
                resources=resources,
                selected_ids=selected_ids,
                conflicts=conflicts
            )

        # No conflicts -> save event
        event = Event(
            title=title,
            description=description,
            start_time=start_time,
            end_time=end_time
        )
        db.session.add(event)
        db.session.flush()  # so event.id is available

        for rid in selected_ids:
            db.session.add(EventResourceAllocation(event_id=event.id, resource_id=rid))

        db.session.commit()
        flash('Event created successfully.', 'success')
        return redirect(url_for('list_events'))

    # GET
    dummy = type('DummyEvent', (), {})()
    dummy.title = ""
    dummy.description = ""
    dummy.start_time = datetime.now()
    dummy.end_time = datetime.now()
    return render_template(
        'event_form.html',
        event=dummy,
        resources=resources,
        selected_ids=selected_ids,
        conflicts=[]
    )


@app.route('/events/<int:event_id>/edit', methods=['GET', 'POST'])
def edit_event(event_id):
    event = Event.query.get_or_404(event_id)
    resources = Resource.query.all()
    selected_ids = [a.resource_id for a in event.allocations]

    if request.method == 'POST':
        title = request.form['title'].strip()
        description = request.form.get('description') or ""
        start_raw = request.form['start_time']
        end_raw = request.form['end_time']

        try:
            start_time = parse_datetime(start_raw)
            end_time = parse_datetime(end_raw)
        except ValueError:
            flash("Invalid date/time format.", "danger")
            return render_template(
                'event_form.html',
                event=event,
                resources=resources,
                selected_ids=selected_ids,
                conflicts=[]
            )

        if start_time >= end_time:
            flash("Start time must be earlier than end time (start != end).", "danger")
            # Update in-memory so form is prefilled
            event.title = title
            event.description = description
            event.start_time = start_time
            event.end_time = end_time
            selected_ids = [int(r) for r in request.form.getlist('resources')]
            return render_template(
                'event_form.html',
                event=event,
                resources=resources,
                selected_ids=selected_ids,
                conflicts=[]
            )

        selected_ids = [int(r) for r in request.form.getlist('resources')]

        conflicts = find_conflicts(start_time, end_time, selected_ids, current_event_id=event.id)
        if conflicts:
            flash("Resource conflict detected. Please resolve the conflicts below.", "danger")
            event.title = title
            event.description = description
            event.start_time = start_time
            event.end_time = end_time
            return render_template(
                'event_form.html',
                event=event,
                resources=resources,
                selected_ids=selected_ids,
                conflicts=conflicts
            )

        # No conflicts -> update event & allocations
        event.title = title
        event.description = description
        event.start_time = start_time
        event.end_time = end_time

        event.allocations.clear()
        db.session.flush()
        for rid in selected_ids:
            db.session.add(EventResourceAllocation(event_id=event.id, resource_id=rid))

        db.session.commit()
        flash('Event updated successfully.', 'success')
        return redirect(url_for('list_events'))

    # GET
    return render_template(
        'event_form.html',
        event=event,
        resources=resources,
        selected_ids=selected_ids,
        conflicts=[]
    )


@app.route('/events/<int:event_id>/delete', methods=['POST'])
def delete_event(event_id):
    event = Event.query.get_or_404(event_id)
    db.session.delete(event)
    db.session.commit()
    flash('Event deleted.', 'success')
    return redirect(url_for('list_events'))


# ------------------ ROUTES: RESOURCES ------------------

@app.route('/resources')
def list_resources():
    resources = Resource.query.all()
    return render_template('resources.html', resources=resources)


@app.route('/resources/new', methods=['GET', 'POST'])
def create_resource():
    if request.method == 'POST':
        name = request.form['resource_name'].strip()
        rtype = request.form['resource_type'].strip()
        if not name or not rtype:
            flash("Name and type are required.", "danger")
            return render_template('resource_form.html', resource=None)

        res = Resource(resource_name=name, resource_type=rtype)
        db.session.add(res)
        db.session.commit()
        flash('Resource created.', 'success')
        return redirect(url_for('list_resources'))

    return render_template('resource_form.html', resource=None)


@app.route('/resources/<int:resource_id>/edit', methods=['GET', 'POST'])
def edit_resource(resource_id):
    res = Resource.query.get_or_404(resource_id)
    if request.method == 'POST':
        name = request.form['resource_name'].strip()
        rtype = request.form['resource_type'].strip()
        if not name or not rtype:
            flash("Name and type are required.", "danger")
            return render_template('resource_form.html', resource=res)

        res.resource_name = name
        res.resource_type = rtype
        db.session.commit()
        flash('Resource updated.', 'success')
        return redirect(url_for('list_resources'))

    return render_template('resource_form.html', resource=res)


@app.route('/resources/<int:resource_id>/delete', methods=['POST'])
def delete_resource(resource_id):
    res = Resource.query.get_or_404(resource_id)
    db.session.delete(res)
    db.session.commit()
    flash('Resource deleted.', 'success')
    return redirect(url_for('list_resources'))


# ------------------ ROUTE: CONFLICT DETECTION VIEW ------------------

@app.route('/conflicts')
def conflict_overview():
    conflicts = find_all_conflicts()
    return render_template('conflicts.html', conflicts=conflicts)


# ------------------ ROUTE: UTILISATION REPORT ------------------

@app.route('/report', methods=['GET', 'POST'])
def utilisation_report():
    results = []
    range_start = None
    range_end = None

    if request.method == 'POST':
        start_raw = request.form['range_start']
        end_raw = request.form['range_end']

        try:
            range_start = parse_datetime(start_raw)
            range_end = parse_datetime(end_raw)
        except ValueError:
            flash("Invalid report date/time format.", "danger")
            return render_template('report.html', results=results, range_start=None, range_end=None)

        if range_start >= range_end:
            flash("Report start must be earlier than report end.", "danger")
            return render_template('report.html', results=results, range_start=range_start, range_end=range_end)

        resources = Resource.query.all()
        now = datetime.now()
        for r in resources:
            total_hours = 0.0
            upcoming = []
            for alloc in r.allocations:
                ev = alloc.event
                total_hours += interval_overlap_hours(ev.start_time, ev.end_time, range_start, range_end)
                if ev.start_time >= now:
                    upcoming.append(ev)

            upcoming_sorted = sorted(upcoming, key=lambda e: e.start_time)
            results.append({
                'resource': r,
                'total_hours': round(total_hours, 2),
                'upcoming': upcoming_sorted
            })

    return render_template('report.html', results=results, range_start=range_start, range_end=range_end)


# ------------------ MAIN ------------------

if __name__ == '__main__':
    app.run(debug=True)
