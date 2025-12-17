from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify, Response
import pymysql
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, time, timedelta
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
import secrets
import qrcode
app = Flask(__name__)
app.secret_key = "yoursecretkey"

# DB Connection
def get_db_connection():
    return pymysql.connect(
        host="127.0.0.1",
        user="root",
        password="",
        database="qr_login_system",
        port=3307,  
        cursorclass=pymysql.cursors.DictCursor
    )

# ------------------ Registration ------------------ #
@app.route("/student-registration")
def student_registration_form():
    return render_template("student-registration.html")

@app.route("/register", methods=["POST"])
def register_student():
    full_name = request.form["full_name"]
    email = request.form["email"]
    username = request.form["username"]
    password = generate_password_hash(request.form["password"])
    student_number = request.form["student_number"]
    year_level = request.form["year_level"]
    program = request.form["program"]
    student_type = request.form["student_type"]
    assigned_duty = request.form["assigned_duty"]

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO users (full_name, email, username, password_hash, student_number,
                               year_level, program, student_type, assigned_duty, role)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'student')
        """, (full_name, email, username, password, student_number,
              year_level, program, student_type, assigned_duty))
        
        conn.commit()
        flash("Student registered successfully!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect("/student-registration")



# ------------------ Login Pages ------------------ #
@app.route('/')
def login():
    return render_template('login.html')

@app.route('/admin-login')
def admin_login():
    return render_template('admin-login.html')

@app.route('/student-login')
def student_login():
    return render_template('student-login.html')

# QR CODE

# Without Restrictions (For demo/testing purposes only)

@app.route('/qr-attendance')
def qr_attendance():
    return render_template('qr_attendance.html')

# @app.route('/validate_qr', methods=['POST'])
# def validate_qr():
#     data = request.get_json()
#     token = data.get('token')

#     if not token:
#         return jsonify({"status": "error", "message": "Invalid QR code."})

#     connection = get_db_connection()
#     cursor = connection.cursor(pymysql.cursors.DictCursor)

#     # Check if QR exists and approved
#     cursor.execute("SELECT * FROM users WHERE qr_token=%s AND status='approved'", (token,))
#     user = cursor.fetchone()

#     if not user:
#         cursor.close()
#         connection.close()
#         return jsonify({"status": "error", "message": "QR code not recognized or not approved."})

#     user_id = user['id']
#     assigned_duty = user.get('assigned_duty', "Unassigned")

#     today = date.today()
#     now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

#     # Get latest attendance today
#     cursor.execute("""
#         SELECT * FROM attendance 
#         WHERE user_id=%s AND date=%s 
#         ORDER BY id DESC LIMIT 1
#     """, (user_id, today))
#     last_log = cursor.fetchone()

#     # No record yet today → Time IN
#     if not last_log:
#         cursor.execute("""
#             INSERT INTO attendance (user_id, date, time_in, assigned_duty)
#             VALUES (%s, %s, %s, %s)
#         """, (user_id, today, now, assigned_duty))
#         message = f"{user['full_name']} - Time In Recorded ✅"

#     # If already timed in but not out → Time OUT
#     elif not last_log['time_out']:
#         time_in_dt = datetime.combine(today, datetime.strptime(str(last_log['time_in']), "%H:%M:%S").time())
#         time_out_dt = datetime.now()

#         # Calculate total hours (minus 1 hr lunch break)
#         total_hours = int((time_out_dt - time_in_dt).total_seconds() // 3600) - 1
#         if total_hours < 0:
#             total_hours = 0

#         cursor.execute("""
#             UPDATE attendance
#             SET time_out=%s, total_hours=%s
#             WHERE id=%s
#         """, (now, total_hours, last_log['id']))
#         message = f"{user['full_name']} - Time Out Recorded ⏰ (Total: {total_hours} hrs)"

#     # If already timed out, create new time in for next day/session
#     else:
#         cursor.execute("""
#             INSERT INTO attendance (user_id, date, time_in, assigned_duty)
#             VALUES (%s, %s, %s, %s)
#         """, (user_id, today, now, assigned_duty))
#         message = f"{user['full_name']} - New Time In Recorded ✅"

#     connection.commit()
#     cursor.close()
#     connection.close()

#     return jsonify({"status": "success", "message": message})


# With Restrictions (8-8:15 AM, 5-5:15 PM)

@app.route('/validate_qr', methods=['POST'])
def validate_qr():
    data = request.get_json()
    token = data.get('token')

    if not token:
        return jsonify({"status": "error", "message": "Invalid QR code."})

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Validate QR token
        cursor.execute("""
            SELECT * FROM users 
            WHERE qr_token=%s AND status='approved'
        """, (token,))
        user = cursor.fetchone()

        if not user:
            return jsonify({"status": "error", "message": "QR code not recognized or not approved."})

        user_id = user['id']
        student_type = user['student_type']
        assigned_duty = user.get('assigned_duty') or "General Services"
        today = date.today()
        now = datetime.now().time()

        # Get latest attendance today
        cursor.execute("""
            SELECT * FROM attendance
            WHERE user_id=%s AND date=%s
            ORDER BY id DESC
            LIMIT 1
        """, (user_id, today))
        record = cursor.fetchone()

        # ===============================
        # ===== S.T.A.R.S USERS =========
        # ===============================
        if student_type == "S.T.A.R.S":

            # ---- TIME IN ----
            if not record or record['time_out']:
                cursor.execute("""
                    INSERT INTO attendance (user_id, date, time_in, assigned_duty)
                    VALUES (%s, %s, %s, %s)
                """, (
                    user_id,
                    today,
                    datetime.now().strftime("%H:%M:%S"),
                    assigned_duty
                ))
                conn.commit()

                return jsonify({
                    "status": "success",
                    "message": f"{user['full_name']} - Time In recorded ✅"
                })

            # ---- TIME OUT ----
            time_in_value = record['time_in']

            if isinstance(time_in_value, timedelta):
                secs = int(time_in_value.total_seconds())
                time_in_value = time(secs // 3600, (secs % 3600) // 60)
            elif isinstance(time_in_value, str):
                time_in_value = datetime.strptime(time_in_value, "%H:%M:%S").time()

            time_in_dt = datetime.combine(today, time_in_value)
            time_out_dt = datetime.combine(today, datetime.now().time())

            # Deduct lunch
            lunch_start = datetime.combine(today, time(12, 0))
            lunch_end = datetime.combine(today, time(13, 0))

            total_seconds = (time_out_dt - time_in_dt).total_seconds()
            if time_in_dt < lunch_start < time_out_dt:
                total_seconds -= 3600

            # Rounding (same as /time_out)
            base_hours = int(total_seconds // 3600)
            remaining_minutes = int((total_seconds % 3600) // 60)

            if 29 <= remaining_minutes <= 31:
                total_hours = base_hours + 0.5
            elif remaining_minutes >= 30:
                total_hours = base_hours + 1
            else:
                total_hours = base_hours

            cursor.execute("""
                UPDATE attendance
                SET time_out=%s, total_hours=%s
                WHERE id=%s
            """, (
                datetime.now().strftime("%H:%M:%S"),
                total_hours,
                record['id']
            ))

            # Update schedule
            cursor.execute("""
                INSERT INTO tbl_schedule (user_id, day, rendered_hours)
                VALUES (%s, %s, 0)
                ON DUPLICATE KEY UPDATE rendered_hours = (
                    SELECT IFNULL(SUM(total_hours), 0)
                    FROM attendance WHERE user_id = %s
                )
            """, (user_id, today.strftime("%A"), user_id))

            conn.commit()

            return jsonify({
                "status": "success",
                "message": f"{user['full_name']} - Time Out recorded ⏰ | Total Hours: {total_hours} hrs"
            })

        # =================================
        # ===== NON-S.T.A.R.S USERS ========
        # =================================

        # ---- BLOCK MULTIPLE SESSIONS ----
        if record and not record['time_out']:
            return jsonify({
                "status": "error",
                "message": "⚠️ You already timed in today."
            })

        # ---- TIME IN (NO CUT-OFF, ROUNDED) ----
        if not record:
            current_dt = datetime.now()
            minute = current_dt.minute

            if minute <= 30:
                rounded_time = current_dt.replace(minute=0, second=0, microsecond=0)
            else:
                rounded_time = (current_dt + timedelta(hours=1)).replace(
                    minute=0, second=0, microsecond=0
                )

            cursor.execute("""
                INSERT INTO attendance (user_id, date, time_in, assigned_duty)
                VALUES (%s, %s, %s, %s)
            """, (
                user_id,
                today,
                rounded_time.strftime("%H:%M:%S"),
                assigned_duty
            ))
            conn.commit()

            return jsonify({
                "status": "success",
                "message": f"{user['full_name']} - Time In recorded ✅"
            })

        # ---- TIME OUT (5:00–5:15 ONLY) ----
        start_out = time(17, 0)
        cutoff_out = time(17, 15)

        if not (start_out <= now <= cutoff_out):
            return jsonify({
                "status": "error",
                "message": "⏰ You can only time out between 5:00 and 5:15 PM."
            })

        time_in_value = record['time_in']
        if isinstance(time_in_value, str):
            time_in_value = datetime.strptime(time_in_value, "%H:%M:%S").time()

        time_in_dt = datetime.combine(today, time_in_value)
        time_out_dt = datetime.combine(today, datetime.now().time())

        lunch_start = datetime.combine(today, time(12, 0))
        lunch_end = datetime.combine(today, time(13, 0))

        total_seconds = (time_out_dt - time_in_dt).total_seconds()
        if time_in_dt < lunch_start < time_out_dt:
            total_seconds -= 3600

        base_hours = int(total_seconds // 3600)
        remaining_minutes = int((total_seconds % 3600) // 60)

        if 29 <= remaining_minutes <= 31:
            total_hours = base_hours + 0.5
        elif remaining_minutes >= 30:
            total_hours = base_hours + 1
        else:
            total_hours = base_hours

        cursor.execute("""
            UPDATE attendance
            SET time_out=%s, total_hours=%s
            WHERE id=%s
        """, (
            datetime.now().strftime("%H:%M:%S"),
            total_hours,
            record['id']
        ))

        cursor.execute("""
            INSERT INTO tbl_schedule (user_id, day, rendered_hours)
            VALUES (%s, %s, 0)
            ON DUPLICATE KEY UPDATE rendered_hours = (
                SELECT IFNULL(SUM(total_hours), 0)
                FROM attendance WHERE user_id = %s
            )
        """, (user_id, today.strftime("%A"), user_id))

        conn.commit()

        return jsonify({
            "status": "success",
            "message": f"{user['full_name']} - Time Out recorded ⏰ | Total Hours: {total_hours} hrs"
        })

    except Exception as e:
        print("QR ERROR:", e)
        return jsonify({"status": "error", "message": "⚠️ Server error occurred."})

    finally:
        cursor.close()
        conn.close()



# ------------------ Login Handlers ------------------ #
@app.route('/login-admin', methods=['POST'])
def login_admin():
    username = request.form['username']
    password = request.form['password']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username=%s AND role='admin'", (username,))
    admin = cursor.fetchone()
    cursor.close()
    conn.close()

    if admin and check_password_hash(admin['password_hash'], password):
        session['user_id'] = admin['id']
        session['role'] = 'admin'
        #flash("Admin login successful", "success")
        return redirect(url_for('admin_dashboard'))
    else:
        flash("Invalid admin credentials", "danger")
        return redirect(url_for('admin_login'))


@app.route('/login-student', methods=['POST'])
def login_student():
    username = request.form['username']
    password = request.form['password']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username=%s AND role='student'", (username,))
    student = cursor.fetchone()
    cursor.close()
    conn.close()

    if student and check_password_hash(student['password_hash'], password):
        if student['status'] != 'approved':
            flash("Your account is not approved yet.", "warning")
            return redirect(url_for('student_login'))
        session['user_id'] = student['id']
        session['role'] = 'student'
        flash("Student login successful", "success")
        return redirect(url_for('student_dashboard')) 
    else:
        flash("Invalid student credentials", "danger")
        return redirect(url_for('student_login'))

    
# @app.route('/login-student', methods=['POST'])
# def login_student():
#     username = request.form['username']
#     password = request.form['password']

#     conn = get_db_connection()
#     cursor = conn.cursor()
#     cursor.execute("SELECT * FROM users WHERE username=%s AND role='student'", (username,))
#     student = cursor.fetchone()
#     cursor.close()
#     conn.close()

#     if student and check_password_hash(student['password_hash'], password):
#         # Temporarily skip status check
#         session['user_id'] = student['id']
#         session['role'] = 'student'
#         #flash("Student login successful", "success")
#         return redirect(url_for('student_dashboard'))  # Fixed underscore instead of dash
#     else:
#         flash("Invalid student credentials", "danger")
#         return redirect(url_for('student_login'))


# ------------------ Dashboards ------------------ #

@app.route('/admin-dashboard')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))
    
    selected_type = request.args.get('filter')  

    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)  

    today = date.today()  

    
    if selected_type:
        cursor.execute("""
            SELECT attendance.*, users.*
            FROM attendance 
            JOIN users ON attendance.user_id = users.id 
            WHERE users.student_type=%s AND attendance.date=%s
            ORDER BY attendance.time_in DESC
        """, (selected_type, today))
    else:
        cursor.execute("""
            SELECT attendance.*, users.*
            FROM attendance 
            JOIN users ON attendance.user_id = users.id 
            WHERE attendance.date=%s
            ORDER BY attendance.time_in DESC
        """, (today,))

    # if selected_type:
    #     cursor.execute("SELECT * FROM attendance JOIN users ON attendance.user_id = users.id WHERE users.student_type=%s", (selected_type,))
    # else:
    #     cursor.execute("SELECT * FROM attendance JOIN users ON attendance.user_id = users.id")

    attendance = cursor.fetchall()

    #
    cursor.execute("""
        SELECT COUNT(*) AS total 
        FROM attendance 
        WHERE time_out IS NULL AND date=%s
    """, (today,))
    students_in = cursor.fetchone()['total']

    
    cursor.execute("""
        SELECT COUNT(*) AS total 
        FROM attendance 
        WHERE time_out IS NOT NULL AND date=%s
    """, (today,))
    students_out = cursor.fetchone()['total']

    cursor.close()
    conn.close()

    return render_template(
        'admin-dashboard.html',
        attendance=attendance,
        students_in=students_in,
        students_out=students_out,
        selected_type=selected_type
    )

@app.route('/api/student_logs/<int:student_id>')
def api_student_logs(student_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT date, assigned_duty, time_in, time_out, total_hours
        FROM attendance
        WHERE user_id = %s
        ORDER BY date DESC
    """, (student_id,))
    records = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify({"records": records})


@app.route('/view-pending', methods=['GET', 'POST'])
def view_pending():
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE role='student' AND status='pending'")
    pending_users = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('view-pending.html', pending_users=pending_users)

@app.route('/approve-all', methods=['POST'])
def approve_all():
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get all pending students
    cursor.execute("""
        SELECT id, email, full_name
        FROM users
        WHERE role = 'student' AND status = 'pending'
    """)
    pending_users = cursor.fetchall()

    if not pending_users:
        flash("No pending students to approve.", "info")
        cursor.close()
        conn.close()
        return redirect(url_for('view_pending'))

    try:
        for student in pending_users:
            user_id = student['id']
            email = student['email']
            full_name = student['full_name']

            # Generate QR token
            qrtoken = secrets.token_hex(16)

            # Approve user and save QR
            cursor.execute("""
                UPDATE users
                SET status = 'approved', qr_token = %s
                WHERE id = %s
            """, (qrtoken, user_id))

            # Insert into status_history
            cursor.execute("""
                INSERT INTO status_history (user_id, status, date)
                VALUES (%s, 'approved', CURDATE())
            """, (user_id,))

            # Generate QR image (same logic as single approve)
            qrimg = qrcode.make(qrtoken)
            imgbuffer = BytesIO()
            qrimg.save(imgbuffer, format='PNG')
            imgbuffer.seek(0)

            # Send email
            sender_email = "gratisa1200@gmail.com"
            sender_pass = "zolf herh wytf psmd"

            msg = MIMEMultipart()
            msg["From"] = sender_email
            msg["To"] = email
            msg["Subject"] = "Your Gratis Attendance Account Has Been Approved!"

            body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.5;">
                <h2 style="color:#e74c3c;">Hello, {full_name}!</h2>
                <p>Your <strong>Gratis Attendance</strong> account has been <b>approved</b>.</p>
                <p>You can now use the attached QR code to <b>time in and time out</b>.</p>
                <p style="color:red;"><b>Please do not share your QR code with anyone.</b></p>
                <br>
                <p>Best regards,<br><strong>General Services Department</strong></p>
            </body>
            </html>
            """
            msg.attach(MIMEText(body, "html"))

            qrimage = MIMEImage(imgbuffer.read(), _subtype="png")
            qrimage.add_header("Content-Disposition", "attachment", filename="qrcode.png")
            msg.attach(qrimage)

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                smtp.login(sender_email, sender_pass)
                smtp.send_message(msg)

        conn.commit()
        flash("All pending students approved and QR codes emailed successfully!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Approve all failed: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('view_pending'))


@app.route('/approve-student/<int:user_id>')
def approve_student(user_id):
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    
    cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    student = cursor.fetchone()

    if not student:
        flash("Student not found.", "danger")
        cursor.close()
        conn.close()
        return redirect(url_for('view_pending'))
    
    qr_token = secrets.token_hex(16)

    try:
       
        cursor.execute("""
            UPDATE users 
            SET status='approved', qr_token=%s 
            WHERE id=%s
        """, (qr_token, user_id))

        cursor.execute("""
            INSERT INTO status_history (user_id, status, date)
            VALUES (%s, 'approved', CURDATE())
        """, (user_id,))

        conn.commit()

        qr_img = qrcode.make(qr_token)
        img_buffer = BytesIO()
        qr_img.save(img_buffer, format="PNG")
        img_buffer.seek(0)

        
        sender_email = "gratisa1200@gmail.com"
        sender_pass = "zolf herh wytf psmd"
        receiver_email = student["email"]

        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = receiver_email
        msg["Subject"] = "🎉 Your Gratis Attendance Account Has Been Approved!"

        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.5;">
            <h2 style="color:#e74c3c;">Hello, {student['full_name']}!</h2>
            <p>Your <strong>Gratis Attendance</strong> account has been <b>approved</b>.</p>
            <p>You can now use the QR code attached below to <b>time in and time out</b>.</p>
            <p style="color:red;"><b>⚠️ Please do not share your QR code with anyone.</b></p>
            <br>
            <p>Best regards,<br><strong>General Services Department</strong></p>
        </body>
        </html>
        """
        msg.attach(MIMEText(body, "html"))

        
        qr_image = MIMEImage(img_buffer.read(), _subtype="png")
        qr_image.add_header("Content-Disposition", "attachment", filename="qr_code.png")
        msg.attach(qr_image)

        
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender_email, sender_pass)
            smtp.send_message(msg)

        flash(f"{student['full_name']} approved and QR sent successfully via email!", "success")

    except Exception as e:
        conn.rollback()
        flash(f"Student approved but email failed: {str(e)}", "warning")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('view_pending'))


@app.route('/reject-student/<int:user_id>', methods=["POST"])
def reject_student(user_id):
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # 🧭 Fetch student details
    cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    student = cursor.fetchone()

    if not student:
        flash("Student not found.", "danger")
        cursor.close()
        conn.close()
        return redirect(url_for('view_pending'))

    try:
    
        cursor.execute("""
            UPDATE users 
            SET status='rejected' 
            WHERE id=%s
        """, (user_id,))


        cursor.execute("""
            INSERT INTO status_history (user_id, status, date)
            VALUES (%s, 'rejected', CURDATE())
        """, (user_id,))

        conn.commit()


        sender_email = "gratisa1200@gmail.com"
        sender_pass = "zolf herh wytf psmd"
        receiver_email = student["email"]

        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = receiver_email
        msg["Subject"] = "Your Gratis Attendance Application Status"

        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.5;">
            <h2 style="color:#e74c3c;">Hello, {student['full_name']}!</h2>
            <p>We appreciate your interest in joining in <strong>General Services Scholars</strong>.</p>
            <p>Unfortunately, your application has been <b>rejected</b> at this time.</p>
            <p>You may contact your coordinator or administrator if you believe this was a mistake.</p>
            <br>
            <p>— Gratis Services Department</p>
        </body>
        </html>
        """
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender_email, sender_pass)
            smtp.send_message(msg)

        flash(f"{student['full_name']} was rejected and notified via email.", "success")

    except Exception as e:
        conn.rollback()
        flash(f"Student rejected but email failed: {str(e)}", "warning")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('view_pending'))



@app.route('/view-logs', methods=["GET"])
def view_logs():
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor()


    cursor.execute("SELECT id, full_name, student_number FROM users WHERE role='student'")
    students = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("view-logs.html", students=students, student=None, records=None)


@app.route('/view-logs/<int:student_id>', methods=["GET"])
def view_logs_student(student_id):
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id=%s", (student_id,))
    student = cursor.fetchone()

    cursor.execute("""
        SELECT date, assigned_duty, time_in, time_out, total_hours
        FROM attendance
        WHERE user_id=%s
        ORDER BY date ASC
    """, (student_id,))
    records = cursor.fetchall()

    cursor.execute("SELECT id, full_name, student_number FROM users WHERE role='student'")
    students = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("view-logs.html", students=students, student=student, records=records)

@app.route('/view-logs-modal/<int:student_id>', methods=["GET"])
def view_logs_modal(student_id):
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id=%s", (student_id,))
    student = cursor.fetchone()

    
    cursor.execute("""
        SELECT date, assigned_duty, time_in, time_out, total_hours
        FROM attendance
        WHERE user_id=%s
        ORDER BY date ASC
    """, (student_id,))
    records = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("partials/view-logs-modal.html", student=student, records=records)




@app.route('/export-logs/<student_number>')
def export_logs(student_number):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.full_name, u.student_number, u.email, a.date, a.assigned_duty, a.time_in, a.time_out, a.total_hours
        FROM attendance a
        JOIN users u ON a.user_id = u.id
        WHERE u.student_number = %s
        ORDER BY a.date DESC
    """, (student_number,))
    records = cursor.fetchall()


    cursor.execute("SELECT * FROM users WHERE student_number=%s", (student_number,))
    student = cursor.fetchone()

    if student:
        cursor.execute("""
            SELECT date, assigned_duty, time_in, time_out, total_hours
            FROM attendance
            WHERE user_id=%s
            ORDER BY date ASC
        """, (student['id'],))
        Records = cursor.fetchall()

        pdf_data = generate_pdf(student, Records)
        send_pdf_via_email(student, pdf_data)
        
    
    cursor.close()
    conn.close()

    if not records:
        flash("No records found for this student.", "warning")
        return redirect(url_for("view_logs"))
    

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setFont("Helvetica", 12)

    student_name = records[0]['full_name']
    email = records[0]['email']
    pdf.drawString(50, 750, f"Attendance Report for {student_name} ({student_number})")

    y = 720
    for r in records:
        pdf.drawString(
            50, y,
            f"{r['date']} | Duty: {r['assigned_duty']} | In: {r['time_in']} | Out: {r['time_out']} | Hours: {r['total_hours']}"
        )
        y -= 20
        if y < 50:
            pdf.showPage()
            y = 750

    pdf.save()
    buffer.seek(0)



    flash(f"Attendance report sent to {email}", "success")
    return redirect(url_for("view_logs"))


def generate_pdf(student, records):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)

    
    width, height = letter
    margin_left = 0.75 * inch
    margin_right = 0.75 * inch
    margin_top = 0.75 * inch
    margin_bottom = 0.75 * inch

    content_width = width - (margin_left + margin_right)
    start_y = height - margin_top

    # =============== HEADER SECTION ===============
    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawCentredString(width / 2, start_y, "G R A T I S   A T T E N D A N C E   F O R M")

    pdf.setFont("Helvetica", 11)
    pdf.drawString(width - 200, start_y - 25, f"Name: {student['full_name']}")
    pdf.drawString(width - 200, start_y - 40, f"Yr/Course: {student['year_level']} / {student['program']}")
    pdf.drawString(width - 200, start_y - 55, f"Student No.: {student['student_number']}")
    pdf.drawString(width - 200, start_y - 70, f"Contact No.: {student['contact_no']}")

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin_left, start_y - 25, "Semester: ____________")
    pdf.drawString(margin_left, start_y - 40, "Office/Place of Assignment: ___________________________")

    # =============== LEFT DECLARATION TEXT ===============
    pdf.saveState()
    pdf.translate(margin_left / 2, height / 2)
    pdf.rotate(90)
    pdf.setFont("Helvetica-Oblique", 7)
    pdf.restoreState()

    # =============== TABLE HEADER ===============
    y = start_y - 100
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(margin_left, y, "Date")
    pdf.drawString(margin_left + 70, y, "Time In")
    pdf.drawString(margin_left + 130, y, "Time Out")
    pdf.drawString(margin_left + 200, y, "Task / Duty Performed")
    pdf.drawString(width - 200, y, "Authorized " \
    "Signature")
    pdf.drawString(width - 80, y, "Hours")
    y -= 10
    pdf.line(margin_left, y, width - margin_right, y)
    y -= 20

    # =============== TABLE CONTENT ===============
    pdf.setFont("Helvetica", 10)
    for record in records:
        if y < margin_bottom + 100: 
            pdf.showPage()
            y = height - margin_top
            pdf.setFont("Helvetica", 10)
        pdf.drawString(margin_left, y, str(record['date']))
        pdf.drawString(margin_left + 70, y, str(record['time_in'] or '--'))
        pdf.drawString(margin_left + 130, y, str(record['time_out'] or '--'))
        pdf.drawString(margin_left + 200, y, str(record['assigned_duty'] or '---'))
        pdf.drawString(width - 80, y, str(record['total_hours'] or '0'))
        y -= 18

    # =============== SIGNATURE FOOTER ===============
    y -= 30
    pdf.line(margin_left, y-40, margin_left + 155, y-40)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margin_left + 45, y - 36, student['full_name'])
    pdf.drawString(margin_left , y - 55, "Signature over Printed Name / Date")

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()

def send_pdf_via_email(student, pdf_data):
    from_email = "gratisa1200@gmail.com"
    password = "zolf herh wytf psmd"  

    msg = MIMEMultipart()
    msg['From'] = "gratisa1200@gmail.com"
    msg['To'] = student['email']
    msg['Subject'] = "Your Attendance Report"

    body = f"Hello {student['full_name']},\n\nAttached is your attendance report."
    msg.attach(MIMEText(body, 'plain'))

   
    attachment = MIMEApplication(pdf_data, _subtype="pdf")
    attachment.add_header('Content-Disposition', 'attachment', filename="Attendance_Report.pdf")
    msg.attach(attachment)

    # Send Email
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(from_email, password) 
        server.send_message(msg)

@app.route('/export-all-attendance', methods=['GET'])
def export_all_attendance():
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch all attendance records with user details
    cursor.execute("""
        SELECT u.full_name, u.student_number, u.student_type, u.program, 
               u.year_level, a.date, a.assigned_duty, a.time_in, a.time_out, 
               a.total_hours
        FROM attendance a
        JOIN users u ON a.user_id = u.id
        ORDER BY a.date DESC, u.full_name ASC
    """)
    records = cursor.fetchall()

    cursor.close()
    conn.close()

    if not records:
        flash("No attendance records to export.", "warning")
        return redirect(url_for('admin_dashboard'))

    # Build CSV content
    lines = [
        "Full Name,Student Number,Student Type,Program,Year Level,Date,"
        "Assigned Duty,Time In,Time Out,Total Hours"
    ]

    for r in records:
        line = (
            f'"{r["full_name"]}",{r["student_number"]},"{r["student_type"]}",'
            f'"{r["program"]}","{r["year_level"]}",{r["date"]},'
            f'"{r["assigned_duty"]}",{r["time_in"]},{r["time_out"]},{r["total_hours"]}'
        )
        lines.append(line)

    csv_data = "\n".join(lines)

    # Send as downloadable CSV
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"gratis_attendance_all_{timestamp}.csv"
    
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        },
    )

@app.route('/view-status-history')
def view_status_history():
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT u.full_name, u.student_number, u.program, sh.status, sh.date
        FROM status_history sh
        JOIN users u ON sh.user_id = u.id
        ORDER BY sh.date DESC
    """)
    history = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('view-status-history.html', history=history)

@app.route('/cs-time-in', methods=['POST'])
def cs_time_in():
    if 'user_id' not in session or session.get('role') != 'student':
        return redirect(url_for('student_login'))

    today = date.today()
    now = datetime.now().time()
    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch user details
    cursor.execute("SELECT student_type, assigned_duty FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()

    if not user:
        flash("⚠️ User not found.", "danger")
        cursor.close()
        conn.close()
        return redirect(url_for('student_login'))

    student_type = user['student_type']
    assigned_duty = user['assigned_duty'] or "Unassigned"

    # Check existing CS record for today (latest)
    cursor.execute("""
        SELECT *
        FROM attendance
        WHERE user_id=%s AND date=%s AND is_cs=1
        ORDER BY id DESC
        LIMIT 1
    """, (user_id, today))
    record = cursor.fetchone()

    if record and record['time_in'] and not record['time_out']:
        flash("⚠️ You already have an active CS session. Please time out first.", "warning")
        cursor.close()
        conn.close()
        return redirect(url_for('student_dashboard'))

    # CS: no time restriction, keep exact time in
    fixed_time_in = datetime.now().strftime("%H:%M:%S")

    cursor.execute("""
        INSERT INTO attendance (user_id, date, time_in, assigned_duty, is_cs)
        VALUES (%s, %s, %s, %s, 1)
    """, (user_id, today, fixed_time_in, assigned_duty))
    conn.commit()

    flash(f"✅ CS Time in recorded at {fixed_time_in}", "success")

    cursor.close()
    conn.close()
    return redirect(url_for('student_dashboard'))

@app.route('/cs-time-out', methods=['POST'])
def cs_time_out():
    if 'user_id' not in session or session.get('role') != 'student':
        return redirect(url_for('student_login'))

    today = date.today()
    now = datetime.now().time()
    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch user details
    cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()
    student_type = user['student_type']

    # Get latest CS attendance record for today
    cursor.execute("""
        SELECT *
        FROM attendance
        WHERE user_id=%s AND DATE(date)=%s AND is_cs=1
        ORDER BY id DESC
        LIMIT 1
    """, (user_id, today))
    record = cursor.fetchone()

    if not record or not record['time_in']:
        flash("⚠️ You must time in for CS before you can time out.", "danger")
    elif record['time_out']:
        flash("⚠️ You already timed out this CS session.", "warning")
    else:
        # For CS: no 5:00–5:15 restriction, no early flag needed

        time_in_value = record['time_in']
        if isinstance(time_in_value, timedelta):
            total_seconds_in = int(time_in_value.total_seconds())
            hours = total_seconds_in // 3600
            minutes = (total_seconds_in % 3600) // 60
            time_in_value = time(hours, minutes)

        # Compute total duration
        time_in_dt = datetime.combine(today, time_in_value)
        time_out_dt = datetime.combine(today, datetime.now().time())

        # Deduct lunch (12:00–13:00)
        lunch_start = datetime.combine(today, time(12, 0))
        lunch_end = datetime.combine(today, time(13, 0))

        total_seconds = (time_out_dt - time_in_dt).total_seconds()
        if time_in_dt < lunch_start < time_out_dt:
            total_seconds -= 3600

        if total_seconds < 0:
            total_seconds = 0

        # Rounding logic (same as scholar)
        base_hours = int(total_seconds // 3600)
        remaining_minutes = int((total_seconds % 3600) // 60)

        if 29 <= remaining_minutes <= 31:
            total_hours = base_hours + 0.5
        else:
            if remaining_minutes >= 30:
                total_hours = base_hours + 1
            else:
                total_hours = base_hours

        # Update CS attendance row
        cursor.execute("""
            UPDATE attendance
            SET time_out=%s, total_hours=%s
            WHERE id=%s
        """, (datetime.now().strftime("%H:%M:%S"), total_hours, record['id']))

        # Recompute total CS hours from attendance (is_cs = 1)
        cursor.execute("""
            SELECT IFNULL(SUM(total_hours), 0) AS cs_total
            FROM attendance
            WHERE user_id = %s AND is_cs = 1
        """, (user_id,))
        row = cursor.fetchone()
        cs_total = row['cs_total'] if row else 0

        # Save to users.cs_rendered (make sure you added this column)
        cursor.execute("""
            UPDATE users
            SET cs_rendered = %s
            WHERE id = %s
        """, (cs_total, user_id))

        conn.commit()

        flash(f"✅ CS Time out recorded. CS hours this session: {total_hours} hrs", "success")

    cursor.close()
    conn.close()
    return redirect(url_for('student_dashboard'))



@app.route('/add-cs-hours', methods=['GET', 'POST'])
def add_cs_hours():
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    # Load students list for the dropdown (include cs_required and cs_rendered for display)
    cursor.execute("""
        SELECT id, full_name, student_number, cs_required, cs_rendered 
        FROM users 
        WHERE role = 'student'
    """)
    students = cursor.fetchall()

    if request.method == 'POST':
        user_id = request.form.get('user_id')
        date_str = request.form.get('date')
        cs_required = request.form.get('cs_required')
        remarks = request.form.get('remarks')

        if not user_id or not date_str or not cs_required:
            flash("All fields except remarks are required.", "error")
        else:
            try:
                # Update users.cs_required
                cursor.execute("""
                    UPDATE users 
                    SET cs_required = %s 
                    WHERE id = %s
                """, (float(cs_required), user_id))
                
                # Optional: Log the change for audit trail
                cursor.execute("""
                    INSERT INTO cs_requirements_log (user_id, date, cs_required, remarks)
                    VALUES (%s, %s, %s, %s)
                """, (user_id, date_str, float(cs_required), remarks or ''))
                
                conn.commit()
                flash(f"CS requirement set to {cs_required} hours for the selected student.", "success")
            except Exception as e:
                conn.rollback()
                flash(f"Failed to update CS requirement: {str(e)}", "error")

    cursor.close()
    conn.close()

    return render_template('add-cs-hours.html', students=students)


@app.route('/student-dashboard')
def student_dashboard():
    if 'user_id' not in session or session.get('role') != 'student':
        return redirect(url_for('student_login'))

    today = date.today()
    conn = get_db_connection()
    cursor = conn.cursor()   # this is already DictCursor from get_db_connection

    cursor.execute("SELECT * FROM users WHERE id=%s", (session['user_id'],))
    student = cursor.fetchone()

    # Latest attendance record for today
    cursor.execute("""
        SELECT *
        FROM attendance
        WHERE user_id=%s AND date=%s
        ORDER BY id DESC
        LIMIT 1
    """, (session['user_id'], today))
    today_record = cursor.fetchone()

    cursor.execute("""
        SELECT date, assigned_duty, time_in, time_out, total_hours
        FROM attendance
        WHERE user_id=%s
        ORDER BY date DESC
    """, (session['user_id'],))
    attendance = cursor.fetchall()

    cursor.execute("SELECT * FROM tbl_schedule WHERE user_id=%s", (session['user_id'],))
    schedule = cursor.fetchone()

    # NEW: CS total (use dict key, not index 0)
    cursor.execute("""
        SELECT IFNULL(SUM(hours), 0) AS cs_total
        FROM cs_hours
        WHERE user_id = %s
    """, (session['user_id'],))
    # NEW: CS from users table (rendered + remaining)
    cs_rendered = student.get('cs_rendered') or 0
    cs_required = student.get('cs_required') or 0
    remaining_cs = max(0, cs_required - cs_rendered)

    cursor.close()
    conn.close()

    return render_template(
        'student-dashboard.html',
        student=student,
        today_record=today_record,
        attendance=attendance,
        schedule=schedule,
        cs_total=cs_rendered,      # for backward compatibility in template
        remaining_cs=remaining_cs,
        current_time=datetime.now().strftime('%H:%M:%S')
    )




# ------------------ Time In/Out without Restrictions ------------------ #

# ------------------ Time In/Out WITHOUT RESTRICTIONS (SAMPLE) ------------------ #
# Uncomment these two routes when you want no restrictions and comment out
# the restricted versions above.

# @app.route('/time_in', methods=['POST'])
# def time_in():
#     if 'user_id' not in session:
#         return redirect(url_for('student_login'))

#     today = date.today()
#     user_id = session['user_id']

#     conn = get_db_connection()
#     cursor = conn.cursor()

#     # Fetch user details
#     cursor.execute("SELECT student_type, assigned_duty FROM users WHERE id=%s", (user_id,))
#     user = cursor.fetchone()

#     if not user:
#         flash("⚠️ User not found.", "danger")
#         cursor.close()
#         conn.close()
#         return redirect(url_for('student_login'))

#     student_type = user['student_type']
#     assigned_duty = user['assigned_duty'] or "Unassigned"

#     # Check existing record for today
#     cursor.execute("SELECT * FROM attendance WHERE user_id=%s AND date=%s", (user_id, today))
#     record = cursor.fetchone()
#     if record:
#         flash("⚠️ You already timed in today.", "warning")
#         cursor.close()
#         conn.close()
#         return redirect(url_for('student_dashboard'))

#     # Same rounding logic, but NO time window restriction
#     if student_type == "S.T.A.R.S":
#         fixed_time_in = datetime.now().strftime("%H:%M:%S")
#     else:
#         current_dt = datetime.now()
#         minute = current_dt.minute

#         if minute <= 30:
#             rounded_hour = current_dt.replace(minute=0, second=0, microsecond=0)
#         else:
#             rounded_hour = (current_dt + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

#         fixed_time_in = rounded_hour.strftime("%H:%M:%S")

#     cursor.execute("""
#         INSERT INTO attendance (user_id, date, time_in, assigned_duty)
#         VALUES (%s, %s, %s, %s)
#     """, (user_id, today, fixed_time_in, assigned_duty))
#     conn.commit()

#     flash(f"✅ [NO RESTRICTION] Time in recorded at {fixed_time_in}", "success")

#     cursor.close()
#     conn.close()
#     return redirect(url_for('student_dashboard'))


# @app.route('/time_out', methods=['POST'])
# def time_out():
#     if 'user_id' not in session:
#         return redirect(url_for('student_login'))

#     today = date.today()
#     user_id = session['user_id']

#     conn = get_db_connection()
#     cursor = conn.cursor()

#     # early flag can stay, but here it has no effect on restrictions
#     is_early = request.form.get("early") == "1"

#     # Fetch user details
#     cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
#     user = cursor.fetchone()
#     student_type = user['student_type']

#     cursor.execute("SELECT * FROM attendance WHERE user_id=%s AND DATE(date)=%s", (user_id, today))
#     record = cursor.fetchone()

#     if not record or not record['time_in']:
#         flash("⚠️ You must time in before you can time out.", "danger")
#     elif record['time_out']:
#         flash("⚠️ You already timed out today.", "warning")
#     else:
#         # NO 5:00–5:15 restriction here

#         time_in_value = record['time_in']
#         if isinstance(time_in_value, timedelta):
#             total_seconds_in = int(time_in_value.total_seconds())
#             hours = total_seconds_in // 3600
#             minutes = (total_seconds_in % 3600) // 60
#             time_in_value = time(hours, minutes)

#         # Compute total duration
#         time_in_dt = datetime.combine(today, time_in_value)
#         time_out_dt = datetime.combine(today, datetime.now().time())

#         # Deduct lunch (12:00–13:00)
#         lunch_start = datetime.combine(today, time(12, 0))
#         lunch_end = datetime.combine(today, time(13, 0))

#         total_seconds = (time_out_dt - time_in_dt).total_seconds()
#         if time_in_dt < lunch_start < time_out_dt:
#             total_seconds -= 3600

#         if total_seconds < 0:
#             total_seconds = 0

#         # Rounding logic: :30 → .5, others to nearest hour
#         base_hours = int(total_seconds // 3600)
#         remaining_minutes = int((total_seconds % 3600) // 60)

#         if 29 <= remaining_minutes <= 31:
#             total_hours = base_hours + 0.5
#         else:
#             if remaining_minutes >= 30:
#                 total_hours = base_hours + 1
#             else:
#                 total_hours = base_hours

#         cursor.execute("""
#             UPDATE attendance
#             SET time_out=%s, total_hours=%s
#             WHERE id=%s
#         """, (datetime.now().strftime("%H:%M:%S"), total_hours, record['id']))

#         # Update tbl_schedule
#         cursor.execute("SELECT * FROM tbl_schedule WHERE user_id = %s", (user_id,))
#         schedule = cursor.fetchone()
#         if not schedule:
#             cursor.execute("""
#                 INSERT INTO tbl_schedule (user_id, day, rendered_hours)
#                 VALUES (%s, %s, 0)
#             """, (user_id, today.strftime("%A")))
#             conn.commit()

#         cursor.execute("""
#             UPDATE tbl_schedule 
#             SET rendered_hours = (
#                 SELECT IFNULL(SUM(total_hours), 0)
#                 FROM attendance
#                 WHERE user_id = %s
#             )
#             WHERE user_id = %s
#         """, (user_id, user_id))
#         conn.commit()

#         # You can keep or remove the 60-hour email logic here as needed
#         cursor.execute("""
#             SELECT u.email, u.full_name, u.student_type, u.created_at, s.rendered_hours
#             FROM users u
#             JOIN tbl_schedule s ON u.id = s.user_id
#             WHERE u.id = %s
#         """, (user_id,))
#         user_data = cursor.fetchone()

#         if user_data:
#             rendered_hours = user_data['rendered_hours']
#             created_at = user_data['created_at']

#             if isinstance(created_at, datetime):
#                 created_at = created_at.date()

#             email = user_data['email']
#             full_name = user_data['full_name']
#             student_type = user_data['student_type']

#             six_months_after = created_at + timedelta(days=180)

#             if student_type in ("S.A", "Housekeeping", "S.T.A.R.S") and rendered_hours >= 60 and date.today() <= six_months_after:
#                 sender_email = "gratisa1200@gmail.com"
#                 sender_pass = "zolf herh wytf psmd"

#                 msg = MIMEMultipart()
#                 msg["From"] = sender_email
#                 msg["To"] = email
#                 msg["Subject"] = "🎉 Congratulations! You’ve Completed Your 60 Hours"

#                 body = f"""
#                 <html>
#                 <body style="font-family: Arial, sans-serif; line-height: 1.5;">
#                     <h2 style="color:#e74c3c;">Congratulations, {full_name}!</h2>
#                     <p>You’ve successfully rendered <b>60 hours</b> of duty under the Gratis Attendance program.</p>
#                     <p>Your hard work and dedication are greatly appreciated. Please report to your coordinator for clearance processing.</p>
#                     <br>
#                     <p>Best regards,<br><strong>General Services Department</strong></p>
#                 </body>
#                 </html>
#                 """
#                 msg.attach(MIMEText(body, "html"))

#                 with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
#                     smtp.login(sender_email, sender_pass)
#                     smtp.send_message(msg)

#                 flash("🎉 You have completed 60 hours! Email notification sent successfully!", "success")

#         flash(f"✅ [NO RESTRICTION] Time out recorded. Total hours: {total_hours} hrs", "success")

#     cursor.close()
#     conn.close()
#     return redirect(url_for('student_dashboard'))




# # ------------------ Time In/Out with Restrictions ------------------ #


def to_time(value):
    """Convert MySQL TIME (possibly timedelta) to datetime.time."""
    if isinstance(value, timedelta):
        total_seconds = value.total_seconds()
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        return time(hours, minutes, seconds)
    return value


@app.route('/time_in', methods=['POST'])
def time_in():
    if 'user_id' not in session:
        return redirect(url_for('student_login'))

    today = date.today()
    now = datetime.now().time()
    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch user details
    cursor.execute("SELECT student_type, assigned_duty FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()

    if not user:
        flash("⚠️ User not found.", "danger")
        cursor.close()
        conn.close()
        return redirect(url_for('student_login'))

    student_type = user['student_type']
    assigned_duty = user['assigned_duty'] or "Unassigned"

    # For NON-S.T.A.R.S users: allow any time <= 8:30, but store as rounded hour
    # S.T.A.R.S → no time-in restriction (can time in anytime)


    # Check existing record for today (latest record)
    cursor.execute("""
        SELECT *
        FROM attendance
        WHERE user_id=%s AND date=%s
        ORDER BY id DESC
        LIMIT 1
    """, (user_id, today))
    record = cursor.fetchone()

    # For NON-S.T.A.R.S: only one time-in per day
    # For S.T.A.R.S: allow multiple time-ins as long as the last one is completed (has time_out)
    if record:
        if student_type != "S.T.A.R.S":
            flash("⚠️ You already timed in today.", "warning")
            cursor.close()
            conn.close()
            return redirect(url_for('student_dashboard'))
        else:
            # S.T.A.R.S: if last record has no time_out, block; otherwise allow new time in
            if not record['time_out']:
                flash("⚠️ You already have an active duty session. Please time out first.", "warning")
                cursor.close()
                conn.close()
                return redirect(url_for('student_dashboard'))

    # --- ROUNDING LOGIC FOR TIME IN ---
    if student_type == "S.T.A.R.S":
        # S.T.A.R.S → keep exact time in
        fixed_time_in = datetime.now().strftime("%H:%M:%S")
    else:
        # Non-S.T.A.R.S → round to nearest hour:
        # <= 8:30 → 8:00, > 8:30 would have been blocked above
        current_dt = datetime.now()
        minute = current_dt.minute

        if minute <= 30:
            rounded_hour = current_dt.replace(minute=0, second=0, microsecond=0)
        else:
            rounded_hour = (current_dt + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        fixed_time_in = rounded_hour.strftime("%H:%M:%S")

    cursor.execute("""
        INSERT INTO attendance (user_id, date, time_in, assigned_duty)
        VALUES (%s, %s, %s, %s)
    """, (user_id, today, fixed_time_in, assigned_duty))
    conn.commit()

    flash(f"✅ Time in recorded at {fixed_time_in}", "success")

    cursor.close()
    conn.close()
    return redirect(url_for('student_dashboard'))


@app.route('/time_out', methods=['POST'])
def time_out():
    if 'user_id' not in session:
        return redirect(url_for('student_login'))

    today = date.today()
    now = datetime.now().time()
    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if this is an early-out request (from the Early Time Out button)
    is_early = request.form.get("early") == "1"

    # Fetch user details
    cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()
    student_type = user['student_type']

    # Get latest attendance record for today
    cursor.execute("""
        SELECT *
        FROM attendance
        WHERE user_id=%s AND DATE(date)=%s
        ORDER BY id DESC
        LIMIT 1
    """, (user_id, today))
    record = cursor.fetchone()

    if not record or not record['time_in']:
        flash("⚠️ You must time in before you can time out.", "danger")
    elif record['time_out']:
        flash("⚠️ You already timed out today.", "warning")
    else:
        # Time-out restriction for NON-S.T.A.R.S
        # S.T.A.R.S → no time restriction, can time out anytime
        if student_type != "S.T.A.R.S" and not is_early:
            start_out = time(17, 0)
            cutoff_out = time(17, 15)
            if not (start_out <= now <= cutoff_out):
                flash("⏰ You can only time out between 5:00 and 5:15 PM.", "danger")
                cursor.close()
                conn.close()
                return redirect(url_for('student_dashboard'))

        time_in_value = record['time_in']
        if isinstance(time_in_value, timedelta):
            total_seconds_in = int(time_in_value.total_seconds())
            hours = total_seconds_in // 3600
            minutes = (total_seconds_in % 3600) // 60
            time_in_value = time(hours, minutes)

        # Compute total duration
        time_in_dt = datetime.combine(today, time_in_value)
        time_out_dt = datetime.combine(today, datetime.now().time())

        # Deduct lunch (12:00–13:00)
        lunch_start = datetime.combine(today, time(12, 0))
        lunch_end = datetime.combine(today, time(13, 0))

        total_seconds = (time_out_dt - time_in_dt).total_seconds()
        if time_in_dt < lunch_start < time_out_dt:
            total_seconds -= 3600

        if total_seconds < 0:
            total_seconds = 0

        # ----- NEW ROUNDING LOGIC -----
        # Base hours and minutes part
        base_hours = int(total_seconds // 3600)
        remaining_minutes = int((total_seconds % 3600) // 60)

        # Rule:
        # - if the exit minute is exactly around :30  -> add 0.5 hour
        # - if not :30, round to nearest full hour (e.g. :50 => +1 hour)
        if 29 <= remaining_minutes <= 31:
            total_hours = base_hours + 0.5
        else:
            if remaining_minutes >= 30:
                total_hours = base_hours + 1
            else:
                total_hours = base_hours

        # Update attendance
        cursor.execute("""
            UPDATE attendance
            SET time_out=%s, total_hours=%s
            WHERE id=%s
        """, (datetime.now().strftime("%H:%M:%S"), total_hours, record['id']))

        # Update tbl_schedule
        cursor.execute("SELECT * FROM tbl_schedule WHERE user_id = %s", (user_id,))
        schedule = cursor.fetchone()
        if not schedule:
            cursor.execute("""
                INSERT INTO tbl_schedule (user_id, day, rendered_hours)
                VALUES (%s, %s, 0)
            """, (user_id, today.strftime("%A")))
            conn.commit()

        cursor.execute("""
            UPDATE tbl_schedule 
            SET rendered_hours = (
                SELECT IFNULL(SUM(total_hours), 0)
                FROM attendance
                WHERE user_id = %s
            )
            WHERE user_id = %s
        """, (user_id, user_id))
        conn.commit()

        # check total rendered hours (unchanged logic)
        cursor.execute("""
            SELECT u.email, u.full_name, u.student_type, u.created_at, s.rendered_hours
            FROM users u
            JOIN tbl_schedule s ON u.id = s.user_id
            WHERE u.id = %s
        """, (user_id,))
        user_data = cursor.fetchone()

        if user_data:
            rendered_hours = user_data['rendered_hours']
            created_at = user_data['created_at']

            if isinstance(created_at, datetime):
                created_at = created_at.date()

            email = user_data['email']
            full_name = user_data['full_name']
            student_type = user_data['student_type']

            six_months_after = created_at + timedelta(days=180)

            if student_type in ("SA", "Housekeeping", "S.T.A.R.S") and rendered_hours >= 60 and date.today() <= six_months_after:
                sender_email = "gratisa1200@gmail.com"
                sender_pass = "zolf herh wytf psmd"

                msg = MIMEMultipart()
                msg["From"] = sender_email
                msg["To"] = email
                msg["Subject"] = "🎉 Congratulations! You’ve Completed Your 60 Hours"

                body = f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.5;">
                    <h2 style="color:#e74c3c;">Congratulations, {full_name}!</h2>
                    <p>You’ve successfully rendered <b>60 hours</b> of duty under the Gratis Attendance program.</p>
                    <p>Your hard work and dedication are greatly appreciated. Please report to your coordinator for clearance processing.</p>
                    <br>
                    <p>Best regards,<br><strong>General Services Department</strong></p>
                </body>
                </html>
                """
                msg.attach(MIMEText(body, "html"))

                with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                    smtp.login(sender_email, sender_pass)
                    smtp.send_message(msg)

                flash("🎉 You have completed 60 hours! Email notification sent successfully!", "success")

        flash(f"✅ Time out recorded. Total hours: {total_hours} hrs", "success")

    cursor.close()
    conn.close()
    return redirect(url_for('student_dashboard'))






# ------------------ Logout ------------------ #
@app.route('/logoutS')
def logoutA():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for('admin_login'))

@app.route('/logoutA')
def logoutS():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for('student_login'))



if __name__ == '__main__':
    app.run(debug=True)
