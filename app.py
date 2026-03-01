import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Restaurant, MenuItem, Order, OrderItem, BackupLog

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///restaurant.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Создание таблиц при первом запуске
with app.app_context():
    db.create_all()
    # Создаем тестового админа если нет пользователей
    if not User.query.first():
        admin = User(
            username='admin',
            email='admin@restaurant.com',
            password_hash=generate_password_hash('admin123'),
            role='admin'
        )
        db.session.add(admin)
        db.session.commit()


@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Неверное имя пользователя или пароль')
    return render_template('login.html')  # ← ИСПРАВЛЕНО: было restaurants.html


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        # Проверяем существование пользователя
        if User.query.filter_by(username=username).first():
            flash('Имя пользователя уже занято')
            return redirect(url_for('register'))

        # Создаем нового пользователя
        hashed_password = generate_password_hash(password)
        new_user = User(
            username=username,
            email=email,
            password_hash=hashed_password,
            role='staff'
        )
        db.session.add(new_user)
        db.session.commit()

        flash('Регистрация успешна! Войдите в систему.')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/dashboard')
@login_required
def dashboard():
    # Статистика для дашборда
    restaurants_count = Restaurant.query.count()
    users_count = User.query.count()
    menu_count = MenuItem.query.count()
    orders_today = Order.query.filter(
        db.func.date(Order.created_at) == datetime.today().date()
    ).count()

    # Добавим отладочный вывод
    print(f"DEBUG: restaurants={restaurants_count}, users={users_count}, menu={menu_count}, orders={orders_today}")

    return render_template('dashboard.html',
                           restaurants_count=restaurants_count,
                           users_count=users_count,
                           menu_count=menu_count,
                           orders_today=orders_today)


@app.route('/admin')
@login_required
def admin_panel():
    if current_user.role != 'admin':
        flash('Доступ запрещен')
        return redirect(url_for('dashboard'))

    # Получаем данные для админ-панели
    restaurants = Restaurant.query.all()
    users = User.query.all()
    menu_items = MenuItem.query.all()

    # Статистика
    total_revenue = db.session.query(db.func.sum(Order.total_amount)).scalar() or 0
    total_orders = Order.query.count()

    return render_template('admin_panel.html',
                           restaurants=restaurants,
                           users=users,
                           menu_items=menu_items,
                           total_revenue=total_revenue,
                           total_orders=total_orders)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)