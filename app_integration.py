import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, g
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash


from models_orm import db, User, Restaurant, MenuItem, Order, OrderItem, Session as DbSession, AuditLog


from db_manager import DatabaseManager
from auth_manager import AuthManager, login_required, admin_required, permission_required, api_auth_required


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'


DB_USERNAME = 'root'
DB_PASSWORD = ''
DB_HOST = 'localhost'
DB_PORT = '3306'
DB_NAME = 'restaurant_db'


app.config[
    'SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 10,
    'pool_recycle': 3600,
    'pool_pre_ping': True,
}


db.init_app(app)


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = '🔐 Пожалуйста, войдите в систему'
login_manager.login_message_category = 'info'


auth_manager = AuthManager(app, db)
db_manager = DatabaseManager(host=DB_HOST, user=DB_USERNAME, password=DB_PASSWORD, database=DB_NAME)




@login_manager.user_loader
def load_user(user_id):

    return User.query.get(int(user_id))




@app.context_processor
def utility_processor():

    return {
        'now': datetime.now,
        'has_permission': lambda p: current_user.is_authenticated and current_user.has_permission(p),
        'has_role': lambda r: current_user.is_authenticated and current_user.role == r,
        'app_version': '2.0.3'
    }


@app.before_request
def before_request():

    if auth_manager.is_ip_blocked(request.remote_addr):
        return render_template('blocked.html'), 403


    if current_user.is_authenticated:

        if not current_user.is_active:
            logout_user()
            flash('Аккаунт деактивирован', 'warning')
            return redirect(url_for('login'))


        if current_user.is_locked():
            logout_user()
            flash('Аккаунт заблокирован', 'danger')
            return redirect(url_for('login'))


@app.after_request
def after_request(response):

    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'

    return response




@app.route('/login', methods=['GET', 'POST'])
def login():

    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False


        user, session_token = auth_manager.authenticate(
            username=username,
            password=password,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )

        if user:
            login_user(user, remember=remember)
            session['session_token'] = session_token


            AuditLog.log(
                user_id=user.id,
                action='LOGIN',
                ip_address=request.remote_addr
            )

            flash(f'👋 Добро пожаловать, {user.username}!', 'success')

            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('dashboard'))
        else:
            flash('❌ Неверное имя пользователя или пароль', 'danger')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():

    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm = request.form.get('confirm')


        if not username or not email or not password:
            flash('⚠️ Все поля обязательны', 'warning')
            return redirect(url_for('register'))

        if password != confirm:
            flash('❌ Пароли не совпадают', 'danger')
            return redirect(url_for('register'))


        is_valid, errors = auth_manager.validate_password_strength(password)
        if not is_valid:
            for error in errors:
                flash(f'❌ {error}', 'danger')
            return redirect(url_for('register'))


        if User.query.filter_by(username=username).first():
            flash('❌ Имя пользователя уже занято', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('❌ Email уже зарегистрирован', 'danger')
            return redirect(url_for('register'))


        user = User(
            username=username,
            email=email,
            role='staff'
        )
        user.password_hash = password
        db.session.add(user)
        db.session.commit()


        AuditLog.log(
            user_id=user.id,
            action='REGISTER',
            ip_address=request.remote_addr
        )

        flash('✅ Регистрация успешна! Теперь вы можете войти.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():

    AuditLog.log(
        user_id=current_user.id,
        action='LOGOUT',
        ip_address=request.remote_addr
    )


    if 'session_token' in session:
        auth_manager.logout(session['session_token'])

    logout_user()
    session.clear()

    flash('👋 Вы вышли из системы', 'info')
    return redirect(url_for('login'))




@app.route('/')
def index():

    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():

    restaurants_count = Restaurant.query.count()
    users_count = User.query.count()
    menu_count = MenuItem.query.count()

    today = datetime.today().date()
    orders_today = Order.query.filter(
        db.func.date(Order.created_at) == today
    ).count()


    popular_items = db_manager.get_popular_items(limit=5)
    kitchen_stats = db_manager.get_kitchen_stats(
        restaurant_id=current_user.restaurant_id if current_user.restaurant_id else None
    )

    return render_template('dashboard.html',
                           restaurants_count=restaurants_count,
                           users_count=users_count,
                           menu_count=menu_count,
                           orders_today=orders_today,
                           popular_items=popular_items,
                           kitchen_stats=kitchen_stats)




@app.route('/restaurants')
@login_required
@permission_required('view_restaurants')
def restaurants():

    if current_user.role == 'admin':
        restaurants_list = Restaurant.query.all()
    else:
        restaurants_list = Restaurant.query.filter_by(id=current_user.restaurant_id).all()

    return render_template('restaurants.html', restaurants=restaurants_list)


@app.route('/restaurants/add', methods=['POST'])
@login_required
@permission_required('manage_restaurants')
def add_restaurant():

    name = request.form.get('name')
    address = request.form.get('address')
    phone = request.form.get('phone')
    email = request.form.get('email')

    if not name:
        flash('⚠️ Название ресторана обязательно', 'warning')
        return redirect(url_for('restaurants'))


    restaurant = Restaurant(
        name=name,
        address=address,
        phone=phone,
        email=email
    )
    db.session.add(restaurant)
    db.session.commit()


    AuditLog.log(
        user_id=current_user.id,
        action='CREATE_RESTAURANT',
        entity_type='restaurant',
        entity_id=restaurant.id,
        new_data={'name': name},
        ip_address=request.remote_addr
    )

    flash(f'✅ Ресторан "{name}" добавлен', 'success')
    return redirect(url_for('restaurants'))




@app.route('/menu')
@login_required
@permission_required('view_menu')
def menu():

    restaurant_id = request.args.get('restaurant_id')

    if restaurant_id:
        items = MenuItem.query.filter_by(restaurant_id=restaurant_id).all()
    elif current_user.role == 'admin':
        items = MenuItem.query.all()
    else:
        items = MenuItem.query.filter_by(restaurant_id=current_user.restaurant_id).all()

    restaurants_list = Restaurant.query.filter_by(is_active=True).all()

    return render_template('menu.html', menu_items=items, restaurants=restaurants_list)


@app.route('/menu/add', methods=['POST'])
@login_required
@permission_required('manage_menu')
def add_menu_item():

    name = request.form.get('name')
    price = request.form.get('price')
    category = request.form.get('category')
    restaurant_id = request.form.get('restaurant_id')
    description = request.form.get('description')


    menu_item = MenuItem(
        name=name,
        description=description,
        price=price,
        category=category,
        restaurant_id=restaurant_id
    )
    db.session.add(menu_item)
    db.session.commit()

    flash(f'✅ Блюдо "{name}" добавлено в меню', 'success')
    return redirect(url_for('menu'))




@app.route('/orders')
@login_required
@permission_required('view_orders')
def orders():

    status = request.args.get('status')

    query = Order.query

    if current_user.role != 'admin' and current_user.restaurant_id:
        query = query.filter_by(restaurant_id=current_user.restaurant_id)

    if status:
        query = query.filter_by(status=status)

    orders_list = query.order_by(Order.created_at.desc()).all()

    return render_template('orders.html', orders=orders_list)


@app.route('/orders/create', methods=['POST'])
@login_required
@permission_required('manage_orders')
def create_order():

    restaurant_id = request.form.get('restaurant_id') or current_user.restaurant_id
    table_number = request.form.get('table_number')
    items_json = request.form.get('items')

    import json
    items = json.loads(items_json) if items_json else []

    try:

        order = Order.create_from_cart(
            restaurant_id=restaurant_id,
            user_id=current_user.id,
            cart_items=items,
            table_number=table_number
        )

        flash(f'✅ Заказ {order.order_number} создан', 'success')
        return redirect(url_for('order_detail', order_id=order.id))

    except Exception as e:
        flash(f'❌ Ошибка создания заказа: {str(e)}', 'danger')
        return redirect(url_for('orders'))


@app.route('/orders/<int:order_id>')
@login_required
def order_detail(order_id):

    order = Order.query.get_or_404(order_id)


    if current_user.role != 'admin' and order.restaurant_id != current_user.restaurant_id:
        flash('⛔ Доступ запрещен', 'danger')
        return redirect(url_for('orders'))

    return render_template('order_detail.html', order=order)


@app.route('/orders/<int:order_id>/status', methods=['POST'])
@login_required
@permission_required('manage_orders')
def update_order_status(order_id):

    status = request.form.get('status')

    order = Order.query.get_or_404(order_id)


    if current_user.role != 'admin' and order.restaurant_id != current_user.restaurant_id:
        return jsonify({'error': 'Access denied'}), 403

    order.update_status(status)


    AuditLog.log(
        user_id=current_user.id,
        action='UPDATE_ORDER_STATUS',
        entity_type='order',
        entity_id=order.id,
        new_data={'status': status},
        ip_address=request.remote_addr
    )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})

    flash(f'Статус заказа обновлен: {status}', 'success')
    return redirect(url_for('order_detail', order_id=order_id))




@app.route('/reports/sales')
@login_required
@permission_required('view_reports')
def sales_report():

    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    restaurant_id = request.args.get('restaurant_id')

    if not date_from:
        date_from = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not date_to:
        date_to = datetime.now().strftime('%Y-%m-%d')


    sales_data = db_manager.get_sales_report(date_from, date_to, restaurant_id)
    popular_items = db_manager.get_popular_items(limit=10)

    return render_template('sales_report.html',
                           sales_data=sales_data,
                           popular_items=popular_items,
                           date_from=date_from,
                           date_to=date_to)




@app.route('/api/menu')
def api_menu():

    restaurant_id = request.args.get('restaurant_id')
    category = request.args.get('category')


    items = db_manager.get_menu_items(
        restaurant_id=restaurant_id,
        category=category,
        available_only=True
    )

    return jsonify(items)


@app.route('/api/orders', methods=['GET'])
@api_auth_required
def api_orders():

    status = request.args.get('status')
    limit = request.args.get('limit', 50, type=int)

    orders = db_manager.get_orders(
        restaurant_id=g.user_id,  # TODO: получить ресторан пользователя
        status=status,
        date_from=(datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    )

    return jsonify(orders[:limit])


@app.route('/api/orders', methods=['POST'])
@api_auth_required
def api_create_order():

    data = request.get_json()

    try:
        order_id = db_manager.create_order(
            restaurant_id=data['restaurant_id'],
            user_id=g.user_id,
            table_number=data.get('table_number'),
            customer_name=data.get('customer_name')
        )

        for item in data.get('items', []):
            db_manager.add_order_item(
                order_id=order_id,
                menu_item_id=item['id'],
                quantity=item['quantity'],
                price=item['price']
            )

        order = db_manager.get_order(order_id)
        return jsonify({'success': True, 'order': order}), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 400




@app.route('/profile')
@login_required
def profile():

    sessions = auth_manager.get_active_sessions(current_user.id)
    permissions = auth_manager.get_user_permissions(current_user.id)

    return render_template('profile.html',
                           sessions=sessions,
                           permissions=permissions)


@app.route('/profile/sessions/terminate/<int:session_id>', methods=['POST'])
@login_required
def terminate_session(session_id):

    if auth_manager.terminate_session(session_id, current_user.id):
        flash('✅ Сессия завершена', 'success')
    else:
        flash('❌ Ошибка завершения сессии', 'danger')

    return redirect(url_for('profile'))


@app.route('/profile/sessions/terminate-all', methods=['POST'])
@login_required
def terminate_all_sessions():

    auth_manager.terminate_all_sessions(current_user.id, exclude_current=True)
    flash('✅ Все другие сессии завершены', 'success')
    return redirect(url_for('profile'))




def init_database():

    with app.app_context():

        db.create_all()


        if not User.query.first():
            admin = User(
                username='admin',
                email='admin@restaurant.com',
                role='admin'
            )
            admin.password_hash = 'admin123'
            db.session.add(admin)


            restaurant = Restaurant(
                name='Gourmet Central',
                address='ул. Пушкина, 10',
                phone='+7 (999) 123-45-67',
                email='central@gourmet.com'
            )
            db.session.add(restaurant)
            db.session.commit()


            db_manager.create_menu_item(
                name='Цезарь с курицей',
                price=450.00,
                restaurant_id=restaurant.id,
                category='Салаты',
                description='Классический салат с пармезаном'
            )

            print("✅ База данных инициализирована")


        Session.cleanup_expired()




if __name__ == '__main__':
    print("=" * 60)
    print("🍽️  RESTAURANT SYSTEM v2.0.3")
    print("=" * 60)
    print(f"📅  Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print(f"🗄️  База данных: MySQL (XAMPP)")
    print(f"🔐  Аутентификация: Flask-Login + JWT")
    print(f"📊  ORM: SQLAlchemy")
    print("=" * 60)
    print("👤  Тестовый доступ: admin / admin123")
    print("=" * 60)


    init_database()


    app.run(debug=True, host='0.0.0.0', port=5000)