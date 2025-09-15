from werkzeug.security import generate_password_hash
from gratissys import get_db_connection

# To create an admin
username = "admin"
email = "Iamadmin00@gmail.com"
password = "GRCgratisadmin"
fullname = "Admin User"  
role = "admin"

# To hash the password
hashed_password = generate_password_hash(password)

# Insert sa DB
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("""
    INSERT INTO users (
        username, email, password_hash, full_name, role
    )
    VALUES (%s, %s, %s, %s, %s)
""", (username, email, hashed_password, fullname, role))

conn.commit()
conn.close()

print("Admin account created!")
