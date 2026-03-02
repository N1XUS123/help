import pymysql


connection = pymysql.connect(
    host='localhost',
    user='root',
    password='',
    database='restaurant_db'
)

try:
    with connection.cursor() as cursor:
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        print("✅ Подключение к MySQL успешно!")
        print("Таблицы в базе данных:")
        for table in tables:
            print(f"  - {table[0]}")
finally:
    connection.close()