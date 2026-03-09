import pymysql
import pymysql.cursors
from contextlib import contextmanager
import logging
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class DatabaseManager:


    _instance = None
    _connection_pool = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, host='localhost', user='root', password='',
                 database='restaurant_db', port=3306, pool_size=10):

        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.port = port
        self.pool_size = pool_size
        self.connection = None

    def connect(self):

        try:
            self.connection = pymysql.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                port=self.port,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False
            )
            logger.info(f"✅ Подключено к MySQL: {self.host}/{self.database}")
            return self.connection
        except pymysql.Error as e:
            logger.error(f"❌ Ошибка подключения к MySQL: {e}")
            raise

    def disconnect(self):

        if self.connection:
            self.connection.close()
            logger.info("🔌 Соединение с MySQL закрыто")

    @contextmanager
    def get_cursor(self):

        cursor = None
        try:
            if not self.connection:
                self.connect()
            cursor = self.connection.cursor()
            yield cursor
            self.connection.commit()
        except Exception as e:
            if self.connection:
                self.connection.rollback()
            logger.error(f"❌ Ошибка выполнения запроса: {e}")
            raise
        finally:
            if cursor:
                cursor.close()



    def create_user(self, username, email, password_hash, role='staff', restaurant_id=None):

        query = """
            INSERT INTO users (username, email, password_hash, role, restaurant_id)
            VALUES (%s, %s, %s, %s, %s)
        """
        with self.get_cursor() as cursor:
            cursor.execute(query, (username, email, password_hash, role, restaurant_id))
            user_id = cursor.lastrowid
            logger.info(f"👤 Создан пользователь ID: {user_id}")
            return user_id

    def get_user(self, user_id):

        query = "SELECT * FROM users WHERE id = %s"
        with self.get_cursor() as cursor:
            cursor.execute(query, (user_id,))
            return cursor.fetchone()

    def get_user_by_username(self, username):

        query = "SELECT * FROM users WHERE username = %s OR email = %s"
        with self.get_cursor() as cursor:
            cursor.execute(query, (username, username))
            return cursor.fetchone()

    def update_user(self, user_id, **kwargs):

        if not kwargs:
            return False

        fields = []
        values = []
        for key, value in kwargs.items():
            if key in ['username', 'email', 'role', 'restaurant_id', 'is_active']:
                fields.append(f"{key} = %s")
                values.append(value)

        if not fields:
            return False

        values.append(user_id)
        query = f"UPDATE users SET {', '.join(fields)} WHERE id = %s"

        with self.get_cursor() as cursor:
            cursor.execute(query, values)
            logger.info(f"👤 Обновлен пользователь ID: {user_id}")
            return cursor.rowcount > 0

    def delete_user(self, user_id):

        query = "DELETE FROM users WHERE id = %s"
        with self.get_cursor() as cursor:
            cursor.execute(query, (user_id,))
            logger.info(f"👤 Удален пользователь ID: {user_id}")
            return cursor.rowcount > 0



    def create_restaurant(self, name, address=None, phone=None, email=None):

        query = """
            INSERT INTO restaurants (name, address, phone, email)
            VALUES (%s, %s, %s, %s)
        """
        with self.get_cursor() as cursor:
            cursor.execute(query, (name, address, phone, email))
            restaurant_id = cursor.lastrowid
            logger.info(f"🏢 Создан ресторан ID: {restaurant_id}")
            return restaurant_id

    def get_restaurant(self, restaurant_id):

        query = "SELECT * FROM restaurants WHERE id = %s"
        with self.get_cursor() as cursor:
            cursor.execute(query, (restaurant_id,))
            return cursor.fetchone()

    def get_all_restaurants(self, active_only=True):

        query = "SELECT * FROM restaurants"
        if active_only:
            query += " WHERE is_active = TRUE"
        query += " ORDER BY name"

        with self.get_cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchall()

    def update_restaurant(self, restaurant_id, **kwargs):

        if not kwargs:
            return False

        fields = []
        values = []
        for key, value in kwargs.items():
            if key in ['name', 'address', 'phone', 'email', 'is_active']:
                fields.append(f"{key} = %s")
                values.append(value)

        if not fields:
            return False

        values.append(restaurant_id)
        query = f"UPDATE restaurants SET {', '.join(fields)} WHERE id = %s"

        with self.get_cursor() as cursor:
            cursor.execute(query, values)
            logger.info(f"🏢 Обновлен ресторан ID: {restaurant_id}")
            return cursor.rowcount > 0

    def delete_restaurant(self, restaurant_id):

        query = "DELETE FROM restaurants WHERE id = %s"
        with self.get_cursor() as cursor:
            cursor.execute(query, (restaurant_id,))
            logger.info(f"🏢 Удален ресторан ID: {restaurant_id}")
            return cursor.rowcount > 0



    def create_menu_item(self, name, price, restaurant_id, category=None,
                         description=None, preparation_time=15):

        query = """
            INSERT INTO menu_items (name, description, price, category, restaurant_id, preparation_time)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        with self.get_cursor() as cursor:
            cursor.execute(query, (name, description, price, category, restaurant_id, preparation_time))
            item_id = cursor.lastrowid
            logger.info(f"🍽️ Создано блюдо ID: {item_id}")
            return item_id

    def get_menu_items(self, restaurant_id=None, category=None, available_only=True):

        query = """
            SELECT mi.*, r.name as restaurant_name 
            FROM menu_items mi
            JOIN restaurants r ON mi.restaurant_id = r.id
            WHERE 1=1
        """
        params = []

        if restaurant_id:
            query += " AND mi.restaurant_id = %s"
            params.append(restaurant_id)

        if category:
            query += " AND mi.category = %s"
            params.append(category)

        if available_only:
            query += " AND mi.is_available = TRUE"

        query += " ORDER BY mi.category, mi.sort_order"

        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def update_menu_item(self, item_id, **kwargs):

        if not kwargs:
            return False

        fields = []
        values = []
        for key, value in kwargs.items():
            if key in ['name', 'description', 'price', 'category', 'is_available', 'preparation_time']:
                fields.append(f"{key} = %s")
                values.append(value)

        if not fields:
            return False

        values.append(item_id)
        query = f"UPDATE menu_items SET {', '.join(fields)} WHERE id = %s"

        with self.get_cursor() as cursor:
            cursor.execute(query, values)
            logger.info(f"🍽️ Обновлено блюдо ID: {item_id}")
            return cursor.rowcount > 0

    def delete_menu_item(self, item_id):

        query = "DELETE FROM menu_items WHERE id = %s"
        with self.get_cursor() as cursor:
            cursor.execute(query, (item_id,))
            logger.info(f"🍽️ Удалено блюдо ID: {item_id}")
            return cursor.rowcount > 0



    def create_order(self, restaurant_id, user_id, table_number=None,
                     customer_name=None, customer_phone=None):

        order_number = f"ORD-{datetime.now().strftime('%Y%m%d')}-{self._get_next_order_num():04d}"

        query = """
            INSERT INTO orders (order_number, restaurant_id, user_id, table_number, 
                               customer_name, customer_phone, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'pending')
        """
        with self.get_cursor() as cursor:
            cursor.execute(query, (order_number, restaurant_id, user_id,
                                   table_number, customer_name, customer_phone))
            order_id = cursor.lastrowid
            logger.info(f"📦 Создан заказ ID: {order_id} ({order_number})")
            return order_id

    def add_order_item(self, order_id, menu_item_id, quantity, price):

        query = """
            INSERT INTO order_items (order_id, menu_item_id, quantity, price)
            VALUES (%s, %s, %s, %s)
        """
        with self.get_cursor() as cursor:
            cursor.execute(query, (order_id, menu_item_id, quantity, price))
            item_id = cursor.lastrowid


            self._update_order_total(order_id)

            return item_id

    def _update_order_total(self, order_id):

        query = """
            UPDATE orders 
            SET total_amount = (
                SELECT COALESCE(SUM(quantity * price), 0) 
                FROM order_items 
                WHERE order_id = %s
            )
            WHERE id = %s
        """
        with self.get_cursor() as cursor:
            cursor.execute(query, (order_id, order_id))

    def get_order(self, order_id):

        order_query = "SELECT * FROM orders WHERE id = %s"
        items_query = """
            SELECT oi.*, mi.name as item_name 
            FROM order_items oi
            JOIN menu_items mi ON oi.menu_item_id = mi.id
            WHERE oi.order_id = %s
        """

        with self.get_cursor() as cursor:
            cursor.execute(order_query, (order_id,))
            order = cursor.fetchone()

            if order:
                cursor.execute(items_query, (order_id,))
                order['items'] = cursor.fetchall()

            return order

    def get_orders(self, restaurant_id=None, status=None, date_from=None, date_to=None):

        query = """
            SELECT o.*, r.name as restaurant_name, u.username as waiter
            FROM orders o
            JOIN restaurants r ON o.restaurant_id = r.id
            JOIN users u ON o.user_id = u.id
            WHERE 1=1
        """
        params = []

        if restaurant_id:
            query += " AND o.restaurant_id = %s"
            params.append(restaurant_id)

        if status:
            query += " AND o.status = %s"
            params.append(status)

        if date_from:
            query += " AND DATE(o.created_at) >= %s"
            params.append(date_from)

        if date_to:
            query += " AND DATE(o.created_at) <= %s"
            params.append(date_to)

        query += " ORDER BY o.created_at DESC"

        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def update_order_status(self, order_id, status):

        query = """
            UPDATE orders 
            SET status = %s,
                completed_at = CASE WHEN %s = 'completed' THEN NOW() ELSE completed_at END
            WHERE id = %s
        """
        with self.get_cursor() as cursor:
            cursor.execute(query, (status, status, order_id))
            logger.info(f"📦 Обновлен статус заказа {order_id}: {status}")
            return cursor.rowcount > 0



    def get_sales_report(self, start_date, end_date, restaurant_id=None):

        query = """
            SELECT 
                DATE(o.created_at) as sale_date,
                COUNT(DISTINCT o.id) as orders_count,
                SUM(o.total_amount) as total_revenue,
                AVG(o.total_amount) as avg_order_value,
                COUNT(oi.id) as items_sold,
                SUM(CASE WHEN o.payment_status = 'paid' THEN o.total_amount ELSE 0 END) as paid_revenue
            FROM orders o
            LEFT JOIN order_items oi ON o.id = oi.order_id
            WHERE DATE(o.created_at) BETWEEN %s AND %s
        """
        params = [start_date, end_date]

        if restaurant_id:
            query += " AND o.restaurant_id = %s"
            params.append(restaurant_id)

        query += " GROUP BY DATE(o.created_at) ORDER BY sale_date"

        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def get_popular_items(self, limit=10, days=30):

        query = """
            SELECT 
                mi.id,
                mi.name,
                mi.category,
                COUNT(oi.id) as times_ordered,
                SUM(oi.quantity) as total_sold,
                SUM(oi.quantity * oi.price) as total_revenue
            FROM menu_items mi
            JOIN order_items oi ON mi.id = oi.menu_item_id
            JOIN orders o ON oi.order_id = o.id
            WHERE o.created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
            GROUP BY mi.id, mi.name, mi.category
            ORDER BY total_sold DESC
            LIMIT %s
        """
        with self.get_cursor() as cursor:
            cursor.execute(query, (days, limit))
            return cursor.fetchall()

    def get_kitchen_stats(self, restaurant_id=None):

        query = """
            SELECT 
                COUNT(CASE WHEN o.status = 'pending' THEN 1 END) as pending_orders,
                COUNT(CASE WHEN o.status = 'preparing' THEN 1 END) as preparing_orders,
                AVG(TIMESTAMPDIFF(MINUTE, o.created_at, o.completed_at)) as avg_prep_time,
                SUM(CASE WHEN o.status = 'pending' THEN 
                    (SELECT SUM(mi.preparation_time * oi.quantity) 
                     FROM order_items oi 
                     JOIN menu_items mi ON oi.menu_item_id = mi.id 
                     WHERE oi.order_id = o.id) 
                END) as total_prep_time
            FROM orders o
            WHERE o.status IN ('pending', 'preparing')
        """
        if restaurant_id:
            query += " AND o.restaurant_id = %s"

        with self.get_cursor() as cursor:
            params = [restaurant_id] if restaurant_id else []
            cursor.execute(query, params)
            return cursor.fetchone()

    def _get_next_order_num(self):

        query = """
            SELECT COUNT(*) as cnt 
            FROM orders 
            WHERE DATE(created_at) = CURDATE()
        """
        with self.get_cursor() as cursor:
            cursor.execute(query)
            result = cursor.fetchone()
            return (result['cnt'] or 0) + 1



    def execute_transaction(self, queries):

        try:
            with self.get_cursor() as cursor:
                for query, params in queries:
                    cursor.execute(query, params)
                logger.info(f"✅ Транзакция из {len(queries)} запросов выполнена")
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка транзакции: {e}")
            return False

    def backup_database(self, backup_path):

        import subprocess
        import os

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"backup_{timestamp}.sql"
        filepath = os.path.join(backup_path, filename)


        cmd = f"mysqldump -h {self.host} -u {self.user} -p{self.password} {self.database} > {filepath}"

        try:
            subprocess.run(cmd, shell=True, check=True)
            logger.info(f"💾 Бэкап создан: {filename}")
            return filename
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Ошибка создания бэкапа: {e}")
            return None

    def restore_database(self, backup_file):

        import subprocess

        cmd = f"mysql -h {self.host} -u {self.user} -p{self.password} {self.database} < {backup_file}"

        try:
            subprocess.run(cmd, shell=True, check=True)
            logger.info(f"🔄 База данных восстановлена из: {backup_file}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Ошибка восстановления: {e}")
            return False




if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)


    db = DatabaseManager()

    try:

        db.connect()


        rest_id = db.create_restaurant(
            name='Gourmet Тестовый',
            address='ул. Тестовая, 1',
            phone='+7 (999) 111-22-33',
            email='test@gourmet.com'
        )


        from werkzeug.security import generate_password_hash

        user_id = db.create_user(
            username='test_user',
            email='test@example.com',
            password_hash=generate_password_hash('password123'),
            role='manager',
            restaurant_id=rest_id
        )


        item1 = db.create_menu_item(
            name='Тестовое блюдо 1',
            price=350.00,
            category='Основные блюда',
            restaurant_id=rest_id
        )

        item2 = db.create_menu_item(
            name='Тестовое блюдо 2',
            price=250.00,
            category='Закуски',
            restaurant_id=rest_id
        )


        order_id = db.create_order(
            restaurant_id=rest_id,
            user_id=user_id,
            table_number=10,
            customer_name='Тестовый Клиент'
        )


        db.add_order_item(order_id, item1, 2, 350.00)
        db.add_order_item(order_id, item2, 1, 250.00)


        order = db.get_order(order_id)
        print("\n📦 Заказ:", json.dumps(order, indent=2, default=str))


        report = db.get_sales_report(
            start_date='2026-03-01',
            end_date='2026-03-02'
        )
        print("\n📊 Отчет:", json.dumps(report, indent=2, default=str))


        popular = db.get_popular_items(limit=5)
        print("\n🔥 Популярные блюда:", json.dumps(popular, indent=2, default=str))

    finally:

        db.disconnect()