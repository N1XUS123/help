from functools import wraps
from flask import session, redirect, url_for, flash, request, jsonify, g
from flask_login import current_user
import jwt
from datetime import datetime, timedelta
import secrets
import hashlib
import hmac
from datetime import datetime, timedelta, UTC
from models_orm import User, Session as DbSession
import logging

logger = logging.getLogger(__name__)




class AuthConfig:

    SECRET_KEY = 'your-super-secret-key-change-in-production'
    JWT_SECRET = 'jwt-secret-key-change-in-production'
    JWT_ALGORITHM = 'HS256'
    JWT_EXPIRY_HOURS = 24
    SESSION_EXPIRY_DAYS = 7
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_MINUTES = 15
    PASSWORD_MIN_LENGTH = 8
    PASSWORD_REQUIRE_DIGIT = True
    PASSWORD_REQUIRE_UPPERCASE = True
    PASSWORD_REQUIRE_SPECIAL = True




def login_required(f):


    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('🔐 Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):


    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('🔐 Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login'))

        if current_user.role != 'admin':
            logger.warning(f"Попытка доступа к админ-панели: {current_user.username}")
            flash('⛔ Доступ запрещен. Требуются права администратора.', 'danger')
            return redirect(url_for('dashboard'))

        return f(*args, **kwargs)

    return decorated_function


def permission_required(permission_name):


    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('🔐 Пожалуйста, войдите в систему', 'warning')
                return redirect(url_for('login'))

            if not current_user.has_permission(permission_name):
                logger.warning(f"Попытка доступа без права {permission_name}: {current_user.username}")
                flash(f'⛔ У вас нет права: {permission_name}', 'danger')
                return redirect(url_for('dashboard'))

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def role_required(*roles):


    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('🔐 Пожалуйста, войдите в систему', 'warning')
                return redirect(url_for('login'))

            if current_user.role not in roles:
                logger.warning(f"Попытка доступа с ролью {current_user.role}, требуются {roles}")
                flash(f'⛔ Доступ запрещен. Требуется роль: {", ".join(roles)}', 'danger')
                return redirect(url_for('dashboard'))

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def api_auth_required(f):


    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')

        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Требуется авторизация'}), 401

        token = auth_header.split(' ')[1]

        try:
            payload = jwt.decode(
                token,
                AuthConfig.JWT_SECRET,
                algorithms=[AuthConfig.JWT_ALGORITHM]
            )
            g.user_id = payload['user_id']
            g.user_role = payload['role']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Токен истек'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Невалидный токен'}), 401

        return f(*args, **kwargs)

    return decorated_function




class AuthManager:


    def __init__(self, app=None, db=None):
        self.app = app
        self.db = db
        if app:
            self.init_app(app)

    def init_app(self, app):

        self.app = app
        app.config['SECRET_KEY'] = AuthConfig.SECRET_KEY


        app.before_request(self.before_request)
        app.after_request(self.after_request)

        logger.info("✅ AuthManager инициализирован")

    def before_request(self):

        if self.db:
            self.db.session.query(DbSession).filter(
                DbSession.expires_at < datetime.utcnow()
            ).delete()
            self.db.session.commit()

    def after_request(self, response):

        return response



    def authenticate(self, username, password, ip_address=None, user_agent=None):

        from models_orm import User


        user = User.query.filter(
            (User.username == username) | (User.email == username)
        ).first()

        if not user:
            logger.warning(f"Попытка входа с несуществующим логином: {username}")
            return None, None


        if user.is_locked():
            logger.warning(f"Заблокированный пользователь пытается войти: {username}")
            return None, None


        if user.check_password(password):

            user.login_attempts = 0
            user.locked_until = None


            session_token = secrets.token_urlsafe(32)
            db_session = DbSession(
                user_id=user.id,
                session_token=session_token,
                ip_address=ip_address,
                user_agent=user_agent,
                expires_at=datetime.utcnow() + timedelta(days=AuthConfig.SESSION_EXPIRY_DAYS)
            )
            self.db.session.add(db_session)
            self.db.session.commit()

            logger.info(f"✅ Успешный вход: {user.username} с IP {ip_address}")
            return user, session_token
        else:

            user.login_attempts += 1
            if user.login_attempts >= AuthConfig.MAX_LOGIN_ATTEMPTS:
                user.locked_until = datetime.utcnow() + timedelta(minutes=AuthConfig.LOCKOUT_MINUTES)
                logger.warning(f"Пользователь {user.username} заблокирован на {AuthConfig.LOCKOUT_MINUTES} минут")

            self.db.session.commit()
            logger.warning(f"Неудачная попытка входа для {username}")
            return None, None

    def logout(self, session_token):

        DbSession.query.filter_by(session_token=session_token).delete()
        self.db.session.commit()
        logger.info("👋 Пользователь вышел из системы")

    def validate_session(self, session_token):

        db_session = DbSession.query.filter_by(session_token=session_token).first()

        if not db_session:
            return None

        if db_session.expires_at < datetime.utcnow():
            db_session.delete()
            self.db.session.commit()
            return None

        return db_session.user

    def generate_jwt(self, user):

        payload = {
            'user_id': user.id,
            'username': user.username,
            'role': user.role,
            'exp': datetime.utcnow() + timedelta(hours=AuthConfig.JWT_EXPIRY_HOURS),
            'iat': datetime.utcnow()
        }
        return jwt.encode(payload, AuthConfig.JWT_SECRET, algorithm=AuthConfig.JWT_ALGORITHM)



    def validate_password_strength(self, password):

        errors = []

        if len(password) < AuthConfig.PASSWORD_MIN_LENGTH:
            errors.append(f"Минимальная длина: {AuthConfig.PASSWORD_MIN_LENGTH} символов")

        if AuthConfig.PASSWORD_REQUIRE_DIGIT and not any(c.isdigit() for c in password):
            errors.append("Должна быть хотя бы одна цифра")

        if AuthConfig.PASSWORD_REQUIRE_UPPERCASE and not any(c.isupper() for c in password):
            errors.append("Должна быть хотя бы одна заглавная буква")

        if AuthConfig.PASSWORD_REQUIRE_SPECIAL and not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password):
            errors.append("Должен быть хотя бы один спецсимвол")

        return len(errors) == 0, errors

    def change_password(self, user_id, old_password, new_password):

        from models_orm import User

        user = User.query.get(user_id)
        if not user:
            return False, "Пользователь не найден"

        if not user.check_password(old_password):
            return False, "Неверный текущий пароль"

        is_valid, errors = self.validate_password_strength(new_password)
        if not is_valid:
            return False, errors

        user.password_hash = new_password
        self.db.session.commit()


        DbSession.query.filter_by(user_id=user_id).delete()
        self.db.session.commit()

        logger.info(f"🔐 Пароль изменен для пользователя {user.username}")
        return True, "Пароль успешно изменен"

    def reset_password(self, email):

        from models_orm import User

        user = User.query.filter_by(email=email).first()
        if not user:
            return False, "Пользователь не найден"


        reset_token = secrets.token_urlsafe(32)


        logger.info(f"📧 Запрошен сброс пароля для {email}")
        return True, "Инструкции по сбросу пароля отправлены на email"



    def get_user_permissions(self, user_id):

        from models_orm import User

        user = User.query.get(user_id)
        if not user:
            return []

        return user.get_permissions()

    def check_permission(self, user_id, permission_name):

        from models_orm import User

        user = User.query.get(user_id)
        if not user:
            return False

        return user.has_permission(permission_name)

    def get_users_by_role(self, role):

        from models_orm import User

        return User.query.filter_by(role=role, is_active=True).all()



    def log_security_event(self, event_type, user_id=None, details=None, ip_address=None):

        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            'user_id': user_id,
            'ip_address': ip_address,
            'details': details
        }


        logger.info(f"🔒 Security event: {log_entry}")

    def is_ip_blocked(self, ip_address):

        return False

    def get_active_sessions(self, user_id):

        sessions = DbSession.query.filter_by(user_id=user_id).all()
        return [
            {
                'id': s.id,
                'ip_address': s.ip_address,
                'user_agent': s.user_agent,
                'created_at': s.created_at.isoformat(),
                'expires_at': s.expires_at.isoformat(),
                'is_current': s.session_token == session.get('session_token', '')
            }
            for s in sessions
        ]

    def terminate_session(self, session_id, user_id):

        session = DbSession.query.filter_by(id=session_id, user_id=user_id).first()
        if session:
            session.delete()
            self.db.session.commit()
            return True
        return False

    def terminate_all_sessions(self, user_id, exclude_current=True):

        query = DbSession.query.filter_by(user_id=user_id)

        if exclude_current and 'session_token' in session:
            query = query.filter(DbSession.session_token != session['session_token'])

        query.delete()
        self.db.session.commit()
        logger.info(f"Завершены все сессии пользователя {user_id}")
        return True




def flash_errors(form):

    for field, errors in form.errors.items():
        for error in errors:
            flash(f'❌ {getattr(form, field).label.text}: {error}', 'danger')


def flash_auth_message(category, **kwargs):

    messages = {
        'login_success': '✅ Добро пожаловать, {username}!',
        'login_failed': '❌ Неверное имя пользователя или пароль',
        'logout': '👋 Вы вышли из системы',
        'register_success': '✅ Регистрация успешна! Теперь вы можете войти',
        'register_failed': '❌ Ошибка регистрации',
        'password_changed': '🔐 Пароль успешно изменен',
        'password_reset_sent': '📧 Инструкции отправлены на email',
        'account_locked': '🔒 Аккаунт заблокирован на {minutes} минут',
        'session_expired': '⏰ Сессия истекла. Пожалуйста, войдите снова',
        'permission_denied': '⛔ У вас нет прав для этого действия'
    }

    message = messages.get(category, category)
    if kwargs:
        message = message.format(**kwargs)

    flash(message, 'info' if 'success' in category else 'warning')




def register_auth_routes(app, auth_manager):


    @app.route('/login', methods=['GET', 'POST'])
    def login():

        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            remember = request.form.get('remember', False)

            user, session_token = auth_manager.authenticate(
                username=username,
                password=password,
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string
            )

            if user:

                from flask_login import login_user
                login_user(user, remember=remember)


                session['session_token'] = session_token

                flash_auth_message('login_success', username=user.username)

                next_page = request.args.get('next')
                if next_page and next_page.startswith('/'):
                    return redirect(next_page)
                return redirect(url_for('dashboard'))
            else:
                flash_auth_message('login_failed')

        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():

        if 'session_token' in session:
            auth_manager.logout(session['session_token'])

        from flask_login import logout_user
        logout_user()
        session.clear()

        flash_auth_message('logout')
        return redirect(url_for('login'))

    @app.route('/profile')
    @login_required
    def profile():

        sessions = auth_manager.get_active_sessions(current_user.id)
        permissions = auth_manager.get_user_permissions(current_user.id)

        return render_template('profile.html',
                               sessions=sessions,
                               permissions=permissions)

    @app.route('/change-password', methods=['POST'])
    @login_required
    def change_password():

        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')

        success, message = auth_manager.change_password(
            current_user.id,
            old_password,
            new_password
        )

        if success:
            flash_auth_message('password_changed')

            return redirect(url_for('logout'))
        else:
            if isinstance(message, list):
                for msg in message:
                    flash(msg, 'danger')
            else:
                flash(message, 'danger')

        return redirect(url_for('profile'))

    @app.route('/api/auth/login', methods=['POST'])
    def api_login():

        data = request.get_json()

        if not data or not data.get('username') or not data.get('password'):
            return jsonify({'error': 'Требуются username и password'}), 400

        user, session_token = auth_manager.authenticate(
            username=data['username'],
            password=data['password'],
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )

        if user:
            jwt_token = auth_manager.generate_jwt(user)
            return jsonify({
                'success': True,
                'token': jwt_token,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'role': user.role
                }
            })
        else:
            return jsonify({'error': 'Неверные учетные данные'}), 401

    @app.route('/api/auth/logout', methods=['POST'])
    @api_auth_required
    def api_logout():
        """API для выхода"""

        return jsonify({'success': True})

    @app.route('/api/auth/me')
    @api_auth_required
    def api_me():

        from models_orm import User
        user = User.query.get(g.user_id)

        if not user:
            return jsonify({'error': 'Пользователь не найден'}), 404

        return jsonify({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'permissions': auth_manager.get_user_permissions(user.id)
        })

    return app




if __name__ == '__main__':

    auth = AuthManager()


    test_passwords = ['123', 'password', 'Password123', 'P@ssw0rd!']
    for pwd in test_passwords:
        valid, errors = auth.validate_password_strength(pwd)
        print(f"Пароль '{pwd}': {'✅' if valid else '❌'}")
        if not valid:
            for e in errors:
                print(f"  - {e}")



    class MockUser:
        def __init__(self):
            self.id = 1
            self.username = 'test'
            self.role = 'admin'


    token = auth.generate_jwt(MockUser())
    print(f"\n🔑 JWT Token: {token[:50]}...")