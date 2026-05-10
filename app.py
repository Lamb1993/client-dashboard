import os
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

basedir = os.path.abspath(os.path.dirname(__file__))
    
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'dashboard.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Models
class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    data_points = db.relationship('DataPoint', backref='client', lazy=True)

class DataPoint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    value = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# Routes
@app.route('/')
def index():
    clients = Client.query.all()
    return render_template('dashboard.html', clients=clients)

@app.route('/add_client', methods=['POST'])
def add_client():
    name = request.form['name']
    if name:
        client = Client(name=name)
        db.session.add(client)
        db.session.commit()
        return jsonify({'id': client.id, 'name': client.name})
    return jsonify({'error': 'Name required'}), 400

@app.route('/add_data', methods=['POST'])
def add_data():
    client_id = int(request.form['client_id'])
    date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    value = float(request.form['value'])
    data_point = DataPoint(client_id=client_id, date=date, value=value)
    db.session.add(data_point)
    db.session.commit()
    return jsonify({'id': data_point.id, 'date': date.strftime('%Y-%m-%d'), 'value': value})

@app.route('/get_data/<int:client_id>')
def get_data(client_id):
    client = Client.query.get_or_404(client_id)
    data_points = sorted(client.data_points, key=lambda x: x.date)
    dates = [dp.date.strftime('%Y-%m-%d') for dp in data_points]
    values = [dp.value for dp in data_points]
    return jsonify({'dates': dates, 'values': values})

# ----------------------------
# Delete a client and all its data
# ----------------------------
@app.route('/delete_client/<int:client_id>', methods=['POST'])
def delete_client(client_id):
    client = Client.query.get_or_404(client_id)
    # Optional: delete all related data points first
    DataPoint.query.filter_by(client_id=client.id).delete()
    db.session.delete(client)
    db.session.commit()
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True)