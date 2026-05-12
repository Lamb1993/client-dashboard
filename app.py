import os
from io import TextIOWrapper
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

# Models - tables for SQLAlchemy metadata
class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    archived = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    data_points = db.relationship('ClientData', backref='client', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Client {self.id} {self.name}>"

class ClientData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    value = db.Column(db.Float, nullable=False)
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
# Routes
#####################################

# Dashboard - show active and archived clients
@app.route('/')
def index():
    active_clients = Client.query.filter_by(archived=False).all()
    archived_clients = Client.query.filter_by(archived=True).all()
    return render_template('dashboard.html', active_clients=active_clients, archived_clients=archived_clients)

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

# Add a new data point for a client (or update if date already exists)
@app.route('/add_data', methods=['POST'])
def add_data():
    try:
        client_id = int(request.form['client_id'])
        date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        value = float(request.form['value'])
    except Exception:
        return jsonify({'error': 'Invalid input'}), 400

    # Check for existing datapoint for this client/date
    existing = ClientData.query.filter_by(client_id=client_id, date=date).first()

    if existing: # Update instead of inserting a duplicate
        existing.value = value
        existing.created_at = datetime.utcnow()
        db.session.commit()

        return jsonify({'updated': True, 'id': existing.id, 'date': date.strftime('%Y-%m-%d'), 'value': value})

    # Otherwise create a new datapoint
    new_dp = ClientData(client_id=client_id, date=date, value=value)
    db.session.add(new_dp)
    db.session.commit()

    return jsonify({'updated': False, 'id': new_dp.id, 'date': date.strftime('%Y-%m-%d'), 'value': value})

# Get data points for a client (for charts)
@app.route('/get_data/<int:client_id>')
def get_data(client_id):
    client = Client.query.get_or_404(client_id)
    data_points = sorted(client.data_points, key=lambda x: x.date)
    dates = [dp.date.strftime('%Y-%m-%d') for dp in data_points]
    values = [dp.value for dp in data_points]
    return jsonify({'dates': dates, 'values': values})

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

# upload a CSV file with date/value pairs for a client
# date,value
# 2024-01-01,10
# 2024-01-02,12.5
# 2024-01-03,9
@app.route('/upload_csv/<int:client_id>', methods=['POST'])
def upload_csv(client_id):
    client = Client.query.get_or_404(client_id)

    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'Empty filename'}), 400

    # Wrap file for text reading
    try:
        stream = TextIOWrapper(file.stream, encoding='utf-8')
        reader = csv.DictReader(stream)
    except Exception:
        return jsonify({'error': 'Invalid CSV format'}), 400

    created = 0
    updated = 0
    errors = []

    for i, row in enumerate(reader, start=1):
        try:
            date = datetime.strptime(row['date'], '%Y-%m-%d').date()
            value = float(row['value'])
        except Exception:
            errors.append(f"Row {i}: invalid date/value")
            continue

        # Check for existing datapoint
        existing = ClientData.query.filter_by(client_id=client_id, date=date).first()

        if existing:
            existing.value = value
            existing.created_at = datetime.utcnow()
            updated += 1
        else:
            dp = ClientData(client_id=client_id, date=date, value=value)
            db.session.add(dp)
            created += 1

    db.session.commit()

    return jsonify({
        'success': True,
        'client_id': client_id,
        'created': created,
        'updated': updated,
        'errors': errors
    })

if __name__ == '__main__':
    app.run(debug=True)