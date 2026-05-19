import os
import io
import csv
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import Index, UniqueConstraint

basedir = os.path.abspath(os.path.dirname(__file__))
    
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'dashboard.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

#####################################
# Database Models (Tables)
#####################################

# Models - tables for SQLAlchemy metadata
class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    archived = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # data_points = db.relationship('ClientData', backref='client', lazy=True, cascade="all, delete-orphan")
    program_lists = db.relationship('ProgramList', backref='client', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Client {self.id} {self.name}>"

class ProgramList(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)

    programs = db.relationship('Program', backref='program_list', cascade="all, delete-orphan")

class Program(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    program_list_id = db.Column(db.Integer, db.ForeignKey('program_list.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)

    targets = db.relationship('Target', backref='program', lazy=True, cascade="all, delete-orphan")

class Target(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('program.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)

    data_points = db.relationship('DataPoint', backref='target', lazy=True, cascade="all, delete-orphan")

class DataPoint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    target_id = db.Column(db.Integer, db.ForeignKey('target.id'), nullable=False)

    date = db.Column(db.Date, nullable=False)
    value = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)
  
class ClientData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    value = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False, default=1.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Prevent duplicate entries for the same client/date
    __table_args__ = (
        UniqueConstraint('client_id', 'date', name='uq_client_date'),
        Index('idx_client_date', 'client_id', 'date'),
    )

    def __repr__(self):
        return f"<DataPoint client={self.client_id} date={self.date} value={self.value}>"

with app.app_context():
    db.create_all()
    
#####################################
# Dashboard Routes
#####################################

# Dashboard - show active and archived clients
@app.route('/')
def index():
    active_clients = Client.query.filter_by(archived=False).all()
    archived_clients = Client.query.filter_by(archived=True).all()
    return render_template('dashboard.html', active_clients=active_clients, archived_clients=archived_clients)

# Archive a client
@app.route('/archive_client/<int:client_id>', methods=['POST'])
def archive_client(client_id):
    client = Client.query.get_or_404(client_id)
    client.archived = True
    db.session.commit()
    return jsonify({'success': True})

# Unarchive a client
@app.route('/unarchive_client/<int:client_id>', methods=['POST'])
def unarchive_client(client_id):
    client = Client.query.get_or_404(client_id)
    client.archived = False
    db.session.commit()
    return jsonify({'success': True})

# Delete a client and all its data points
@app.route('/delete_client/<int:client_id>', methods=['POST'])
def delete_client(client_id):
    client = Client.query.get_or_404(client_id)
    # Optional: delete all related data points first
    ClientData.query.filter_by(client_id=client.id).delete()
    db.session.delete(client)
    db.session.commit()
    return jsonify({'success': True})

# Add a new client
@app.route('/add_client', methods=['POST'])
def add_client():
    name = request.form['name']
    if name:
        client = Client(name=name)
        db.session.add(client)
        db.session.commit()
        return jsonify({'id': client.id, 'name': client.name})
    return jsonify({'error': 'Name required'}), 400


#####################################
# Client Page Routes
#####################################

# Client Page - render a new template for a single client
@app.route('/client/<int:client_id>')
def client_page(client_id):
    client = Client.query.get_or_404(client_id)
    return render_template('client_page.html', client=client)

# Add a new data point for a client (or update if date already exists)
@app.route('/add_data', methods=['POST'])
def add_data():
    try:
        client_id = int(request.form['client_id'])
        date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        value = float(request.form['value'])
        total = float(request.form['total'])
    except Exception:
        return jsonify({'error': 'Invalid input'}), 400

    # Check for existing datapoint for this client/date
    existing = ClientData.query.filter_by(client_id=client_id, date=date).first()

    if existing: # Update instead of inserting a duplicate
        existing.value = value
        existing.total = total
        existing.created_at = datetime.utcnow()
        db.session.commit()

        return jsonify({'updated': True, 'id': existing.id, 'date': date.strftime('%Y-%m-%d'), 'value': value})

    # Otherwise create a new datapoint
    new_dp = ClientData(client_id=client_id, date=date, value=value, total=total)
    db.session.add(new_dp)
    db.session.commit()

    return jsonify({'updated': False, 'id': new_dp.id, 'date': date.strftime('%Y-%m-%d'), 'value': value})

# Get data points for a client (for charts)
@app.route('/get_data/<int:client_id>')
def get_data(client_id):
    client = Client.query.get_or_404(client_id)
    data_points = sorted(client.data_points, key=lambda x: x.date)

    dates = [dp.date.strftime('%Y-%m-%d') for dp in data_points]
    percentages = [(dp.value / dp.total) * 100 for dp in data_points]

    return jsonify({'dates': dates, 'values': percentages})

# upload a CSV file with date/value pairs for a client
# date,value,total
# 2024-01-01,3,6
# 2024-01-02,5,10
# 2024-01-03,2,4
@app.route('/upload_target_csv/<int:target_id>', methods=['POST'])
def upload_target_csv(target_id):
    if 'csv_file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['csv_file']
    created = 0
    updated = 0

    for raw_line in file.stream.read().decode('utf-8').splitlines():
        line = raw_line.strip()

        if not line:
            continue

        # Skip header row
        if line.lower().startswith("date"):
            continue

        try:
            date_str, value_str, total_str = [x.strip() for x in line.split(',')]
        except ValueError:
            continue

        # Convert date → Python date object
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        # Convert numbers
        try:
            value = float(value_str)
            total = float(total_str)
        except ValueError:
            continue

        # Insert/update
        dp = DataPoint.query.filter_by(target_id=target_id, date=date_obj).first()
        if dp:
            dp.value = value
            dp.total = total
            updated += 1
        else:
            dp = DataPoint(
                target_id=target_id,
                date=date_obj,
                value=value,
                total=total
            )
            db.session.add(dp)
            created += 1

    db.session.commit()
    return jsonify({'created': created, 'updated': updated})


#####################################
# Program List Routes
#####################################

@app.route('/add_program_list', methods=['POST'])
def add_program_list():
    client_id = request.form.get('client_id')
    name = request.form.get('name')

    if not name:
        return jsonify({'error': 'Name required'}), 400

    pl = ProgramList(client_id=client_id, name=name)
    db.session.add(pl)
    db.session.commit()

    return jsonify({'id': pl.id, 'name': pl.name})

@app.route('/get_program_lists/<int:client_id>')
def get_program_lists(client_id):
    lists = ProgramList.query.filter_by(client_id=client_id).all()
    return jsonify([{'id': pl.id, 'name': pl.name} for pl in lists])

@app.route('/delete_program_list/<int:pl_id>', methods=['POST'])
def delete_program_list(pl_id):
    pl = ProgramList.query.get_or_404(pl_id)
    db.session.delete(pl)
    db.session.commit()
    return jsonify({'success': True})


#####################################
# Program Routes
#####################################

@app.route('/add_program', methods=['POST'])
def add_program():
    pl_id = request.form.get('program_list_id')
    name = request.form.get('name')

    if not name:
        return jsonify({'error': 'Name required'}), 400

    program = Program(program_list_id=pl_id, name=name)
    db.session.add(program)
    db.session.commit()

    return jsonify({'id': program.id, 'name': program.name})

@app.route('/get_programs/<int:pl_id>')
def get_programs(pl_id):
    programs = Program.query.filter_by(program_list_id=pl_id).all()
    return jsonify([{'id': p.id, 'name': p.name} for p in programs])

@app.route('/delete_program/<int:program_id>', methods=['POST'])
def delete_program(program_id):
    program = Program.query.get_or_404(program_id)
    db.session.delete(program)
    db.session.commit()
    return jsonify({'success': True})


#####################################
# Targets Routes
#####################################

@app.route('/add_target', methods=['POST'])
def add_target():
    program_id = request.form.get('program_id')
    name = request.form.get('name')

    if not name:
        return jsonify({'error': 'Name required'}), 400

    t = Target(program_id=program_id, name=name)
    db.session.add(t)
    db.session.commit()

    return jsonify({'id': t.id, 'name': t.name})

@app.route('/get_targets/<int:program_id>')
def get_targets(program_id):
    targets = Target.query.filter_by(program_id=program_id).all()
    return jsonify([{'id': t.id, 'name': t.name} for t in targets])

@app.route('/delete_target/<int:target_id>', methods=['POST'])
def delete_target(target_id):
    t = Target.query.get_or_404(target_id)
    db.session.delete(t)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/get_target_data', methods=['POST'])
def get_target_data():
    target_ids = request.json.get('target_ids', [])

    result = {}

    for tid in target_ids:
        t = Target.query.get(tid)
        if not t:
            continue

        points = DataPoint.query.filter_by(target_id=tid).order_by(DataPoint.date).all()

        result[tid] = {
            'name': t.name,
            'dates': [p.date.strftime('%Y-%m-%d') for p in points],
            'values': [p.value for p in points],
            'totals': [p.total for p in points],
            'percentages': [(p.value / p.total * 100) if p.total else 0 for p in points]
        }

    return jsonify(result)


#####################################
# Datapoints Routes
#####################################
@app.route('/add_or_update_datapoint', methods=['POST']) # type: ignore
def add_or_update_datapoint():
    try:
        target_id = int(request.form.get('target_id')) # type: ignore
        date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date() # type: ignore
        value = float(request.form.get('value')) # type: ignore
        total = float(request.form.get('total')) # type: ignore
    except Exception:
        return jsonify({'error': 'Invalid input'}), 400

    # Did the user confirm an update?
    confirm = request.form.get('confirm', 'false').lower() == 'true'

    existing = DataPoint.query.filter_by(target_id=target_id, date=date).first()

    # CASE 1 - Datapoint exists but user has NOT confirmed yet
    if existing and not confirm:
        return jsonify({
            'needs_confirmation': True,
            'old_value': existing.value,
            'old_total': existing.total
        })

    # CASE 2 - Datapoint exists AND user confirmed - perform update
    if existing and confirm:
        existing.value = value
        existing.total = total
        db.session.commit()
        return jsonify({'updated': True})

    # CASE 3 - No datapoint exists - create new
    if not existing:
        dp = DataPoint(target_id=target_id, date=date, value=value, total=total)
        db.session.add(dp)
        db.session.commit()
        return jsonify({'created': True})

@app.route('/get_datapoints/<int:target_id>')
def get_datapoints(target_id):
    points = DataPoint.query.filter_by(target_id=target_id).order_by(DataPoint.date).all()
    return jsonify([
        {
            'id': p.id,
            'date': p.date.strftime('%Y-%m-%d'),
            'value': p.value,
            'total': p.total
        }
        for p in points
    ])

@app.route('/delete_datapoint/<int:dp_id>', methods=['POST'])
def delete_datapoint(dp_id):
    dp = DataPoint.query.get_or_404(dp_id)
    db.session.delete(dp)
    db.session.commit()
    return jsonify({'success': True})


if __name__ == '__main__':
    app.run(debug=True)